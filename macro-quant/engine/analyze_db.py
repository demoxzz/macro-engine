#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
ANALYZE DB — lecture CROSS-DAY de la base quant accumulée
================================================================================
Répond à : "depuis combien de jours suis-je dans CE régime ? combien de mes runs
passés lui ressemblent ? comment le régime dérive-t-il ? où en est le lift VIX ?"

Lit  Macro/Quant/db/regime_features.csv  (z-scores/jour)
     Macro/Quant/db/base_rates.csv       (base rates/jour/asset/horizon)
Produit :
  - un résumé texte (stdout)
  - une figure  Macro/Quant/analysis/macro-quant/analyze_db_YYYY-MM-DD.png :
      ① heatmap régime (features × temps) = "le film du régime"
      ② distance de chaque run passé à AUJOURD'HUI (+ seuil "même régime")
      ③ lift 10j dans le temps : VIX (validé OOS) + MOVE (candidat, à trancher au backtest trimestriel)

Dégrade proprement si peu d'historique (le message le dit).
Seuil "même régime" = RMS des écarts de z sur les 8 features < THRESH (en σ).
Dépendances : numpy + matplotlib + stdlib.
================================================================================
"""
import os, sys, csv, math
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
# override optionnel : argv[1]=dossier DB, argv[2]=dossier sortie figure (sert aux démos /tmp)
DB   = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.abspath(os.path.join(HERE, "..", "..", "db"))
OUT  = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else os.path.join(HERE, "..", "..", "analysis", "macro-quant")
os.makedirs(OUT, exist_ok=True)

FEATS = ["d10_5","dreal_5","dbe_5","vix_lvl","slope","dusd_5","brwti","brent_mom"]
FLAB  = {"d10_5":"Δ10Y nom","dreal_5":"Δ10Y réel","dbe_5":"Δbreakeven","vix_lvl":"VIX niv",
         "slope":"pente 2s10s","dusd_5":"USD","brwti":"Brent−WTI","brent_mom":"Brent mom"}
THRESH = 0.75   # RMS z-distance (σ) en-deçà duquel deux jours = "même régime"

# Assets suivis cross-day pour leur base rate forward (lift 10j).
#   VIX  = seul asset VALIDÉ OOS (cf backtest — IC 0.170, t=3.22).
#   MOVE = CANDIDAT 2e étoile, en observation. MOVE est déjà dans l'univers-réponse du
#          backtest (RESP_BT) : l'IC OOS est tranché au backtest TRIMESTRIEL ;
#          ici on accumule son lift réalisé run-après-run pour le voir converger (ou pas).
#   -> couplage : le backtest donne le verdict IC OOS ; analyze_db donne le film forward.
TRACK = [
    ("VIXCLS", "VIX",  "#6a1b9a", True),    # (sid, label, couleur, validé_OOS)
    ("MOVE",   "MOVE", "#00838f", False),
]


def load_features():
    p = os.path.join(DB, "regime_features.csv")
    if not os.path.exists(p): sys.exit("[analyze] pas de regime_features.csv — lance d'abord macro_quant_daily.py")
    rows = list(csv.DictReader(open(p)))
    rows.sort(key=lambda r: r["run_date"])
    dates = [r["run_date"] for r in rows]
    Z = np.array([[float(r[f]) for f in FEATS] for r in rows])   # (T, 8)
    nan = np.array([float(r.get("n_analog") or "nan") for r in rows])
    return dates, Z, nan


def load_lift(sid, h="10"):
    """lift_mean forward (h j) de `sid`, run-après-run, trié par date."""
    p = os.path.join(DB, "base_rates.csv")
    if not os.path.exists(p): return [], []
    d, v = [], []
    for r in csv.DictReader(open(p)):
        if r["sid"] == sid and r["h"] == h:
            try: lift = float(r["lift_mean"])
            except (ValueError, TypeError): continue
            d.append(r["run_date"]); v.append(lift)
    order = np.argsort(d); return list(np.array(d)[order]), list(np.array(v)[order])


def regime_streak(Z, thresh):
    """nb de jours consécutifs (en remontant depuis le dernier) restés dans le régime du dernier jour."""
    today = Z[-1]; k = 0
    for i in range(len(Z) - 1, -1, -1):
        d = math.sqrt(np.mean((Z[i] - today) ** 2))
        if d <= thresh: k += 1
        else: break
    return k


def main():
    dates, Z, nan = load_features()
    T = len(dates)
    today = Z[-1]
    dist = np.sqrt(np.mean((Z - today) ** 2, axis=1))     # RMS z-distance à aujourd'hui
    similar = int(np.sum(dist <= THRESH))                 # runs (dont aujourd'hui) dans le même régime
    streak = regime_streak(Z, THRESH)
    tracks = {sid: load_lift(sid, "10") for sid, _, _, _ in TRACK}

    # ---------- résumé texte ----------
    print(f"\n=== ANALYSE CROSS-DAY — base de {T} run(s) ({dates[0]} → {dates[-1]}) ===")
    print(f"Régime du jour ({dates[-1]}) : " + "  ".join(f"{FLAB[f]}={today[j]:+.2f}" for j,f in enumerate(FEATS)))
    print(f"Analogues HISTORIQUES (moteur, sur 2007→) au dernier run : {nan[-1]:.0f} jours.")
    if T < 10:
        print(f">> Base encore courte ({T} runs) : la lecture cross-day de TES runs devient parlante à partir de ~30-60 jours.")
    print(f"Parmi tes {T} run(s) accumulé(s) : {similar} dans le même régime qu'aujourd'hui (seuil RMS {THRESH}σ).")
    print(f"Streak : {streak} jour(s) consécutif(s) dans ce régime.")
    if T >= 2:
        j = int(np.argsort(dist)[1]) if T > 1 else -1     # plus proche autre que soi
        print(f"Run passé le plus proche d'aujourd'hui : {dates[j]} (distance {dist[j]:.2f}σ).")
    for sid, lab, _, oos in TRACK:
        _, tv = tracks[sid]
        if not tv: continue
        pct = 100.0 * np.mean(np.array(tv) <= tv[-1])
        star = "validé OOS" if oos else "CANDIDAT — verdict IC au backtest trimestriel"
        print(f"Lift {lab} 10j du jour = {tv[-1]:+.2f} pt — percentile {pct:.0f}% de ton historique ({len(tv)} runs) — {star}.")

    # ---------- figure ----------
    fig = plt.figure(figsize=(13, 10))
    gs = fig.add_gridspec(3, 1, height_ratios=[1.4, 1.0, 1.0], hspace=0.45)
    xt = np.arange(T)
    show_lab = (T <= 40)

    # ① heatmap régime (features × temps)
    ax1 = fig.add_subplot(gs[0])
    im = ax1.imshow(Z.T, aspect="auto", cmap="RdYlGn", vmin=-2.5, vmax=2.5,
                    interpolation="nearest")
    ax1.set_yticks(range(len(FEATS))); ax1.set_yticklabels([FLAB[f] for f in FEATS], fontsize=9)
    ax1.set_xticks(xt if show_lab else xt[::max(1,T//20)])
    ax1.set_xticklabels((dates if show_lab else dates[::max(1,T//20)]), rotation=90, fontsize=7)
    ax1.set_title("① LE FILM DU RÉGIME — z-scores dans le temps (vert = haut, rouge = bas)",
                  loc="left", fontweight="bold", fontsize=12)
    fig.colorbar(im, ax=ax1, fraction=0.025, pad=0.01, label="z (σ)")

    # ② distance à aujourd'hui
    ax2 = fig.add_subplot(gs[1])
    ax2.plot(xt, dist, "-o", ms=3, color="#1565c0")
    ax2.axhline(THRESH, color="#c62828", ls="--", lw=1, label=f"seuil même régime ({THRESH}σ)")
    ax2.fill_between(xt, 0, THRESH, color="#c62828", alpha=0.06)
    ax2.set_ylabel("distance RMS\nà aujourd'hui (σ)")
    ax2.set_xticks(xt if show_lab else xt[::max(1,T//20)])
    ax2.set_xticklabels((dates if show_lab else dates[::max(1,T//20)]), rotation=90, fontsize=7)
    ax2.set_title(f"② PROXIMITÉ AU RÉGIME DU JOUR — {similar}/{T} run(s) sous le seuil (dont aujourd'hui)",
                  loc="left", fontweight="bold", fontsize=12)
    ax2.legend(fontsize=8, loc="upper left")

    # ③ lift forward 10j — VIX (validé OOS) vs MOVE (candidat, à trancher au backtest trimestriel)
    ax3 = fig.add_subplot(gs[2])
    plotted = False
    for sid, lab, col, oos in TRACK:
        td, tv = tracks[sid]
        if not tv: continue
        xv = np.arange(len(td))
        ls = "-" if oos else "--"
        ax3.plot(xv, tv, ls + "o", ms=3, color=col,
                 label=f"{lab} ({'validé OOS' if oos else 'candidat'})")
        ax3.set_xticks(xv if len(xv)<=40 else xv[::max(1,len(xv)//20)])
        ax3.set_xticklabels((td if len(xv)<=40 else td[::max(1,len(xv)//20)]), rotation=90, fontsize=7)
        plotted = True
    if plotted:
        ax3.axhline(0, color="black", lw=0.8)
        ax3.legend(fontsize=8, loc="upper left")
    else:
        ax3.text(0.5,0.5,"pas encore de lift suivi", ha="center", va="center")
    ax3.set_ylabel("lift 10j (pt)")
    ax3.set_title("③ ÉVOLUTION DU LIFT 10j — VIX (validé OOS) vs MOVE (candidat, backtest trimestriel)",
                  loc="left", fontweight="bold", fontsize=12)

    fig.suptitle(f"MACRO QUANT — analyse cross-day  ·  {T} run(s)  ·  {dates[0]} → {dates[-1]}",
                 fontsize=13, fontweight="bold", y=0.995)
    out = os.path.join(OUT, f"analyze_db_{dates[-1]}.png")
    fig.savefig(out, dpi=115, bbox_inches="tight"); plt.close(fig)
    print(f"\nOK -> {out}\n")


if __name__ == "__main__":
    main()
