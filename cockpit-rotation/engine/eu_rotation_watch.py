#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
EU ROTATION — WATCH (entrée QUOTIDIENNE : alerte de franchissement + rapport hebdo)
================================================================================
Le cadran de rotation (eu_rotation.py) est HEBDO par nature (fenêtres lentes
1m/3m/6m, recalcul stateless depuis tout l'historique — le faire tourner tous les
jours n'ajoute pas de signal, seulement du bruit). MAIS on veut être PRÉVENU le
jour où un FRANCHISSEMENT se produit sans attendre le lundi. D'où ce watcher :

  • TOUS LES JOURS (via launchd) :
      1. compute() l'état du jour et le logue (rotation_history.csv, idempotent).
      2. compare au DERNIER run loggé antérieur → détecte les franchissements :
           - secteur THÈSE qui change de quadrant (surtout LAGGING→IMPROVING =
             1ère brique rotation-IN ; IMPROVING→LAGGING = faux départ avorté).
           - dispersion qui franchit P70 (rotation qui s'active / se rendort).
      3. si franchissement → ALERTE (stdout + append dans « ALERTES rotation EU.md »).
         sinon → RAS silencieux (rien écrit dans la note).

  • LE LUNDI (ou 1er run d'une nouvelle semaine ISO, rattrapage si machine off) :
      rapport complet stdout + régénère la figure RRG. C'est la cadence hebdo.

⚠️ Un franchissement N'EST PAS un trigger d'exécution : le cadran reste DESCRIPTIF.
   Une vraie rotation-IN doit TENIR 2-3 semaines (ne pas confondre avec le faux
   départ LAGGING→IMPROVING→LAGGING observé au 1er run). L'alerte dit « regarde »,
   pas « achète ». Confirmation = croisement + dispersion>P70 + catalyseur exogène.
================================================================================
"""
import os, sys, csv, datetime as dt
import eu_rotation as er

ALERTLOG = os.path.join(er.OUT, "ALERTES rotation EU.md")

# messages par transition de quadrant, pour un secteur de la thèse
TRANS = {
    ("LAGGING", "IMPROVING"):  "⚡ LAGGING→IMPROVING : momentum relatif qui se retourne = **1ère brique rotation-IN**. À CONFIRMER 2-3 sem (piège du faux départ).",
    ("IMPROVING", "LAGGING"):  "↩︎ IMPROVING→LAGGING : **faux départ avorté**, le momentum a rechuté. Rotation-IN PAS trouvé son point d'appui.",
    ("IMPROVING", "LEADING"):  "✅ IMPROVING→LEADING : la force relative a suivi le momentum = **rotation-IN confirmée en cours**.",
    ("LAGGING", "LEADING"):    "✅ LAGGING→LEADING : bascule directe faible→fort (rare, mouvement violent) = **rotation-IN**.",
    ("LEADING", "WEAKENING"):  "⚠︎ LEADING→WEAKENING : la force s'essouffle = rotation qui mûrit / argent qui commence à sortir.",
    ("WEAKENING", "LAGGING"):  "▼ WEAKENING→LAGGING : décrochage confirmé = sortie de liquidité.",
    ("LEADING", "IMPROVING"):  "≈ LEADING→IMPROVING (transition atypique — vérifier bruit basse dispersion).",
    ("WEAKENING", "LEADING"):  "↺ WEAKENING→LEADING : regain de momentum sur un secteur encore fort.",
    ("LAGGING", "WEAKENING"):  "≈ LAGGING→WEAKENING (transition atypique — vérifier bruit basse dispersion).",
    ("IMPROVING", "WEAKENING"):"↺ IMPROVING→WEAKENING (transition atypique — vérifier).",
    ("WEAKENING", "IMPROVING"):"↺ WEAKENING→IMPROVING (transition atypique — vérifier).",
    ("LEADING", "LAGGING"):    "▼▼ LEADING→LAGGING : effondrement de la force relative (mouvement violent).",
}


def load_prev(asof):
    """Dernier run loggé STRICTEMENT antérieur à asof : {sid: row}. Vide si aucun."""
    if not os.path.exists(er.HISTLOG):
        return None, {}
    runs = {}
    for row in csv.DictReader(open(er.HISTLOG)):
        rd = row.get("run_date", "")
        if rd and rd < asof:
            runs.setdefault(rd, {})[row.get("sid")] = row
    if not runs:
        return None, {}
    last = max(runs)
    return last, runs[last]


def detect(res, prev):
    """Retourne (events_secteurs_these, event_dispersion|None)."""
    events = []
    for r in res["rows"]:
        if not r["thesis"]:
            continue
        p = prev.get(r["tk"])
        if not p:
            continue
        pq, nq = p.get("quad"), r["quad"]
        if pq and nq and pq != nq:
            msg = TRANS.get((pq, nq), f"{pq}→{nq}")
            events.append(dict(lab=r["lab"], pq=pq, nq=nq, rs=r["rs"], mom=r["mom"],
                               relret3=r["relret3"], msg=msg))
    disp_ev = None
    if prev:
        # disp_pct est identique sur toutes les lignes d'un run ; on prend la 1ère.
        try:
            pdp = float(next(iter(prev.values())).get("disp_pct", "nan"))
        except (ValueError, StopIteration):
            pdp = float("nan")
        ndp = res["disp_pct"]
        if pdp == pdp:  # non-NaN
            if pdp < er.DISP_HOT <= ndp:
                disp_ev = dict(dir="up", pdp=pdp, ndp=ndp,
                               msg=f"dispersion P{pdp:.0f}→P{ndp:.0f} (>P{er.DISP_HOT:.0f}) = régime de rotation qui **s'ACTIVE**.")
            elif ndp < er.DISP_HOT <= pdp:
                disp_ev = dict(dir="down", pdp=pdp, ndp=ndp,
                               msg=f"dispersion P{pdp:.0f}→P{ndp:.0f} (<P{er.DISP_HOT:.0f}) = rotation qui **se rendort**.")
    return events, disp_ev


def write_alert(res, prev_date, events, disp_ev):
    asof = res["asof"]
    lines = [f"\n## {asof} — ⚡ ALERTE franchissement  (réf. run {prev_date})"]
    for e in events:
        lines.append(f"- **{e['lab']}** (secteur thèse) · RS z {e['rs']:+.2f} · Mom z "
                     f"{e['mom']:+.2f} · rel3m {e['relret3']:+.1f}% — {e['msg']}")
    if disp_ev:
        lines.append(f"- **Dispersion** — {disp_ev['msg']}")
    lines.append("- _Rappel : cadran DESCRIPTIF, pas un trigger. Une rotation-IN doit "
                 "TENIR 2-3 sem + dispersion>P70 + catalyseur (Chine/RCO)._")
    block = "\n".join(lines) + "\n"

    header = ("---\ntitle: \"ALERTES — Cadran Rotation Liquidité EU (franchissements)\"\n"
              "type: quant\nstatut: en-cours\ntier: episodic\nconfidence: 40\n"
              "hallucination-risk: low\ntopic: rotation-eu\n"
              "tags: [type/quant, topic/macro, topic/equity, statut/en-cours]\n"
              "source: \"Macro/Quant/engine/eu_rotation_watch.py (append quotidien)\"\n"
              "related: [\"[[Research/2026-08-14 - Cadran Rotation Liquidite EU (secteurs STOXX 600)]]\"]\n"
              "---\n\n# ALERTES — franchissements du cadran de rotation EU\n\n"
              "> Log append-only. Chaque bloc = un jour où un secteur THÈSE a changé de "
              "quadrant (surtout LAGGING↔IMPROVING) et/ou la dispersion a franchi P70.\n"
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
    res = er.compute()
    prev_date, prev = load_prev(res["asof"])
    events, disp_ev = detect(res, prev)

    er.log_history(res)  # logue TOUJOURS l'état du jour (substrat idempotent)

    weekly = is_weekly_run(res["asof"], prev_date)
    if weekly:
        er.print_report(res)
        out = er.figure(res)
        print(f"[weekly] rapport complet + figure -> {out}", file=sys.stderr)

    if events or disp_ev:
        write_alert(res, prev_date or "—", events, disp_ev)
        print(f"\n⚡ ALERTE FRANCHISSEMENT (as-of {res['asof']}, réf {prev_date}) :")
        for e in events:
            print(f"   • {e['lab']} : {e['pq']}→{e['nq']}  (RS {e['rs']:+.2f} / Mom {e['mom']:+.2f})")
        if disp_ev:
            print(f"   • Dispersion : P{disp_ev['pdp']:.0f}→P{disp_ev['ndp']:.0f}")
        print(f"   → écrit dans {ALERTLOG}")
    else:
        print(f"[watch] RAS — aucun franchissement (as-of {res['asof']}, réf {prev_date}).")


if __name__ == "__main__":
    main()
