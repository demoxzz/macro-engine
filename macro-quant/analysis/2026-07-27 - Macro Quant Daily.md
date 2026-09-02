---
title: "Macro Quant Daily — 2026-07-27 (données as-of 2026-07-22)"
type: quant
statut: draft
tier: episodic
confidence: 45
created: 2026-07-27
updated: 2026-07-27
decay-date: 2026-08-03
hallucination-risk: low
validated-by: quant-backtest
topic: macro-quant-daily
cadence: daily
methode: "base rates conditionnels au régime (k-NN Mahalanobis, 2007-2026) + winsor ±2.5σ + oil frais futures"
instruments: ["taux", "vol", "fx", "commodities", "indices", "credit", "crypto"]
tags: [type/quant, topic/quant, topic/macro, topic/daily, statut/draft]
source: "FRED+Yahoo via macro_quant_daily.py (run 2026-07-27, as-of 2026-07-22)"
sources: ["[[Wiki/macro/Macro-Quant-Methodo]]", "[[Macro/Quant/research/2026-07-23 - Backtest Robustesse (DSR PBO Holdout)]]"]
related: ["[[Macro/Daily/2026-07-27 - Macro Daily]]", "[[Macro/Quant/analysis/macro-quant/2026-07-24 - Macro Quant Daily]]"]
---

# 📊 Macro Quant Daily — Couche 2
**Run 2026-07-27 · régime as-of 2026-07-22** · 244 analogues (rayon Maha 1,91)

![](daily/2026-07-27.png)

> 🔴🔴 **PÉRIMÉ — À NE PAS TRADER AUJOURD'HUI (latence data + régime qui a basculé)** : FRED (taux/vol) est figé au **22/07**, donc le régime est **identique au run du 24/07** — inchangé depuis 5 jours. **MAIS la Couche 1 live (27/07) a basculé à l'INVERSE** : *désescalade Iran → Brent **−10,5%** (krach), yields/USD **baissent**, risk-on relief*. Or ce run affiche **oil melt-up (`brent_mom` +1,64σ, 53% du matching) + yields↑** — **l'exact contraire de la réalité live.** La feature dominante (oil) est **stale ET inversée**. → **ce run ne décrit PAS le marché d'aujourd'hui.** Sa seule valeur : archivage point-in-time. Priorité **totale** à la Couche 1.

---

## 1. Régime du jour (as-of 22/07 — inchangé vs 24/07)

| Feature | z | Lecture · statut live |
|---|---:|---|
| `brent_mom` (Brent 20j) | **+1,64** | ⚠️ **PÉRIMÉ/INVERSÉ** — oil a krashé −10,5% depuis (Couche 1) ; 53% du matching = régime faussé |
| `d10_5` / `dreal_5` / `dbe_5` | +0,79 / +0,61 / +0,62 | taux se tendaient au 22/07 — **mais yields baissent live** (risk-on) |
| `growth` (cuivre/or) | +0,64 | croissance ON as-of 22/07 |
| `brwti` · `dusd_5` | +0,37 · +0,21 | — |
| `vix_lvl` · `slope` | −0,36 · −0,53 | VIX calme, courbe plate |

**Signature as-of 22/07** = reflation-oil intensifiée. **Signature live 27/07** = risk-on relief / oil-crash. **Les deux sont opposées** → le régime quant est hors-sujet pour aujourd'hui.

---

## 2. Base rates 10j (identiques au 24/07 — pour mémoire, non exploitables aujourd'hui)

| Asset | lift | %neg | fiab. OOS |
|---|---:|---:|:--:|
| **VIX ★** | +0,59 pt | 48 | ✅ IC +0,19 — *mais as-of 22/07, contredit par le relief live* |
| UST 10Y / 30Y / 5Y | +3,1 / +2,9 / +2,6 bps | ~42 | ≈0 contexte (+ périmé : yields baissent live) |
| Brent / WTI | +0,6% / +0,5% | ~42 | ≈0 contexte (+ **inversé** : oil krashe live) |
| BTC / MOVE / Or | +1,7% / +2,0pt / +0,4% | — | réfutés OOS |
| S&P / Nasdaq | −0,3% / −0,4% | ~40 | ≈0 contexte |

*(Détail complet inchangé vs [[Macro/Quant/analysis/macro-quant/2026-07-24 - Macro Quant Daily|run du 24/07]].)*

---

## 3. Conclusion statistique
- **VIX (seul validé)** : biais vol-up modeste as-of 22/07 (+0,59 pt @10j, %neg 48 = coin-flip). **Mais** live = risk-on relief → VIX probablement en baisse → même ce read est **contredit par l'événement** (désescalade). Rappel : le signal VIX est **aveugle aux chocs** de toute façon (capture ~1% de la queue).
- Tout le reste : contexte, et aujourd'hui **doublement disqualifié** (non validé OOS + périmé).

---

## 4. Confrontation Couche 1 ↔ Couche 2 — DIVERGENCE TOTALE

| Dimension | Couche 1 (live 27/07) | Couche 2 (as-of 22/07) | Verdict |
|---|---|---|---|
| **Oil** | **Brent −10,5%** (krach, désescalade Iran) | `brent_mom` +1,64σ (melt-up) | ❌ **INVERSÉ** — quant aveugle au krach |
| **Taux** | yields **baissent** (risk-on) | taux se **tendent** (base rate ↑) | ❌ inversé |
| **Vol / risque** | risk-on relief, indices +1% | vol calme + léger biais up | ❌ contredit |
| **Régime global** | risk-on relief / trêve conditionnelle | reflation-oil intensifiée | ❌ **opposés** |

> **La divergence EST le diagnostic** : le régime a **basculé les 23-27/07** (désescalade + oil-crash) et le quant, figé au 22/07, ne le voit **pas encore**. C'est exactement le rôle de la Couche 1 (live) de mener sur les bascules ; la Couche 2 (fréquentielle) suivra quand FRED intègrera post-22/07. **Priorité totale à la Couche 1 aujourd'hui.**

---

## 5. À rerunner
- **Dès que FRED avance past 22/07** → `brent_mom` va **s'effondrer** (oil −10,5%), le régime basculera de reflation-oil vers risk-on/détente. C'est le run qui décrira enfin le marché réel.
- Semaine chargée (Couche 1) : **FOMC + PCE** → catalyseurs susceptibles de re-basculer le régime.
- Cross-day : 3ᵉ run archivé, mais les 3 partagent le même as-of 22/07 (distance 0,00σ) → pas encore de trajectoire réelle.
