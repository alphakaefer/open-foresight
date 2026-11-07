"""Committor (Spezifikation 12): auf welche Seite kippt es? Hinter Schalter.

q(s) = P_s(zuerst B, dann A); q|A = 0, q|B = 1, (Qq)(s) = 0 sonst.
Heute q0 = sum pi(s) q(s); Hebel eines Anzeichens dq = sum (pi_i - pi) q mit
pi_i proportional zu pi * LR_i. Nur Standardbibliothek.
"""
from __future__ import annotations

from .bayes import likelihood_ratios

PASS = 0.15


def committor(sids: list, q: list, a: list, b: list) -> dict:
    """{sid: q} ueber Gauss mit Spaltenpivot; ValueError, wenn A u B nicht ueberall erreichbar ist."""
    a, b = set(a), set(b)
    if not a or not b or a & b or not (a | b) <= set(sids):
        raise ValueError("A und B muessen disjunkte, nichtleere Mengen von Szenarien sein")
    idx = {s: i for i, s in enumerate(sids)}
    frei = [s for s in sids if s not in a | b]
    n = len(frei)
    m = []
    for s in frei:
        i = idx[s]
        zeile = [q[i][idx[t]] for t in frei]
        rechts = -sum(q[i][idx[t]] for t in b)
        m.append(zeile + [rechts])
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(m[r][c]))
        if abs(m[piv][c]) < 1e-12:
            raise ValueError("A oder B ist nicht von jedem Szenario aus erreichbar; der Committor ist nicht bestimmt")
        m[c], m[piv] = m[piv], m[c]
        for r in range(n):
            if r != c and m[r][c] != 0:
                f = m[r][c] / m[c][c]
                m[r] = [x - f * y for x, y in zip(m[r], m[c])]
    aus = {s: 0.0 for s in a}
    aus.update({s: 1.0 for s in b})
    for r, s in enumerate(frei):
        aus[s] = min(1.0, max(0.0, m[r][n] / m[r][r]))
    return {s: aus[s] for s in sids}


def heute(pi: dict, qwerte: dict) -> float:
    summe = sum(pi.values())
    return sum(pi[s] * qwerte[s] for s in qwerte) / summe


def hebel(model: dict, anzeichen: list, pi: dict, qwerte: dict, k: float) -> list:
    """Je Anzeichen mit Wirkung: Aenderung von q0, wenn es eintritt; nach |dq| geordnet."""
    sids = list(qwerte)
    q0 = heute(pi, qwerte)
    aus = []
    for a in anzeichen:
        w = a.get("wirkung")
        if not w:
            continue
        lr = likelihood_ratios(w, model["treiber_kopplung"], sids, k)
        neu = {s: pi[s] * lr[s] for s in sids}
        aus.append({"anzeichen": a["id"], "text": a["text"], "delta_q": round(heute(neu, qwerte) - q0, 4)})
    return sorted(aus, key=lambda x: -abs(x["delta_q"]))


def auswertung(model: dict, q: list, paar: dict, pi: dict, anzeichen: list, k: float, vorlaeufig: bool) -> dict:
    """Ausgabe im festen Schema der Spezifikation 12."""
    sids = [s["id"] for s in model["szenarien"]]
    qw = committor(sids, q, paar["A"], paar["B"])
    return {"vorlaeufig": bool(vorlaeufig),
            "paar": {"id": paar["id"], "A": list(paar["A"]), "B": list(paar["B"])},
            "q": {s: round(x, 4) for s, x in qw.items()},
            "q0": round(heute(pi, qw), 4),
            "paesse": [s for s in sids if s not in set(paar["A"]) | set(paar["B"]) and abs(qw[s] - 0.5) < PASS],
            "hebel": hebel(model, anzeichen, pi, qw, k)}
