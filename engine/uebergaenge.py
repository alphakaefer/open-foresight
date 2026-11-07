"""Uebergaenge zwischen Szenarien: Verweildauern und Ausgaenge als Markov-Kette.

Schritt 2 aus docs/review-2026-10.md. Hier steht nur die Rechnung, die Karls
Urteile in data/uebergaenge.json pruefbar macht; in run_update haengt nichts
davon, keine Modellzahl aendert sich. Ob und wie die Matrix die Horizonte
bindet, entscheidet die Strukturpruefung (Termin legt Karl fest).

Stetige Zeit, Raten pro Jahr:

    Q_ii = -1 / V_i,   Q_ij = a_ij / V_i,   sum_j a_ij = 1,   P(t) = exp(t Q)

V_i ist die mittlere Verweildauer in Szenario i (Jahre), a_ij der Anteil der
Ausgaenge nach j. Karl nennt je Szenario zwei bis drei Hauptausgaenge mit
Anteil; der Rest verteilt sich auf die uebrigen Szenarien anteilig nach
rest_gewichte (Vorschlag: mittlere Wahrscheinlichkeit ueber die Horizonte).

P(t) ueber Uniformisierung, nur Standardbibliothek: laeuft auch dort, wo es
kein numpy gibt.
"""
from __future__ import annotations

import math

TOLERANZ = 1e-15


# --- Generator -------------------------------------------------------------------

def generator(sids: list, verweildauer: dict, ausgaenge: dict, rest_gewichte: dict | None = None) -> list:
    """Q als Liste von Zeilen in der Reihenfolge von sids.

    verweildauer: {sid: Jahre}; math.inf heisst, die Welt bleibt (Zeile 0).
    ausgaenge: {sid: {nach: anteil}}, Summe hoechstens 1; der Rest geht an die
    uebrigen Szenarien anteilig nach rest_gewichte (ohne Angabe gleich).
    """
    n = len(sids)
    idx = {s: i for i, s in enumerate(sids)}
    gew = rest_gewichte or {s: 1.0 for s in sids}
    q = [[0.0] * n for _ in range(n)]
    for s in sids:
        v = verweildauer[s]
        if v is None or v <= 0:
            raise ValueError(f"{s}: Verweildauer muss positiv sein, nicht {v}")
        if math.isinf(v):
            continue
        haupt = ausgaenge.get(s) or {}
        if s in haupt:
            raise ValueError(f"{s}: ein Ausgang nach sich selbst ist kein Ausgang")
        if any(a < 0 for a in haupt.values()):
            raise ValueError(f"{s}: negativer Anteil")
        summe = sum(haupt.values())
        if summe > 1 + 1e-9:
            raise ValueError(f"{s}: Hauptausgaenge zusammen {summe:.2f}, mehr als 1")
        anteil = {j: a for j, a in haupt.items()}
        rest = max(0.0, 1.0 - summe)
        uebrige = [j for j in sids if j != s and j not in haupt]
        g = sum(gew.get(j, 0.0) for j in uebrige)
        if rest > 1e-12:
            if g <= 0:
                raise ValueError(f"{s}: Rest {rest:.2f} hat kein Ziel")
            for j in uebrige:
                anteil[j] = anteil.get(j, 0.0) + rest * gew.get(j, 0.0) / g
        i = idx[s]
        for j, a in anteil.items():
            q[i][idx[j]] += a / v
        q[i][i] = -1.0 / v
    return q


# --- P(t) ------------------------------------------------------------------------

def _mal(a: list, b: list) -> list:
    n, m = len(a), len(b[0])
    bt = list(zip(*b))
    return [[sum(x * y for x, y in zip(a[i], bt[j])) for j in range(m)] for i in range(n)]


def einheit(n: int) -> list:
    return [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]


def uebergang(q: list, t: float) -> list:
    """P(t) = exp(tQ) ueber Uniformisierung: sum_k Poisson(k; lt) K^k mit K = I + Q/l.

    Fuer grosses l*t wird erst P(t / 2^m) gerechnet und dann m-mal quadriert;
    so bleibt die Poisson-Summe kurz und e^(-lt) unterlaeuft nicht.
    """
    n = len(q)
    lam = max((-q[i][i] for i in range(n)), default=0.0)
    if lam == 0 or t == 0:
        return einheit(n)
    m = max(0, math.ceil(math.log2(lam * t / 4.0))) if lam * t > 4.0 else 0
    tau = t / 2 ** m
    k_matrix = [[(1.0 if i == j else 0.0) + q[i][j] / lam for j in range(n)] for i in range(n)]
    lt = lam * tau
    gewicht = math.exp(-lt)
    potenz = einheit(n)
    p = [[gewicht * x for x in zeile] for zeile in potenz]
    summe, k = gewicht, 0
    while 1.0 - summe > TOLERANZ and k < 1000:
        k += 1
        potenz = _mal(potenz, k_matrix)
        gewicht *= lt / k
        summe += gewicht
        for i in range(n):
            for j in range(n):
                p[i][j] += gewicht * potenz[i][j]
    for _ in range(m):
        p = _mal(p, p)
    return p


def weiter(p: list, matrix: list) -> list:
    """Zeilenvektor mal Matrix: die Verteilung nach dem Uebergang."""
    return [sum(p[i] * matrix[i][j] for i in range(len(p))) for j in range(len(matrix[0]))]


# --- Langfristig -------------------------------------------------------------------

def stationaer(q: list) -> list:
    """pi mit pi Q = 0 und Summe 1 (Gauss mit Spaltenpivot).

    Ist die Kette nicht irreduzibel, gibt es mehrere Loesungen; dann ValueError.
    """
    n = len(q)
    # Gleichungen: Q^T pi = 0, die letzte ersetzt durch sum pi = 1.
    a = [[q[j][i] for j in range(n)] + [0.0] for i in range(n)]
    a[-1] = [1.0] * n + [1.0]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(a[r][c]))
        if abs(a[piv][c]) < 1e-12:
            raise ValueError("Die Kette hat keine eindeutige langfristige Verteilung (nicht irreduzibel)")
        a[c], a[piv] = a[piv], a[c]
        for r in range(n):
            if r != c and a[r][c] != 0:
                f = a[r][c] / a[c][c]
                a[r] = [x - f * y for x, y in zip(a[r], a[c])]
    return [a[i][n] / a[i][i] for i in range(n)]


# --- Gegenprobe Horizonte -----------------------------------------------------------

def relative_entropie(p: list, q: list) -> float:
    aus = 0.0
    for pi, qi in zip(p, q):
        if pi > 0:
            if qi <= 0:
                return math.inf
            aus += pi * math.log(pi / qi)
    return aus


def horizont_konsistenz(sids: list, wahrscheinlichkeiten: dict, q: list) -> list:
    """Je Horizontpaar: p_vorher P(Abstand) gegen das gesetzte p_h.

    wahrscheinlichkeiten: {jahr: {sid: prozent}}. Gibt je spaeterem Horizont
    D(p_h || p_dach_h), die groesste Abweichung in Punkten und p_dach_h zurueck.
    """
    jahre = sorted(wahrscheinlichkeiten, key=int)
    aus = []
    for vor, nach in zip(jahre, jahre[1:]):
        p_vor = [wahrscheinlichkeiten[vor][s] / 100 for s in sids]
        p_nach = [wahrscheinlichkeiten[nach][s] / 100 for s in sids]
        dach = weiter(p_vor, uebergang(q, int(nach) - int(vor)))
        abw = {s: 100 * (a - b) for s, a, b in zip(sids, p_nach, dach)}
        groesste = max(abw, key=lambda s: abs(abw[s]))
        aus.append({"von": vor, "nach": nach, "D": relative_entropie(p_nach, dach),
                    "groesste_abweichung": {"szenario": groesste, "punkte": round(abw[groesste], 1)},
                    "p_dach": {s: round(100 * x, 1) for s, x in zip(sids, dach)}})
    return aus


def mindestwechsel(wahrscheinlichkeiten: dict) -> list:
    """Wie viel Welt muss zwischen zwei Horizonten mindestens das Szenario wechseln?

    Fuer jede gemeinsame Verteilung zweier Zeitpunkte mit diesen Randverteilungen
    gilt P(S_vorher != S_nachher) >= 1/2 sum |p_nachher - p_vorher|
    (Kopplungsungleichung). Das folgt aus den Horizonten allein, ohne Urteil.
    """
    jahre = sorted(wahrscheinlichkeiten, key=int)
    aus = []
    for vor, nach in zip(jahre, jahre[1:]):
        ids = set(wahrscheinlichkeiten[vor]) | set(wahrscheinlichkeiten[nach])
        tv = sum(abs(wahrscheinlichkeiten[nach].get(s, 0) - wahrscheinlichkeiten[vor].get(s, 0)) for s in ids) / 2
        aus.append({"von": vor, "nach": nach, "prozent": round(tv, 1)})
    return aus


def enthaelt_vorschlaege(vorlage: dict) -> bool:
    """True, wenn ein Wert der Vorlage als Vorschlag markiert ist (nicht Karls Urteil)."""
    return any(z.get("vorschlag") or any(a.get("vorschlag") for a in z.get("hauptausgaenge", []))
               for z in vorlage.get("szenarien", []))


def aus_vorlage(model: dict, vorlage: dict, vorschlaege: bool = False) -> tuple:
    """(sids, Q) aus data/uebergaenge.json; ValueError, solange etwas fehlt.

    Werte mit vorschlag: true sind nicht Karls Urteil. Sie rechnen nur mit
    vorschlaege=True, also in Pruefungen und Proben, die das Ergebnis als
    vorlaeufig kennzeichnen, nie im oeffentlichen Tagesstand.
    """
    sids = [s["id"] for s in model["szenarien"]]
    zeilen = {z["id"]: z for z in vorlage["szenarien"]}
    if set(zeilen) != set(sids):
        raise ValueError("Die Vorlage passt nicht zu den Szenarien des Modells")
    if not vorschlaege and enthaelt_vorschlaege(vorlage):
        raise ValueError("Die Uebergaenge sind ein Vorschlag (vorschlag: true); Karl legt sie fest. "
                         "Fuer eine vorlaeufige Rechnung vorschlaege=True setzen")
    fehlt = [s for s in sids if zeilen[s].get("verweildauer_jahre") is None]
    if fehlt:
        raise ValueError(f"Verweildauer fehlt fuer {len(fehlt)} von {len(sids)} Szenarien: {', '.join(fehlt)}")
    verweil = {s: float(zeilen[s]["verweildauer_jahre"]) for s in sids}
    ausg = {s: {a["nach"]: float(a["anteil"]) for a in zeilen[s].get("hauptausgaenge", [])
                if a.get("nach") and a.get("anteil") is not None} for s in sids}
    horizonte = model["meta"]["horizonte"]
    gew = {s["id"]: sum(s["wahrscheinlichkeit"][h] for h in horizonte) / len(horizonte) for s in model["szenarien"]}
    return sids, generator(sids, verweil, ausg, gew)
