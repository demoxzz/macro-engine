# Macro Engine — Couche 1 / Couche 2 + Cadrans de rotation

Extrait d'un système personnel de recherche macro et systématique, orienté **discipline out-of-sample** plutôt que sur-promesse. Trois briques indépendantes sont partagées ici.

> **Note.** Ce dépôt est un **export ciblé** d'un vault de recherche plus large. Il ne contient volontairement que les trois outils ci-dessous. Aucune donnée client, de portefeuille ou personnelle n'y figure (les notes quotidiennes partagées sont expurgées de toute section de suivi client).

---

## Vision à deux étages

La conviction ne se construit pas en une couche mais en deux, volontairement séparées :

- **Couche 1 — le OÙ** (`macro-daily/`) : où est le prix. Niveaux, position dans la value area (Auction Market Theory), calendrier de catalyseurs, chaîne de transmission cross-asset. **Pas de conclusion forward assertive** — c'est une mise en condition.
- **Couche 2 — les ODDS** (`macro-quant/`) : à quelle fréquence un régime historiquement comparable a été suivi de tel move. Base rates conditionnels au régime, chiffrés.

Le principe : la Couche 1 dit *où on est*, la Couche 2 dit *ce qui a suivi historiquement*. Là où elles convergent → conviction renforcée ; là où elles divergent → on isole pourquoi (souvent la latence des données) et on donne priorité au live.

---

## 1. macro-quant — base rates conditionnels au régime

`macro-quant/engine/` · analyses quotidiennes dans `macro-quant/analysis/`

**Méthode.**
1. Features causales (expanding z-score, aucun look-ahead) : croissance, vol, USD, taux réels, breakevens, pente, momentum oil, spread Brent-WTI.
2. Sélection d'analogues historiques par distance de **Mahalanobis** (k plus proches régimes).
3. **Base rates forward** {5, 10, 20 j} sur ~25 actifs (taux, crédit, vol, FX, indices, oil, or, BTC).
4. Le chiffre utile n'est jamais la probabilité conditionnelle brute mais le **LIFT** = P_cond − P_uncond (un base rate sans baseline ne veut rien dire).
5. Intervalle de confiance par **block-bootstrap**, taille d'échantillon effective **n_eff** (tag 🔴 <20 · 🟡 20-60 · 🟢 >60).

**Le point qui compte — le filtre out-of-sample.**
Une conclusion **directionnelle** n'est autorisée que pour un actif dont l'IC out-of-sample est significatif ET robuste (déflaté, hold-out). À ce jour, **un seul actif passe ce filtre : le VIX** — et uniquement en *rang* (percentile), pas en niveau, et jamais comme trigger d'entrée. Tout le reste (taux, indices, FX, oil…) est affiché en **contexte de régime uniquement**, marqué « direction non exploitable ». Les signaux réfutés en backtest (net de coûts) sont documentés comme réfutés, pas enterrés.

**Track-record live.** Un scorecard confronte chaque base rate VIX *prédit* au *réalisé*, run après run. Le signal reste « verrouillé en contexte » tant qu'il n'a pas accumulé assez de calls **indépendants** (fenêtres non chevauchantes) sur plusieurs régimes de vol — c'est une performance mesurée qui remplace un niveau de confiance figé.

## 2. cockpit-rotation — cadrans de rotation de liquidité

`cockpit-rotation/engine/` · figures et alertes dans `cockpit-rotation/analysis/`

Cartographie de la rotation sectorielle (S&P 500, STOXX 600) et pays (Asie-Pacifique) via des cadrans momentum/force relative, avec détection de franchissement (alertes de croisement). Trois moteurs : `us_rotation`, `eu_rotation`, `asia_rotation`.

## 3. macro-daily — la Couche 1 (exemple)

`macro-daily/` contient **une** note quotidienne à titre d'illustration du format Couche 1 (mise en condition, niveaux, calendrier, watchlist actionnable). La section de suivi client a été retirée.

---

## Philosophie

Zéro affirmation sans source datée. Zéro sur-promesse : un signal n'a le droit de devenir directionnel que s'il a survécu à un backtest OOS robuste — sinon il reste du contexte. Les hypothèses qui ne passent pas sont archivées comme réfutées. L'objectif n'est pas d'avoir raison souvent, mais de savoir *quand* le modèle a le droit de parler.

## Structure

```
macro-quant/
  engine/            moteur (features causales, analogues, base rates, backtest, scorecard)
  analysis/          runs quotidiens (notes + figures)
  SCHEMA.md          schéma de la base append-only (données non incluses)
  Cockpit Quant.md
cockpit-rotation/
  engine/            us / eu / asia rotation
  analysis/          cadrans + alertes
  Cockpit Rotation.md
macro-daily/
  2026-09-01 ... (exemple sanitisé)
```

*Stack : Python (numpy), sources FRED / Yahoo Finance. Notes au format Markdown (vault Obsidian).*
