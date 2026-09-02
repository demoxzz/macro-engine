#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
MACRO QUANT ENGINE — v1  (Couche 2 : base rates conditionnels au régime)
================================================================================
Objet : répondre à "ce régime pose-t-il souci aux indices/commos, et combien de
        fois ?" par des base rates HISTORIQUES conditionnels, avec n, lift vs
        baseline, intervalle de confiance robuste, et tag de confiance.

Philosophie (anti-fausse-précision) :
  - Un base rate sans n et sans comparaison au baseline ne veut rien dire.
  - Le chiffre utile n'est pas P(asset baisse) mais LIFT = P_cond - P_uncond.
  - Fenêtres forward chevauchantes => t-stat naïf FAUX => on utilise un
    stationary block bootstrap (Politis-Romano 1994) pour les IC.
  - Causalité stricte : features standardisées en EXPANDING (info <= t only),
    forward returns t -> t+h. Aucun leak du futur dans le conditionnement.

Source data : FRED (Federal Reserve Economic Data), séries quotidiennes.
Dépendances : numpy uniquement (+ stdlib).
--------------------------------------------------------------------------------
FORMULES (résumé ; détail complet dans Wiki/macro/Macro-Quant-Methodo.md)
--------------------------------------------------------------------------------
 (1) PRIX (equities, FX, commodities)  -> log-returns
        r_t          = ln(P_t / P_{t-1})
        R_{t,h}      = ln(P_{t+h} / P_t)                 (forward h-day)
 (2) TAUX / SPREADS (yields, OAS, fed funds) -> variations en points de base
        d_k(t)       = (y_t - y_{t-k}) * 100  [bps]
        dfwd_h(t)    = (y_{t+h} - y_t) * 100  [bps]      (forward)
 (3) VOL (VIX) -> niveau + rang percentile EXPANDING (mean-reverting)
 (4) Standardisation causale (expanding, warmup >= W0) :
        z_t          = (x_t - mu_{0:t}) / sigma_{0:t}
        mu, sigma calculés SUR [0..t] uniquement (pas de look-ahead)
 (5) Régime = vecteur des features standardisées au dernier jour : v*
 (6) Distance de Mahalanobis (via whitening PCA de la matrice de corrélation R
     des z-features ; R = V Λ V^T) :
        p_t   = V^T z_t             (projection sur composantes principales)
        D(t)  = sqrt( sum_j (p_{t,j} - p*_j)^2 / λ_j )   = Mahalanobis(z_t, v*)
     Analogues A = k plus proches voisins par D(t).
 (7) Base rate conditionnel (ex. proba de baisse) :
        P_cond = (1/|A|) * sum_{t in A} 1[ R_{t,h} < 0 ]
        LIFT   = P_cond - P_uncond
 (8) IC par stationary block bootstrap (longueur moyenne L = h) :
        rééchantillonne des BLOCS d'indices (préserve l'autocorrélation induite
        par le chevauchement) ; B répétitions -> percentiles 5/95 de la stat.
 (9) n_eff = |A| / h   (obs. indépendantes effectives, honnête vs |A| brut)
(10) Tag confiance : 🔴 n_eff<20 · 🟡 20-60 · 🟢 >60 ; "signal" seulement si
     l'IC bootstrap EXCLUT la valeur inconditionnelle.
================================================================================
"""

import urllib.request, csv, io, json, os, sys, math
import numpy as np
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import yfetch  # MOVE (vol taux) via Yahoo ^MOVE — pas dispo sur FRED

CACHE = "/tmp/fredcache"
os.makedirs(CACHE, exist_ok=True)
np.random.seed(42)

# ------------------------------------------------------------------ #
# 1. UNIVERS FRED
#    role: 'cond' = sert à définir le régime ; 'resp' = asset-réponse.
#    kind: 'price' (log-ret) | 'yield' (bps) | 'vol' (level+pct)
#    Un asset peut être 'both'.
# ------------------------------------------------------------------ #
SERIES = {
    # --- Taux ---
    "DFF":            dict(kind="yield", role="resp", name="Fed Funds eff."),
    "DGS2":           dict(kind="yield", role="both", name="UST 2Y"),
    "DGS5":           dict(kind="yield", role="resp", name="UST 5Y"),
    "DGS10":          dict(kind="yield", role="both", name="UST 10Y"),
    "DGS30":          dict(kind="yield", role="resp", name="UST 30Y"),
    "DFII10":         dict(kind="yield", role="both", name="UST 10Y reel (TIPS)"),
    "T10YIE":         dict(kind="yield", role="both", name="Breakeven 10Y"),
    "T10Y2Y":         dict(kind="yield", role="both", name="Pente 2s10s"),
    # --- Credit --- (NB: HY/IG OAS tronques a 2023 dans cet env FRED -> RESP only,
    #     exclus du conditionnement pour ne pas ecraser l'echantillon)
    "BAMLH0A0HYM2":   dict(kind="yield", role="resp", name="HY OAS (credit)"),
    "BAMLC0A0CM":     dict(kind="yield", role="resp", name="IG OAS (credit)"),
    # --- Vol ---
    "VIXCLS":         dict(kind="vol",   role="both", name="VIX"),
    "MOVE":           dict(kind="vol",   role="resp", name="MOVE (vol taux)"),  # Yahoo ^MOVE ; resp-only (IC OOS~0, cf backtest 23/07)
    # --- FX ---
    "DTWEXBGS":       dict(kind="price", role="both", name="USD broad"),
    "DEXJPUS":        dict(kind="price", role="both", name="USD/JPY"),
    "DEXUSEU":        dict(kind="price", role="resp", name="EUR/USD"),
    # --- Commodities ---
    "DCOILBRENTEU":   dict(kind="price", role="both", name="Brent"),
    "DCOILWTICO":     dict(kind="price", role="resp", name="WTI"),
    "DHHNGSP":        dict(kind="price", role="resp", name="NatGas Henry Hub"),
    "GOLD":           dict(kind="price", role="resp", name="Or (GC futures)"),  # Yahoo GC=F ; resp-only (comble le trou FRED)
    # --- Equities US ---
    "NASDAQCOM":      dict(kind="price", role="resp", name="Nasdaq Composite"),
    "SP500":          dict(kind="price", role="resp", name="S&P 500"),
    "DJIA":           dict(kind="price", role="resp", name="Dow Jones"),
    # --- Equities Europe --- (Yahoo ; resp-only : CONTEXTE pour PF clients FR/EU,
    #     le régime reste US-conditionné → direction attendue = bruit OOS)
    "CAC40":          dict(kind="price", role="resp", name="CAC 40"),
    "DAX":            dict(kind="price", role="resp", name="DAX"),
    "STOXX50":        dict(kind="price", role="resp", name="Euro Stoxx 50"),
    # --- Crypto --- (Yahoo BTC-USD ; resp-only : histoire courte ~2014 -> n_eff faible)
    "BTCUSD":         dict(kind="price", role="resp", name="Bitcoin"),
}

YAHOO = {"MOVE": "^MOVE", "BTCUSD": "BTC-USD", "GOLD": "GC=F",
         "CAC40": "^FCHI", "DAX": "^GDAXI", "STOXX50": "^STOXX50E"}   # ids non-FRED -> Yahoo via yfetch

def fetch(sid):
    if sid in YAHOO:
        return yfetch.fetch(YAHOO[sid])
    fp = os.path.join(CACHE, sid + ".csv")
    if not os.path.exists(fp) or os.path.getsize(fp) < 50:
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd=1900-01-01"
        data = urllib.request.urlopen(url, timeout=30).read()
        with open(fp, "wb") as f: f.write(data)
    d = {}
    with open(fp) as f:
        r = csv.reader(f); next(r, None)
        for row in r:
            if len(row) < 2: continue
            dt, v = row[0], row[1]
            if v in (".", "", "NA"): continue
            try: d[dt] = float(v)
            except: pass
    return d

# ------------------------------------------------------------------ #
# 2. TÉLÉCHARGEMENT + CALENDRIER MAÎTRE
# ------------------------------------------------------------------ #
print("[1] Download FRED ...", file=sys.stderr)
raw = {}
for sid in SERIES:
    try:
        raw[sid] = fetch(sid)
        print(f"    {sid:14} {len(raw[sid]):6} obs  {min(raw[sid])}..{max(raw[sid])}", file=sys.stderr)
    except Exception as e:
        print(f"    {sid:14} FAIL {e}", file=sys.stderr); raw[sid] = {}

# calendrier maître = jours ouvrés US proxied par DGS10 (marché obligataire)
cal = sorted(raw["DGS10"].keys())
idx = {d: i for i, d in enumerate(cal)}
N = len(cal)
print(f"[2] Master calendar (DGS10): {cal[0]}..{cal[-1]}  N={N}", file=sys.stderr)

# ------------------------------------------------------------------ #
# 3. ALIGNEMENT + NETTOYAGE
#    - reindex sur le calendrier maître
#    - forward-fill LIMITÉ à 3 jours ouvrés (comble les décalages de jours
#      fériés entre marchés : ex. bonds fermés / actions ouvertes). Au-delà
#      de 3 -> NaN (on ne fabrique pas de données).
# ------------------------------------------------------------------ #
FFILL_LIMIT = 3
def align(series_dict):
    out = np.full(N, np.nan)
    last, gap = np.nan, 0
    for i, d in enumerate(cal):
        if d in series_dict:
            out[i] = series_dict[d]; last = series_dict[d]; gap = 0
        else:
            if not math.isnan(last) and gap < FFILL_LIMIT:
                out[i] = last; gap += 1
            else:
                out[i] = np.nan
    return out

LV = {sid: align(raw[sid]) for sid in SERIES}   # levels alignés

# (B) OIL FRAIS : FRED Brent/WTI accusent ~2-9j de latence -> on prolonge à partir du
#     DERNIER JOUR FRED RÉEL (écrase le ffill périmé) avec les futures Yahoo (BZ=F/CL=F),
#     en return-chaining (préserve le niveau FRED, tail live). Corrige la latence ET
#     dé-périme `brent_mom` (la feature qui DOMINE le matching -> critique de la review).
_pos = {d: i for i, d in enumerate(cal)}
def _extend_oil_tail(fred_sid, yahoo_sym):
    out = LV[fred_sid].copy()
    fut = align(yfetch.fetch(yahoo_sym))
    real = [_pos[d] for d in raw[fred_sid] if d in _pos]
    if not real: return out
    last = max(real)                                   # dernier jour FRED RÉEL (pas ffill)
    if not (math.isfinite(fut[last]) and fut[last] > 0): return out
    n_ext = 0
    for i in range(last + 1, N):                        # écrase ffill + prolonge
        if math.isfinite(fut[i]): out[i] = out[last] * (fut[i] / fut[last]); n_ext += 1
    if n_ext: print(f"    [B] {yahoo_sym}: {n_ext}j frais (FRED réel ->{cal[last]}, +futures)", file=sys.stderr)
    return out
LV["DCOILBRENTEU"] = _extend_oil_tail("DCOILBRENTEU", "BZ=F")
LV["DCOILWTICO"]   = _extend_oil_tail("DCOILWTICO",   "CL=F")

# ------------------------------------------------------------------ #
# 4. TRANSFORMS + DÉTECTION OUTLIERS (flag, pas drop)
#    - price  : log-return quotidien
#    - yield  : diff 1j (bps) pour info ; les impulsions k-jours calculées plus bas
#    - vol    : niveau
#    Outliers : z robuste via MAD ; on FLAGue |z|>8 (jours 2008/2020 réels).
# ------------------------------------------------------------------ #
def logret(x):
    # log-return quotidien. On masque AVANT le log : sinon np.log(<=0 / NaN)
    # déclenche un RuntimeWarning ("invalid value in log") sur les trous de série
    # (0, NaN, forward-fill, extension oil). Résultat identique, sans le warning.
    r = np.full(N, np.nan)
    prev, cur = x[:-1], x[1:]
    ok = np.isfinite(prev) & np.isfinite(cur) & (prev > 0) & (cur > 0)
    r[1:][ok] = np.log(cur[ok] / prev[ok])
    return r

def dbps(x, k):
    r = np.full(N, np.nan)
    r[k:] = (x[k:] - x[:-k]) * 100.0
    return r

RET = {}   # rendement quotidien "natif" (log pour price, bps 1j pour yield)
for sid, m in SERIES.items():
    if m["kind"] == "price":
        RET[sid] = logret(LV[sid])
    elif m["kind"] == "yield":
        RET[sid] = dbps(LV[sid], 1)
    else:  # vol : on garde le niveau
        RET[sid] = LV[sid]

def flag_outliers(x, thr=8.0):
    v = x[np.isfinite(x)]
    if len(v) < 50: return 0
    med = np.median(v); mad = np.median(np.abs(v - med)) or 1e-9
    z = 0.6745 * (x - med) / mad
    return int(np.sum(np.abs(z) > thr))

nout = {sid: flag_outliers(RET[sid]) for sid in SERIES if SERIES[sid]["kind"] != "vol"}
print(f"[3] Outliers |robustZ|>8 (flag, non supprimés): "
      + ", ".join(f"{s}:{n}" for s, n in nout.items() if n), file=sys.stderr)

# ------------------------------------------------------------------ #
# 5. FEATURES DE RÉGIME (causales, expanding-z)
#    Chaque feature f, brute, PUIS standardisée en expanding.
# ------------------------------------------------------------------ #
K_IMP = 5          # horizon d'impulsion (jours ouvrés) pour Δ
W0    = 252        # warmup mini avant d'émettre un z (1 an)

def expanding_pct(x):
    """rang percentile de x_t dans [0..t] (causal). NaN-safe."""
    out = np.full(N, np.nan); buf = []
    for i in range(N):
        xi = x[i]
        if math.isfinite(xi):
            # rang parmi les valeurs passées (incluant t)
            buf.append(xi)
            arr = np.array(buf)
            out[i] = np.mean(arr <= xi)
        else:
            if buf: out[i] = np.nan
    return out

def expanding_z(x):
    """z causal : (x_t - mean_{0:t}) / std_{0:t}, warmup W0, NaN-safe."""
    out = np.full(N, np.nan)
    cnt = 0; s = 0.0; s2 = 0.0
    for i in range(N):
        xi = x[i]
        if math.isfinite(xi):
            cnt += 1; s += xi; s2 += xi * xi
            if cnt >= W0:
                mu = s / cnt
                var = max(s2 / cnt - mu * mu, 1e-12)
                out[i] = (xi - mu) / math.sqrt(var)
    return out

# features brutes
raw_feat = {
    "d10_5":   dbps(LV["DGS10"], K_IMP),                    # impulsion 10Y nominal
    "dreal_5": dbps(LV["DFII10"], K_IMP),                   # impulsion 10Y reel
    "dbe_5":   dbps(LV["T10YIE"], K_IMP),                   # impulsion breakeven
    "vix_lvl": LV["VIXCLS"],                                # niveau VIX
    "slope":   LV["T10Y2Y"],                                # pente 2s10s (niveau)
    "dusd_5":  None,                                        # placeholder (rempli ci-dessous)
    "brwti":   LV["DCOILBRENTEU"] - LV["DCOILWTICO"],       # spread Brent-WTI (dislocation oil)
    "brent_mom": None,                                      # momentum Brent 20j
}
# dusd_5 = variation 5j du broad USD en % (log*100)
usd_ret5 = np.full(N, np.nan); usd_ret5[K_IMP:] = np.log(LV["DTWEXBGS"][K_IMP:] / LV["DTWEXBGS"][:-K_IMP]) * 100
raw_feat["dusd_5"] = usd_ret5
brent_mom = np.full(N, np.nan); brent_mom[20:] = np.log(LV["DCOILBRENTEU"][20:] / LV["DCOILBRENTEU"][:-20]) * 100
raw_feat["brent_mom"] = brent_mom

# (D) JAMBE CROISSANCE : momentum 20j du ratio CUIVRE/OR (HG=F / GC=F).
#     C'est l'axe qui MANQUAIT -> distingue reflation (croissance↑) de stagflation (croissance↓),
#     qui partagent la jambe inflation (breakeven/oil). Signe + = growth-on, - = growth-scare.
#     Cuivre = demande industrielle ; or = peur ; le ratio nette le pur USD/liquidité.
_copper = align(yfetch.fetch("HG=F"))
_copgold = np.where((LV["GOLD"] > 0) & np.isfinite(_copper), _copper / LV["GOLD"], np.nan)
growth = np.full(N, np.nan)
for i in range(20, N):
    a, b = _copgold[i], _copgold[i - 20]
    if math.isfinite(a) and math.isfinite(b) and a > 0 and b > 0:
        growth[i] = math.log(a / b) * 100
raw_feat["growth"] = growth

# (Japon) carry yen (momentum USD/JPY) TESTÉ 2026-07-27 -> REJETÉ comme feature de conditionnement :
#     dilue le VIX (0,19->0,16), best_train bascule VIX->BTC (bruit), redondant avec dusd_5.
#     Raison de fond : le carry-unwind est un ÉVÉNEMENT de QUEUE (Août 2024) ; ce moteur, bâti sur
#     des base rates MOYENS, est aveugle aux queues par construction -> mauvais outil pour le Japon.
#     USD/JPY reste asset-RÉPONSE (DEXJPUS) pour le monitoring.

FEATNAMES = ["d10_5","dreal_5","dbe_5","vix_lvl","slope","dusd_5","brwti","brent_mom","growth"]
WINSOR = 2.5   # (A) winsorizing : cape les features à ±2.5σ -> un outlier de crise (2008/2020,
               #     ex. brent_mom -2,6σ) ne peut plus écraser la distance de Mahalanobis. NaN préservés.
# VIX -> on standardise le niveau ; les autres aussi via expanding_z
Zf = {}
for fn in FEATNAMES:
    Zf[fn] = np.clip(expanding_z(raw_feat[fn]), -WINSOR, WINSOR)

# matrice de features standardisées (lignes = jours, colonnes = features)
Z = np.column_stack([Zf[fn] for fn in FEATNAMES])
valid = np.all(np.isfinite(Z), axis=1)     # jours où TOUTES les features existent
vidx = np.where(valid)[0]
print(f"[4] Feature matrix: {len(FEATNAMES)} features, jours valides={len(vidx)} "
      f"({cal[vidx[0]]}..{cal[vidx[-1]]})", file=sys.stderr)

# ------------------------------------------------------------------ #
# 6. PCA / WHITENING (Mahalanobis) sur la matrice de corrélation
#    NOTE causalité : la métrique de distance utilise la covariance PLEINE
#    échantillon (léger look-ahead sur la MÉTRIQUE uniquement ; features &
#    labels restent causaux). v2 = covariance expanding.
# ------------------------------------------------------------------ #
Zv = Z[vidx]                                   # (n_valid, p)
# corrélation (features déjà ~standardisées mais expanding => on re-standardise full pour la métrique)
mu_full = Zv.mean(axis=0); sd_full = Zv.std(axis=0) + 1e-12
Zs = (Zv - mu_full) / sd_full
C = np.corrcoef(Zs, rowvar=False)
eval_, evec_ = np.linalg.eigh(C)               # C = V Λ V^T, eigh -> croissant
eval_ = np.clip(eval_, 1e-6, None)
P = Zs @ evec_                                 # projections PCA (n_valid, p)
# variance expliquée
varexp = eval_[::-1] / eval_.sum()
print(f"[5] PCA var expliquee (PC1..): "
      + ", ".join(f"{v*100:.0f}%" for v in varexp[:5]), file=sys.stderr)

def mahalanobis_to(target_row_in_vidx):
    """D(t) vers un jour cible (index dans vidx-space) en distance de Maha."""
    pt = P[target_row_in_vidx]
    diff = P - pt                              # (n_valid, p)
    D = np.sqrt(np.sum(diff * diff / eval_, axis=1))
    return D

# ------------------------------------------------------------------ #
# 7. RÉGIME DU JOUR + ANALOGUES
# ------------------------------------------------------------------ #
today_v = len(vidx) - 1                        # dernier jour valide (dans vidx-space)
today_global = vidx[today_v]
D = mahalanobis_to(today_v)
# exclut le voisinage immédiat (recouvrement direct) : |i-j| > 20
mask_far = np.abs(vidx - today_global) > 20
order = np.argsort(D)
K_ANALOG = max(120, int(0.05 * len(vidx)))     # >=120 ou 5% de l'echantillon
analog_local = [j for j in order if mask_far[j]][:K_ANALOG]
analog_global = vidx[analog_local]
radius = D[analog_local[-1]]
print(f"[6] Regime du jour = {cal[today_global]} ; analogues k={len(analog_global)} "
      f"(rayon Maha={radius:.2f})", file=sys.stderr)

# (A) FLAG DE DOMINANCE : quelle feature pèse le plus dans le matching du jour ?
#     part_i = z_i² / Σ z_j²  (proxy Euclidien de la contribution à la distance).
#     Flag si une feature > 40% -> le régime multivarié s'effondre vers ~univarié.
zt = np.array([Zf[fn][today_global] for fn in FEATNAMES])
_ss = float(np.sum(zt * zt)) or 1e-12
dom_shares = {fn: float(zt[i] * zt[i] / _ss) for i, fn in enumerate(FEATNAMES)}
dom_feat = max(dom_shares, key=dom_shares.get)
dom_pct = dom_shares[dom_feat]
dom_flag = bool(dom_pct > 0.40)
print(f"[6b] Dominance matching : {dom_feat} = {dom_pct*100:.0f}%"
      + ("  ⚠️ DOMINE (>40% -> matching quasi-univarié)" if dom_flag else "  (ok, réparti)"),
      file=sys.stderr)

# ------------------------------------------------------------------ #
# 8. FORWARD RETURNS + BASE RATES + LIFT + BOOTSTRAP IC
# ------------------------------------------------------------------ #
HORIZONS = [5, 10, 20]

def fwd_price(sid, t, h):
    p0, p1 = LV[sid][t], LV[sid][t + h] if t + h < N else np.nan
    if math.isfinite(p0) and math.isfinite(p1) and p0 > 0 and p1 > 0:
        return math.log(p1 / p0) * 100.0      # % log
    return np.nan

def fwd_yield(sid, t, h):
    y0, y1 = LV[sid][t], LV[sid][t + h] if t + h < N else np.nan
    if math.isfinite(y0) and math.isfinite(y1):
        return (y1 - y0) * 100.0              # bps
    return np.nan

def fwd_vol(sid, t, h):
    v0, v1 = LV[sid][t], LV[sid][t + h] if t + h < N else np.nan
    if math.isfinite(v0) and math.isfinite(v1):
        return v1 - v0                        # variation en POINTS de VIX
    return np.nan

def fwd(sid, t, h):
    k = SERIES[sid]["kind"]
    if k == "price": return fwd_price(sid, t, h)
    if k == "vol":   return fwd_vol(sid, t, h)
    return fwd_yield(sid, t, h)

def stationary_bootstrap_ci(vals, stat_fn, L, B=2000, lo=5, hi=95):
    """IC par stationary block bootstrap (Politis-Romano). L=longueur moy. bloc."""
    vals = np.asarray(vals); n = len(vals)
    if n < 5: return (np.nan, np.nan)
    p = 1.0 / max(L, 1)
    stats = np.empty(B)
    for b in range(B):
        out = []; i = np.random.randint(n)
        while len(out) < n:
            out.append(vals[i])
            if np.random.rand() < p: i = np.random.randint(n)
            else: i = (i + 1) % n
        stats[b] = stat_fn(np.asarray(out[:n]))
    return (np.percentile(stats, lo), np.percentile(stats, hi))

def tag(n_eff, ci, uncond):
    base = "🔴" if n_eff < 20 else ("🟡" if n_eff < 60 else "🟢")
    signal = (ci[0] > uncond) or (ci[1] < uncond)   # IC exclut le baseline
    return base, bool(signal)

# assets réponse = tous
RESP = list(SERIES.keys())
report = {"asof": cal[today_global], "n_analog": int(len(analog_global)),
          "maha_radius": float(radius), "k_impulse": K_IMP, "winsor": WINSOR,
          "pca_varexp": [float(x) for x in varexp[:5]],
          "regime_today": {fn: float(Zf[fn][today_global]) for fn in FEATNAMES},
          "feature_dominance": {"feature": dom_feat, "pct": dom_pct,
                                "flag": dom_flag, "shares": dom_shares},
          "assets": {}}

alldays = vidx[:-max(HORIZONS)]                # baseline : tous les jours valides
for sid in RESP:
    m = SERIES[sid]; entry = {"name": m["name"], "kind": m["kind"], "h": {}}
    for h in HORIZONS:
        cond = np.array([fwd(sid, t, h) for t in analog_global], dtype=float)
        cond = cond[np.isfinite(cond)]
        unc  = np.array([fwd(sid, t, h) for t in alldays], dtype=float)
        unc  = unc[np.isfinite(unc)]
        if len(cond) < 10 or len(unc) < 30:
            continue
        pneg_c = float(np.mean(cond < 0)); pneg_u = float(np.mean(unc < 0))
        mean_c = float(np.mean(cond));     mean_u = float(np.mean(unc))
        med_c  = float(np.median(cond))
        n_eff  = len(cond) / h
        ci_mean = stationary_bootstrap_ci(cond, np.mean, L=h)
        b, sig  = tag(n_eff, ci_mean, mean_u)
        entry["h"][h] = dict(
            n=len(cond), n_eff=round(n_eff, 1),
            mean_cond=round(mean_c, 3), mean_uncond=round(mean_u, 3),
            lift_mean=round(mean_c - mean_u, 3),
            median_cond=round(med_c, 3),
            pneg_cond=round(pneg_c * 100, 1), pneg_uncond=round(pneg_u * 100, 1),
            lift_pneg=round((pneg_c - pneg_u) * 100, 1),
            ci90_mean=[round(ci_mean[0], 3), round(ci_mean[1], 3)],
            tag=b, signal=sig)
    report["assets"][sid] = entry

outjson = "/tmp/macro_quant_report.json"
with open(outjson, "w") as f: json.dump(report, f, indent=2)
print(f"[7] OK -> {outjson}", file=sys.stderr)

# ------------------------------------------------------------------ #
# 9. RENDU CONSOLE (aperçu)
# ------------------------------------------------------------------ #
print("\n=== REGIME DU JOUR :", report["asof"], "(z-scores expanding) ===")
for fn in FEATNAMES:
    print(f"   {fn:10} z={report['regime_today'][fn]:+.2f}")
print(f"\nAnalogues n={report['n_analog']}  (Maha radius={report['maha_radius']:.2f})")
print("\n=== FORWARD 10j : lift vs baseline (asset trie par |lift_pneg|) ===")
rows = []
for sid, e in report["assets"].items():
    if 10 in e["h"]:
        hh = e["h"][10]; rows.append((abs(hh["lift_pneg"]), sid, e, hh))
rows.sort(reverse=True)
print(f"{'asset':22} {'meanC%':>7} {'meanU%':>7} {'lift':>6} {'%neg_C':>7} {'%neg_U':>7} {'liftNeg':>7} {'n_eff':>5} {'tag':>4} {'sig':>4}")
for _, sid, e, hh in rows:
    unit = "bps" if e["kind"] != "price" else "%"
    print(f"{e['name'][:22]:22} {hh['mean_cond']:>7.2f} {hh['mean_uncond']:>7.2f} "
          f"{hh['lift_mean']:>6.2f} {hh['pneg_cond']:>7.1f} {hh['pneg_uncond']:>7.1f} "
          f"{hh['lift_pneg']:>+7.1f} {hh['n_eff']:>5.0f} {hh['tag']:>4} {'YES' if hh['signal'] else '-':>4}")
