---
title: "Macro Quant Daily — 2026-07-24 (données as-of 2026-07-22)"
type: quant
statut: draft
tier: episodic
confidence: 60
created: 2026-07-24
updated: 2026-07-24
decay-date: 2026-07-31
hallucination-risk: low
validated-by: quant-backtest
topic: macro-quant-daily
cadence: daily
methode: "base rates conditionnels au régime (k-NN Mahalanobis, 2007-2026) + winsor ±2.5σ + oil frais futures + block bootstrap"
instruments: ["taux", "vol", "fx", "commodities", "indices", "credit", "crypto"]
tags: [type/quant, topic/quant, topic/macro, topic/daily, statut/draft]
source: "FRED+Yahoo via macro_quant_daily.py (run 2026-07-24, as-of 2026-07-22)"
sources: ["[[Wiki/macro/Macro-Quant-Methodo]]", "[[Macro/Quant/research/2026-07-23 - Backtest Robustesse (DSR PBO Holdout)]]"]
related: ["[[Macro/Daily/2026-07-24 - Macro Daily]]", "[[Macro/Quant/analysis/macro-quant/2026-07-23 - Macro Quant Daily]]"]
---

# 📊 Macro Quant Daily — Couche 2
**Run 2026-07-24 · régime as-of 2026-07-22** · 244 analogues (rayon Maha 1,77) · *winsor ±2,5σ + oil frais (futures)*

![](daily/2026-07-24.png)

> 🔴 **CAVEAT DOMINANCE (à lire en premier)** : `brent_mom` = **53% du matching** → le régime « multivarié » s'effondre aujourd'hui vers du **quasi-univarié sur le momentum pétrole**. Les 244 analogues ≈ « les jours où l'oil accélérait ». Lire tout le reste comme *conditionné à l'oil*. (Flag auto, seuil 40%.)

> 🟢 **REFLATION vs STAGFLATION — tranché par CALCUL (nouveau, jambe croissance)** : la jambe croissance (`growth` = momentum cuivre/or) = **+0,64σ → growth-ON**. Comme l'inflation est aussi ↑ (breakeven, oil), **inflation↑ + croissance↑ = REFLATION**, pas stagflation. Le cuivre surperforme l'or → optimisme de croissance, pas peur. → la lecture « reflation-oil » est **confirmée par la mesure**, l'axe qui la distingue de la stagflation étant désormais présent. (Une intuition « stagflation » resterait à valider par un `growth` qui passe **négatif** — ce n'est pas le cas aujourd'hui.)

> **Améliorations appliquées** (retour mentor) : **(A)** winsor ±2,5σ → **RENFORCE le VIX** (IC OOS 0,17→0,20). **(B)** oil frais futures → `brent_mom` +1,18→**+1,64σ** (stale le sous-estimait). **(D)** **jambe croissance** cuivre/or → distingue enfin reflation/stagflation ; **VIX survit** (IC OOS 0,19, hold-out test 0,19).

---

## 1. Régime du jour (z-scores winsorisés, causaux · 9 features)

| Feature | z | part matching | Lecture |
|---|---:|---:|---|
| `brent_mom` (Brent 20j) | **+1,64** | **53%** ⚠️ | momentum oil fort (frais) — **domine** |
| `d10_5` (Δ10Y nominal) | +0,79 | 12% | 10Y se tend nettement |
| **`growth` (cuivre/or 20j)** | **+0,64** | 8% | 🟢 **croissance ON → reflation** (nouveau) |
| `dbe_5` (Δbreakeven) | +0,62 | 8% | inflation anticipée bondit |
| `dreal_5` (Δ10Y réel) | +0,61 | 7% | taux réels se tendent |
| `slope` (2s10s) | −0,53 | 6% | courbe plate |
| `brwti` (Brent−WTI) | +0,37 | 3% | spread au-dessus de sa moyenne |
| `vix_lvl` | −0,36 | 3% | VIX sous sa moyenne — calme |
| `dusd_5` (USD 5j) | +0,21 | 1% | USD se raffermit un peu |

**Signature** = *momentum oil fort (frais) + taux qui se tendent + **croissance ON (cuivre/or +0,64)** + vol calme + courbe plate* → **REFLATION-oil** (inflation↑ **et** croissance↑, désormais mesuré sur les 2 jambes), **mais lue à 53% via l'oil**.

---

## 2. Base rates forward — horizon 10 jours

> `lift` = écart au baseline · unités % (prix), bps (taux), pts (VIX/MOVE). **fiab. OOS** = IC hold-out. ⚠️ tout est conditionné à l'oil aujourd'hui (dominance 53%).

| Asset | meanC | lift | %neg C | n_eff | tag | fiab. OOS |
|---|---:|---:|---:|---:|:--:|:--:|
| **VIX ★** | +0,61 pt | +0,59 | 48 | 24 | 🟡 | ✅ **IC +0,19** |
| UST 10Y | +3,04 bps | +3,10 | 42 | 24 | 🟡 | ≈0 — contexte |
| UST 30Y | +2,91 bps | +2,89 | 41 | 24 | 🟡 | ≈0 — contexte |
| UST 5Y | +2,47 bps | +2,58 | 43 | 24 | 🟡 | ≈0 — contexte |
| MOVE (vol taux) | +2,05 pt | +2,03 | 45 | 24 | 🟡 | ≈0 — réfuté 23/07 |
| Bitcoin | +3,41% | +1,71 | 42 | 24 | 🟡 | ≈0 — réfuté 23/07 |
| Pente 2s10s | +1,35 bps | +1,25 | 43 | 24 | 🟡 | ≈0 — contexte |
| Breakeven 10Y | +1,09 bps | +1,10 | 43 | 24 | 🟡 | ≈0 — contexte |
| Brent | +0,70% | +0,64 | 42 | 24 | 🟡 | ≈0 — contexte |
| WTI | +0,61% | +0,54 | 43 | 24 | 🟡 | ≈0 — contexte |
| Or (GC) | +0,82% | +0,43 | 38 | 24 | 🟡 | ≈0 — réfuté 24/07 |
| USD broad | +0,12% | +0,08 | 46 | 24 | 🟡 | ≈0 — contexte |
| S&P 500 | +0,16% | −0,34 | 40 | 22 | 🟡 | ≈0 — contexte |
| Nasdaq Comp. | +0,04% | −0,44 | 42 | 24 | 🟡 | ≈0 — contexte |
| HY OAS (credit) | +1,75 bps | +3,29 | 46 | **6** | 🔴 | ≈0 — bruit (n faible) |

---

## 3. Conclusion statistique — filtrée par le hold-out

**Le seul read forward défendable :**
- ⚠️ **VIX** : pred **+0,59 pt @10j**, %neg 48 (**coin-flip**). Biais vol-up **modeste**. Contexte live : oil élevé + repricing hawkish + VIX contenu → **ne pas être short vol**, dimensionner le risque.

**📏 Stabilité de l'edge VIX** — backtest walk-forward causal (9 features, winsorisé). La seule chose qu'on trade → robustesse multi-horizon :

| Horizon | IC OOS | t-stat | Q5−Q1 moy | Q5−Q1 méd | robuste ? |
|:---:|:---:|:---:|:---:|:---:|:---:|
| **5 j** | +0,17 | **+4,7** | +1,46 pt | +1,17 pt | ✅ 80% |
| **10 j** | +0,19 | +3,6 | +2,07 pt | +1,86 pt | ✅ 90% |
| **20 j** | +0,25 | +3,3 | +3,65 pt | +3,47 pt | ✅ 95% |

→ **IC positif 12/15 ans**, croissant avec l'horizon, t-stats **>2,7** (seuil Bonferroni) aux 3.
→ **Colonne médiane** (garde-fou anti-artefact) : Q5−Q1 **médian = 80-95% du moyen** → l'edge **n'est PAS porté par les queues**, même le jour *typique* de Q5 monte bien plus que Q1. Réparti, robuste. **Vrai edge de *timing de volatilité***. *(Flag : si méd ≪ moy → edge tail-dépendant, prudence. Ici ✅.)*

**Base rates de contexte (PAS de skill OOS — ne pas trader la direction) :**
- **Taux ↑↑** (10Y +3,10 bps, 30Y +2,89, 2s10s +1,25, breakeven +1,10) : le régime « oil-momentum + reflation » a historiquement été suivi de **yields up**. Cohérent avec le hawkish live — **mais conditionné à l'oil (dominance 53%) + IC OOS ≈ 0** → toile de fond, pas un pari.
- **Oil** (Brent/WTI ~+0,6%) : continue up contemporainement (en partie tautologique vu la dominance oil). Contexte.
- **Actions** (S&P −0,34 / NQ −0,44 lift) : léger biais baissier, lift ≈ 0 → muet.
- **BTC / MOVE / Or** : réfutés OOS → contexte pur.

**Traduction conviction** : un seul apport exploitable, le **biais vol-up modeste**. Tout le reste = contexte, **et aujourd'hui fortement biaisé oil** (à pondérer). C'est la Couche 1 qui pilote la direction.

---

## 4. Confrontation Couche 1 ↔ Couche 2

| Dimension | Couche 1 (daily live 24/07) | Couche 2 (quant as-of 22/07) | Verdict |
|---|---|---|---|
| **Oil** | Brent **~$92** (BZ=F 24/07, 5ᵉ séance ↑) [⚠️ le daily narratif disait « >$100 » — **erreur de Couche 1**, la donnée réelle = $91,78] | `brent_mom` +1,64σ (frais), base rate oil +0,6% | ✅ **convergent** (oil frais) |
| **Taux / hawkish** | hike Sept ~80%, US10 4,70% | taux se tendent fort, base rate yields ↑↑ | ✅ **convergent fort** |
| **Vol** | VIX contenu 18,7 | VIX calme (−0,36σ) mais forward **+0,59 pt** | ✅ convergent ; ⚠️ C2 penche *up* |
| **Actions** | semis blowout Intel, pas de crash | muet / léger biais baissier | ⚖️ C2 sans edge → priorité C1 |
| **Or** | défend $4 000 (refuge) | **or-up** contextuel (+0,43) — non validé | ✅ convergent en biais ; non tradable |

> **Convergence forte** sur oil + taux + vol + or. **Nuance** : la C2 est à **53% une lecture de l'oil** → sa "confirmation" du régime est en partie tautologique. **MAIS** la jambe croissance (cuivre/or +0,64, indépendante de l'oil) tranche le point clé : **c'est bien reflation, pas stagflation** — mesuré, pas assumé. Apport tradable = **biais vol-up modeste**.

---

## 5. À rerunner / suivi
- **⚠️ Dominance brent_mom 53%** : à surveiller run après run (flag auto). Si ça persiste, le régime est piloté par l'oil — base rates des autres assets à pondérer.
- **Surveiller `growth`** : tant qu'il reste **positif** = reflation ; s'il passe **négatif** avec inflation toujours haute = bascule **stagflation** (là le calcul rejoindrait le narratif du mentor). Aujourd'hui : +0,64 → reflation.
- **Cross-day (2ᵉ run)** : streak 2 j, distance à hier faible → on s'enfonce dans le régime oil/reflation.
- **A (winsor) + B (oil frais) + D (jambe croissance)** appliqués et validés (VIX survit, IC OOS 0,19). Prochaine (mentor) = **(E) cibles vol réalisée** (S&P/oil/BTC) pour chercher une 2ᵉ étoile sur le 2nd moment.
- Backtest OOS trimestriel — validés : **VIX only** ; MOVE + BTC + Or réfutés.
