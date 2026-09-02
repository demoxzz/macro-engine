---
title: Cockpit Quant — Couche 2 (base rates conditionnels au régime)
type: moc
statut: en-cours
tier: working
confidence: 70
created: 2026-07-23
updated: 2026-07-23
decay-date: 2027-07-23
hallucination-risk: low
validated-by: self
topic: cockpit
tags:
  - type/moc
  - topic/quant
  - topic/cockpit
  - statut/en-cours
source: ""
sources: []
related:
  - "[[Cockpit Macro]]"
  - "[[Cockpit PF]]"
  - "[[Wiki/macro/Macro-Quant-Methodo]]"
  - "[[2026-07-23 - Backtest Robustesse (DSR PBO Holdout)]]"
---

# 🧮 Cockpit Quant

> 🗺️ **État du projet & chantiers → [[Macro/Quant/research/00 - MOC Macro-Quant (etat & chantiers)]]** (doc vivante : validé/réfuté, backlog, retours externes). Ce cockpit = lecture du jour ; le MOC = pilotage du projet.

> **Couche 2** de la vision à deux étages. Là où le [[Cockpit Macro]] dit **OÙ** est le prix (niveaux/AMT, mise en condition), ce cockpit dit **À QUELLE FRÉQUENCE** un régime historiquement comparable a été suivi de tel move.
> Généré via `/macro-quant` (moteur + base append-only + dashboard). Ce cockpit ne fait qu'**agréger** ce qui existe.
> ⚖️ **Règle d'or** : le chiffre utile = **LIFT** (écart au hasard), jamais la proba brute. **Base rate ≠ prévision.**

---

## 🎯 Ce qui est réellement exploitable (filtre OOS)

> Seul un asset à **IC hors-échantillon significatif** autorise une conclusion directionnelle. Backtest : [[2026-07-23 - Backtest Robustesse (DSR PBO Holdout)]].

- ✅ **VIX** — IC hold-out **~0,19**, seul edge validé → *timing de vol **en moyenne***.
- 🚨 **PAS une protection anti-krach** : le signal capture **~1% de la queue** (mars 2020 : VIX +49 réel, prédit −2). Il est **aveugle aux spikes** → ne JAMAIS s'en servir pour se couvrir d'un krach. « Ça dépend de ton objectif » (PG).
- ❌ **Tout le reste** (actions, USD, FX, oil, taux, **MOVE réfuté**) — IC OOS ≈ 0 → **contexte de régime uniquement**, jamais un pari directionnel.
- ⚠️ Même le VIX : l'edge est dans le **signal (IC)**, pas dans une stratégie au seuil naïf (DSR 0,18). Et non tradable sur VIXY (contango, cf. C5).

---

## 🟢 Récap quant du jour (le plus récent)
```dataviewjs
const q = dv.pages('"Macro/Quant"')
  .where(p => p.type == "quant" && p.cadence == "daily")
  .sort(p => p.file.mtime, 'desc');
if (q.length) {
  dv.paragraph("**Dernier run : [[" + q[0].file.path + "|" + q[0].file.name + "]]**");
  dv.paragraph("![[" + q[0].file.path + "]]");
} else {
  dv.paragraph("*Aucun run pour l'instant — lance `/macro-quant`.*");
}
```

---

## 📈 Lecture cross-day (trajectoire du régime)
> « Depuis combien de jours dans ce régime ? entre-t-on / sort-on ? » — généré par `analyze_db.py` (parlant à partir de ~30-60 runs).
```dataviewjs
const imgs = app.vault.getFiles()
  .filter(f => f.path.includes("analysis/macro-quant/") && f.name.startsWith("analyze_db_"))
  .sort((a, b) => b.name.localeCompare(a.name));
if (imgs.length) {
  dv.paragraph("Dernière analyse (" + imgs[0].name.replace("analyze_db_", "").replace(".png", "") + ") :");
  dv.paragraph("![[" + imgs[0].path + "]]");
} else {
  dv.paragraph("*Pas encore d'analyse cross-day — `python3 Macro/Quant/engine/analyze_db.py`.*");
}
```

---

## 🔬 Validation & méthode (références stables)
| Ressource | Rôle |
|---|---|
| [[Wiki/macro/Macro-Quant-Methodo]] | les 10 formules, limites v1, roadmap |
| [[2026-07-23 - Backtest Robustesse (DSR PBO Holdout)]] | DSR + PBO + hold-out (VIX seul validé) |
| [[2026-07-14 - Backtest Validation]] | backtest walk-forward causal v1 |
| `Macro/Quant/db/SCHEMA.md` | schéma de la base append-only (vintage + outputs) |

---

## 🗂️ Historique des runs quant
```dataview
TABLE WITHOUT ID file.link AS "Run", title AS "Titre", confidence AS "Conf.", updated AS "MAJ"
FROM "Macro/Quant"
WHERE type = "quant" AND cadence = "daily"
SORT file.name DESC
```

---

## ⚙️ Lancer / maintenir
- **Run du jour** (moteur + base + dashboard) : `/macro-quant`
- **Lecture cross-day** : `python3 Macro/Quant/engine/analyze_db.py`
- **Rafraîchir la liste des assets validés OOS** (trimestriel) : `python3 Macro/Quant/engine/macro_quant_backtest.py`
- **Base** : `Macro/Quant/db/` (runs/ · vintage/ · regime_features.csv · base_rates.csv) — *append-only, ne pas éditer à la main*
- **Figures** : `Macro/Quant/analysis/macro-quant/` (dashboards quotidiens dans `daily/`)

> 💡 Fichiers non-`.md` (`.py`, `.csv`, `.json`) masqués par défaut dans Obsidian → Settings ▸ Files & Links ▸ *Detect all file extensions* pour les voir.
