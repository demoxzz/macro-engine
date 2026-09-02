#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
EU ROTATION — cadran de ROTATION DE LIQUIDITÉ entre secteurs (STOXX Europe 600)
================================================================================
Objet : répondre « vers QUELS secteurs EU la liquidité tourne (ou fuit) ? »,
au service de la thèse rotation quality-value EU (spiritueux/luxe/santé massacrés
pendant que la liquidité allait à l'IA/tech → pari de ré-allocation).

Méthode = RRG (Relative Rotation Graph), le cadre institutionnel standard :
  - RS-Ratio  (axe X) : FORCE relative du secteur vs benchmark (STOXX 600).
                        = z-score de la ligne relative (secteur/benchmark) sur L jours.
  - RS-Mom    (axe Y) : MOMENTUM de cette force relative (z-score de sa variation).
  - 4 quadrants (rotation ~horaire) :
        LEADING (RS>0,Mom>0) · WEAKENING (RS>0,Mom<0) · LAGGING (RS<0,Mom<0) ·
        IMPROVING (RS<0,Mom>0)  ← faible mais momentum qui se retourne = rotation-IN.

⚠️ CADRAN DESCRIPTIF, PAS un trigger. Proxy PRIX de la liquidité (pas de flux ETF
réels ni de valo — dette de données phase 2). z-scores centrés à 0 (simplification
transparente du RRG JdK centré à 100 : même logique, calcul auditable).

Cadence : HEBDO (rotation lente). Le run complet écrit la figure + logue l'état du
jour dans rotation_history.csv (substrat de la détection de franchissement, cf.
eu_rotation_watch.py = entrée quotidienne alerte + rapport lundi).

Univers : 18 ETF iShares STOXX Europe 600 (Xetra EUR, noms VÉRIFIÉS source Yahoo)
+ benchmark ^STOXX + noms thèse .PA. Tout EUR (FX cohérent).
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
OUT  = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(HERE, "..", "..", "analysis", "eu-rotation")
os.makedirs(OUT, exist_ok=True)
HISTLOG = os.path.join(OUT, "rotation_history.csv")
HIST_FIELDS = ["run_date", "sid", "label", "thesis", "rs", "mom", "quad", "disp", "disp_pct"]

BENCH = ("^STOXX", "STOXX 600")
# (ticker, label court, thèse?) — noms officiels vérifiés via meta Yahoo le 14/08/2026.
SECTORS = [
    ("EXV1.DE", "Banks",            False),
    ("EXV2.DE", "Télécoms",         False),
    ("EXV3.DE", "Technology",       False),
    ("EXV4.DE", "Health Care",      True),   # défensive quality — jambe thèse
    ("EXV5.DE", "Auto & Parts",     False),
    ("EXV6.DE", "Basic Resources",  False),
    ("EXV7.DE", "Chemicals",        False),
    ("EXV8.DE", "Construction",     False),
    ("EXV9.DE", "Travel & Leisure", False),
    ("EXH1.DE", "Oil & Gas",        False),
    ("EXH2.DE", "Financial Svs",    False),
    ("EXH3.DE", "Food & Beverage",  True),   # spiritueux/conso — cœur thèse (RI, RCO)
    ("EXH4.DE", "Indus. G&S",       False),
    ("EXH5.DE", "Insurance",        False),
    ("EXH6.DE", "Media",            False),
    ("EXH7.DE", "Pers.& Household", True),   # LUXE/cosméto — cœur thèse (EL, RMS, MC, OR)
    ("EXH8.DE", "Retail",           False),
    ("EXH9.DE", "Utilities",        False),
]
NAMES = [  # noms de la thèse à situer vs leur secteur & le benchmark
    ("RI.PA",  "Pernod-Ricard",    "EXH3.DE"),
    ("RCO.PA", "Rémy-Cointreau",   "EXH3.DE"),
    ("EL.PA",  "EssilorLuxottica", "EXH7.DE"),
    ("RMS.PA", "Hermès",           "EXH7.DE"),
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
# COMPUTE — état du cadran (importé par eu_rotation_watch.py)
# ===========================================================================
def compute():
    keys = [BENCH[0]] + [s[0] for s in SECTORS] + [n[0] for n in NAMES]
    raw = {}
    for k in keys:
        raw[k] = yfetch.fetch(k)
        if not raw[k]:
            raise SystemExit(f"[eu_rotation] fetch vide pour {k} — abandon.")
    dates, px = align(raw, keys)
    if len(dates) < L + M + 5:
        raise SystemExit("[eu_rotation] historique commun trop court.")
    asof = dates[-1]
    bench = px[BENCH[0]]

    rows, tails = [], {}
    for tk, lab, thesis in SECTORS:
        rel = px[tk] / bench
        r1, r2 = rs_series(rel)
        rs, mom = r1[-1], r2[-1]
        r1m = 100.0 * (px[tk][-1] / px[tk][-M] - 1)
        r3m = 100.0 * (px[tk][-1] / px[tk][-3 * M] - 1)
        relret3 = 100.0 * ((px[tk][-1] / px[tk][-3 * M]) / (bench[-1] / bench[-3 * M]) - 1)
        rows.append(dict(tk=tk, lab=lab, thesis=thesis, rs=float(rs), mom=float(mom),
                         quad=quadrant(rs, mom), r1m=r1m, r3m=r3m, relret3=relret3))
        idx = [i for i in ([len(dates) - 1 - 5 * i for i in range(TAILW)][::-1]) if i >= 0]
        tails[tk] = [(r1[i], r2[i]) for i in idx]

    sec_1m = np.array([r["r1m"] for r in rows if not np.isnan(r["r1m"])])
    disp = float(np.std(sec_1m))
    disp_hist = []
    for t in range(len(dates) - 252, len(dates)):
        if t - M < 0:
            continue
        rr = [100.0 * (px[s[0]][t] / px[s[0]][t - M] - 1) for s in SECTORS]
        disp_hist.append(float(np.std(rr)))
    disp_pct = 100.0 * sum(1 for d in disp_hist if d <= disp) / len(disp_hist) if disp_hist else float("nan")

    names = []
    for tk, lab, sec in NAMES:
        rel = px[tk] / bench
        r1, r2 = rs_series(rel)
        relret3 = 100.0 * ((px[tk][-1] / px[tk][-3 * M]) / (bench[-1] / bench[-3 * M]) - 1)
        names.append(dict(tk=tk, lab=lab, sec=sec, rs=float(r1[-1]), mom=float(r2[-1]),
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
    print(f"CADRAN ROTATION LIQUIDITÉ EU — STOXX Europe 600 par secteur  ·  as-of {asof}")
    print("=" * 82)
    print("RRG : X = force relative (z, 6m) · Y = momentum relatif (z, 1m). Quadrants →")
    print("  LEADING fort&↑ · WEAKENING fort&↓ · LAGGING faible&↓ · IMPROVING faible&↑(rotation-IN)")
    print(f"\nIntensité de rotation (dispersion perfs 1m) : {res['disp']:.1f} pts = "
          f"P{res['disp_pct']:.0f} sur 1 an  "
          f"({'ÉLEVÉE→rotation active' if res['disp_pct'] >= DISP_HOT else 'moyenne/faible'})")
    print(f"\n{'Secteur':<18}{'quadrant':<11}{'RS(z)':>7}{'Mom(z)':>8}{'1m%':>7}{'3m%':>7}{'rel3m%':>8}  thèse")
    print("-" * 82)
    for r in res["order"]:
        print(f"{r['lab']:<18}{r['quad']:<11}{r['rs']:>7.2f}{r['mom']:>8.2f}"
              f"{r['r1m']:>7.1f}{r['r3m']:>7.1f}{r['relret3']:>8.1f}  {'★' if r['thesis'] else ''}")
    print("\n--- FOCUS THÈSE quality-value / luxe / santé ---")
    msgmap = {"LAGGING": "faible & s'enfonce — thèse PAS encore validée par le tape",
              "IMPROVING": "⚡ faible mais MOMENTUM QUI TOURNE — 1ère brique rotation-IN",
              "LEADING": "fort & se renforce — rotation DÉJÀ en cours",
              "WEAKENING": "fort mais s'essouffle — rotation mature", "?": "données insuffisantes"}
    for r in [x for x in res["rows"] if x["thesis"]]:
        print(f"  {r['lab']:<18} [{r['quad']}] rel3m {r['relret3']:+.1f}% → {msgmap[r['quad']]}")
    print("\n--- Noms de la thèse (force relative vs STOXX 600, 3m) ---")
    for n in res["names"]:
        print(f"  {n['lab']:<18} RS(z) {n['rs']:+.2f}  Mom(z) {n['mom']:+.2f}  [{n['quad']}]  "
              f"rel3m {n['relret3']:+.1f}%")
    print("\n>> LECTURE : cadran DESCRIPTIF (où en est la rotation), PAS un trigger. Rotation-IN")
    print("   crédible = secteur thèse en IMPROVING + dispersion élevée + catalyseur (Chine/RCO).")
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
    ax.set_xlabel("Force relative RS-Ratio (z, 6m)  →  sur-performance vs STOXX 600")
    ax.set_ylabel("Momentum relatif RS-Mom (z, 1m)  →  amélioration")
    ax.set_title(f"RRG secteurs STOXX Europe 600 — as-of {asof}\n"
                 "★/violet = secteurs thèse (Food&Bev, Pers.&Household/luxe, Health Care) · queue = 6 sem.",
                 loc="left", fontweight="bold", fontsize=10)
    ax2 = fig.add_subplot(gs[0, 2])
    dh = res["disp_hist"]
    ax2.plot(range(len(dh)), dh, color="#00695c", lw=1.2)
    ax2.axhline(res["disp"], color="#d84315", lw=1.2, ls="--", label=f"actuel P{res['disp_pct']:.0f}")
    ax2.set_title("Dispersion perfs 1m\n(intensité de rotation, 1 an)", fontsize=9, fontweight="bold")
    ax2.set_ylabel("écart-type cross-sectionnel (pts)", fontsize=8)
    ax2.legend(fontsize=8); ax2.set_xticks([])
    fig.suptitle("MACRO/EQUITY — CADRAN ROTATION LIQUIDITÉ EU  ·  descriptif (pas un trigger) · proxy prix (flux/valo = phase 2)",
                 fontsize=11, fontweight="bold", y=1.0)
    fig.subplots_adjust(left=0.06, right=0.98, top=0.90, bottom=0.08)
    out = os.path.join(OUT, f"eu_rotation_{asof}.png")
    fig.savefig(out, dpi=115, bbox_inches="tight")
    # copie à nom stable pour le tableau de bord (toujours = dernier run)
    fig.savefig(os.path.join(OUT, "eu_rotation_latest.png"), dpi=115, bbox_inches="tight")
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
