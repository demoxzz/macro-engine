#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
SCORECARD — track-record LIVE du signal (prédit vs RÉALISÉ)
================================================================================
Ce que ça répond : « depuis que je tourne le moteur en live, mes base rates
VIX se sont-ils VÉRIFIÉS ? ». C'est le complément manquant d'analyze_db.py, qui
ne trace que le lift PRÉDIT dans le temps sans jamais le confronter au réalisé.

Méthode (fidèle à la cible du moteur) :
  - Prédiction : pour chaque run (clé = as-of D), mean_cond forward {5,10,20 j}
    lu dans db/base_rates.csv. Pour VIX c'est fwd_vol = mean(VIX[t+h]-VIX[t])
    sur les analogues, EN POINTS de VIX (cf macro_quant_engine.fwd_vol).
  - Réalisé : VIX[D+h] - VIX[D], même définition, série prise dans la DERNIÈRE
    vintage (db/vintage/<plus récente>/VIXCLS.csv). Utiliser la donnée
    d'aujourd'hui pour noter un call passé n'est PAS du look-ahead : on note
    a posteriori un pari déjà émis (le leak serait dans la PRÉDICTION, déjà
    géré causalement par le moteur).
  - Horizon h = h jours de COTATION. Approx faite : on avance de h pas sur le
    calendrier propre du VIX (jours où VIXCLS cote) ≈ calendrier maître DGS10
    du moteur (mêmes jours fériés US) — écart marginal, signalé.

Honnêteté obligatoire :
  - Runs quotidiens = fenêtres QUI SE CHEVAUCHENT + même régime sur des jours
    consécutifs => le nb de calls "indépendants" est BIEN plus petit que le nb
    de lignes. On dédoublonne par as-of, et on affiche le caveat.
  - Un call isolé ne prouve rien (modèle favorable ~55% @10j). Le scorecard ne
    devient parlant qu'en agrégé sur beaucoup de calls => il se REMPLIT dans le
    temps. Au démarrage il est volontairement maigre, et il le dit.

Sortie : résumé stdout + figure scorecard_<dernier run>.png (prédit vs réalisé).
Dépendances : numpy + matplotlib + stdlib.
================================================================================
"""
import os, sys, csv, math
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
DB   = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.abspath(os.path.join(HERE, "..", "..", "db"))
OUT  = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else os.path.join(HERE, "..", "..", "analysis", "macro-quant")
os.makedirs(OUT, exist_ok=True)

HORIZONS = [5, 10, 20]
# Assets notables ici = ceux dont la cible est une variation en POINTS (kind=vol).
#   VIX  = seul validé OOS -> le seul dont le hit-rate est un VERDICT.
#   MOVE = candidat resp-only -> noté en CONTEXTE (ne jamais présenter comme pari).
TRACK = [
    ("VIXCLS", "VIX",  "^VIXCLS", True),
    ("MOVE",   "MOVE", "^MOVE",   False),
]


def latest_vintage_dir():
    vroot = os.path.join(DB, "vintage")
    if not os.path.isdir(vroot):
        return None
    ds = sorted(d for d in os.listdir(vroot) if os.path.isdir(os.path.join(vroot, d)))
    return os.path.join(vroot, ds[-1]) if ds else None


def load_series(vdir, fname):
    """Charge <vdir>/<fname>.csv -> (dates triées, valeurs) en jours de cotation."""
    for cand in (fname + ".csv", fname.lstrip("^") + ".csv"):
        p = os.path.join(vdir, cand)
        if os.path.exists(p):
            rows = []
            for r in csv.reader(open(p)):
                if not r or len(r) < 2:
                    continue
                d, v = r[0].strip(), r[1].strip()
                try:
                    rows.append((d, float(v)))
                except ValueError:
                    continue  # header / vide
            rows.sort(key=lambda x: x[0])
            return [d for d, _ in rows], [v for _, v in rows]
    return [], []


def load_predictions(sid):
    """Prédictions mean_cond/lift/pneg par as-of & horizon. Dédoublonné par as-of."""
    p = os.path.join(DB, "base_rates.csv")
    if not os.path.exists(p):
        return {}
    seen = {}   # (asof, h) -> dict
    for r in csv.DictReader(open(p)):
        if r["sid"] != sid:
            continue
        try:
            key = (r["asof"], int(r["h"]))
        except (ValueError, TypeError):
            continue
        if key in seen:
            continue  # 1er run rencontré par as-of (idempotent : valeurs identiques)
        try:
            seen[key] = dict(asof=r["asof"], h=int(r["h"]),
                             mean_cond=float(r["mean_cond"]),
                             lift=float(r["lift_mean"]),
                             pneg=float(r["pneg_cond"]))
        except (ValueError, TypeError):
            continue
    return seen


def realized_move(dates, vals, asof, h):
    """VIX[asof+h] - VIX[asof] en avançant de h pas de cotation. None si pas mûr."""
    if asof not in dates:
        # as-of absent de la série (jour non coté ?) -> on prend le dernier <= asof
        idx = None
        for i, d in enumerate(dates):
            if d <= asof:
                idx = i
            else:
                break
        if idx is None:
            return None, None, None
    else:
        idx = dates.index(asof)
    j = idx + h
    if j >= len(dates):
        return None, None, None   # call pas encore mûr (fenêtre non écoulée)
    return vals[j] - vals[idx], dates[j], vals[idx]


def score_asset(sid, label, vdir):
    dates, vals = load_series(vdir, dict((s, y) for s, _, y, _ in TRACK)[sid])
    preds = load_predictions(sid)
    if not dates or not preds:
        return None
    last_obs = dates[-1]
    rows = {h: [] for h in HORIZONS}   # h -> list of dicts
    for (asof, h), pr in preds.items():
        rz, dz, base = realized_move(dates, vals, asof, h)
        rows[h].append(dict(asof=asof, h=h, pred=pr["mean_cond"], lift=pr["lift"],
                            pneg=pr["pneg"], realized=rz, date_at=dz, vix0=base))
    for h in HORIZONS:
        rows[h].sort(key=lambda x: x["asof"])
    return dict(label=label, sid=sid, last_obs=last_obs, rows=rows, dates=dates,
                n_asof=len(set(a for a, _ in preds.keys())))


def summarize(res, stale=False, ref_last=None):
    L = res["label"]
    print(f"\n================ SCORECARD {L} — prédit vs RÉALISÉ ================")
    print(f"Série réalisée jusqu'au {res['last_obs']} (dernière vintage).  "
          f"{res['n_asof']} as-of distincts émis.")
    if stale:
        print(f"  ⚠ SÉRIE PÉRIMÉE : {L} s'arrête au {res['last_obs']} alors que le VIX est à jour "
              f"au {ref_last}.")
        print(f"    -> Yahoo a coupé le flux gratuit ^MOVE (et ^VIX3M) mi-2026. {L} = CONTEXTE INDISPO,")
        print(f"       ne PAS lire comme vivant. Calls ci-dessous figés, affichés pour mémoire seulement.")
    for h in HORIZONS:
        rr = res["rows"][h]
        graded = [x for x in rr if x["realized"] is not None]
        pending = len(rr) - len(graded)
        if not graded:
            print(f"  [{h:>2}j] 0 call MÛR (il faut +{h} j de cotation) — {pending} en attente.")
            continue
        preds = np.array([x["pred"] for x in graded])
        real  = np.array([x["realized"] for x in graded])
        # hit directionnel : le signe prédit s'est-il réalisé ?
        hits = np.sum(np.sign(preds) == np.sign(real))
        hit_rate = 100.0 * hits / len(graded)
        # IC réalisé (corrélation prédit/réalisé) — bruité si peu de points
        ic = float(np.corrcoef(preds, real)[0, 1]) if len(graded) >= 3 and np.std(preds) > 0 and np.std(real) > 0 else float("nan")
        print(f"  [{h:>2}j] {len(graded)} call(s) mûr(s), {pending} en attente.")
        print(f"        prédit moy {preds.mean():+.2f} pt  vs  réalisé moy {real.mean():+.2f} pt")
        print(f"        hit directionnel {hits}/{len(graded)} = {hit_rate:.0f}%   "
              f"| IC réalisé { 'n/a' if math.isnan(ic) else f'{ic:+.2f}'} (bruité si <~10 pts indép.)")
        for x in graded:
            print(f"          as-of {x['asof']} → {x['date_at']} : prédit {x['pred']:+.2f} | "
                  f"réalisé {x['realized']:+.2f} pt ({x['vix0']:.1f}→{x['vix0']+x['realized']:.1f})")


# ===========================================================================
# BRIQUE 1 (calibration + rang) & BRIQUE 3 (porte de promotion pré-enregistrée)
# ===========================================================================
# Le base rate VIX a un skill de RANG (IC réalisé +0,68 au 1er run) mais un
# NIVEAU biaisé trop vol-up (prédit +0,26 vs réalisé −1,13). On (a) exprime le
# call live en PERCENTILE de son propre historique (le rang = là où est le
# skill), (b) recalibre le niveau par un biais SHRINKÉ (n petit => on corrige
# peu), (c) mesure la PORTE DE PROMOTION : le signal reste "contexte" tant qu'il
# n'a pas accumulé assez de calls INDÉPENDANTS sur PLUSIEURS régimes.

SHRINK_K = 10.0          # shrink du biais : w = n/(n+K). n petit -> correction douce.
PROMO_MIN_INDEP = 30     # calls à fenêtres non-chevauchantes requis (pré-enregistré)
PROMO_MIN_REGIMES = 2    # nb de régimes de vol distincts requis (proxy = bucket VIX)
REG_BUCKETS = [("bas<16", lambda v: v < 16.0),
               ("moyen16-22", lambda v: 16.0 <= v < 22.0),
               ("haut>=22", lambda v: v >= 22.0)]


def regime_bucket(vix0):
    if vix0 is None or (isinstance(vix0, float) and math.isnan(vix0)):
        return "?"
    for name, f in REG_BUCKETS:
        if f(vix0):
            return name
    return "?"


def _idx_of(dates, asof):
    """index du jour de cotation = asof, sinon dernier <= asof."""
    if asof in dates:
        return dates.index(asof)
    cand = [i for i, d in enumerate(dates) if d <= asof]
    return cand[-1] if cand else None


def independent_calls(graded, dates, h):
    """Sous-ensemble greedy de calls dont les fenêtres forward NE SE CHEVAUCHENT
    PAS (espacés d'au moins h jours de cotation) => calls ~indépendants."""
    picks = []; last_i = None
    for x in sorted(graded, key=lambda z: z["asof"]):
        i = _idx_of(dates, x["asof"])
        if i is None:
            continue
        if last_i is None or (i - last_i) >= h:
            picks.append(x); last_i = i
    return picks


def percentile_of(value, pool):
    pool = [p for p in pool if p is not None and not (isinstance(p, float) and math.isnan(p))]
    if not pool or value is None:
        return None
    return 100.0 * sum(1 for p in pool if p <= value) / len(pool)


def live_report(res):
    """Lecture LIVE du dernier call : rang (percentile), niveau recalibré (biais
    shrinké), et statut de la porte de promotion. Retourne {h: gate_bool}."""
    L = res["label"]; dates = res["dates"]
    print(f"\n================ {L} — LECTURE LIVE · CALIBRATION · PROMOTION ================")
    all_asof = sorted({x["asof"] for h in HORIZONS for x in res["rows"][h]})
    live_asof = all_asof[-1] if all_asof else None
    print(f"Dernier call émis : as-of {live_asof}. "
          f"Rappel : le VIX a un skill de RANG, pas de niveau -> lire le percentile, pas les points.")
    gate = {}
    for h in HORIZONS:
        rr = res["rows"][h]
        graded = [x for x in rr if x["realized"] is not None]
        pool = [x["pred"] for x in rr]
        live = next((x for x in rr if x["asof"] == live_asof), None)
        pct = percentile_of(live["pred"], pool) if live else None
        if graded:
            preds = np.array([x["pred"] for x in graded]); real = np.array([x["realized"] for x in graded])
            n = len(graded); bias = float(real.mean() - preds.mean()); w = n / (n + SHRINK_K)
            ic = float(np.corrcoef(preds, real)[0, 1]) if n >= 3 and preds.std() > 0 and real.std() > 0 else float("nan")
        else:
            n = 0; bias = float("nan"); w = 0.0; ic = float("nan")
        ind = independent_calls(graded, dates, h)
        buckets = sorted({regime_bucket(x["vix0"]) for x in ind} - {"?"})
        g = (len(ind) >= PROMO_MIN_INDEP and len(buckets) >= PROMO_MIN_REGIMES
             and not math.isnan(ic) and ic > 0)
        gate[h] = g
        print(f"\n  [{h:>2}j]")
        if live is not None and pct is not None:
            flag = "INHABITUEL" if (pct >= 80 or pct <= 20) else "médian"
            print(f"    rang du call live : tilt {live['pred']:+.2f} pt = P{pct:.0f} "
                  f"de l'historique VIX ({flag})")
        if n:
            corr = (live["pred"] + w * bias) if live is not None else float("nan")
            icf = "n/a" if math.isnan(ic) else f"{ic:+.2f}"
            print(f"    calibration : biais réalisé−prédit {bias:+.2f} pt sur {n} calls mûrs "
                  f"(IC rang {icf}) ; tilt RECALIBRÉ (shrink w={w:.2f}) = {corr:+.2f} pt")
        else:
            print(f"    calibration : aucun call mûr à {h}j.")
        icf = "n/a" if math.isnan(ic) else f"{ic:+.2f}"
        print(f"    PROMOTION : {len(ind)}/{PROMO_MIN_INDEP} calls indépendants · "
              f"{len(buckets)}/{PROMO_MIN_REGIMES} régimes {buckets} · IC {icf} "
              f"-> {'✅ PROMOUVABLE en sizing' if g else '🔒 VERROUILLÉ EN CONTEXTE'}")
    return gate


def usage_banner():
    print("\n" + "=" * 78)
    print("RÈGLE D'USAGE (brique 2) — ce que le VIX base rate a le DROIT de faire")
    print("=" * 78)
    print("  Scope prouvé : prédit la VOL IMPLICITE, EN MOYENNE, EN RANG. Muet en")
    print("  direction actions (IC~0) ; aveugle aux krachs (capture ~1% des spikes).")
    print("  USAGE AUTORISÉ  : cadran de CONTEXTE-VOL / multiplicateur de CONVICTION.")
    print("    - rang vol-up ÉLEVÉ (P>=80) partant d'un VIX bas (complacency) ->")
    print("      contexte pour DÉ-SIZER / resserrer côté PF & discrétionnaire.")
    print("  USAGE INTERDIT  : trigger directionnel, short-vol, achat de hedge de")
    print("    queue (tous réfutés net de coûts/contango en C5). Ce n'est PAS un signal")
    print("    d'entrée ni une protection anti-krach.")
    print("  Poids : reste CONTEXTE tant que la porte de promotion ci-dessus est 🔒.")


def figure(results, last_run):
    horizons = HORIZONS
    fig, axes = plt.subplots(len(horizons), 1, figsize=(11, 9), sharex=False)
    if len(horizons) == 1:
        axes = [axes]
    for ax, h in zip(axes, horizons):
        for sid, label, _, oos in TRACK:
            res = next((r for r in results if r and r["sid"] == sid), None)
            if res is None:
                continue
            rr = res["rows"][h]
            xs = list(range(len(rr)))
            labs = [x["asof"] for x in rr]
            pred = [x["pred"] for x in rr]
            real = [x["realized"] if x["realized"] is not None else np.nan for x in rr]
            col = "#6a1b9a" if sid == "VIXCLS" else "#00838f"
            ls = "-" if oos else "--"
            ax.plot(xs, pred, ls, color=col, alpha=0.55, lw=1.4,
                    label=f"{label} prédit" + ("" if oos else " (candidat)"))
            ax.plot(xs, real, "o", color=col, ms=6,
                    label=f"{label} RÉALISÉ")
            ax.set_xticks(xs); ax.set_xticklabels(labs, rotation=90, fontsize=7)
        ax.axhline(0, color="black", lw=0.8)
        ax.set_ylabel(f"Δ VIX {h}j (pt)")
        ax.set_title(f"Horizon {h}j — ligne = tilt prédit (mean_cond), point = réalisé (vide = pas mûr)",
                     loc="left", fontweight="bold", fontsize=10)
        ax.legend(fontsize=7, loc="upper left", ncol=2)
    fig.suptitle(f"MACRO QUANT — SCORECARD prédit vs réalisé  ·  run {last_run}",
                 fontsize=12, fontweight="bold", y=0.997)
    fig.tight_layout(rect=[0, 0, 1, 0.98])
    out = os.path.join(OUT, f"scorecard_{last_run}.png")
    fig.savefig(out, dpi=115, bbox_inches="tight"); plt.close(fig)
    return out


def main():
    vdir = latest_vintage_dir()
    if not vdir:
        sys.exit("[scorecard] pas de vintage — lance d'abord macro_quant_daily.py")
    last_run = os.path.basename(vdir)
    results = [score_asset(sid, label, vdir) for sid, label, _, _ in TRACK]
    results = [r for r in results if r]
    if not results:
        sys.exit("[scorecard] rien à noter (pas de prédictions/série).")
    # référence de fraîcheur = VIX (verdict, toujours à jour via FRED VIXCLS)
    vix = next((r for r in results if r["sid"] == "VIXCLS"), None)
    ref_last = vix["last_obs"] if vix else None
    for res in results:
        stale = bool(ref_last and res["sid"] != "VIXCLS" and res["last_obs"] < ref_last)
        summarize(res, stale=stale, ref_last=ref_last)
    print("\n>> RAPPEL HONNÊTETÉ : runs quotidiens = fenêtres chevauchantes + régime")
    print("   persistant => calls fortement corrélés. Le hit-rate n'est PARLANT qu'en")
    print("   agrégé sur beaucoup de calls INDÉPENDANTS. Au démarrage il est maigre et")
    print("   se remplit dans le temps. VIX = verdict ; MOVE = contexte (resp-only).")
    # BRIQUE 1+3 : lecture live calibrée (rang + niveau shrinké) + porte de promotion
    if vix:
        live_report(vix)
    # BRIQUE 2 : règle d'usage (ce que le signal a le droit de faire)
    usage_banner()
    out = figure(results, last_run)
    print(f"\nOK -> {out}\n")


if __name__ == "__main__":
    main()
