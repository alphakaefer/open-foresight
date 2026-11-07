"""Bayes-Update der Szenariowahrscheinlichkeiten.

Ehrliche Vorbemerkung: Bayes entfernt das Urteil nicht, es verschiebt es an eine
sichtbare Stelle. Frueher hiess es "ich habe S03 etwas hochgesetzt". Jetzt steht
je Signal eine Likelihood pro Szenario, die aus zwei dokumentierten Groessen
folgt: der Signalstaerke und der Kopplung der betroffenen Treiber an das Szenario.
Der einzige freie Parameter ist die Daempfung k. k = 0 schaltet das Update ab.

Likelihood eines Signals fuer Szenario s:

    LR(s) = exp( k * richtung * staerke * mittlere_kopplung(treiber_ids, s) )

Posterior:

    P'(s) proportional zu P(s) * LR(s), danach auf 100 normiert.

Ein Signal, das Treiber bestaetigt, die stark in ein Szenario hineinspielen,
hebt dessen Wahrscheinlichkeit. Ein widersprechendes Signal senkt sie.
"""
from __future__ import annotations

import math

from .zufluss import aktiv as zufluss_aktiv, gewichte, posterior as zufluss_posterior, ungerundet_an

RICHTUNG = {"bestaetigend": 1.0, "widersprechend": -1.0, "neutral": 0.0, "neu": 0.0}
"""Ein noch nicht eingeordnetes Signal (richtung "neu") bewegt nichts. Es soll
auffallen und eingeordnet werden, nicht still wirken."""


def coupling_mean(signal: dict, kopplung: dict, scenario_id: str) -> float:
    """Mittlere Kopplung der im Signal genannten Treiber an ein Szenario."""
    vals = [kopplung[t][scenario_id] for t in signal.get("treiber_ids", [])
            if t in kopplung and scenario_id in kopplung[t]]
    return sum(vals) / len(vals) if vals else 0.0


def likelihood_ratios(signal: dict, kopplung: dict, scenario_ids: list, k: float) -> dict:
    """Likelihood-Verhaeltnis je Szenario fuer ein Signal."""
    direction = RICHTUNG.get(signal.get("richtung", "neutral"), 0.0)
    strength = float(signal.get("staerke", 0))
    return {
        sid: math.exp(k * direction * strength * coupling_mean(signal, kopplung, sid))
        for sid in scenario_ids
    }


def largest_remainder(values: dict, total: int = 100) -> dict:
    """Rundet auf ganze Zahlen, deren Summe exakt total ergibt."""
    scaled = {k: v * total / sum(values.values()) for k, v in values.items()}
    floors = {k: math.floor(v) for k, v in scaled.items()}
    rest = total - sum(floors.values())
    order = sorted(scaled, key=lambda k: scaled[k] - floors[k], reverse=True)
    for k in order[:rest]:
        floors[k] += 1
    return floors


def log_likelihoods(signal: dict, kopplung: dict, scenario_ids: list, k: float) -> dict:
    """log LR je Szenario, ohne den Umweg ueber exp und log."""
    direction = RICHTUNG.get(signal.get("richtung", "neutral"), 0.0)
    strength = float(signal.get("staerke", 0))
    return {sid: k * direction * strength * coupling_mean(signal, kopplung, sid)
            for sid in scenario_ids}


def update_probabilities(model: dict, signals: list, k: float, zufluss: dict | None = None,
                         prior_exakt: dict | None = None) -> dict:
    """Neue Wahrscheinlichkeiten je Horizont plus Nachweis je Signal.

    Gibt zurueck: {"posterior": {horizont: {szenario: prozent}},
                   "beitraege": [{signal, lr_je_szenario}],
                   "diff": {horizont: {szenario: delta_prozentpunkte}}}

    zufluss: die Schalter aus data/datenzufluss.json (Spezifikation 7a). Sind
    beide aus oder fehlt er, rechnet die Funktion genau wie bis v1.4.0.
    prior_exakt: {horizont: {szenario: prozent}}, ungerundeter Prior statt der
    ganzen Zahlen im Modell (nur mit ungerundet an).
    """
    if zufluss_aktiv(zufluss):
        return _update_zufluss(model, signals, k, zufluss, prior_exakt)
    scenarios = model["szenarien"]
    sids = [s["id"] for s in scenarios]
    kopplung = model["treiber_kopplung"]
    horizons = model["meta"]["horizonte"]

    contributions = []
    combined = {sid: 1.0 for sid in sids}
    for sig in signals:
        lr = likelihood_ratios(sig, kopplung, sids, k)
        for sid in sids:
            combined[sid] *= lr[sid]
        contributions.append({
            "datum": sig.get("datum"),
            "titel": sig.get("titel"),
            "quelle_url": sig.get("quelle_url"),
            "treiber_ids": sig.get("treiber_ids", []),
            "richtung": sig.get("richtung"),
            "staerke": sig.get("staerke"),
            "likelihood": {sid: round(v, 4) for sid, v in lr.items()},
        })

    posterior, diff = {}, {}
    for h in horizons:
        prior = {s["id"]: s["wahrscheinlichkeit"][h] for s in scenarios}
        raw = {sid: prior[sid] * combined[sid] for sid in sids}
        post = largest_remainder(raw, 100) if sum(raw.values()) > 0 else prior
        posterior[h] = post
        diff[h] = {sid: post[sid] - prior[sid] for sid in sids}

    return {"posterior": posterior, "beitraege": contributions, "diff": diff,
            "k_daempfung": k}


def _update_zufluss(model: dict, signals: list, k: float, cfg: dict, prior_exakt: dict | None) -> dict:
    """Der Weg mit Entdoppeln und/oder ungerundetem Rechnen (Spezifikation 7a).

    Der Posterior ist P(s) * prod LR_i(s) ** g_i, mit Untergrenze, wenn
    ungerundet an ist. diff misst gegen die ganzen Zahlen im Modell, also
    gegen das, was als Basis angezeigt wird.
    """
    scenarios = model["szenarien"]
    sids = [s["id"] for s in scenarios]
    kopplung = model["treiber_kopplung"]
    horizons = model["meta"]["horizonte"]
    g = gewichte(signals, cfg)
    p_min = float(cfg["ungerundet"].get("p_min_prozent", 0.0)) if ungerundet_an(cfg) else 0.0

    log_lr = {sid: 0.0 for sid in sids}
    contributions = []
    for sig, gi in zip(signals, g):
        einzel = log_likelihoods(sig, kopplung, sids, k)
        for sid in sids:
            log_lr[sid] += gi * einzel[sid]
        contributions.append({
            "datum": sig.get("datum"),
            "titel": sig.get("titel"),
            "quelle_url": sig.get("quelle_url"),
            "treiber_ids": sig.get("treiber_ids", []),
            "richtung": sig.get("richtung"),
            "staerke": sig.get("staerke"),
            **({"ereignis": sig["ereignis"]} if sig.get("ereignis") else {}),
            "gewicht": round(gi, 4),
            "likelihood": {sid: round(math.exp(v), 4) for sid, v in einzel.items()},
        })

    posterior, diff, exakt = {}, {}, {}
    for h in horizons:
        basis = {s["id"]: s["wahrscheinlichkeit"][h] for s in scenarios}
        prior = prior_exakt[h] if prior_exakt else basis
        if ungerundet_an(cfg):
            exakt[h] = zufluss_posterior(prior, log_lr, p_min)
            post = largest_remainder(exakt[h], 100)
        else:
            raw = {sid: prior[sid] * math.exp(log_lr[sid]) for sid in sids}
            post = largest_remainder(raw, 100) if sum(raw.values()) > 0 else dict(prior)
        posterior[h] = post
        diff[h] = {sid: post[sid] - basis[sid] for sid in sids}

    aus = {"posterior": posterior, "beitraege": contributions, "diff": diff, "k_daempfung": k}
    if exakt:
        aus["posterior_exakt"] = {h: {sid: round(v, 6) for sid, v in w.items()} for h, w in exakt.items()}
    return aus


def apply_posterior(model: dict, posterior: dict) -> dict:
    """Schreibt die neuen Wahrscheinlichkeiten ins Modell. Gibt das Modell zurueck."""
    for s in model["szenarien"]:
        for h, values in posterior.items():
            if s["id"] in values:
                s["wahrscheinlichkeit"][h] = values[s["id"]]
    return model
