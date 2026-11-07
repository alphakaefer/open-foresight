"""Datenzufluss: Ereignisse entdoppeln, Buendel daempfen, ungerundet rechnen.

Schritt 1 des Plans (docs/review-2026-10.md), Spezifikation Abschnitt 7a.
Schalter und Urteile stehen in data/datenzufluss.json. Sind beide Schalter
aus, aendert dieses Modul nichts: bayes.update_probabilities nimmt dann den
alten Weg, Zeichen fuer Zeichen.

Drei Fehler des alten Wegs behebt es, wenn es an ist:

- Dieselbe Nachricht aus zwei Quellen zaehlt doppelt; zehn Studien derselben
  Welle zaehlen zehnfach.
- Jede Uebernahme rundet auf ganze Prozent und macht das zum neuen Prior.
  Das Basismodell haengt dann davon ab, wie oft uebernommen wurde.
- Ein Szenario, das auf 0 gerundet wird, kommt nie wieder hoch.

Nur Standardbibliothek: der Tagesstand rechnet damit auf dem Webspace.
"""
from __future__ import annotations

import json
import math

WIRKSAM = ("bestaetigend", "widersprechend")
"""Nur diese Richtungen tragen Evidenz; neutral und neu zaehlen in keinem Buendel."""


def lade(pfad=None) -> dict:
    """Die Schalter aus data/datenzufluss.json; fehlt die Datei, ist alles aus."""
    if pfad is None:
        from .io import DATA
        pfad = DATA / "datenzufluss.json"
    try:
        with open(pfad, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def entdoppeln_an(cfg: dict | None) -> bool:
    return bool(cfg) and bool((cfg.get("entdoppeln") or {}).get("an"))


def ungerundet_an(cfg: dict | None) -> bool:
    return bool(cfg) and bool((cfg.get("ungerundet") or {}).get("an"))


def aktiv(cfg: dict | None) -> bool:
    return entdoppeln_an(cfg) or ungerundet_an(cfg)


# --- Gewichte ----------------------------------------------------------------

def gewichte(signale: list, cfg: dict | None) -> list:
    """Gewicht g je Signal in [0, 1]; der Posterior nutzt LR ** g.

    Ohne Entdoppeln ist jedes Gewicht 1. Sonst, in dieser Reihenfolge:
    gemeldete Anzeichen zaehlen nicht, je Ereignis zaehlt das staerkste, und
    Signale mit gleicher Treibermenge im gleichen Monat teilen sich n ** -beta.
    Das Ergebnis haengt nicht von der Reihenfolge der Signale ab.
    """
    g = [1.0] * len(signale)
    if not entdoppeln_an(cfg):
        return g

    for i, s in enumerate(signale):
        if s.get("meldet_anzeichen"):
            g[i] = 0.0

    gruppen = {}
    for i, s in enumerate(signale):
        if g[i] > 0 and s.get("ereignis"):
            gruppen.setdefault(s["ereignis"], []).append(i)
    for glieder in gruppen.values():
        bestes = min(glieder, key=lambda i: (-float(signale[i].get("staerke", 0)),
                                             str(signale[i].get("datum", "")),
                                             str(signale[i].get("titel", ""))))
        for i in glieder:
            if i != bestes:
                g[i] = 0.0

    beta = float(cfg["entdoppeln"].get("buendel_exponent", 0.0))
    buendel = {}
    for i, s in enumerate(signale):
        if g[i] > 0 and s.get("richtung") in WIRKSAM:
            schluessel = (tuple(sorted(set(s.get("treiber_ids", [])))), str(s.get("datum", ""))[:7])
            buendel.setdefault(schluessel, []).append(i)
    for glieder in buendel.values():
        for i in glieder:
            g[i] = g[i] * len(glieder) ** -beta
    return g


# --- Untergrenze und Posterior -------------------------------------------------

def untergrenze(werte: dict, p_min: float, summe: float = 100.0) -> dict:
    """Auf summe normieren; was unter p_min liegt, wird p_min, der Rest skaliert.

    Wiederholt, bis keines mehr darunter liegt (bei jedem Schritt kommt
    mindestens ein Szenario dazu, also hoechstens so viele Schritte wie
    Szenarien). Liegt nichts darunter, ist es die reine Normierung.
    """
    if p_min * len(werte) > summe:
        raise ValueError(f"Untergrenze {p_min} mal {len(werte)} Szenarien liegt ueber {summe}")
    fest = set()
    while True:
        frei = [k for k in werte if k not in fest]
        rest = summe - p_min * len(fest)
        gesamt = sum(werte[k] for k in frei)
        skaliert = ({k: werte[k] * rest / gesamt for k in frei} if gesamt > 0
                    else {k: rest / len(frei) for k in frei})
        darunter = [k for k, v in skaliert.items() if v < p_min]
        if not darunter:
            return {k: (p_min if k in fest else skaliert[k]) for k in werte}
        fest.update(darunter)


def posterior(prior: dict, log_lr: dict, p_min: float) -> dict:
    """Prior (Prozent) mal exp(Summe der gewichteten log-Likelihoods), mit Untergrenze."""
    roh = {s: prior[s] * math.exp(log_lr[s]) for s in prior}
    return untergrenze(roh, p_min)


# --- Basis fuer das ungerundete Rechnen -----------------------------------------

def basis(model: dict, journal: list, cfg: dict) -> tuple:
    """P_U je Horizont (aus dem Journal) und die Signale seit dem Urteil U."""
    u = cfg["ungerundet"]
    eintrag = next((e for e in journal if e["version"] == u["basis_version"]), None)
    if eintrag is None:
        raise ValueError(f"basis_version {u['basis_version']} fehlt im Prognose-Journal")
    p_u = eintrag["wahrscheinlichkeiten"]
    sids = {s["id"] for s in model["szenarien"]}
    for h, werte in p_u.items():
        if set(werte) != sids:
            raise ValueError(f"Die Szenarien von {u['basis_version']} ({h}) sind nicht die des Modells; "
                             "nach einer Neu-Ermittlung basis_version und basis_signale neu setzen")
    signale = model.get("signale", [])
    if u["basis_signale"] > len(signale):
        raise ValueError(f"basis_signale {u['basis_signale']} ist groesser als die Zahl der Signale ({len(signale)})")
    return p_u, signale[u["basis_signale"]:]


def oeffentlicher_block(model: dict, journal: list | None, cfg: dict) -> dict | None:
    """Der Block 'zufluss' fuer exports/weltmodell.json; None, wenn alles aus ist.

    Signale ohne Titel und Quelle: der Tagesstand braucht nur, was rechnet.
    """
    if not aktiv(cfg):
        return None
    block = {"entdoppeln": {k: v for k, v in (cfg.get("entdoppeln") or {}).items()
                            if k in ("an", "buendel_exponent")},
             "ungerundet": {k: v for k, v in (cfg.get("ungerundet") or {}).items()
                            if k in ("an", "p_min_prozent", "basis_version")}}
    if ungerundet_an(cfg):
        p_u, seit = basis(model, journal or [], cfg)
        block["p_basis"] = p_u
        block["signale"] = [{k: s[k] for k in ("datum", "treiber_ids", "richtung", "staerke",
                                                "ereignis", "meldet_anzeichen") if k in s}
                            for s in seit]
    return block
