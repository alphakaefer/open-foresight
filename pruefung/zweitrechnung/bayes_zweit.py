"""Zweitrechnung Bayes-Schritt (RA1): LR und Rundung ein zweites Mal gerechnet, aus model_spec.md allein.

Spezifikation 7 (Foresight-Modell), bis "Mehrere Signale, Horizonte,
Rundung": Die Likelihood eines Signals fuer Szenario s ist

    LR(s) = exp( k * d * sigma * c_mittel(s) ),

mit der Richtung d (+1 bestaetigend, -1 widersprechend, 0 neutral oder nicht
eingeordnet, auch "neu"), der Signalstaerke sigma (1 bis 5) und der mittleren
Kopplung c_mittel(s) der Treiber des Signals an das Szenario. Mehrere Signale
werden multipliziert, die Reihenfolge ist gleichgueltig. Der Posterior ist
P(s) * prod LR_i(s), normiert auf 100 mit dem Verfahren der groessten Reste:
Jeder Wert wird auf die Summe 100 hochskaliert, abgerundet, und die
verbleibenden ganzen Punkte gehen an die groessten Reste.

Bauweise (anders als engine/bayes.py): Die mittlere Kopplung wird je Szenario
in einer eigenen Schleife ueber die Treiber aufsummiert und erst am Ende
geteilt, nicht als Liste gefiltert und gemittelt; die Richtung wird je Signal
einmal in einer Tabelle nachgeschlagen.

Dieses Modul ist die unabhaengige Zweitrechnung: Es importiert nichts aus
engine/ und liest keine Datei; alles folgt der Spezifikation. Nur
Standardbibliothek.
"""

import math

RICHTUNG_ZWEIT = {"bestaetigend": 1.0, "widersprechend": -1.0, "neutral": 0.0, "neu": 0.0}


def lr_zweit(signal, kopplung, scenario_ids, k):
    """{sid: LR(s)} aus der Spezifikation allein; fehlende Richtung oder Staerke zaehlen 0."""
    d = RICHTUNG_ZWEIT.get(signal.get("richtung"), 0.0)
    sigma = float(signal.get("staerke", 0))
    aus = {}
    for sid in scenario_ids:
        summe = 0.0
        anzahl = 0
        for t in signal.get("treiber_ids", []):
            if t in kopplung and sid in kopplung[t]:
                summe += kopplung[t][sid]
                anzahl += 1
        mittel = summe / anzahl if anzahl else 0.0
        aus[sid] = math.exp(k * d * sigma * mittel)
    return aus


def largest_remainder_zweit(values, total=100):
    """Rundet auf ganze Zahlen mit Summe exakt total (Verfahren der groessten Reste)."""
    keys = list(values)
    s = sum(values[kk] for kk in keys)
    scaled = {kk: values[kk] * total / s for kk in keys}
    floors = {kk: math.floor(scaled[kk]) for kk in keys}
    rest = total - sum(floors.values())
    order = sorted(keys, key=lambda kk: scaled[kk] - floors[kk], reverse=True)
    for kk in order[:rest]:
        floors[kk] += 1
    return floors
