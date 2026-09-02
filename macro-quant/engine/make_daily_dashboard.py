#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dashboard visuel du run quant du jour : "ce que dit l'histoire pour aujourd'hui".
Lit un rapport moteur JSON (/tmp/macro_quant_report.json par défaut, ou db/runs/DATE.json)
et produit UNE figure datée -> Macro/Quant/analysis/macro-quant/daily/YYYY-MM-DD.png

Panneau A : RÉGIME DU JOUR — les 8 z-scores (où on est sur chaque dimension macro).
Panneau B : CE QUE L'HISTOIRE DIT ENSUITE (10j) — pour chaque asset, la variation
            de proba de baisse vs hasard (lift_pneg, en points de %), triée, colorée
            par confiance (n_eff). VIX = seul validé OOS -> étoilé.
Bandeau    : as-of, nb de jours analogues ("l'histoire ressemble à N jours").
Dépendances : numpy + matplotlib.
"""
import sys, os, json, math
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
OUT  = os.path.join(HERE, "..", "..", "analysis", "macro-quant", "daily")
os.makedirs(OUT, exist_ok=True)

FEAT_LABEL = {
    "d10_5":"Δ10Y nominal (5j)","dreal_5":"Δ10Y réel (5j)","dbe_5":"Δbreakeven (5j)",
    "vix_lvl":"VIX (niveau)","slope":"pente 2s10s","dusd_5":"USD (5j)",
    "brwti":"Brent−WTI","brent_mom":"Brent momentum (20j)",
    "growth":"Croissance (cuivre/or 20j)",
}
OOS_VALIDATED = {"VIXCLS"}   # seuls assets à IC OOS significatif (cf backtest 23/07)
HZ = "10"                    # horizon headline

rep_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/macro_quant_report.json"
R = json.load(open(rep_path))
asof   = R.get("asof","?")
nan    = R.get("n_analog","?")
radius = R.get("maha_radius", float("nan"))
run_date = R.get("_run_date", asof)
FLAB_SHORT = {"brent_mom":"brent_mom","d10_5":"Δ10Y","dreal_5":"Δ10Y réel","dbe_5":"Δbe",
              "vix_lvl":"VIX niv","slope":"pente","dusd_5":"USD","brwti":"Brent−WTI","growth":"croissance"}
dom = R.get("feature_dominance", {})   # (A) flag de dominance du matching

# ---------- données panneau A : z-scores régime ----------
reg = R.get("regime_today", {})
feats = [f for f in FEAT_LABEL if f in reg]
zvals = [reg[f] for f in feats]
order = np.argsort(zvals)
feats = [feats[i] for i in order]; zvals = [zvals[i] for i in order]

# ---------- données panneau B : base rates 10j (lift_pneg) ----------
# IC90 du jour = intervalle de confiance analytique sur la proba conditionnelle de baisse,
# avec n_eff obs indépendantes : demi-largeur = 1.645*sqrt(p(1-p)/n_eff) (approx normale), en pp.
def ci90_halfwidth(pneg_pct, n_eff):
    p = min(max((pneg_pct or 0.0) / 100.0, 1e-4), 1 - 1e-4)
    if not n_eff or n_eff <= 0: return np.nan
    return 1.645 * math.sqrt(p * (1 - p) / n_eff) * 100.0   # points de %

rows = []
for sid, a in R.get("assets", {}).items():
    m = a.get("h", {}).get(HZ)
    if not m: continue
    rows.append(dict(sid=sid, name=a.get("name", sid),
                     lift_pneg=m.get("lift_pneg", 0.0), n_eff=m.get("n_eff", 0.0),
                     pneg_cond=m.get("pneg_cond", 0.0),
                     ci=ci90_halfwidth(m.get("pneg_cond", 0.0), m.get("n_eff", 0.0)),
                     kind=a.get("kind")))
rows.sort(key=lambda r: r["lift_pneg"])
names  = [r["name"] + ("  ★" if r["sid"] in OOS_VALIDATED else "") for r in rows]
lifts  = [r["lift_pneg"] for r in rows]
cis    = [r["ci"] for r in rows]
# COULEUR = statut d'edge (PAS la précision) : ★ validé OOS vs contexte de régime
EDGE, CTX = "#1565c0", "#cfd8dc"
colors = [EDGE if r["sid"] in OOS_VALIDATED else CTX for r in rows]

# ---------- figure ----------
fig = plt.figure(figsize=(13, 10))
gs  = fig.add_gridspec(2, 1, height_ratios=[1.0, 1.7], hspace=0.32)

# Panneau A
axA = fig.add_subplot(gs[0])
zc = ["#c62828" if z < 0 else "#2e7d32" for z in zvals]
axA.barh([FEAT_LABEL[f] for f in feats], zvals, color=zc, edgecolor="black", lw=0.5)
for x in (-2,-1,1,2): axA.axvline(x, color="grey", ls=":", lw=0.8)
axA.axvline(0, color="black", lw=1)
axA.set_xlabel("z-score (écart à la moyenne historique, en σ)  —  ⟵ inhabituel bas   |   inhabituel haut ⟶")
axA.set_title("① RÉGIME DU JOUR — où l'on est sur chaque dimension macro", loc="left",
              fontweight="bold", fontsize=12)
for i,z in enumerate(zvals):
    axA.text(z + (0.05 if z>=0 else -0.05), i, f"{z:+.2f}", va="center",
             ha="left" if z>=0 else "right", fontsize=9)
axA.set_xlim(min(-2.6, min(zvals)-0.4), max(2.6, max(zvals)+0.4))

# Panneau B
axB = fig.add_subplot(gs[1])
yb = np.arange(len(names))
axB.barh(yb, lifts, color=colors, edgecolor="black", lw=0.5, zorder=2)
# barres d'erreur = IC90 du jour (précision), calculées sur la proba avec n_eff
axB.errorbar(lifts, yb, xerr=cis, fmt="none", ecolor="#37474f", elinewidth=1.1,
             capsize=3, alpha=0.8, zorder=3)
axB.set_yticks(yb); axB.set_yticklabels(names, fontsize=9)
axB.axvline(0, color="black", lw=1, zorder=1)
axB.set_xlabel("lift de P(baisse) vs hasard, en points de %   —   ⟵ MOINS susceptible de baisser   |   PLUS susceptible de baisser ⟶")
axB.set_title(f"② CE QUE L'HISTOIRE DIT ENSUITE ({HZ}j) — biais conditionnel au régime",
              loc="left", fontweight="bold", fontsize=12)
# annotation : lift + n_eff (taille d'échantillon du jour)
for i,(l,r) in enumerate(zip(lifts, rows)):
    ci = r["ci"] if np.isfinite(r["ci"]) else 0
    off = ci + 0.5
    axB.text(l + (off if l>=0 else -off), i,
             f"{l:+.1f} ±{ci:.0f}  (n≈{r['n_eff']:.0f})", va="center",
             ha="left" if l>=0 else "right", fontsize=7.5, color="#333")
# légende = STATUT D'EDGE (découplé de la précision)
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
axB.legend(handles=[Patch(color=EDGE, label="★ VIX — seul edge validé OOS (tradable)"),
                    Patch(color=CTX, label="contexte de régime (non validé)"),
                    Line2D([0],[0], color="#37474f", lw=1.1, label="│—│ IC90 du jour (précision, ∝ n_eff)")],
           loc="lower right", fontsize=8, title="couleur = edge  ·  barre d'erreur = précision")
axB.margins(y=0.01)

fig.suptitle(f"MACRO QUANT — lecture du {run_date}  ·  données as-of {asof}  ·  "
             f"l'histoire ressemble à {nan} jours analogues (rayon Maha {radius:.2f})",
             fontsize=13, fontweight="bold", y=0.985)
if dom:
    dfeat = FLAB_SHORT.get(dom.get("feature"), dom.get("feature","?"))
    dpct = dom.get("pct", 0) * 100
    if dom.get("flag"):
        fig.text(0.5, 0.955, f"⚠️ matching dominé par « {dfeat} » = {dpct:.0f}%  →  régime quasi-univarié, lire les analogues avec prudence",
                 ha="center", fontsize=9.5, color="#c62828", fontweight="bold")
    else:
        fig.text(0.5, 0.955, f"matching réparti (feature max « {dfeat} » = {dpct:.0f}%)",
                 ha="center", fontsize=9, color="#2e7d32")
fig.text(0.5, 0.008,
         "Couleur = statut d'EDGE (validé OOS sur ~3600 j de backtest) ≠ précision du jour (barre d'erreur IC90, ∝ n_eff).",
         ha="center", fontsize=8.5, color="#333")
fig.text(0.5, -0.004,
         "Une barre longue ou une petite barre d'erreur ne fait PAS un edge : seul le ★ est tradable ; le reste = contexte. Base rate ≠ prévision.",
         ha="center", fontsize=8, style="italic", color="#666")

out = os.path.join(OUT, f"{run_date}.png")
fig.savefig(out, dpi=115, bbox_inches="tight"); plt.close(fig)
print(f"OK -> {out}")
