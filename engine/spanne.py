"""Spanne: wie weit eine Ueberarbeitung wie die letzte eine Zahl hoechstens verschieben koennte.

Review docs/review-2026-10-cloud.md (M2), Spezifikation 5b. Prototyp hinter
Schalter (data/entwurf/spanne.json, aus); aendert keine Zahl im Modell.

Zwei Teile:

1. Massstab ohne Strukturbruch. Der Kippabstand (5a) misst, wie weit die
   Prozente bei der letzten Revision gewandert sind: D(P_vorher || P_jetzt)
   je Horizont. Ein Szenario, das in der neueren Version abgespalten wurde
   (abgespalten_von, seit), zaehlt dort heute als neu; sein ganzes Gewicht
   erscheint als Bewegung. Hier wird es fuer den Vergleich seinem Ursprung
   zugerechnet. Was bleibt, ist die Bewegung der Prozente, nicht der Struktur.

2. Spanne einer Wahrscheinlichkeit p (ein Szenario oder eine Menge von
   Szenarien, etwa "teure Energie") bei Massstab eta:

       [q_min, q_max] = { q : kl(q || p) <= eta },
       kl(q || p) = q log(q/p) + (1-q) log((1-q)/(1-p))

   Genau das ist die Menge aller Q(A) mit D(Q || P) <= eta: Fuer jedes Q gilt
   D(Q || P) >= kl(Q(A) || P(A)) (Datenverarbeitung), und Gleichheit erreicht
   das Q, das innerhalb von A und ausserhalb proportional zu P bleibt. Die
   Spanne ist damit derselbe Massstab wie der Kippabstand, angewandt auf eine
   Zahl. Sie ist eine Grenze ("hoechstens"), kein Konfidenzintervall.

Nur Standardbibliothek; laeuft auch dort, wo es kein numpy gibt.
"""
from __future__ import annotations

import json
import math

GENAUIGKEIT = 1e-12


def lade(pfad=None) -> dict:
    """Der Schalter; fehlt die Datei, ist alles aus."""
    if pfad is None:
        from .io import DATA
        pfad = DATA / "entwurf" / "spanne.json"
    try:
        with open(pfad, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def an(cfg: dict | None) -> bool:
    c = cfg or {}
    return bool(c.get("an")) and not c.get("erledigt")


# --- Spanne ------------------------------------------------------------------------

def kl(q: float, p: float) -> float:
    """Relative Entropie zweier Bernoulli-Verteilungen in nat; unendlich, wo q Masse hat und p nicht."""
    aus = 0.0
    for a, b in ((q, p), (1.0 - q, 1.0 - p)):
        if a > 0:
            if b <= 0:
                return math.inf
            aus += a * math.log(a / b)
    return max(0.0, aus)


def _grenze(p: float, eta: float, ziel: float) -> float:
    """Der Punkt zwischen p und ziel (0 oder 1), an dem kl(q || p) = eta; ziel selbst, wenn er im Ball liegt."""
    if kl(ziel, p) <= eta:
        return ziel
    innen, aussen = p, ziel           # kl waechst monoton von p weg
    for _ in range(200):
        mitte = (innen + aussen) / 2
        if kl(mitte, p) <= eta:
            innen = mitte
        else:
            aussen = mitte
        if abs(aussen - innen) <= GENAUIGKEIT:
            break
    return innen


def spanne(p: float, eta: float) -> tuple:
    """(q_min, q_max) mit kl(q || p) <= eta, fuer p in [0, 1] und eta >= 0."""
    if not 0.0 <= p <= 1.0:
        raise ValueError(f"p = {p} liegt nicht in [0, 1]")
    if eta < 0:
        raise ValueError("eta ist mindestens 0")
    if p in (0.0, 1.0):
        return (p, p)
    return (_grenze(p, eta, 0.0), _grenze(p, eta, 1.0))


def spanne_prozent(prozent: float, eta: float, stellen: int = 0) -> dict:
    """Spanne fuer einen Prozentwert, gerundet: {p, von, bis} in Prozent."""
    lo, hi = spanne(prozent / 100.0, eta)
    r = (lambda x: round(100 * x, stellen) + 0.0) if stellen else (lambda x: int(round(100 * x)))
    return {"p": prozent, "von": r(lo), "bis": r(hi)}


# --- Massstab ----------------------------------------------------------------------

def _relative_entropie(p: list, q: list) -> float:
    aus = 0.0
    for a, b in zip(p, q):
        if a > 0:
            if b <= 0:
                return math.inf
            aus += a * math.log(a / b)
    return aus


def massstab(journal: list, model: dict, ohne_strukturbruch: bool = True) -> dict:
    """D(P_vorher || P_jetzt) je Horizont zwischen den letzten beiden Journal-Eintraegen.

    Wie robustheit.massstab_aus_journal: Beendete Szenarien zaehlen fuer ihren
    Nachfolger. Mit ohne_strukturbruch zaehlt zusaetzlich ein Szenario, das
    seit der neueren Version abgespalten ist, fuer seinen Ursprung. Ohne zwei
    Eintraege: leer.
    """
    if len(journal) < 2:
        return {}
    vorher, jetzt = journal[-2], journal[-1]
    nachfolger = {b["id"]: b.get("nachfolger") for b in model.get("szenarien_beendet", [])}
    ursprung = {}
    if ohne_strukturbruch:
        ursprung = {s["id"]: s["abgespalten_von"] for s in model.get("szenarien", [])
                    if s.get("abgespalten_von") and s.get("seit") == jetzt["version"]}
    aus = {}
    for h, p_jetzt in jetzt["wahrscheinlichkeiten"].items():
        p_vorher = vorher["wahrscheinlichkeiten"].get(h)
        if not p_vorher:
            continue
        q = {}
        for sid, wert in p_vorher.items():
            ziel = sid
            while nachfolger.get(ziel):
                ziel = nachfolger[ziel]
            q[ziel] = q.get(ziel, 0) + wert
        n = {}
        for sid, wert in p_jetzt.items():
            ziel = ursprung.get(sid, sid)
            n[ziel] = n.get(ziel, 0) + wert
        ids = sorted(set(q) | set(n))
        sq, sn = sum(q.values()), sum(n.values())
        aus[h] = _relative_entropie([q.get(s, 0) / sq for s in ids], [n.get(s, 0) / sn for s in ids])
    return {"von": vorher["version"], "nach": jetzt["version"], "je_horizont": aus,
            "zusammengelegt": ursprung}


def massstab_je_horizont(cfg: dict | None, journal: list, model: dict) -> dict:
    """{h: eta} und Quelle.

    Ein Urteil (massstab.wert) gilt fuer alle Horizonte. Sonst die letzte
    Revision (ohne Strukturbruch, wenn nicht anders gesetzt); mit
    zusammenfassung "groesster" (Vorgabe) gilt ihr groesster Wert fuer alle
    Horizonte: Ein ferner Horizont ist nicht sicherer, nur weil die letzte
    Revision ihn wenig bewegt hat. "je_horizont" nimmt jeden Wert einzeln.
    """
    m_cfg = (cfg or {}).get("massstab") or {}
    horizonte = model["meta"]["horizonte"]
    if m_cfg.get("wert") is not None:
        return {"je_horizont": {h: float(m_cfg["wert"]) for h in horizonte},
                "quelle": "Urteil in data/entwurf/spanne.json"}
    ohne = m_cfg.get("ohne_strukturbruch", True)
    m = massstab(journal, model, ohne_strukturbruch=ohne)
    je = m.get("je_horizont", {})
    quelle = (f"letzte Revision {m.get('von')} -> {m.get('nach')}"
              + (", Abspaltungen ihrem Ursprung zugerechnet" if ohne else ""))
    art = m_cfg.get("zusammenfassung", "groesster")
    if art == "groesster" and je:
        g = max(je.values())
        return {"je_horizont": {h: g for h in horizonte}, "quelle": quelle + ", groesster Wert fuer alle Horizonte"}
    if art not in ("groesster", "je_horizont"):
        raise ValueError(f"spanne: zusammenfassung {art!r} ist 'groesster' oder 'je_horizont'")
    return {"je_horizont": je, "quelle": quelle}


# --- Fuer das Modell ---------------------------------------------------------------

def szenarien(model: dict, eta_je_h: dict, probs: dict | None = None) -> dict:
    """Spanne je Szenario und Horizont: {h: {sid: {p, von, bis}}}.

    probs: {h: {sid: prozent}} statt der Werte im Modell (etwa der Tagesstand).
    """
    aus = {}
    for h in model["meta"]["horizonte"]:
        if h not in eta_je_h:
            continue
        p = probs[h] if probs else {s["id"]: s["wahrscheinlichkeit"][h] for s in model["szenarien"]}
        aus[h] = {sid: spanne_prozent(v, eta_je_h[h]) for sid, v in p.items()}
    return aus


def ereignis(probs: dict, menge: list, eta_je_h: dict, stellen: int = 0) -> dict:
    """Wahrscheinlichkeit einer Menge von Szenarien je Horizont mit Spanne: {h: {p, von, bis}}."""
    aus = {}
    for h, p in probs.items():
        summe = sum(float(p[s]) for s in menge if s in p)
        gesamt = sum(float(v) for v in p.values())
        prozent = 100.0 * summe / gesamt if gesamt else 0.0
        e = spanne_prozent(round(prozent, 6), eta_je_h[h], stellen) if h in eta_je_h else {"p": prozent}
        e["p"] = round(prozent, stellen) + 0.0 if stellen else int(round(prozent))
        aus[h] = e
    return aus


def bericht(model: dict, journal: list, cfg: dict | None = None) -> dict:
    """Der Export exports/spanne.json (nur mit Schalter an)."""
    m = massstab_je_horizont(cfg, journal, model)
    return {"modellversion": model["meta"]["version"], "einheit": "Prozent der Welt im Jahr h",
            "lesart": "So weit koennte eine Ueberarbeitung von der Groesse der letzten diese eine Zahl hoechstens "
                      "verschieben. Eine Grenze, kein Konfidenzintervall; das Modell ist nicht kalibriert.",
            "massstab": {"je_horizont": {h: round(v, 4) for h, v in m["je_horizont"].items()}, "quelle": m["quelle"]},
            "szenarien": szenarien(model, m["je_horizont"])}
