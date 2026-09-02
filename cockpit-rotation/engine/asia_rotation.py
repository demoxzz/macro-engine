#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
ASIA ROTATION — cadran de ROTATION DE LIQUIDITÉ entre PAYS d'Asie-Pacifique
================================================================================
Objet : répondre « vers QUEL pays d'Asie la liquidité tourne (ou fuit) ? ».
Contrairement aux cadrans EU/US (secteurs d'un même indice), l'Asie est un
ensemble de marchés fragmentés → on fait tourner le RRG sur des PAYS via ETF
US-listés (tout USD, FX cohérent, data Yahoo fiable) vs un benchmark synthétique
« Asie EW » (panier equal-weight des pays du cadran).

Méthode = RRG (Relative Rotation Graph), identique EU/US :
  - RS-Ratio (X) : FORCE relative du pays vs benchmark Asie EW (z-score, ~6 mois).
  - RS-Mom   (Y) : MOMENTUM de cette force relative (z-score, ~1 mois).
  - 4 quadrants (rotation ~horaire) :
        LEADING (RS>0,Mom>0) · WEAKENING (RS>0,Mom<0) · LAGGING (RS<0,Mom<0) ·
        IMPROVING (RS<0,Mom>0)  ← faible mais momentum qui se retourne = rotation-IN.

★ LENTILLE semis/IA : Corée (EWY) + Taïwan (EWT) = expression asiatique de la
concentration IA suivie dans le cadran US → lien cross-cockpit. (Pas une position,
juste une grille de lecture.)

⚠️ CADRAN DESCRIPTIF, PAS un trigger. Proxy PRIX de la liquidité (pas de flux ETF
réels ni de valo — dette de données phase 2). z-scores centrés à 0 (simplification
transparente du RRG JdK centré à 100 : même logique, calcul auditable).

Cadence : HEBDO (rotation lente). Le run complet écrit la figure + logue l'état du
jour dans rotation_history.csv (substrat de la détection de franchissement).

Univers : 11 ETF-pays US-listés (USD) + 2 ADR bellwether (TSM, BABA). Benchmark =
panier equal-weight synthétique des 11 pays.
Dépendances : numpy + matplotlib + yfetch (stdlib).
================================================================================
"""
import os, sys, csv, datetime as dt
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import yfetch

HERE = os.path.dirname(os.path.abspath(__file__))
OUT  = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(HERE, "..", "..", "analysis", "asia-rotation")
os.makedirs(OUT, exist_ok=True)
HISTLOG = os.path.join(OUT, "rotation_history.csv")
HIST_FIELDS = ["run_date", "sid", "label", "thesis", "rs", "mom", "quad", "disp", "disp_pct"]

BENCH_LABEL = "Asie EW"
# (ticker ETF-pays US-listé USD, label court, lentille semis/IA ?)
COUNTRIES = [
    ("EWJ",  "Japon",     False),
    ("MCHI", "Chine",     False),
    ("EWY",  "Corée",     True),   # ★ semis/IA (Samsung, SK Hynix)
    ("EWT",  "Taïwan",    True),   # ★ semis/IA (TSMC)
    ("INDA", "Inde",      False),
    ("EWH",  "Hong Kong", False),
    ("EWS",  "Singapour", False),
    ("EWA",  "Australie", False),
    ("EIDO", "Indonésie", False),
    ("THD",  "Thaïlande", False),
    ("EWM",  "Malaisie",  False),
]
NAMES = [  # ADR bellwether (USD) à situer vs leur pays & le benchmark Asie EW
    ("TSM",  "TSMC (Taïwan)",   "EWT"),
    ("BABA", "Alibaba (Chine)", "MCHI"),
]

L = 126   # fenêtre z-score de la force relative (~6 mois de cotation)
M = 21    # horizon du momentum relatif (~1 mois)
TAILW = 6 # nb de points hebdo de la trajectoire (queue RRG)
DISP_HOT = 70.0  # percentile de dispersion au-delà duquel la rotation est "active"


def zlast(x):
    m, s = np.mean(x), np.std(x)
    return (x[-1] - m) / s if s > 0 else 0.0


def rs_series(rel):
    """Séries RS-Ratio et RS-Mom (z-scores glissants) pour une ligne relative rel."""
    n = len(rel)
    r1 = np.full(n, np.nan); r2 = np.full(n, np.nan)
    mom = np.full(n, np.nan)
    mom[M:] = rel[M:] - rel[:-M]
    for t in range(L, n):
        r1[t] = zlast(rel[t - L + 1:t + 1])
        win = mom[t - L + 1:t + 1]; win = win[~np.isnan(win)]
        if len(win) > 5 and np.std(win) > 0:
            r2[t] = (mom[t] - np.mean(win)) / np.std(win)
    return r1, r2


def quadrant(rs, mom):
    if np.isnan(rs) or np.isnan(mom):
        return "?"
    if rs >= 0 and mom >= 0:  return "LEADING"
    if rs >= 0 and mom < 0:   return "WEAKENING"
    if rs < 0 and mom < 0:    return "LAGGING"
    return "IMPROVING"


def align(series_map, keys):
    common = None
    for k in keys:
        ds = set(series_map[k].keys())
        common = ds if common is None else (common & ds)
    dates = sorted(common)
    return dates, {k: np.array([series_map[k][d] for d in dates]) for k in keys}


# ===========================================================================
# COMPUTE — état du cadran (importé par asia_rotation_watch.py)
# ===========================================================================
def compute():
    keys = [c[0] for c in COUNTRIES] + [n[0] for n in NAMES]
    raw = {}
    for k in keys:
        raw[k] = yfetch.fetch(k)
        if not raw[k]:
            raise SystemExit(f"[asia_rotation] fetch vide pour {k} — abandon.")
    dates, px = align(raw, keys)
    if len(dates) < L + M + 5:
        raise SystemExit("[asia_rotation] historique commun trop court.")
    asof = dates[-1]

    # Benchmark synthétique = panier equal-weight des pays (indice normalisé à 1).
    norm = {c[0]: px[c[0]] / px[c[0]][0] for c in COUNTRIES}
    bench = np.mean(np.vstack([norm[c[0]] for c in COUNTRIES]), axis=0)

    rows, tails = [], {}
    for tk, lab, thesis in COUNTRIES:
        rel = norm[tk] / bench
        r1, r2 = rs_series(rel)
        rs, mom = r1[-1], r2[-1]
        r1m = 100.0 * (px[tk][-1] / px[tk][-M] - 1)
        r3m = 100.0 * (px[tk][-1] / px[tk][-3 * M] - 1)
        relret3 = 100.0 * ((px[tk][-1] / px[tk][-3 * M]) / (bench[-1] / bench[-3 * M]) - 1)
        rows.append(dict(tk=tk, lab=lab, thesis=thesis, rs=float(rs), mom=float(mom),
                         quad=quadrant(rs, mom), r1m=r1m, r3m=r3m, relret3=relret3))
        idx = [i for i in ([len(dates) - 1 - 5 * i for i in range(TAILW)][::-1]) if i >= 0]
        tails[tk] = [(r1[i], r2[i]) for i in idx]

    cty_1m = np.array([r["r1m"] for r in rows if not np.isnan(r["r1m"])])
    disp = float(np.std(cty_1m))
    disp_hist = []
    for t in range(len(dates) - 252, len(dates)):
        if t - M < 0:
            continue
        rr = [100.0 * (px[c[0]][t] / px[c[0]][t - M] - 1) for c in COUNTRIES]
        disp_hist.append(float(np.std(rr)))
    disp_pct = 100.0 * sum(1 for d in disp_hist if d <= disp) / len(disp_hist) if disp_hist else float("nan")

    names = []
    for tk, lab, parent in NAMES:
        rel = (px[tk] / px[tk][0]) / bench
        r1, r2 = rs_series(rel)
        relret3 = 100.0 * ((px[tk][-1] / px[tk][-3 * M]) / (bench[-1] / bench[-3 * M]) - 1)
        names.append(dict(tk=tk, lab=lab, parent=parent, rs=float(r1[-1]), mom=float(r2[-1]),
                          quad=quadrant(r1[-1], r2[-1]), relret3=relret3))

    order = sorted(rows, key=lambda r: r["rs"], reverse=True)
    return dict(asof=asof, rows=rows, order=order, tails=tails,
                disp=disp, disp_hist=disp_hist, disp_pct=disp_pct, names=names)


# ===========================================================================
# LOG — historique append-only (substrat de la détection de franchissement)
# ===========================================================================
def log_history(res):
    rows = [dict(run_date=res["asof"], sid=r["tk"], label=r["lab"],
                 thesis=int(r["thesis"]), rs=round(r["rs"], 4), mom=round(r["mom"], 4),
                 quad=r["quad"], disp=round(res["disp"], 4), disp_pct=round(res["disp_pct"], 2))
            for r in res["rows"]]
    key = {(res["asof"], r["sid"]) for r in rows}
    existing = []
    if os.path.exists(HISTLOG):
        for row in csv.DictReader(open(HISTLOG)):
            if (row.get("run_date"), row.get("sid")) not in key:
                existing.append(row)
    with open(HISTLOG, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HIST_FIELDS); w.writeheader()
        for row in existing + rows:
            w.writerow({k: row.get(k, "") for k in HIST_FIELDS})


# ===========================================================================
# REPORT (stdout) + FIGURE
# ===========================================================================
def print_report(res):
    asof = res["asof"]
    print("\n" + "=" * 82)
    print(f"CADRAN ROTATION LIQUIDITÉ ASIE — pays (ETF US-listés USD)  ·  as-of {asof}")
    print("=" * 82)
    print("RRG : X = force relative (z, 6m) · Y = momentum relatif (z, 1m) vs benchmark Asie EW.")
    print("  LEADING fort&↑ · WEAKENING fort&↓ · LAGGING faible&↓ · IMPROVING faible&↑(rotation-IN)")
    print(f"\nIntensité de rotation (dispersion perfs 1m) : {res['disp']:.1f} pts = "
          f"P{res['disp_pct']:.0f} sur 1 an  "
          f"({'ÉLEVÉE→rotation active' if res['disp_pct'] >= DISP_HOT else 'moyenne/faible'})")
    print(f"\n{'Pays':<12}{'quadrant':<11}{'RS(z)':>7}{'Mom(z)':>8}{'1m%':>7}{'3m%':>7}{'rel3m%':>8}  semis/IA")
    print("-" * 82)
    for r in res["order"]:
        print(f"{r['lab']:<12}{r['quad']:<11}{r['rs']:>7.2f}{r['mom']:>8.2f}"
              f"{r['r1m']:>7.1f}{r['r3m']:>7.1f}{r['relret3']:>8.1f}  {'★' if r['thesis'] else ''}")
    print("\n--- ★ LENTILLE semis/IA (Corée + Taïwan) — lien avec la concentration IA US ---")
    msgmap = {"LAGGING": "faible & s'enfonce — la liquidité IA ne va PAS (encore) aux semis Asie",
              "IMPROVING": "⚡ faible mais MOMENTUM QUI TOURNE — rotation-IN naissante",
              "LEADING": "fort & se renforce — la liquidité IA irrigue les semis Asie",
              "WEAKENING": "fort mais s'essouffle — rotation mature", "?": "données insuffisantes"}
    for r in [x for x in res["rows"] if x["thesis"]]:
        print(f"  {r['lab']:<12} [{r['quad']}] rel3m {r['relret3']:+.1f}% → {msgmap[r['quad']]}")
    print("\n--- Noms bellwether (ADR USD, force relative vs Asie EW, 3m) ---")
    for n in res["names"]:
        print(f"  {n['lab']:<16} RS(z) {n['rs']:+.2f}  Mom(z) {n['mom']:+.2f}  [{n['quad']}]  "
              f"rel3m {n['relret3']:+.1f}%")
    print("\n>> LECTURE : cadran DESCRIPTIF (où en est la rotation), PAS un trigger. Rotation-IN")
    print("   crédible = pays en IMPROVING + dispersion élevée + catalyseur (Fed/USD, Chine, BoJ).")
    print("   Ne mesure PAS les flux réels ni la valo (dette de données phase 2).")


def figure(res):
    order, tails, asof = res["order"], res["tails"], res["asof"]
    fig = plt.figure(figsize=(14, 8))
    gs = fig.add_gridspec(1, 3, width_ratios=[2.2, 2.2, 1.0], wspace=0.28)
    ax = fig.add_subplot(gs[0, :2])
    lim = max(2.0, max(abs(r["rs"]) for r in order) + 0.5, max(abs(r["mom"]) for r in order) + 0.5)
    ax.axhspan(0, lim, xmin=0.5, xmax=1.0, color="#c8e6c9", alpha=0.35)
    ax.axhspan(-lim, 0, xmin=0.5, xmax=1.0, color="#fff9c4", alpha=0.35)
    ax.axhspan(-lim, 0, xmin=0.0, xmax=0.5, color="#ffcdd2", alpha=0.35)
    ax.axhspan(0, lim, xmin=0.0, xmax=0.5, color="#bbdefb", alpha=0.35)
    ax.axhline(0, color="k", lw=0.8); ax.axvline(0, color="k", lw=0.8)
    ax.text(lim * 0.95, lim * 0.92, "LEADING", ha="right", fontsize=9, color="#2e7d32", fontweight="bold")
    ax.text(lim * 0.95, -lim * 0.95, "WEAKENING", ha="right", fontsize=9, color="#f9a825", fontweight="bold")
    ax.text(-lim * 0.95, -lim * 0.95, "LAGGING", ha="left", fontsize=9, color="#c62828", fontweight="bold")
    ax.text(-lim * 0.95, lim * 0.92, "IMPROVING", ha="left", fontsize=9, color="#1565c0", fontweight="bold")
    for r in order:
        col = "#6a1b9a" if r["thesis"] else "#555555"
        tl = tails.get(r["tk"], [])
        if len(tl) >= 2:
            ax.plot([p[0] for p in tl], [p[1] for p in tl], "-", color=col, alpha=0.35, lw=1.0)
        ax.scatter([r["rs"]], [r["mom"]], s=90 if r["thesis"] else 45, color=col,
                   edgecolor="white", zorder=5, marker="o" if r["thesis"] else "s")
        ax.annotate(r["lab"], (r["rs"], r["mom"]), fontsize=7.5,
                    fontweight="bold" if r["thesis"] else "normal",
                    xytext=(4, 4), textcoords="offset points", color=col)
    ax.set_xlim(-lim, lim); ax.set_ylim(-lim, lim)
    ax.set_xlabel("Force relative RS-Ratio (z, 6m)  →  sur-performance vs Asie EW")
    ax.set_ylabel("Momentum relatif RS-Mom (z, 1m)  →  amélioration")
    ax.set_title(f"RRG pays Asie-Pacifique (ETF US-listés USD) — as-of {asof}\n"
                 "★/violet = lentille semis/IA (Corée, Taïwan) · benchmark = panier EW · queue = 6 sem.",
                 loc="left", fontweight="bold", fontsize=10)
    ax2 = fig.add_subplot(gs[0, 2])
    dh = res["disp_hist"]
    ax2.plot(range(len(dh)), dh, color="#00695c", lw=1.2)
    ax2.axhline(res["disp"], color="#d84315", lw=1.2, ls="--", label=f"actuel P{res['disp_pct']:.0f}")
    ax2.set_title("Dispersion perfs 1m\n(intensité de rotation, 1 an)", fontsize=9, fontweight="bold")
    ax2.set_ylabel("écart-type cross-sectionnel (pts)", fontsize=8)
    ax2.legend(fontsize=8); ax2.set_xticks([])
    fig.suptitle("MACRO/EQUITY — CADRAN ROTATION LIQUIDITÉ ASIE  ·  descriptif (pas un trigger) · proxy prix (flux/valo = phase 2)",
                 fontsize=11, fontweight="bold", y=1.0)
    fig.subplots_adjust(left=0.06, right=0.98, top=0.90, bottom=0.08)
    out = os.path.join(OUT, f"asia_rotation_{asof}.png")
    fig.savefig(out, dpi=115, bbox_inches="tight")
    # copie à nom stable pour le cockpit (toujours = dernier run)
    fig.savefig(os.path.join(OUT, "asia_rotation_latest.png"), dpi=115, bbox_inches="tight")
    plt.close(fig)
    return out


def main():
    res = compute()
    print_report(res)
    out = figure(res)
    log_history(res)
    print(f"\nOK -> {out}\n")


if __name__ == "__main__":
    main()
