# Macro Quant DB — schéma

Base append-only alimentée par `engine/macro_quant_daily.py` à chaque run `/macro-quant`.
**Ne jamais éditer/supprimer à la main.** Toute évolution du modèle → bump `SCHEMA_VERSION` dans le wrapper + ligne de changelog ci-dessous, pour rester interprétable sur des années.

## Fichiers
- `runs/YYYY-MM-DD.json` — snapshot complet du run (sortie moteur + méta : `_run_date`, `_schema_version`, `_persisted_at`).
- `vintage/YYYY-MM-DD/*.csv` — séries brutes FRED/Yahoo **point-in-time** téléchargées ce jour-là. Valeur = données AVANT révisions FRED ; irrécupérables autrement.
- `regime_features.csv` — 1 ligne/jour : run_date, asof, n_analog, maha_radius, k_impulse, schema_version + les features z-scorées.
- `base_rates.csv` — 1 ligne/jour/asset/horizon : lift, %neg, n_eff, IC90, tag, signal…

## Changelog des versions
- **v1** (2026-07) — 8 features `[d10_5, dreal_5, dbe_5, vix_lvl, slope, dusd_5, brwti, brent_mom]` ; univers moteur v1 ; MOVE resp-only.
- **v2** (2026-07-24) — post-review mentor :
  - **+feature `growth`** (9ᵉ) = momentum 20j cuivre/or (HG=F/GC=F) → jambe croissance, distingue reflation/stagflation.
  - **winsorizing ±2,5σ** des features avant Mahalanobis (renforce le VIX).
  - **oil frais** : Brent/WTI prolongés aux futures Yahoo (BZ=F/CL=F) depuis le dernier jour FRED réel.
  - `feature_dominance` (flag >40%) ajouté au JSON de run.
  - assets non-FRED : MOVE `^MOVE`, BTC `BTC-USD`, Or `GC=F` (tous resp-only, réfutés OOS).
  - ⚠️ les lignes v1 de `regime_features.csv` ont une cellule `growth` vide (normal).
