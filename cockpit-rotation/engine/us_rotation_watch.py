#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
US ROTATION — WATCH (entrée QUOTIDIENNE : alerte de franchissement + rapport hebdo)
================================================================================
Miroir US de eu_rotation_watch.py. Le cadran (us_rotation.py) est HEBDO par nature
(fenêtres lentes 1m/3m/6m, recalcul stateless depuis tout l'historique — tourner
tous les jours n'ajoute pas de signal, seulement du bruit). MAIS on veut être
PRÉVENU le jour d'un FRANCHISSEMENT sans attendre le lundi. D'où ce watcher :

  • TOUS LES JOURS (via launchd / macro_quant_daily) :
      1. compute() l'état du jour et le logue (rotation_history.csv, idempotent).
      2. compare au DERNIER run loggé antérieur → détecte les franchissements sur
         les DEUX côtés du débat US concentration↔broadening :
           - secteur ◆ IA (role="AI") qui s'essouffle : LEADING→WEAKENING =
             **début de rotation-OUT du trade concentré** (corollaire du broadening).
           - secteur ★ BROADENING (role="ROT") qui se retourne : LAGGING→IMPROVING =
             **1ère brique broadening-IN**. IMPROVING→LAGGING = faux départ avorté.
           - dispersion qui franchit P70 (rotation qui s'active / se rendort).
      3. si franchissement → ALERTE (stdout + append « ALERTES rotation US.md »).
         sinon → RAS silencieux.

  • LE LUNDI (ou 1er run d'une nouvelle semaine ISO, rattrapage si machine off) :
      rapport complet stdout + régénère la figure RRG. Cadence hebdo.

⚠️ Un franchissement N'EST PAS un trigger d'exécution : le cadran reste DESCRIPTIF
   (proxy PRIX, pas de flux ETF ni de valo). Un vrai broadening doit TENIR 2-3 sem
   (◆ IA en WEAKENING + ★ ROT en IMPROVING + dispersion>P70 + RSP/IWM qui
   sur-performent). L'alerte dit « regarde », pas « achète ».
================================================================================
"""
import os, sys, csv, datetime as dt
import us_rotation as ur

ALERTLOG = os.path.join(ur.OUT, "ALERTES rotation US.md")

# messages par transition de quadrant, côté BROADENING (role="ROT") — miroir thèse EU.
TRANS_ROT = {
    ("LAGGING", "IMPROVING"):   "⚡ LAGGING→IMPROVING : délaissé mais momentum relatif qui se retourne = **1ère brique broadening-IN**. À CONFIRMER 2-3 sem (piège du faux départ).",
    ("IMPROVING", "LAGGING"):   "↩︎ IMPROVING→LAGGING : **faux départ avorté**, le momentum a rechuté. Broadening PAS trouvé son point d'appui.",
    ("IMPROVING", "LEADING"):   "✅ IMPROVING→LEADING : la force relative a suivi le momentum = **broadening confirmé en cours**.",
    ("LAGGING", "LEADING"):     "✅ LAGGING→LEADING : bascule directe faible→fort (rare, mouvement violent) = **broadening**.",
    ("LEADING", "WEAKENING"):   "⚠︎ LEADING→WEAKENING : le broadening ici mûrit / l'argent commence à ressortir.",
    ("WEAKENING", "LAGGING"):   "▼ WEAKENING→LAGGING : décrochage confirmé = sortie de liquidité.",
    ("WEAKENING", "LEADING"):   "↺ WEAKENING→LEADING : regain de momentum sur un secteur encore fort.",
    ("LEADING", "IMPROVING"):   "≈ LEADING→IMPROVING (transition atypique — vérifier bruit basse dispersion).",
    ("LAGGING", "WEAKENING"):   "≈ LAGGING→WEAKENING (transition atypique — vérifier bruit basse dispersion).",
    ("IMPROVING", "WEAKENING"): "↺ IMPROVING→WEAKENING (transition atypique — vérifier).",
    ("WEAKENING", "IMPROVING"): "↺ WEAKENING→IMPROVING (transition atypique — vérifier).",
    ("LEADING", "LAGGING"):     "▼▼ LEADING→LAGGING : effondrement de la force relative (mouvement violent).",
}

# messages par transition, côté LEADERS IA/MÉGA-CAP (role="AI") — ici c'est la
# rotation-OUT qui est le signal intéressant (le trade concentré qui se défait).
TRANS_AI = {
    ("LEADING", "WEAKENING"):   "⚡ LEADING→WEAKENING : le trade concentré IA/méga-cap **s'essouffle** = DÉBUT de rotation-OUT. Corollaire du broadening — à CONFIRMER 2-3 sem.",
    ("WEAKENING", "LAGGING"):   "▼ WEAKENING→LAGGING : le leadership IA a **DÉCROCHÉ** = rotation-OUT confirmée.",
    ("WEAKENING", "LEADING"):   "↺ WEAKENING→LEADING : **re-concentration** IA (le trade méga-cap repart).",
    ("LAGGING", "IMPROVING"):   "↺ LAGGING→IMPROVING : rebond du leadership IA (re-concentration naissante).",
    ("IMPROVING", "LEADING"):   "↺ IMPROVING→LEADING : re-concentration confirmée (l'argent revient sur les méga-cap).",
    ("IMPROVING", "LAGGING"):   "≈ IMPROVING→LAGGING (rebond IA avorté).",
    ("LEADING", "IMPROVING"):   "≈ LEADING→IMPROVING (transition atypique — vérifier bruit basse dispersion).",
    ("LAGGING", "WEAKENING"):   "≈ LAGGING→WEAKENING (transition atypique — vérifier).",
    ("WEAKENING", "IMPROVING"): "↺ WEAKENING→IMPROVING (transition atypique — vérifier).",
    ("LAGGING", "LEADING"):     "↺ LAGGING→LEADING : re-concentration violente du leadership IA.",
    ("IMPROVING", "WEAKENING"): "↺ IMPROVING→WEAKENING (transition atypique — vérifier).",
    ("LEADING", "LAGGING"):     "▼▼ LEADING→LAGGING : effondrement du leadership IA (mouvement violent) = rotation-OUT brutale.",
}


def load_prev(asof):
    """Dernier run loggé STRICTEMENT antérieur à asof : {sid: row}. Vide si aucun."""
    if not os.path.exists(ur.HISTLOG):
        return None, {}
    runs = {}
    for row in csv.DictReader(open(ur.HISTLOG)):
        rd = row.get("run_date", "")
        if rd and rd < asof:
            runs.setdefault(rd, {})[row.get("sid")] = row
    if not runs:
        return None, {}
    last = max(runs)
    return last, runs[last]


def detect(res, prev):
    """Retourne (events_secteurs_AI+ROT, event_dispersion|None)."""
    events = []
    for r in res["rows"]:
        if r["role"] not in ("AI", "ROT"):
            continue
        p = prev.get(r["tk"])
        if not p:
            continue
        pq, nq = p.get("quad"), r["quad"]
        if pq and nq and pq != nq:
            table = TRANS_AI if r["role"] == "AI" else TRANS_ROT
            msg = table.get((pq, nq), f"{pq}→{nq}")
            events.append(dict(lab=r["lab"], role=r["role"], pq=pq, nq=nq,
                               rs=r["rs"], mom=r["mom"], relret3=r["relret3"], msg=msg))
    disp_ev = None
    if prev:
        try:
            pdp = float(next(iter(prev.values())).get("disp_pct", "nan"))
        except (ValueError, StopIteration):
            pdp = float("nan")
        ndp = res["disp_pct"]
        if pdp == pdp:  # non-NaN
            if pdp < ur.DISP_HOT <= ndp:
                disp_ev = dict(dir="up", pdp=pdp, ndp=ndp,
                               msg=f"dispersion P{pdp:.0f}→P{ndp:.0f} (>P{ur.DISP_HOT:.0f}) = régime de rotation qui **s'ACTIVE**.")
            elif ndp < ur.DISP_HOT <= pdp:
                disp_ev = dict(dir="down", pdp=pdp, ndp=ndp,
                               msg=f"dispersion P{pdp:.0f}→P{ndp:.0f} (<P{ur.DISP_HOT:.0f}) = rotation qui **se rendort**.")
    return events, disp_ev


def write_alert(res, prev_date, events, disp_ev):
    asof = res["asof"]
    lines = [f"\n## {asof} — ⚡ ALERTE franchissement  (réf. run {prev_date})"]
    for e in events:
        tag = "◆ IA/méga-cap" if e["role"] == "AI" else "★ broadening"
        lines.append(f"- **{e['lab']}** ({tag}) · RS z {e['rs']:+.2f} · Mom z "
                     f"{e['mom']:+.2f} · rel3m {e['relret3']:+.1f}% — {e['msg']}")
    if disp_ev:
        lines.append(f"- **Dispersion** — {disp_ev['msg']}")
    lines.append("- _Rappel : cadran DESCRIPTIF, pas un trigger. Broadening crédible = "
                 "◆ IA en WEAKENING + ★ ROT en IMPROVING + dispersion>P70 + RSP/IWM qui "
                 "sur-performent + catalyseur (Fed/taux, earnings méga-cap)._")
    block = "\n".join(lines) + "\n"

    header = ("---\ntitle: \"ALERTES — Cadran Rotation Liquidité US (franchissements)\"\n"
              "type: quant\nstatut: en-cours\ntier: episodic\nconfidence: 40\n"
              "hallucination-risk: low\ntopic: rotation-us\n"
              "tags: [type/quant, topic/macro, topic/equity, statut/en-cours]\n"
              "source: \"Macro/Quant/engine/rotation/us_rotation_watch.py (append quotidien)\"\n"
              "related: [\"[[Research/2026-08-19 - Cadran Rotation Liquidite US (secteurs S&P 500)]]\"]\n"
              "---\n\n# ALERTES — franchissements du cadran de rotation US\n\n"
              "> Log append-only. Chaque bloc = un jour où un secteur ◆ IA ou ★ BROADENING a "
              "changé de quadrant (rotation-OUT / rotation-IN) et/ou la dispersion a franchi P70.\n"
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
    res = ur.compute()
    prev_date, prev = load_prev(res["asof"])
    events, disp_ev = detect(res, prev)

    ur.log_history(res)  # logue TOUJOURS l'état du jour (substrat idempotent)

    weekly = is_weekly_run(res["asof"], prev_date)
    if weekly:
        ur.print_report(res)
        out = ur.figure(res)
        print(f"[weekly] rapport complet + figure -> {out}", file=sys.stderr)

    if events or disp_ev:
        write_alert(res, prev_date or "—", events, disp_ev)
        print(f"\n⚡ ALERTE FRANCHISSEMENT US (as-of {res['asof']}, réf {prev_date}) :")
        for e in events:
            side = "◆IA" if e["role"] == "AI" else "★ROT"
            print(f"   • {e['lab']} [{side}] : {e['pq']}→{e['nq']}  (RS {e['rs']:+.2f} / Mom {e['mom']:+.2f})")
        if disp_ev:
            print(f"   • Dispersion : P{disp_ev['pdp']:.0f}→P{disp_ev['ndp']:.0f}")
        print(f"   → écrit dans {ALERTLOG}")
    else:
        print(f"[watch] RAS — aucun franchissement (as-of {res['asof']}, réf {prev_date}).")


if __name__ == "__main__":
    main()
