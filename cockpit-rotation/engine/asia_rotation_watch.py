#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
ASIA ROTATION — WATCH (entrée QUOTIDIENNE : alerte de franchissement + rapport hebdo)
================================================================================
Miroir asiatique de eu/us_rotation_watch.py. Le cadran (asia_rotation.py) est HEBDO
par nature (fenêtres lentes 1m/3m/6m, recalcul stateless depuis tout l'historique —
tourner tous les jours n'ajoute pas de signal, seulement du bruit). MAIS on veut
être PRÉVENU le jour d'un FRANCHISSEMENT sans attendre le lundi. D'où ce watcher :

  • TOUS LES JOURS (via launchd / macro_quant_daily) :
      1. compute() l'état du jour et le logue (rotation_history.csv, idempotent).
      2. compare au DERNIER run loggé antérieur → détecte les franchissements de
         quadrant sur TOUS les pays (rotation-IN = LAGGING→IMPROVING, rotation-OUT
         = LEADING→WEAKENING…), avec emphase ★ sur la lentille semis/IA (KR/TW).
      3. dispersion qui franchit P70 (rotation asiatique qui s'active / se rendort).
      4. si franchissement → ALERTE (stdout + append « ALERTES rotation ASIE.md »).
         sinon → RAS silencieux.

  • LE LUNDI (ou 1er run d'une nouvelle semaine ISO, rattrapage si machine off) :
      rapport complet stdout + régénère la figure RRG. Cadence hebdo.

⚠️ Un franchissement N'EST PAS un trigger d'exécution : le cadran reste DESCRIPTIF
   (proxy PRIX, pas de flux ETF ni de valo). Une vraie rotation-IN pays doit TENIR
   2-3 sem + dispersion>P70 + (pour KR/TW) validation par les ADR TSM/BABA +
   catalyseur (Fed/USD, Chine/PBoC, BoJ/yen). L'alerte dit « regarde », pas « achète ».
================================================================================
"""
import os, sys, csv, datetime as dt
import asia_rotation as ar

ALERTLOG = os.path.join(ar.OUT, "ALERTES rotation ASIE.md")

# messages par transition de quadrant (rotation PAYS).
TRANS = {
    ("LAGGING", "IMPROVING"):   "⚡ LAGGING→IMPROVING : pays délaissé, momentum relatif qui se retourne = **1ère brique rotation-IN**. À CONFIRMER 2-3 sem (piège du faux départ).",
    ("IMPROVING", "LAGGING"):   "↩︎ IMPROVING→LAGGING : **faux départ avorté**, le momentum a rechuté.",
    ("IMPROVING", "LEADING"):   "✅ IMPROVING→LEADING : la force relative a suivi le momentum = **rotation-IN confirmée**.",
    ("LAGGING", "LEADING"):     "✅ LAGGING→LEADING : bascule directe faible→fort (rare, mouvement violent) = rotation-IN.",
    ("LEADING", "WEAKENING"):   "⚠︎ LEADING→WEAKENING : le leadership pays mûrit / l'argent commence à ressortir.",
    ("WEAKENING", "LAGGING"):   "▼ WEAKENING→LAGGING : décrochage confirmé = sortie de liquidité.",
    ("WEAKENING", "LEADING"):   "↺ WEAKENING→LEADING : regain de momentum sur un pays encore fort.",
    ("LEADING", "IMPROVING"):   "≈ LEADING→IMPROVING (transition atypique — vérifier bruit basse dispersion).",
    ("LAGGING", "WEAKENING"):   "≈ LAGGING→WEAKENING (transition atypique — vérifier bruit basse dispersion).",
    ("IMPROVING", "WEAKENING"): "↺ IMPROVING→WEAKENING (transition atypique — vérifier).",
    ("WEAKENING", "IMPROVING"): "↺ WEAKENING→IMPROVING (transition atypique — vérifier).",
    ("LEADING", "LAGGING"):     "▼▼ LEADING→LAGGING : effondrement de la force relative (mouvement violent).",
}


def load_prev(asof):
    """Dernier run loggé STRICTEMENT antérieur à asof : {sid: row}. Vide si aucun."""
    if not os.path.exists(ar.HISTLOG):
        return None, {}
    runs = {}
    for row in csv.DictReader(open(ar.HISTLOG)):
        rd = row.get("run_date", "")
        if rd and rd < asof:
            runs.setdefault(rd, {})[row.get("sid")] = row
    if not runs:
        return None, {}
    last = max(runs)
    return last, runs[last]


def detect(res, prev):
    """Retourne (events_pays, event_dispersion|None)."""
    events = []
    for r in res["rows"]:
        p = prev.get(r["tk"])
        if not p:
            continue
        pq, nq = p.get("quad"), r["quad"]
        if pq and nq and pq != nq:
            msg = TRANS.get((pq, nq), f"{pq}→{nq}")
            events.append(dict(lab=r["lab"], thesis=r["thesis"], pq=pq, nq=nq,
                               rs=r["rs"], mom=r["mom"], relret3=r["relret3"], msg=msg))
    disp_ev = None
    if prev:
        try:
            pdp = float(next(iter(prev.values())).get("disp_pct", "nan"))
        except (ValueError, StopIteration):
            pdp = float("nan")
        ndp = res["disp_pct"]
        if pdp == pdp:  # non-NaN
            if pdp < ar.DISP_HOT <= ndp:
                disp_ev = dict(dir="up", pdp=pdp, ndp=ndp,
                               msg=f"dispersion P{pdp:.0f}→P{ndp:.0f} (>P{ar.DISP_HOT:.0f}) = régime de rotation qui **s'ACTIVE**.")
            elif ndp < ar.DISP_HOT <= pdp:
                disp_ev = dict(dir="down", pdp=pdp, ndp=ndp,
                               msg=f"dispersion P{pdp:.0f}→P{ndp:.0f} (<P{ar.DISP_HOT:.0f}) = rotation qui **se rendort**.")
    return events, disp_ev


def write_alert(res, prev_date, events, disp_ev):
    asof = res["asof"]
    lines = [f"\n## {asof} — ⚡ ALERTE franchissement  (réf. run {prev_date})"]
    for e in events:
        tag = "★ semis/IA" if e["thesis"] else "pays"
        lines.append(f"- **{e['lab']}** ({tag}) · RS z {e['rs']:+.2f} · Mom z "
                     f"{e['mom']:+.2f} · rel3m {e['relret3']:+.1f}% — {e['msg']}")
    if disp_ev:
        lines.append(f"- **Dispersion** — {disp_ev['msg']}")
    lines.append("- _Rappel : cadran DESCRIPTIF, pas un trigger. Rotation-IN crédible = "
                 "pays en IMPROVING qui TIENT 2-3 sem + dispersion>P70 + (pour KR/TW) "
                 "validation par les ADR TSM/BABA + catalyseur (Fed/USD, Chine/PBoC, BoJ/yen)._")
    block = "\n".join(lines) + "\n"

    header = ("---\ntitle: \"ALERTES — Cadran Rotation Liquidité ASIE (franchissements)\"\n"
              "type: quant\nstatut: en-cours\ntier: episodic\nconfidence: 40\n"
              "hallucination-risk: low\ntopic: rotation-asie\n"
              "tags: [type/quant, topic/macro, topic/equity, statut/en-cours]\n"
              "source: \"Macro/Quant/engine/rotation/asia_rotation_watch.py (append quotidien)\"\n"
              "related: [\"[[Research/2026-08-31 - Cadran Rotation Liquidite Asie (pays Asie-Pacifique)]]\"]\n"
              "---\n\n# ALERTES — franchissements du cadran de rotation ASIE\n\n"
              "> Log append-only. Chaque bloc = un jour où un PAYS a changé de quadrant "
              "(rotation-IN / rotation-OUT) et/ou la dispersion a franchi P70.\n"
              "> **Descriptif, pas un trigger.** Silence = RAS (aucun franchissement).\n")
    new = not os.path.exists(ALERTLOG)
    with open(ALERTLOG, "a") as f:
        if new:
            f.write(header)
        f.write(block)


def is_weekly_run(asof, prev_date):
    """Rapport complet le lundi, OU 1er run d'une nouvelle semaine ISO (rattrapage)."""
    today = dt.date.today()
    if today.weekday() == 0:  # lundi
        return True
    if prev_date is None:
        return True
    try:
        pw = dt.date.fromisoformat(prev_date).isocalendar()[:2]
        aw = dt.date.fromisoformat(asof).isocalendar()[:2]
        return aw != pw
    except ValueError:
        return False


def main():
    res = ar.compute()
    prev_date, prev = load_prev(res["asof"])
    events, disp_ev = detect(res, prev)

    ar.log_history(res)  # logue TOUJOURS l'état du jour (substrat idempotent)

    weekly = is_weekly_run(res["asof"], prev_date)
    if weekly:
        ar.print_report(res)
        out = ar.figure(res)
        print(f"[weekly] rapport complet + figure -> {out}", file=sys.stderr)

    if events or disp_ev:
        write_alert(res, prev_date or "—", events, disp_ev)
        print(f"\n⚡ ALERTE FRANCHISSEMENT ASIE (as-of {res['asof']}, réf {prev_date}) :")
        for e in events:
            side = "★" if e["thesis"] else " "
            print(f"   • {e['lab']} [{side}] : {e['pq']}→{e['nq']}  (RS {e['rs']:+.2f} / Mom {e['mom']:+.2f})")
        if disp_ev:
            print(f"   • Dispersion : P{disp_ev['pdp']:.0f}→P{disp_ev['ndp']:.0f}")
        print(f"   → écrit dans {ALERTLOG}")
    else:
        print(f"[watch] RAS — aucun franchissement (as-of {res['asof']}, réf {prev_date}).")


if __name__ == "__main__":
    main()
