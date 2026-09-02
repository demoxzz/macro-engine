#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
MACRO QUANT DAILY — wrapper de PERSISTANCE (la "base sacrée")
================================================================================
Objet : chaque run du moteur alimente une base append-only, datée et versionnée,
        pour accumuler sur des ANNÉES une trace point-in-time exploitable.

Ce que ça capture (et qu'on ne peut PAS reconstruire plus tard) :
  1. VINTAGE brute : les séries FRED/Yahoo TELLES QUE téléchargées ce jour-là
     (FRED révise -> impossible de retrouver la donnée as-of a posteriori).
  2. LECTURE du modèle : régime (z-scores), analogues, base rates {5,10,20 j}.

Pipeline :
  - force une vintage fraîche 1x/jour calendaire (vide le cache -> re-download),
    puis réutilise si on relance le même jour.
  - lance macro_quant_engine.py -> /tmp/macro_quant_report.json
  - persiste dans Macro/Quant/db/ :
        runs/YYYY-MM-DD.json         snapshot complet du run (+ meta)
        vintage/YYYY-MM-DD/*.csv     séries brutes point-in-time
        regime_features.csv          1 ligne/jour (z-scores + analogues)
        base_rates.csv               1 ligne/jour/asset/horizon
        SCHEMA.md                    version du schéma (cohérence pluriannuelle)

Idempotent : re-run le même jour -> MAJ (pas de doublon de lignes).
Dépendances : stdlib only. Ne fait AUCUN calcul de marché — il persiste, c'est tout.
================================================================================
"""
import os, sys, json, csv, glob, shutil, subprocess
from datetime import date, datetime

SCHEMA_VERSION = 2   # v2 (2026-07-24) : +feature `growth` (cuivre/or) + winsor ±2.5σ + oil frais futures
HERE   = os.path.dirname(os.path.abspath(__file__))
DB     = os.path.abspath(os.path.join(HERE, "..", "..", "db"))
ENGINE = os.path.join(HERE, "macro_quant_engine.py")
REPORT = "/tmp/macro_quant_report.json"
FREDCACHE = "/tmp/fredcache"
YFCACHE   = "/tmp/yfcache"

FEATNAMES = ["d10_5","dreal_5","dbe_5","vix_lvl","slope","dusd_5","brwti","brent_mom","growth"]
BR_FIELDS = ["run_date","asof","sid","name","kind","h","n","n_eff","mean_cond",
             "mean_uncond","lift_mean","median_cond","pneg_cond","pneg_uncond",
             "lift_pneg","ci90_lo","ci90_hi","tag","signal","schema_version"]
RF_FIELDS = ["run_date","asof","n_analog","maha_radius","k_impulse","schema_version"] + FEATNAMES


def ensure_dirs():
    for d in ("runs", "vintage"):
        os.makedirs(os.path.join(DB, d), exist_ok=True)


def write_schema():
    p = os.path.join(DB, "SCHEMA.md")
    if os.path.exists(p):
        return
    with open(p, "w") as f:
        f.write(
"# Macro Quant DB — schéma (version {ver})\n\n"
"Base append-only alimentée par `engine/macro_quant_daily.py` à chaque run.\n"
"**Ne jamais éditer/supprimer à la main.** Toute évolution du modèle → bump `SCHEMA_VERSION`\n"
"dans le wrapper + note ci-dessous, pour rester interprétable sur des années.\n\n"
"## Fichiers\n"
"- `runs/YYYY-MM-DD.json` — snapshot complet du run (sortie moteur + méta : run_date, schema_version).\n"
"- `vintage/YYYY-MM-DD/*.csv` — séries brutes FRED/Yahoo **point-in-time** téléchargées ce jour-là.\n"
"  Valeur = données AVANT révisions FRED ; irrécupérables autrement.\n"
"- `regime_features.csv` — 1 ligne/jour : {rf}.\n"
"- `base_rates.csv` — 1 ligne/jour/asset/horizon : {br}.\n\n"
"## Journal des versions\n"
"- v1 (2026-07): 8 features {feats} ; assets = univers moteur v1 ; MOVE présent en resp-only (IC OOS~0).\n"
            .format(ver=SCHEMA_VERSION, rf=", ".join(RF_FIELDS),
                    br=", ".join(BR_FIELDS), feats=FEATNAMES))


def run_date_str():
    return date.today().isoformat()


def need_fresh_vintage(rundate):
    """vintage fraîche seulement si pas déjà capturée aujourd'hui."""
    return not os.path.isdir(os.path.join(DB, "vintage", rundate))


def clear_caches():
    for c in (FREDCACHE, YFCACHE):
        if os.path.isdir(c):
            shutil.rmtree(c, ignore_errors=True)


def run_engine():
    print("[daily] run moteur ...", file=sys.stderr)
    r = subprocess.run([sys.executable, ENGINE], cwd=HERE,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if r.returncode != 0:
        sys.stderr.write(r.stderr.decode(errors="replace"))
        raise SystemExit("[daily] moteur en échec — rien persisté.")


def snapshot_vintage(rundate):
    dst = os.path.join(DB, "vintage", rundate)
    os.makedirs(dst, exist_ok=True)
    n = 0
    for c in (FREDCACHE, YFCACHE):
        for fp in glob.glob(os.path.join(c, "*.csv")):
            shutil.copy2(fp, os.path.join(dst, os.path.basename(fp)))
            n += 1
    print(f"[daily] vintage: {n} séries brutes -> {dst}", file=sys.stderr)


def dedup_append(path, fields, rows, key):
    """append idempotent : retire les lignes existantes ayant la même clé, puis append."""
    existing = []
    if os.path.exists(path):
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                if tuple(row.get(k, "") for k in key) not in {tuple(str(r[k]) for k in key) for r in rows}:
                    existing.append(row)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in existing:
            w.writerow({k: row.get(k, "") for k in fields})
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})


def persist(rep, rundate):
    asof = rep.get("asof", "")
    # 1) snapshot complet du run
    rep_out = dict(rep, _run_date=rundate, _schema_version=SCHEMA_VERSION,
                   _persisted_at=datetime.now().isoformat(timespec="seconds"))
    with open(os.path.join(DB, "runs", f"{rundate}.json"), "w") as f:
        json.dump(rep_out, f, indent=2)
    # 2) regime_features.csv
    rf = dict(run_date=rundate, asof=asof, n_analog=rep.get("n_analog"),
              maha_radius=round(rep.get("maha_radius", float("nan")), 4),
              k_impulse=rep.get("k_impulse"), schema_version=SCHEMA_VERSION)
    for fn in FEATNAMES:
        rf[fn] = round(rep.get("regime_today", {}).get(fn, float("nan")), 4)
    dedup_append(os.path.join(DB, "regime_features.csv"), RF_FIELDS, [rf], key=("run_date",))
    # 3) base_rates.csv (1 ligne/asset/horizon)
    rows = []
    for sid, a in rep.get("assets", {}).items():
        for h, m in a.get("h", {}).items():
            ci = m.get("ci90_mean", [None, None])
            rows.append(dict(run_date=rundate, asof=asof, sid=sid, name=a.get("name"),
                             kind=a.get("kind"), h=h, n=m.get("n"), n_eff=m.get("n_eff"),
                             mean_cond=m.get("mean_cond"), mean_uncond=m.get("mean_uncond"),
                             lift_mean=m.get("lift_mean"), median_cond=m.get("median_cond"),
                             pneg_cond=m.get("pneg_cond"), pneg_uncond=m.get("pneg_uncond"),
                             lift_pneg=m.get("lift_pneg"),
                             ci90_lo=ci[0], ci90_hi=ci[1], tag=m.get("tag"),
                             signal=m.get("signal"), schema_version=SCHEMA_VERSION))
    dedup_append(os.path.join(DB, "base_rates.csv"), BR_FIELDS, rows, key=("run_date","sid","h"))
    print(f"[daily] persisté : run {rundate} (as-of {asof}), {len(rows)} lignes base_rates.", file=sys.stderr)


def main():
    ensure_dirs(); write_schema()
    rundate = run_date_str()
    if need_fresh_vintage(rundate):
        clear_caches()   # force une vintage fraîche 1x/jour
    run_engine()
    if not os.path.exists(REPORT):
        raise SystemExit("[daily] pas de JSON moteur — abandon.")
    rep = json.load(open(REPORT))
    snapshot_vintage(rundate)
    persist(rep, rundate)
    # dashboard visuel du jour (best-effort : ne bloque pas la persistance)
    try:
        run_json = os.path.join(DB, "runs", f"{rundate}.json")
        subprocess.run([sys.executable, os.path.join(HERE, "make_daily_dashboard.py"), run_json],
                       cwd=HERE, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=True)
        print(f"[daily] dashboard -> analysis/macro-quant/daily/{rundate}.png", file=sys.stderr)
    except Exception as e:
        print(f"[daily] dashboard non généré ({e}) — persistance OK quand même.", file=sys.stderr)
    # lecture cross-day (analyse de la base append-only) : best-effort, après persistance
    # -> se rafraîchit à CHAQUE run pour ne jamais retarder derrière la base.
    try:
        subprocess.run([sys.executable, os.path.join(HERE, "analyze_db.py")],
                       cwd=HERE, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=True)
        print(f"[daily] cross-day -> analysis/macro-quant/analyze_db_{rundate}.png", file=sys.stderr)
    except Exception as e:
        print(f"[daily] cross-day non généré ({e}) — persistance OK quand même.", file=sys.stderr)
    # scorecard live : track-record prédit vs RÉALISÉ du signal VIX (best-effort).
    # -> se remplit à chaque run à mesure que les fenêtres forward arrivent à maturité.
    try:
        subprocess.run([sys.executable, os.path.join(HERE, "scorecard.py")],
                       cwd=HERE, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=True)
        print(f"[daily] scorecard -> analysis/macro-quant/scorecard_{rundate}.png", file=sys.stderr)
    except Exception as e:
        print(f"[daily] scorecard non généré ({e}) — persistance OK quand même.", file=sys.stderr)
    # réaction CT post-régime : diagnostic du tape T+1/2/3 après le label (best-effort).
    # -> DISTINCT du scorecard (espérance lente forward) ; lit la réaction immédiate.
    try:
        subprocess.run([sys.executable, os.path.join(HERE, "reaction.py")],
                       cwd=HERE, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=True)
        print(f"[daily] reaction -> analysis/macro-quant/reaction_{rundate}.png", file=sys.stderr)
    except Exception as e:
        print(f"[daily] reaction non généré ({e}) — persistance OK quand même.", file=sys.stderr)
    # watch rotation EU : vérifie un FRANCHISSEMENT du cadran (secteur thèse LAGGING↔
    # IMPROVING / dispersion>P70) et logue l'état. Domaine EU distinct du régime VIX US,
    # mais on l'accroche ici pour un check quotidien FIABLE (contexte déjà autorisé —
    # évite le mur TCC de launchd sur ~/Desktop). Weekly full-report géré en interne.
    try:
        subprocess.run([sys.executable, os.path.join(HERE, "..", "rotation", "eu_rotation_watch.py")],
                       cwd=HERE, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=True)
        print("[daily] eu_rotation_watch -> franchissement vérifié (alerte si croisement)", file=sys.stderr)
    except Exception as e:
        print(f"[daily] eu_rotation_watch non exécuté ({e}) — reste du daily OK.", file=sys.stderr)
    # watch rotation US : miroir de l'EU. Vérifie un FRANCHISSEMENT du cadran US
    # (◆ IA LEADING→WEAKENING = rotation-OUT du trade concentré / ★ ROT LAGGING→IMPROVING
    # = broadening-IN / dispersion>P70) et logue l'état. Débat concentration↔breadth US.
    try:
        subprocess.run([sys.executable, os.path.join(HERE, "..", "rotation", "us_rotation_watch.py")],
                       cwd=HERE, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=True)
        print("[daily] us_rotation_watch -> franchissement vérifié (alerte si croisement)", file=sys.stderr)
    except Exception as e:
        print(f"[daily] us_rotation_watch non exécuté ({e}) — reste du daily OK.", file=sys.stderr)
    # watch rotation ASIE : rotation PAYS Asie-Pacifique (ETF US-listés USD). Vérifie un
    # FRANCHISSEMENT du cadran (pays LAGGING→IMPROVING = rotation-IN / LEADING→WEAKENING =
    # rotation-OUT / dispersion>P70), emphase ★ sur la lentille semis/IA (Corée/Taïwan).
    try:
        subprocess.run([sys.executable, os.path.join(HERE, "..", "rotation", "asia_rotation_watch.py")],
                       cwd=HERE, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=True)
        print("[daily] asia_rotation_watch -> franchissement vérifié (alerte si croisement)", file=sys.stderr)
    except Exception as e:
        print(f"[daily] asia_rotation_watch non exécuté ({e}) — reste du daily OK.", file=sys.stderr)
    print(f"[daily] OK -> {DB}", file=sys.stderr)


if __name__ == "__main__":
    main()
