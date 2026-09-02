#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
REACTION — lecture de la RÉACTION COURT-TERME du tape APRÈS un label de régime
================================================================================
Ce que ça répond : « le régime que le moteur a identifié le jour D, comment le
tape a-t-il réagi JUSTE APRÈS — T+1, T+2, T+3 jours ? ». C'est un outil DISTINCT
du scorecard :
  - scorecard.py  = espérance LENTE, multi-semaines, du signal VIX forward
                    {5,10,20 j} (base rates sur analogues historiques). Verdict
                    d'un PARI (VIX seul validé OOS).
  - reaction.py   = réaction IMMÉDIATE du PRIX cross-asset (jours) après que le
                    régime a été posé. Plus proche de la Couche 1 (tape) que du
                    moteur de base rates. Cf. mémoire project_quant_shortterm_reaction.

⚠️ CE QUE CET OUTIL EST — ET N'EST PAS (discipline anti-auto-illusion) :
  - C'est un DIAGNOSTIC / POST-MORTEM : « le tape a-t-il CONFIRMÉ ou COMBATTU la
    lecture de régime ? ». PAS un signal prédictif.
  - Le move T+1/2/3 après un label est DOMINÉ par l'information NEUVE (catalyseurs
    arrivés APRÈS le label : CPI, Fed, géopol...). Le régime n'a quasi AUCUNE
    prétention causale sur 1-3 jours — c'est exactement le mur C6/NQ-engine. Donc
    on LIT la réaction, on n'en TIRE PAS un edge directionnel.
  - N minuscule (≈ nb de runs) + régime persistant => fenêtres T+1/2/3 sur jours
    consécutifs FORTEMENT chevauchantes => réactions NON indépendantes. Descriptif,
    pas inférentiel. Se remplit dans le temps, comme le scorecard.
  - Recoupe le tail-detector : le SAUT court-terme est justement ce que le moteur
    de moyennes ignore ; ici on le regarde en face, sans prétendre le prédire.

Données : base append-only db/ (regime_features.csv = 1 régime/jour + z-scores ;
vintage/<dernière>/*.csv = séries fraîches). Réalisé pris dans la DERNIÈRE vintage
(noter a posteriori un label déjà émis n'est PAS du look-ahead ; le leak serait
dans le LABEL, déjà causal côté moteur).

Sortie : résumé stdout + figure reaction_<dernier run>.png.
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

HORIZONS = [1, 2, 3]                       # T+1, T+2, T+3 jours de cotation

# Panel cross-asset "risk". kind = unité de la réaction :
#   pt  = variation en points (VIX)         ; pct = rendement %          ; bp = Δ rendement *100.
# Oil/Or en FUTURES Yahoo (CL_F/GC_F) = frais (les DCOIL* FRED sont lagés ~3-4 j).
ASSETS = [
    ("VIXCLS",    "VIX",     "pt"),
    ("SP500",     "S&P500",  "pct"),
    ("NASDAQCOM", "Nasdaq",  "pct"),
    ("DGS10",     "UST10Y",  "bp"),
    ("CL_F",      "WTI",     "pct"),
    ("GC_F",      "Or",      "pct"),
]

FEATNAMES = ["d10_5","dreal_5","dbe_5","vix_lvl","slope","dusd_5","brwti","brent_mom","growth"]
FEATLABEL = {"d10_5":"10Y↑5j", "dreal_5":"réel↑5j", "dbe_5":"BE↑5j", "vix_lvl":"VIX-niveau",
             "slope":"pente2s10s", "dusd_5":"USD↑5j", "brwti":"spread-Brent-WTI",
             "brent_mom":"Brent-mom", "growth":"croiss(Cu/Au)"}

REG_BUCKETS = [("bas<16", lambda v: v < 16.0),
               ("moyen16-22", lambda v: 16.0 <= v < 22.0),
               ("haut>=22", lambda v: v >= 22.0)]


def load_series(vdir, fname):
    """<vdir>/<fname>.csv -> (dates triées, valeurs). Gère FRED (observation_date,
    VALUE) et Yahoo (Date,Close) : on ne garde que les lignes à 2e colonne float."""
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
                    continue   # header / "." FRED manquant
            rows.sort(key=lambda x: x[0])
            return [d for d, _ in rows], [v for _, v in rows]
    return [], []


def latest_vintage_dir():
    vroot = os.path.join(DB, "vintage")
    if not os.path.isdir(vroot):
        return None
    ds = sorted(d for d in os.listdir(vroot) if os.path.isdir(os.path.join(vroot, d)))
    return os.path.join(vroot, ds[-1]) if ds else None


def _idx_of(dates, asof):
    """index du jour de cotation == asof, sinon dernier <= asof (jour non coté)."""
    if asof in dates:
        return dates.index(asof)
    cand = [i for i, d in enumerate(dates) if d <= asof]
    return cand[-1] if cand else None


def reaction(dates, vals, asof, k, kind):
    """Réaction de l'asset entre asof et asof+k pas de cotation, dans son unité.
    Retourne (valeur, date_at) ou (None, None) si pas encore mûr."""
    idx = _idx_of(dates, asof)
    if idx is None:
        return None, None
    j = idx + k
    if j >= len(dates):
        return None, None           # fenêtre pas écoulée (run récent)
    a, b = vals[idx], vals[j]
    if kind == "pt":
        r = b - a
    elif kind == "bp":
        r = (b - a) * 100.0
    else:  # pct
        r = 100.0 * (b / a - 1.0) if a else None
    return r, dates[j]


def regime_bucket(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "?"
    for name, f in REG_BUCKETS:
        if f(v):
            return name
    return "?"


def load_regimes():
    """regime_features.csv -> liste de dicts {asof, z:{feat:val}}, dédoublonnée par
    asof (1er run rencontré), triée par asof."""
    p = os.path.join(DB, "regime_features.csv")
    if not os.path.exists(p):
        return []
    seen = {}
    for r in csv.DictReader(open(p)):
        asof = r.get("asof", "").strip()
        if not asof or asof in seen:
            continue
        z = {}
        for fn in FEATNAMES:
            try:
                z[fn] = float(r[fn])
            except (KeyError, ValueError, TypeError):
                pass
        seen[asof] = dict(asof=asof, z=z)
    return [seen[a] for a in sorted(seen)]


def dominant(z):
    """(feature dominante, z signé) = celle de |z| max. ('', nan) si vide."""
    if not z:
        return "", float("nan")
    fn = max(z, key=lambda k: abs(z[k]))
    return fn, z[fn]


def build(regimes, series):
    """Pour chaque régime (asof), attache la réaction T+1/2/3 de chaque asset +
    la feature dominante + le bucket VIX de départ."""
    vix_dates, vix_vals = series["VIXCLS"]
    out = []
    for reg in regimes:
        asof = reg["asof"]
        fn, zf = dominant(reg["z"])
        vidx = _idx_of(vix_dates, asof)
        vix0 = vix_vals[vidx] if vidx is not None else None
        rec = dict(asof=asof, dom=fn, domz=zf, vix0=vix0, bucket=regime_bucket(vix0), react={})
        for sid, label, kind in ASSETS:
            dts, vls = series[sid]
            rec["react"][sid] = {k: reaction(dts, vls, asof, k, kind)[0] for k in HORIZONS}
        out.append(rec)
    return out


def _fmt(v, kind):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "   .  "
    u = {"pt": "pt", "bp": "bp", "pct": "%"}[kind]
    return f"{v:+5.1f}{u}"


def summarize(recs):
    last = recs[-1]["asof"] if recs else "?"
    print("\n" + "=" * 84)
    print("REACTION CT POST-RÉGIME — le tape juste APRÈS le label (T+1/T+2/T+3)")
    print("=" * 84)
    print(f"{len(recs)} régimes datés (dédoublonnés par as-of). Réalisé = dernière vintage.")
    print("⚠ DIAGNOSTIC, pas prédiction : le move 1-3 j est piloté par les catalyseurs")
    print("  arrivés APRÈS le label (mur C6). Fenêtres chevauchantes => non indépendant.\n")

    # --- Vue A : chronologique, headline = réaction à T+3 ---
    hdr = f"{'as-of':<11} {'régime dominant':<22} {'VIX0':>6} |"
    for _, label, _ in ASSETS:
        hdr += f" {label+'@T+3':>12}"
    print(hdr); print("-" * len(hdr))
    for r in recs:
        dom = f"{FEATLABEL.get(r['dom'], r['dom'])} ({r['domz']:+.2f})" if r["dom"] else "?"
        v0 = f"{r['vix0']:.1f}" if r["vix0"] is not None else "  .  "
        line = f"{r['asof']:<11} {dom:<22} {v0:>6} |"
        for sid, label, kind in ASSETS:
            line += f" {_fmt(r['react'][sid][3], kind):>12}"
        print(line)

    # --- Vue B : agrégat par bucket de départ VIX (thin, flaggé) ---
    print("\n--- Agrégat par régime de vol de départ (bucket VIX0) — ⚠ n minuscule ---")
    for bname, _ in REG_BUCKETS:
        sub = [r for r in recs if r["bucket"] == bname]
        if not sub:
            continue
        print(f"  [{bname}] {len(sub)} régime(s) :")
        for sid, label, kind in ASSETS:
            for k in HORIZONS:
                vals = [r["react"][sid][k] for r in sub
                        if r["react"][sid][k] is not None]
                if not vals:
                    continue
                m = float(np.mean(vals))
                # part de réactions dans le sens du move moyen (cohérence, pas hit)
                agree = 100.0 * sum(1 for v in vals if np.sign(v) == np.sign(m)) / len(vals)
                if k == 3:  # n'imprime que le headline T+3 pour rester lisible
                    print(f"      {label:<8} T+3 : moy {_fmt(m, kind).strip():>8} "
                          f"(n={len(vals)}, {agree:.0f}% même sens)")
    print("\n>> LECTURE : ces moyennes disent 'le tape a fait X après ce type de régime',")
    print("   PAS 'ce régime CAUSE X'. Outil de confirmation/contradiction, pas d'entrée.")
    return last


def figure(recs, last_run):
    xs = list(range(len(recs)))
    labs = [r["asof"] for r in recs]
    n = len(ASSETS)
    ncol = 2; nrow = (n + 1) // 2
    fig, axes = plt.subplots(nrow, ncol, figsize=(13, 2.4 * nrow), sharex=True)
    axes = np.array(axes).reshape(-1)
    cols = {1: "#90caf9", 2: "#42a5f5", 3: "#1565c0"}
    for ax, (sid, label, kind) in zip(axes, ASSETS):
        for k in HORIZONS:
            ys = [r["react"][sid][k] if r["react"][sid][k] is not None else np.nan for r in recs]
            ax.plot(xs, ys, "-o", ms=3, lw=1.2, color=cols[k], label=f"T+{k}")
        ax.axhline(0, color="black", lw=0.8)
        u = {"pt": "pt", "bp": "bp", "pct": "%"}[kind]
        ax.set_ylabel(f"Δ {label} ({u})", fontsize=9)
        ax.set_title(label, loc="left", fontweight="bold", fontsize=10)
        ax.legend(fontsize=7, ncol=3, loc="best")
        ax.set_xticks(xs); ax.set_xticklabels(labs, rotation=90, fontsize=6)
    for ax in axes[n:]:
        ax.set_visible(False)
    fig.suptitle(f"MACRO QUANT — RÉACTION CT post-régime (T+1/2/3)  ·  run {last_run}\n"
                 f"diagnostic du tape (PAS un signal) — n minuscule, fenêtres chevauchantes",
                 fontsize=11, fontweight="bold", y=1.0)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out = os.path.join(OUT, f"reaction_{last_run}.png")
    fig.savefig(out, dpi=115, bbox_inches="tight"); plt.close(fig)
    return out


def main():
    vdir = latest_vintage_dir()
    if not vdir:
        sys.exit("[reaction] pas de vintage — lance d'abord macro_quant_daily.py")
    last_run = os.path.basename(vdir)
    regimes = load_regimes()
    if not regimes:
        sys.exit("[reaction] regime_features.csv vide — rien à lire.")
    series = {sid: load_series(vdir, sid) for sid, _, _ in ASSETS}
    missing = [sid for sid, (d, _) in series.items() if not d]
    if missing:
        print(f"[reaction] séries absentes de la vintage, ignorées : {missing}", file=sys.stderr)
    recs = build(regimes, series)
    summarize(recs)
    out = figure(recs, last_run)
    print(f"\nOK -> {out}\n")


if __name__ == "__main__":
    main()
