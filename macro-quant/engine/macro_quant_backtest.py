#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
MACRO QUANT BACKTEST — validation walk-forward CAUSALE du modèle de base rates
================================================================================
Objet : répondre à "ce modèle a-t-il un pouvoir prédictif hors-échantillon, et
        peut-on faire confiance aux probas du jour ?"

Le moteur v1 (macro_quant_engine.py) calcule les analogues sur TOUT l'échantillon
(métrique full-sample) : OK pour un affichage, INTERDIT pour un backtest.
Ici tout est strictement causal + purgé :

  Pour chaque jour de décision t :
    - la métrique de whitening (PCA) est ré-estimée sur les données <= t
      (rafraîchie tous les 63 j pour la vitesse) -> pas de leak de covariance.
    - les analogues sont pris UNIQUEMENT dans le passé (j < t) ET leur fenêtre
      forward est entièrement révolue (PURGE : global(j) + h <= global(t)),
      donc leur label était connu à t. Aucun chevauchement avec le futur de t.
    - la prédiction (base rate / mean_cond) sort de ces analogues passés.
    - le label réalisé R_{t,h} (jours t..t+h) est le futur qu'on cherche à noter.

Métriques OOS (le "a-t-il de la valeur ?") :
    (A) Information Coefficient : corr(pred_mean, realized)  [Pearson + Spearman]
    (B) Monotonicité par quintiles de pred_mean : Q5_realized - Q1_realized
    (C) Calibration de P(neg) : réalisé vs prédit par déciles + Brier skill
    (D) Stratégie causale (seuil = médiane glissante des prédictions) :
        rendement, Sharpe, hit-rate, vs baseline buy&hold — jours NON chevauchants
    (E) Découpage PAR ANNÉE (IC, hit, strat) = "perfs sur les années précédentes"
    Significativité : block bootstrap (bloc = h) sur IC et sur le PnL strat.

Enfin : "PROBAS DU JOUR" recalculées avec CETTE machinerie causale (pool = tout
le passé, purge h), chaque proba annotée de la fiabilité OOS de l'asset.

Dépendances : numpy uniquement. Réutilise le pipeline data de l'engine.
================================================================================
"""
import urllib.request, csv, os, sys, math, json
import numpy as np
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import yfetch  # MOVE (vol taux) via Yahoo ^MOVE — pas dispo sur FRED

CACHE = "/tmp/fredcache"; os.makedirs(CACHE, exist_ok=True)
np.random.seed(42)

# ------------------------------------------------------------------ #
# Univers (features de conditionnement + assets-reponse a valider)
# ------------------------------------------------------------------ #
COND_SERIES = ["DGS10","DFII10","T10YIE","VIXCLS","T10Y2Y","DTWEXBGS","DCOILBRENTEU","DCOILWTICO"]
RESP_BT     = ["NASDAQCOM","DTWEXBGS","VIXCLS","MOVE","BTCUSD","GOLD","CAC40","DAX","STOXX50","DGS10","DGS2","DCOILBRENTEU","DEXUSEU","DEXJPUS","T10Y2Y"]
YAHOO = {"MOVE":"^MOVE", "BTCUSD":"BTC-USD", "GOLD":"GC=F", "CAC40":"^FCHI", "DAX":"^GDAXI", "STOXX50":"^STOXX50E"}   # ids non-FRED -> fetch Yahoo via yfetch
KIND = {  # nature de chaque serie
    "DGS10":"yield","DGS2":"yield","DFII10":"yield","T10YIE":"yield","T10Y2Y":"yield",
    "VIXCLS":"vol","MOVE":"vol","BTCUSD":"price","GOLD":"price","DTWEXBGS":"price","DEXUSEU":"price","DEXJPUS":"price","DCOILBRENTEU":"price","DCOILWTICO":"price",
    "NASDAQCOM":"price","CAC40":"price","DAX":"price","STOXX50":"price",
}
NAME = {
    "DGS10":"UST 10Y","DGS2":"UST 2Y","DFII10":"UST 10Y reel","T10YIE":"Breakeven 10Y",
    "T10Y2Y":"Pente 2s10s","VIXCLS":"VIX","MOVE":"MOVE (vol taux)","BTCUSD":"Bitcoin","GOLD":"Or (GC)","DTWEXBGS":"USD broad","DEXUSEU":"EUR/USD","DEXJPUS":"USD/JPY",
    "DCOILBRENTEU":"Brent","DCOILWTICO":"WTI","NASDAQCOM":"Nasdaq Comp.","CAC40":"CAC 40","DAX":"DAX","STOXX50":"Euro Stoxx 50",
}
# (E) CIBLES VOL RÉALISÉE : pseudo-assets kind="rvol" -> vol réalisée annualisée forward
#     du prix de base. Test du 2nd moment sur des assets non-actions (oil/BTC/or) + S&P (contrôle).
RVOL = {"RV_OIL":"DCOILBRENTEU", "RV_BTC":"BTCUSD", "RV_GOLD":"GOLD", "RV_SPX":"SP500"}
RVCHG = {"RVC_OIL":"DCOILBRENTEU", "RVC_BTC":"BTCUSD", "RVC_GOLD":"GOLD", "RVC_SPX":"SP500"}
NAME.update({"RV_OIL":"Vol réal. Oil","RV_BTC":"Vol réal. BTC","RV_GOLD":"Vol réal. Or","RV_SPX":"Vol réal. S&P",
             "RVC_OIL":"ΔVol Oil","RVC_BTC":"ΔVol BTC","RVC_GOLD":"ΔVol Or","RVC_SPX":"ΔVol S&P","SP500":"S&P 500"})
# (E) TESTÉ 2026-07-24 -> NÉGATIF : rvol (NIVEAU) IC OOS 0,22-0,53 mais = pure PERSISTANCE
#     (clustering GARCH) ; rvchg (Δ vol = expansion, le vrai test) IC ≈ 0 partout -> le régime
#     ne prédit PAS le changement de vol. Pas de 2ᵉ étoile. Désactivé ; TEST_RVOL=True pour re-tester.
TEST_RVOL = False
if TEST_RVOL:
    for rid in RVOL:  RESP_BT.append(rid); KIND[rid]="rvol"
    for rid in RVCHG: RESP_BT.append(rid); KIND[rid]="rvchg"
    if "SP500" not in RESP_BT: RESP_BT.append("SP500"); KIND["SP500"]="price"
ALL = sorted((set(COND_SERIES) | set(RESP_BT)) - set(RVOL) - set(RVCHG))   # pseudo-assets, pas de fetch

def fetch(sid):
    fp = os.path.join(CACHE, sid + ".csv")
    if not os.path.exists(fp) or os.path.getsize(fp) < 50:
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd=1900-01-01"
        with open(fp,"wb") as f: f.write(urllib.request.urlopen(url,timeout=30).read())
    d={}
    with open(fp) as f:
        r=csv.reader(f); next(r,None)
        for row in r:
            if len(row)<2: continue
            dt,v=row[0],row[1]
            if v in (".","","NA"): continue
            try: d[dt]=float(v)
            except: pass
    return d

print("[1] Download FRED (+ Yahoo MOVE) ...", file=sys.stderr)
raw={sid:(yfetch.fetch(YAHOO[sid]) if sid in YAHOO else fetch(sid)) for sid in ALL}
cal=sorted(raw["DGS10"].keys()); N=len(cal)
year=np.array([int(d[:4]) for d in cal])
print(f"    master cal {cal[0]}..{cal[-1]} N={N}", file=sys.stderr)

FFILL=3
def align(sd):
    out=np.full(N,np.nan); last=np.nan; gap=0
    for i,d in enumerate(cal):
        if d in sd: out[i]=sd[d]; last=sd[d]; gap=0
        elif not math.isnan(last) and gap<FFILL: out[i]=last; gap+=1
        else: out[i]=np.nan
    return out
LV={sid:align(raw[sid]) for sid in ALL}

# ------------------------------------------------------------------ #
# Features de regime (expanding-z causal, warmup 252)  -- identiques a l'engine
# ------------------------------------------------------------------ #
K_IMP=5; W0=252
def dbps(x,k):
    r=np.full(N,np.nan); r[k:]=(x[k:]-x[:-k])*100.0; return r
def expanding_z(x):
    out=np.full(N,np.nan); cnt=0; s=0.0; s2=0.0
    for i in range(N):
        xi=x[i]
        if math.isfinite(xi):
            cnt+=1; s+=xi; s2+=xi*xi
            if cnt>=W0:
                mu=s/cnt; var=max(s2/cnt-mu*mu,1e-12); out[i]=(xi-mu)/math.sqrt(var)
    return out

usd5=np.full(N,np.nan); usd5[K_IMP:]=np.log(LV["DTWEXBGS"][K_IMP:]/LV["DTWEXBGS"][:-K_IMP])*100
bmom=np.full(N,np.nan); bmom[20:]=np.log(LV["DCOILBRENTEU"][20:]/LV["DCOILBRENTEU"][:-20])*100
# (D) jambe croissance = momentum 20j cuivre/or (HG=F/GC=F) — meme construction que le moteur
_cop=align(yfetch.fetch("HG=F"))
_cg=np.where((LV["GOLD"]>0)&np.isfinite(_cop), _cop/LV["GOLD"], np.nan)
gmom=np.full(N,np.nan)
for i in range(20,N):
    a,b=_cg[i],_cg[i-20]
    if math.isfinite(a) and math.isfinite(b) and a>0 and b>0: gmom[i]=math.log(a/b)*100
# (Japon) carry yen testé 2026-07-27 -> REJETÉ (dilue VIX 0,19->0,16, best_train->BTC).
raw_feat={
    "d10_5":dbps(LV["DGS10"],K_IMP),"dreal_5":dbps(LV["DFII10"],K_IMP),
    "dbe_5":dbps(LV["T10YIE"],K_IMP),"vix_lvl":LV["VIXCLS"],
    "slope":LV["T10Y2Y"],"dusd_5":usd5,
    "brwti":LV["DCOILBRENTEU"]-LV["DCOILWTICO"],"brent_mom":bmom,"growth":gmom,
}
# NB : move_lvl testé 2026-07-23 -> REJETE (pas d'edge MOVE robuste).
# (D) growth (cuivre/or) ajouté 2026-07-24 -> re-valide que le VIX tient avec la jambe croissance.
FEATNAMES=["d10_5","dreal_5","dbe_5","vix_lvl","slope","dusd_5","brwti","brent_mom","growth"]
WINSOR=2.5   # (A) winsorizing ±2.5σ (identique au moteur) -> re-valide que le VIX tient sous cap
Zf={fn:np.clip(expanding_z(raw_feat[fn]),-WINSOR,WINSOR) for fn in FEATNAMES}
Z=np.column_stack([Zf[fn] for fn in FEATNAMES])
valid=np.all(np.isfinite(Z),axis=1); vidx=np.where(valid)[0]
Zv=Z[vidx]; nvalid=len(vidx); P=len(FEATNAMES)
gidx=vidx.copy()               # global index de chaque jour valide
vyear=year[vidx]
print(f"[2] Feature matrix p={P}, valid={nvalid} ({cal[vidx[0]]}..{cal[vidx[-1]]})", file=sys.stderr)

# ------------------------------------------------------------------ #
# Forward returns (labels) precalcules par asset/horizon
# ------------------------------------------------------------------ #
HORIZONS=[5,10,20]
def fwd(sid,t,h):
    k=KIND[sid];
    if t+h>=N: return np.nan
    if k in ("rvol","rvchg"):          # (E) vol réalisée (niveau) ou son Δlog forward/trailing
        base = RVOL[sid] if k=="rvol" else RVCHG[sid]
        def _rv(i0,i1):
            p=LV[base][i0:i1+1]; p=p[np.isfinite(p)]
            if len(p)<max(3,h//2) or np.any(p<=0): return np.nan
            r=np.diff(np.log(p))
            return float(np.std(r)*math.sqrt(252)*100.0) if len(r)>=2 else np.nan
        if k=="rvol": return _rv(t, t+h)
        rf, rb = _rv(t, t+h), _rv(t-h, t)   # forward vs trailing (causal)
        return math.log(rf/rb)*100.0 if (t-h>=0 and rf and rb and rf>0 and rb>0) else np.nan
    a,b=LV[sid][t],LV[sid][t+h]
    if not(math.isfinite(a) and math.isfinite(b)): return np.nan
    if k=="price":
        return math.log(b/a)*100.0 if (a>0 and b>0) else np.nan
    if k=="vol":
        return b-a                     # points VIX
    return (b-a)*100.0                 # bps
FR={sid:{h:np.array([fwd(sid,t,h) for t in range(N)]) for h in HORIZONS} for sid in RESP_BT}

# ------------------------------------------------------------------ #
# Metrique de whitening CAUSALE (rafraichie tous les REFRESH jours valides)
# ------------------------------------------------------------------ #
REFRESH=63
def build_metric(upto_pos):
    """PCA-whitening estimee sur Zv[:upto_pos+1] (donnees <= jour de decision)."""
    sub=Zv[:upto_pos+1]
    mu=sub.mean(axis=0); sd=sub.std(axis=0)+1e-12
    Zs=(sub-mu)/sd
    C=np.corrcoef(Zs,rowvar=False)
    ev,V=np.linalg.eigh(C); ev=np.clip(ev,1e-6,None)
    Pall=((Zv-mu)/sd)@V           # projette TOUTES les lignes valides
    return Pall,ev

EMBARGO=5
KFLOOR=60
def analogs(it,h,Pall,ev):
    """k plus proches voisins PASSES et PURGES pour le jour valide it, horizon h."""
    gi=gidx[it]
    gj=gidx[:it]
    cond=(gj+h<=gi)&((gi-gj)>EMBARGO)         # purge : label de l'analogue revolu
    elig=np.where(cond)[0]
    if len(elig)<KFLOOR: return None
    diff=Pall[elig]-Pall[it]
    D=np.sqrt(np.sum(diff*diff/ev,axis=1))
    k=max(KFLOOR,int(0.05*len(elig)))
    sel=elig[np.argsort(D)[:k]]
    return gidx[sel]                           # global indices des analogues

# ------------------------------------------------------------------ #
# WALK-FORWARD
# ------------------------------------------------------------------ #
START=next(i for i in range(nvalid) if vyear[i]>=2012 and i>=500)
print(f"[3] Walk-forward de {cal[gidx[START]]} a {cal[gidx[-1]]}  "
      f"({nvalid-START} jours de decision)", file=sys.stderr)

# accumulateurs par (sid,h)
rec={sid:{h:{"date":[],"year":[],"pred_mean":[],"pred_pneg":[],"real":[],"n":[]}
          for h in HORIZONS} for sid in RESP_BT}

Pall,ev=build_metric(START); last_ref=START
for it in range(START,nvalid):
    if it-last_ref>=REFRESH:
        Pall,ev=build_metric(it); last_ref=it
    for h in HORIZONS:
        ag=analogs(it,h,Pall,ev)
        if ag is None: continue
        for sid in RESP_BT:
            fa=FR[sid][h][ag]; fa=fa[np.isfinite(fa)]
            if len(fa)<KFLOOR*0.5: continue
            real=FR[sid][h][gidx[it]]
            if not math.isfinite(real): continue
            r=rec[sid][h]
            r["date"].append(cal[gidx[it]]); r["year"].append(int(vyear[it]))
            r["pred_mean"].append(float(np.mean(fa))); r["pred_pneg"].append(float(np.mean(fa<0)))
            r["real"].append(float(real)); r["n"].append(len(fa))

# ------------------------------------------------------------------ #
# METRIQUES
# ------------------------------------------------------------------ #
def rankdata(a):
    a=np.asarray(a,float); order=a.argsort(); ranks=np.empty(len(a),float)
    ranks[order]=np.arange(1,len(a)+1)
    # moyenne des rangs pour ex-aequo
    _,inv,cnt=np.unique(a,return_inverse=True,return_counts=True)
    csum=np.cumsum(cnt); start=csum-cnt
    avg=(start+csum+1)/2.0
    return avg[inv]
def pearson(x,y):
    x=np.asarray(x,float); y=np.asarray(y,float)
    if len(x)<10: return np.nan
    xd=x-x.mean(); yd=y-y.mean(); d=math.sqrt((xd@xd)*(yd@yd))
    return float(xd@yd/d) if d>0 else np.nan
def spearman(x,y): return pearson(rankdata(x),rankdata(y))

def block_boot_mean(v,L,B=2000):
    v=np.asarray(v,float); n=len(v)
    if n<10: return (np.nan,np.nan)
    p=1.0/max(L,1); out=np.empty(B)
    for b in range(B):
        s=[]; i=np.random.randint(n)
        while len(s)<n:
            s.append(v[i]); i=np.random.randint(n) if np.random.rand()<p else (i+1)%n
        out[b]=np.mean(s[:n])
    return (float(np.percentile(out,5)),float(np.percentile(out,95)))

def quintile_spread(pred,real):
    """Retourne (moyennes par quintile, Q5-Q1 MOYEN, Q5-Q1 MÉDIAN).
    L'écart moyen/médian = flag anti-artefact : s'ils divergent fort, l'edge est
    porté par les queues (normal pour le VIX ; suspect si data-snooping ailleurs)."""
    pred=np.asarray(pred); real=np.asarray(real)
    q=np.quantile(pred,[.2,.4,.6,.8])
    buck=np.digitize(pred,q)
    means=[float(real[buck==b].mean())   if np.any(buck==b) else np.nan for b in range(5)]
    meds =[float(np.median(real[buck==b])) if np.any(buck==b) else np.nan for b in range(5)]
    return means,(means[4]-means[0]),(meds[4]-meds[0])

def strat_causal(dates,pred,real,h):
    """position = signe(pred - mediane glissante des pred passees) ; jours NON chevauchants."""
    pred=np.asarray(pred); real=np.asarray(real)
    pos=np.zeros(len(pred))
    for i in range(len(pred)):
        thr=np.median(pred[:i]) if i>=20 else 0.0
        pos[i]=np.sign(pred[i]-thr)
    pnl=pos*real
    step=np.arange(0,len(pnl),h)          # sous-echantillon non chevauchant
    s=pnl[step]; bh=real[step]            # baseline = buy&hold memes jours
    ann=252.0/h
    def sharpe(a):
        a=a[np.isfinite(a)];
        return float(np.mean(a)/(np.std(a)+1e-12)*math.sqrt(ann)) if len(a)>2 else np.nan
    hit=float(np.mean(np.sign(s)>0)) if len(s) else np.nan
    return dict(n=int(len(s)),strat_mean=float(np.nanmean(s)),bh_mean=float(np.nanmean(bh)),
                strat_sharpe=sharpe(s),bh_sharpe=sharpe(bh),hit=hit,
                strat_ci=block_boot_mean(s,1))

report={"asof":cal[gidx[-1]],"test_start":cal[gidx[START]],"n_decision":int(nvalid-START),
        "horizons":HORIZONS,"assets":{}}
H0=10  # horizon headline
print("\n================ BACKTEST OOS (horizon 10j headline) ================")
print(f"{'asset':13} {'nOOS':>5} {'IC_p':>6} {'IC_s':>6} {'Q1r':>6} {'Q5r':>6} {'Q5-Q1':>6} "
      f"{'strat':>6} {'BH':>6} {'Shp_s':>6} {'Shp_bh':>6} {'Brier↑':>6}")
for sid in RESP_BT:
    a={"name":NAME[sid],"kind":KIND[sid],"h":{}}
    for h in HORIZONS:
        r=rec[sid][h]
        if len(r["real"])<50: continue
        pred=np.array(r["pred_mean"]); real=np.array(r["real"]); pneg=np.array(r["pred_pneg"])
        icp=pearson(pred,real); ics=spearman(pred,real)
        icci=block_boot_mean((pred-pred.mean())*(real-real.mean()),h)  # proxy signif IC via covariance
        qmeans,qs,qs_med=quintile_spread(pred,real)
        # calibration P(neg) : Brier skill vs baseline (freq inconditionnelle realisee)
        y=(real<0).astype(float); base=y.mean()
        brier=float(np.mean((pneg-y)**2)); brier_base=float(np.mean((base-y)**2))
        bss=1-brier/brier_base if brier_base>0 else np.nan
        st=strat_causal(r["date"],pred,real,h)
        # par annee
        yrs=np.array(r["year"]); peryear={}
        for yy in sorted(set(yrs.tolist())):
            m=yrs==yy
            if m.sum()<20: continue
            peryear[int(yy)]=dict(n=int(m.sum()),ic=pearson(pred[m],real[m]),
                                  qspread=quintile_spread(pred[m],real[m])[1])
        a["h"][h]=dict(n=len(real),ic_pearson=icp,ic_spearman=ics,ic_cov_ci=icci,
                       q_means=qmeans,q_spread=qs,q_spread_median=qs_med,brier=brier,brier_skill=bss,
                       strat=st,peryear=peryear)
        if h==H0:
            print(f"{NAME[sid][:13]:13} {len(real):>5} {icp:>6.3f} {ics:>6.3f} "
                  f"{qmeans[0]:>6.2f} {qmeans[4]:>6.2f} {qs:>6.2f} "
                  f"{st['strat_mean']:>6.3f} {st['bh_mean']:>6.3f} "
                  f"{st['strat_sharpe']:>6.2f} {st['bh_sharpe']:>6.2f} {bss:>6.2f}")
    report["assets"][sid]=a

# ------------------------------------------------------------------ #
# PROBAS DU JOUR (causal, pool = tout le passe)  + fiabilite OOS attachee
# ------------------------------------------------------------------ #
Pall,ev=build_metric(nvalid-1)
today={}
it=nvalid-1
for sid in RESP_BT:
    entry={}
    for h in HORIZONS:
        ag=analogs(it,h,Pall,ev)
        if ag is None: continue
        fa=FR[sid][h][ag]; fa=fa[np.isfinite(fa)]
        if len(fa)<KFLOOR*0.5: continue
        entry[h]=dict(n=len(fa),n_eff=round(len(fa)/h,1),
                      pred_mean=float(np.mean(fa)),pred_pneg=round(float(np.mean(fa<0))*100,1))
    today[sid]=entry
report["today"]=today; report["today_date"]=cal[gidx[-1]]

with open("/tmp/macro_quant_backtest.json","w") as f: json.dump(report,f,indent=2)
print("\n[4] JSON -> /tmp/macro_quant_backtest.json", file=sys.stderr)

print("\n================ PROBAS DU JOUR (causal) — horizon 10j ================")
print(f"as-of {report['today_date']}   (fiabilite = IC OOS de l'asset ci-dessus)")
print(f"{'asset':13} {'pred%neg':>9} {'predMean':>9} {'n_eff':>6} {'IC_OOS':>7}")
for sid in RESP_BT:
    if 10 in today.get(sid,{}) and 10 in report["assets"][sid]["h"]:
        t=today[sid][10]; ic=report["assets"][sid]["h"][10]["ic_pearson"]
        print(f"{NAME[sid][:13]:13} {t['pred_pneg']:>8.1f}% {t['pred_mean']:>9.3f} "
              f"{t['n_eff']:>6.1f} {ic:>7.3f}")

# ================================================================== #
#  ROBUSTESSE "FACON PAIRES" : Deflated Sharpe + PBO(CSCV) + HOLD-OUT
#  (le VIX survit-il au data-snooping ? le choisir = surapprentissage ?
#   tient-il sur un bloc JAMAIS vu ?)  -- meme rigueur que le dossier paires.
# ================================================================== #
ANN=252.0; EULER=0.5772156649015329
def _ncdf(x): return 0.5*(1.0+math.erf(x/math.sqrt(2.0)))
def _nppf(p):
    a=[-3.969683028665376e+01,2.209460984245205e+02,-2.759285104469687e+02,
       1.383577518672690e+02,-3.066479806614716e+01,2.506628277459239e+00]
    b=[-5.447609879822406e+01,1.615858368580409e+02,-1.556989798598866e+02,
       6.680131188771972e+01,-1.328068155288572e+01]
    c=[-7.784894002430293e-03,-3.223964580411365e-01,-2.400758277161838e+00,
       -2.549732539343734e+00,4.374664141464968e+00,2.938163982698783e+00]
    d=[7.784695709041462e-03,3.224671290700398e-01,2.445134137142996e+00,3.754408661907416e+00]
    plow,phigh=0.02425,1-0.02425
    if p<=0: return -np.inf
    if p>=1: return np.inf
    if p<plow:
        qq=math.sqrt(-2*math.log(p))
        return (((((c[0]*qq+c[1])*qq+c[2])*qq+c[3])*qq+c[4])*qq+c[5])/((((d[0]*qq+d[1])*qq+d[2])*qq+d[3])*qq+1)
    if p<=phigh:
        qq=p-0.5; r=qq*qq
        return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*qq/(((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    qq=math.sqrt(-2*math.log(1-p))
    return -(((((c[0]*qq+c[1])*qq+c[2])*qq+c[3])*qq+c[4])*qq+c[5])/((((d[0]*qq+d[1])*qq+d[2])*qq+d[3])*qq+1)
def _sr_moments(r):
    r=np.asarray(r,float); r=r[np.isfinite(r)]
    m,sd=np.mean(r),np.std(r)
    if sd<=0 or len(r)<3: return 0.0,0.0,3.0,len(r)
    z=(r-m)/sd
    return float(m/sd),float(np.mean(z**3)),float(np.mean(z**4)),len(r)
def _psr(sr,sr_star,skew,kurt,T):
    den=math.sqrt(max(1e-12,1.0-skew*sr+(kurt-1.0)/4.0*sr*sr))
    return _ncdf((sr-sr_star)*math.sqrt(max(1,T-1))/den)
def _emax_sr(V,Ntr):
    if Ntr<=1 or V<=0: return 0.0
    z1=_nppf(1.0-1.0/Ntr); z2=_nppf(1.0-1.0/(Ntr*math.e))
    return math.sqrt(V)*((1.0-EULER)*z1+EULER*z2)

def _strat_positions(pred):
    pred=np.asarray(pred); pos=np.zeros(len(pred))
    for i in range(len(pred)):
        thr=np.median(pred[:i]) if i>=20 else 0.0
        pos[i]=np.sign(pred[i]-thr)
    return pos
def _step_series(dates,pred,real,h):
    """serie strat sur jours NON chevauchants (per-periode, pour Sharpe honnete)."""
    pred=np.asarray(pred); real=np.asarray(real)
    pnl=_strat_positions(pred)*real
    step=np.arange(0,len(pnl),h)
    return pnl[step], np.asarray(dates)[step]

# --- (1) univers d'essais = 8 assets x 3 horizons = 24 configs (Sharpe per-periode) ---
trial_sr=[]; per10={}
for sid in RESP_BT:
    for h in HORIZONS:
        r=rec[sid][h]
        if len(r["real"])<50: continue
        s,_=_step_series(r["date"],r["pred_mean"],r["real"],h)
        sr,skew,kurt,T=_sr_moments(s)
        trial_sr.append(sr)
        if h==10: per10[sid]=dict(sr=sr,skew=skew,kurt=kurt,T=T,ann=math.sqrt(ANN/ (1.0)))
trial_sr=np.array([x for x in trial_sr if np.isfinite(x)])
V=float(np.var(trial_sr)) if len(trial_sr)>1 else 0.0

print("\n================ (1) DEFLATED SHARPE — le Sharpe survit-il a 24 essais ? ================")
print(f"  V(trial SR per-periode)={V:.5f}  sur {len(trial_sr)} configs (8 assets x 3 horizons)")
print(f"  {'asset':13} {'SR/periode':>10} {'Sharpe_ann':>10} {'DSR N=8':>8} {'DSR N=24':>9} {'DSR N=72':>9}")
Ntrials=[8,24,72]
dsr_report={}
for sid in RESP_BT:
    if sid not in per10: continue
    p=per10[sid]; ann=p["sr"]*math.sqrt(ANN/10.0)  # annualise (h=10)
    dsrs=[_psr(p["sr"],_emax_sr(V,Nt),p["skew"],p["kurt"],p["T"]) for Nt in Ntrials]
    dsr_report[sid]=dict(sr=p["sr"],ann=ann,dsr={Nt:d for Nt,d in zip(Ntrials,dsrs)})
    print(f"  {NAME[sid][:13]:13} {p['sr']:>10.4f} {ann:>10.2f} "
          f"{dsrs[0]:>8.3f} {dsrs[1]:>9.3f} {dsrs[2]:>9.3f}")
print("  -> DSR>0.95 = le Sharpe bat ce que le hasard produit sur N essais. <0.95 = data-snooping.")

# --- (2) PBO via CSCV : choisir "le meilleur asset" IS = surapprentissage ? ---
# matrice de pnl quotidien (pos*real) alignee sur les dates communes h=10.
H0=10
daily={}
for sid in RESP_BT:
    r=rec[sid][H0]
    if len(r["real"])<200: continue
    pnl=_strat_positions(r["pred_mean"])*np.asarray(r["real"],float)
    daily[sid]=dict(zip(r["date"],pnl))
common=set.intersection(*[set(d.keys()) for d in daily.values()])
common=sorted(common)
cols=[sid for sid in RESP_BT if sid in daily]
R=np.array([[daily[sid][dt] for sid in cols] for dt in common],float)
# normalise chaque colonne en z (scale-free : bps vs % vs pts) pour comparer les Sharpes
R=(R-R.mean(0))/ (R.std(0)+1e-12)
def _sharpe_cols(M):
    mu=M.mean(0); sd=M.std(0); out=np.full(M.shape[1],np.nan); ok=sd>0
    out[ok]=mu[ok]/sd[ok]; return out
def _cscv_pbo(M,S=16):
    T,Nn=M.shape; m=(T//S)*S; M=M[:m]
    blocks=np.array_split(np.arange(m),S); lam=[]
    from itertools import combinations as _cmb
    for comb in _cmb(range(S),S//2):
        iss=set(comb)
        ir=np.concatenate([blocks[i] for i in range(S) if i in iss])
        orr=np.concatenate([blocks[i] for i in range(S) if i not in iss])
        sis=_sharpe_cols(M[ir]); soos=_sharpe_cols(M[orr])
        if np.all(np.isnan(sis)): continue
        nstar=int(np.nanargmax(sis))
        ranks=np.argsort(np.argsort(np.nan_to_num(soos,nan=-1e9)))
        rank=int(ranks[nstar])+1; omega=min(max(rank/(Nn+1.0),1e-6),1-1e-6)
        lam.append(math.log(omega/(1-omega)))
    lam=np.array(lam); return float(np.mean(lam<=0.0)),lam
pbo,lam=_cscv_pbo(R,S=16)
best_is=cols[int(np.nanargmax(_sharpe_cols(R)))]
print("\n================ (2) PBO (CSCV, 16 blocs) — 'choisir le meilleur asset' surapprend-il ? ================")
print(f"  meilleur asset IS (Sharpe full) = {NAME[best_is]}   |  PBO = {pbo:.2%}")
print(f"  logit(lambda) median={np.median(lam):+.2f}  (PBO<0.5 = la selection tient OOS)")

# --- (3) VRAI HOLD-OUT : selection sur TRAIN, jugement sur TEST jamais vu ---
SPLIT=2019
print(f"\n================ (3) HOLD-OUT — TRAIN<{SPLIT}  vs  TEST>={SPLIT} (jamais vu) ================")
print(f"  {'asset':13} {'IC_train':>8} {'IC_test':>8} {'SR_test_ann':>11} {'verdict':>10}")
ho={}
for sid in RESP_BT:
    r=rec[sid][H0]
    yr=np.array(r["year"]); pred=np.array(r["pred_mean"]); real=np.array(r["real"]); dts=np.array(r["date"])
    mtr=yr<SPLIT; mte=yr>=SPLIT
    if mtr.sum()<100 or mte.sum()<100: continue
    ic_tr=pearson(pred[mtr],real[mtr]); ic_te=pearson(pred[mte],real[mte])
    s_te,_=_step_series(dts[mte],pred[mte],real[mte],H0)
    sr_te,_,_,_=_sr_moments(s_te); sr_te_ann=sr_te*math.sqrt(ANN/H0)
    ho[sid]=dict(ic_train=ic_tr,ic_test=ic_te,sr_test_ann=sr_te_ann)
best_train=max(ho,key=lambda s:ho[s]["ic_train"])
for sid in RESP_BT:
    if sid not in ho: continue
    v="<< pick IS" if sid==best_train else ""
    d=ho[sid]
    print(f"  {NAME[sid][:13]:13} {d['ic_train']:>8.3f} {d['ic_test']:>8.3f} {d['sr_test_ann']:>11.2f} {v:>10}")
print(f"  -> asset choisi sur le TRAIN (meilleur IC) = {NAME[best_train]} ; "
      f"son IC_test={ho[best_train]['ic_test']:+.3f}  SR_test={ho[best_train]['sr_test_ann']:+.2f}")

report["robustness"]=dict(trial_var=V,n_trials=len(trial_sr),dsr=dsr_report,
                          pbo=pbo,best_is=best_is,holdout_split=SPLIT,
                          holdout={s:ho[s] for s in ho},best_train=best_train)
with open("/tmp/macro_quant_backtest.json","w") as f: json.dump(report,f,indent=2,default=float)
print("\n[5] robustesse -> /tmp/macro_quant_backtest.json (cle 'robustness')", file=sys.stderr)

# ================================================================== #
#  C5 — VERS LA RENTABILITÉ : le signal VIX survit-il au CONTANGO + coûts
#  sur l'instrument TRADABLE (VIXY) ?  (make-or-break, retour Amundi)
#  Réutilise le signal causal rec["VIXCLS"] (pred_mean = ΔVIX prédit).
# ================================================================== #
H0=10
_vixy=align(yfetch.fetch("VIXY"))                 # ETF futures VIX court-terme (contango inclus)
_pos={d:i for i,d in enumerate(cal)}
r=rec["VIXCLS"][H0]
sig=np.array(r["pred_mean"],float); sdates=r["date"]
# rendement forward VIXY (log %) sur H0 j, aligné aux dates de décision
vret=np.full(len(sdates),np.nan); vixreal=np.array(r["real"],float)
for k,d in enumerate(sdates):
    i=_pos.get(d)
    if i is None or i+H0>=N: continue
    a,b=_vixy[i],_vixy[i+H0]
    if math.isfinite(a) and math.isfinite(b) and a>0 and b>0: vret[k]=math.log(b/a)*100.0
m=np.isfinite(sig)&np.isfinite(vret)
sig,vret,vixreal=sig[m],vret[m],vixreal[m]
yrs=np.array([int(sdates[k][:4]) for k in range(len(sdates)) if m[k]])

print("\n================ C5 — SIGNAL VIX sur VIXY (tradable, net de coûts) ================")
ic_spot=pearson(sig,vixreal); ic_vixy=pearson(sig,vret)
print(f"  IC signal↔ΔVIX spot  = {ic_spot:+.3f}   (ce qu'on avait)")
print(f"  IC signal↔rendement VIXY = {ic_vixy:+.3f}   (le vrai test : prédit-il l'instrument ?)")

# --- stratégies sur pas NON chevauchants (H0), seuil causal = médiane glissante ---
step=np.arange(0,len(sig),H0)
ss,rr,yy=sig[step],vret[step],yrs[step]
thr=np.array([np.median(ss[:i]) if i>=10 else 0.0 for i in range(len(ss))])
up=ss>thr                                        # régime "vol-up" prédit
def _sharpe(x):
    x=x[np.isfinite(x)]; ann=math.sqrt(252.0/H0)
    return float(np.mean(x)/(np.std(x)+1e-12)*ann) if len(x)>2 else float('nan')
def _cagr(x):                                    # rendement annualisé approx (somme log * périodes/an)
    x=x[np.isfinite(x)]; return float(np.sum(x)*(252.0/H0)/max(len(x),1))
def _mdd(x):                                     # max drawdown sur equity cumulée
    e=np.cumsum(x); peak=np.maximum.accumulate(e); return float(np.min(e-peak))
def _run(pos,cost_bp):
    pos=np.asarray(pos,float); chg=np.abs(np.diff(np.concatenate([[0],pos])))
    pnl=pos*rr - cost_bp*chg                     # coût par changement de position (bps aller)
    return pnl
STRATS={
 "B&H VIXY (long vol)": np.ones(len(rr)),
 "Short-vol (carry)":   -np.ones(len(rr)),
 "Signal long/flat":    up.astype(float),
 "Signal long/short":   np.where(up,1.0,-1.0),
 "Carry + filtre vol-up": np.where(up,0.0,-1.0),   # short le carry SAUF quand spike prédit -> flat
}
for CB in (0.05,0.15):                            # coûts aller : 5 bps (optimiste) / 15 bps (stress)
    print(f"\n  --- coûts {CB*100:.0f} bps/aller ---")
    print(f"  {'stratégie':22} {'Sharpe':>7} {'ret/an%':>8} {'maxDD':>7} {'Shp<19':>7} {'Shp>=19':>8}")
    srs=[]
    for nm,pos in STRATS.items():
        pnl=_run(pos,CB); sh=_sharpe(pnl); srs.append(_sr_moments(pnl)[0])
        tr=pnl[yy<2019]; te=pnl[yy>=2019]
        print(f"  {nm:22} {sh:>7.2f} {_cagr(pnl):>8.1f} {_mdd(pnl):>7.0f} {_sharpe(tr):>7.2f} {_sharpe(te):>8.2f}")
    # DSR sur la meilleure (au coût 15bps), N essais = 5 stratégies
    if CB==0.15:
        srs=[s for s in srs if np.isfinite(s)]; V=float(np.var(srs)) if len(srs)>1 else 0.0
        best=max(STRATS,key=lambda k:_sharpe(_run(STRATS[k],CB)))
        pb=_run(STRATS[best],CB); sr,sk,ku,T=_sr_moments(pb)
        dsr=_psr(sr,_emax_sr(V,5),sk,ku,T)
        print(f"  -> meilleure @15bps = «{best}» ; DSR (N=5 essais) = {dsr:.2f}  ({'ROBUSTE' if dsr>0.95 else 'PAS robuste'})")
print("\n  Rappel : B&H VIXY = la saignée du contango ; le signal a de la valeur s'il BAT le carry nu OOS.")

# ================================================================== #
#  PG — TEST DE QUEUE / CRISE : le winsor aveugle-t-il le modèle sur
#  les pires jours ? (IC moyen ≠ résistance de queue). VIX h=10.
# ================================================================== #
rv=rec["VIXCLS"][10]
pr=np.array(rv["pred_mean"],float); re=np.array(rv["real"],float); dt=np.array(rv["date"])
ok=np.isfinite(pr)&np.isfinite(re); pr,re,dt=pr[ok],re[ok],dt[ok]
thr=np.quantile(re,0.90)          # top 10% des hausses VIX réalisées = queue de crise
tail=re>=thr
cap=pr[tail].mean()/re[tail].mean()*100
print(f"\n============ PG TAIL/CRISE (VIX 10j, WINSOR={WINSOR}) ============")
print(f"  queue = top 10% spikes VIX (seuil +{thr:.1f}pt, n={int(tail.sum())})")
print(f"  réalisé moy queue = +{re[tail].mean():.1f}pt | PRÉDIT moy queue = +{pr[tail].mean():.1f}pt  -> CAPTURE {cap:.0f}%")
idx=np.argsort(re)[::-1][:8]
print("  8 pires spikes: "+", ".join(f"{dt[i][:7]} r{re[i]:.0f}/p{pr[i]:.0f}" for i in idx))

# ================================================================== #
#  MOVE — 2e ÉTOILE CANDIDATE : verdict IC OOS + film cross-day
#  ---------------------------------------------------------------
#  Le backtest ci-dessus a déjà noté MOVE (RESP_BT) en OOS : on résume
#  son IC 10j et son test de robustesse "façon VIX". Puis on lance
#  analyze_db pour ACCUMULER son lift forward réalisé run-après-run —
#  les deux ensemble tranchent l'accession de MOVE au filtre OOS.
#  (routine à jouer au rythme TRIMESTRIEL, cf command /macro-quant.)
# ================================================================== #
print("\n================ MOVE — CANDIDAT 2e ÉTOILE (trimestriel) ================")
if "MOVE" in report["assets"] and 10 in report["assets"]["MOVE"]["h"]:
    mh=report["assets"]["MOVE"]["h"][10]
    lo,hi=mh["ic_cov_ci"]
    sig="SIGNIFICATIF (IC OOS>0, CI90 exclut 0)" if (lo is not None and lo>0) else "PAS significatif (CI90 inclut 0)"
    print(f"  IC OOS 10j = {mh['ic_pearson']:.3f} (Spearman {mh['ic_spearman']:.3f}) ; "
          f"CI90 covariance [{lo:.3f}, {hi:.3f}] -> {sig}")
    print(f"  Q5-Q1 = {mh['q_spread']:.2f} (médian {mh['q_spread_median']:.2f}) ; Brier skill = {mh['brier_skill']:.2f}")
    print(f"  Seuil validation = IC OOS significatif ET robuste (façon VIX). Tant que non atteint : MOVE reste resp-only.")
else:
    print("  (MOVE pas assez d'OOS ce run — historique trop court.)")
try:
    import subprocess
    HERE=os.path.dirname(os.path.abspath(__file__))
    subprocess.run([sys.executable, os.path.join(HERE,"analyze_db.py")],
                   cwd=HERE, check=False)
    print("  [analyze_db] film cross-day (lift VIX vs MOVE) rafraîchi -> analysis/macro-quant/analyze_db_*.png")
except Exception as e:
    print(f"  [analyze_db] non lancé ({e}) — backtest OK quand même.")
