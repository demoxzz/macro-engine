---
title: "Macro Quant Daily — 2026-07-14 (données as-of 2026-07-09)"
type: quant
statut: draft
tier: episodic
confidence: 55
created: 2026-07-14
updated: 2026-07-14
decay-date: 2026-07-21
hallucination-risk: low
validated-by: quant-backtest
topic: macro-quant-daily
cadence: daily
methode: "base rates conditionnels au régime (k-NN Mahalanobis, 2007-2026) + block bootstrap"
instruments: ["taux", "vol", "fx", "commodities", "indices", "credit"]
tags: [type/quant, topic/quant, topic/macro, topic/daily, statut/draft]
source: "FRED via macro_quant_engine.py (run 2026-07-14)"
sources: ["[[Wiki/macro/Macro-Quant-Methodo]]", "[[Macro/Daily/2026-07-14 - Macro Daily]]"]
related: ["[[Macro/Flash/2026-07-14 1433 - Flash - CPI]]", "[[Wiki/macro/Cadres-de-Lecture]]"]
---

# 📊 Macro Quant Daily — Couche 2
**Run 2026-07-14 · régime as-of 2026-07-09** (dernière donnée FRED complète)

> **Ce que dit cette note** : dans quels régimes historiquement comparables à aujourd'hui se sont trouvés les marchés, et **combien de fois** un asset a monté/baissé ensuite — avec `n`, **lift vs hasard**, IC bootstrap, tag. **Base rate ≠ prévision.** Dimensionne la conviction ; ne remplace pas la Couche 1 (niveaux/AMT du daily). Méthodo & formules : [[Wiki/macro/Macro-Quant-Methodo]].

> ⚠️ **CAVEAT VINTAGE MAJEUR — à lire avant tout** : FRED Brent s'arrête au **06/07**, donc `brent_mom` = **−2,64σ** reflète le pétrole **AVANT le spike Hormuz du 14/07** ($87). C'est la feature qui **domine** le matching → les analogues sont pris sur des épisodes de **Brent en repli**, soit **l'INVERSE** de la réalité live. **Cette Couche 2 ne voit pas encore le choc oil du 14/07.** Le read forward ci-dessous vaut pour le régime **pré-spike** (taux réels ↑ + oil qui roule + vol calme). À rerunner dès que FRED intègre le spike.

---

## 1. Régime du jour (z-scores expanding, causaux)

| Feature | z | Lecture |
|---|---:|---|
| `brent_mom` (Brent 20j) | **−2,64** | ⚠️ **vintage 06/07** — pré-spike, domine le matching |
| `dreal_5` (Δ10Y réel) | +0,53 | taux réels se tendent modérément |
| `d10_5` (Δ10Y nominal) | +0,39 | 10Y en légère hausse |
| `dbe_5` (Δbreakeven) | −0,01 | inflation anticipée à plat |
| `brwti` (Brent−WTI) | −0,32 | spread sous sa moyenne (vintage 06/07) |
| `dusd_5` (USD 5j) | −0,43 | USD un peu mou |
| `slope` (2s10s) | −0,51 | courbe plus plate que la moyenne |
| `vix_lvl` | −0,47 | VIX sous sa moyenne — calme |

**Signature** = *taux réels qui se raffermissent + momentum pétrole qui roule + vol calme + courbe plate + USD mou*. Analogue = mini « growth-scare / fin de poussée risk-on ». **Échantillon** : 2007-01 → 2026-07, **243 analogues** (rayon Maha 2,22), PCA : PC1-5 = 24/23/16/13/9 %.

---

## 2. Base rates forward — horizon 10 jours

> `meanC` = rendement moyen conditionnel · `lift` = écart au baseline · `%neg` = fréquence de baisse · **SIG** = IC90 bootstrap exclut le baseline (**contemporain**) · unités : **% pour prix, bps pour taux, points pour VIX**.
> ⚠️ **« SIG ✅ » ici = flag contemporain, PAS une validation OOS.** Le backtest (§3) montre que seul le VIX tient hors-échantillon. Lire le §2 comme *description du régime*, le §3 comme *ce qui est réellement exploitable*.

| Asset | meanC | baseline | lift | %neg C | %neg base | IC90 | n_eff | tag | SIG |
|---|---:|---:|---:|---:|---:|---|---:|:--:|:--:|
| **USD broad** | +0,41% | +0,04 | **+0,36** | 33,7 | 49,4 | [+0,26 ; +0,55] | 24 | 🟡 | ✅ |
| **VIX** | +1,61 pt | +0,02 | **+1,59** | — | — | [+0,93 ; +2,38] | 24 | 🟡 | ✅ |
| **Nasdaq Comp.** | −0,63% | +0,48 | **−1,11** | 45,3 | 37,7 | [−1,28 ; +0,01] | 24 | 🟡 | ✅ |
| **EUR/USD** | −0,42% | −0,02 | **−0,40** | 59,3 | 50,4 | [−0,65 ; −0,20] | 24 | 🟡 | ✅ |
| **Breakeven 10Y** | −1,36 bps | −0,00 | −1,36 | 55,6 | 46,6 | [−2,28 ; −0,44] | 24 | 🟡 | ✅ |
| **Pente 2s10s** | −2,09 bps | +0,10 | −2,19 | 60,9 | 49,2 | [−2,87 ; −1,33] | 24 | 🟡 | ✅ |
| **UST 30Y** | −2,02 bps | +0,02 | −2,04 | 54,3 | 48,7 | [−3,93 ; −0,25] | 24 | 🟡 | ✅ |
| UST 10Y | −2,12 bps | −0,06 | −2,07 | 53,1 | 48,7 | [−4,19 ; +0,21] | 24 | 🟡 | — |
| UST 5Y | −1,72 bps | −0,11 | −1,62 | 55,6 | 49,5 | [−4,13 ; +0,73] | 24 | 🟡 | — |
| Brent | −0,69% | +0,09 | −0,78 | 44,4 | 45,9 | [−1,93 ; +0,36] | 24 | 🟡 | — |
| WTI | −0,67% | +0,10 | −0,77 | 46,9 | 45,6 | [−1,73 ; +0,23] | 24 | 🟡 | — |
| S&P 500 | −0,30% | +0,50 | −0,79 | 42,9 | 34,4 | [−0,78 ; +0,20] | **18** | 🔴 | ✅ |
| Dow Jones | −0,35% | +0,41 | −0,76 | 45,1 | 37,6 | [−0,80 ; +0,08] | **18** | 🔴 | ✅ |
| HY OAS | −3,69 bps | −1,62 | −2,08 | 56,4 | 57,2 | [−6,22 ; −1,06] | **6** | 🔴 | — |

---

## 3. Conclusion statistique — filtrée par le backtest OOS

> ⚠️ **CORRECTION POST-BACKTEST** : le backtest walk-forward causal ([[2026-07-14 - Backtest Validation]]) montre que **seul le VIX** a un pouvoir prédictif hors-échantillon (IC +0,170, t=+3,22). Les « signaux » contemporains sur USD/NQ/FX/taux affichés au §2 **ne survivent PAS OOS** (IC ≈ 0). On ne trade donc **que** ce qui est validé.

**Le seul read forward défendable (asset à IC OOS significatif) :**
- ✅ **VIX** : pred **+1,6 pt @10j** (IC OOS 0,170, stable 13/15 années) → ce régime est historiquement suivi d'une **remontée modeste de la volatilité**. Edge validé = *timing de vol*. À pondérer (long vol / dimensionnement du risque). ⚠️ le choc oil non capté (vintage) ne ferait que **renforcer** ce biais vol-up.

**Base rates de contexte (PAS de skill OOS — ne pas trader la direction) :**
- USD +0,41%, NQ −0,73%, EUR/USD −0,42%, 2s10s −2 bps : le régime « penche » ainsi *contemporainement*, mais le backtest prouve qu'aucune de ces directions ne persiste forward (NQ IC OOS **−0,036**, USD **≈0**). → **contexte seulement**, aucune conviction directionnelle.
- Brent/WTI : pas de signal + données vintage → double raison de ne rien conclure sur l'oil ici.

**Traduction conviction** : la Couche 2 n'apporte aujourd'hui **qu'une chose exploitable** : la vol tend à se retendre dans ce type de régime. Pour la direction actions/USD/oil, elle est **muette** (et honnête de l'être) — c'est la Couche 1 (niveaux/AMT live) qui pilote, pas des base rates non validés.

---

## 4. Confrontation Couche 1 ↔ Couche 2

| Dimension | Couche 1 (daily AMT/niveaux, live 14/07) | Couche 2 (quant, as-of 09/07) | Verdict |
|---|---|---|---|
| USD | softer CT post-CPI, rebond si Warsh hawkish | **bid statistique** (+0,36%, 🟡✅) | ⚖️ Couche 2 penche haussier USD |
| Indices | fade le pop dovish, range 27569-30948 | **biais baissier léger** (NQ −1,1%, 🟡✅) | ✅ **convergent** : prudence indices |
| Vol | VIX ~17,4 contenu, gardien non déclenché | **VIX se retend** (+1,6 pt, 🟡✅) | ⚠️ Couche 2 plus prudente |
| Taux | US10 4,62% > pivot, oil re-tend | Couche 2 dit taux **baissent** (vintage pré-oil) | ❌ **divergence = le caveat** |
| Oil | choc Hormuz, Brent $87, spreads alignés | **aucun signal** (données pré-spike) | ❌ Couche 2 aveugle au choc |

> **La divergence taux/oil EST le diagnostic** : elle isole exactement ce que le quant ne voit pas encore. Là où les deux couches **convergent** (prudence indices, bid USD), la conviction se **renforce**. Là où elles divergent (oil, taux), c'est la latence data — priorité à la Couche 1 live.

---

## 5. À rerunner
- **Dès que FRED met à jour Brent/WTI post-14/07** → `brent_mom` bascule positif, l'analogie change de régime. C'est le run qui donnera le base rate du **vrai** choc oil.
- Ticker manquant : or spot quotidien (trou connu).
- Commande cible : `/macro-quant` (à créer une fois v1 validé).
