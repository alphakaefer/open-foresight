"""Zweitrechnung Bayes-Schritt (RA1): LR und Rundung aus engine und aus der Spezifikation allein.

Der Test baut 200 zufaellige Eingaben (fester Seed, 2 bis 12 Szenarien,
1 bis 5 Treiber mit Kopplungen in [-1, 1], Richtung aus bestaetigend /
widersprechend / neutral / neu, Staerke 1 bis 5, k in [0; 0,5]) und vergleicht
likelihood_ratios aus beiden Rechnungen auf 1e-9. Die Rundung mit groessten
Resten stimmt exakt (dict-Gleichheit), ihre Summe ist immer exakt 100, alle
Werte ganzzahlig. Und: Die Reihenfolge der Signale aendert den Posterior nicht.
"""
import importlib.util
import random
from pathlib import Path

import pytest

from engine import bayes as ba

_HIER = Path(__file__).resolve().parent
_ZWEIT = _HIER.parent / "pruefung" / "zweitrechnung" / "bayes_zweit.py"
_spec = importlib.util.spec_from_file_location("bayes_zweit", _ZWEIT)
bz = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bz)

TOL = 1e-9


def _eingabe(rnd):
    n = rnd.randint(2, 12)
    sids = [f"S{i}" for i in range(n)]
    nt = rnd.randint(1, 5)
    treiber = [f"T{i}" for i in range(nt)]
    kopplung = {t: {s: rnd.uniform(-1.0, 1.0) for s in sids} for t in treiber}
    richtungen = ["bestaetigend", "widersprechend", "neutral", "neu"]
    signal = {
        "richtung": richtungen[rnd.randrange(4)],
        "staerke": rnd.randint(1, 5),
        "treiber_ids": treiber[: rnd.randint(1, nt)],
    }
    k = rnd.uniform(0.0, 0.5)
    return sids, kopplung, signal, k


def test_200_zufaellige_eingaben():
    rnd = random.Random(20261030)
    for _ in range(200):
        sids, kopplung, signal, k = _eingabe(rnd)
        lr1 = ba.likelihood_ratios(signal, kopplung, sids, k)
        lr2 = bz.lr_zweit(signal, kopplung, sids, k)
        for sid in sids:
            assert lr1[sid] == pytest.approx(lr2[sid], abs=TOL), (sid, lr1[sid], lr2[sid])
        werte = {sid: rnd.uniform(0.5, 10.0) for sid in sids}
        r1 = ba.largest_remainder(werte, 100)
        r2 = bz.largest_remainder_zweit(werte, 100)
        assert r1 == r2
        assert sum(r2.values()) == 100
        assert all(float(v).is_integer() for v in r2.values())


def test_summe_immer_100_und_reihenfolge_gleichgueltig():
    rnd = random.Random(20261031)
    for _ in range(20):
        sids, kopplung, _, k = _eingabe(rnd)
        richtungen = ["bestaetigend", "widersprechend", "neutral", "neu"]
        signale = [
            {
                "richtung": richtungen[rnd.randrange(4)],
                "staerke": rnd.randint(1, 5),
                "treiber_ids": list(kopplung),
            }
            for _ in range(5)
        ]
        prior = {sid: rnd.uniform(1.0, 10.0) for sid in sids}
        ps = sum(prior.values())
        prior = {sid: prior[sid] * 100.0 / ps for sid in sids}

        def posterior(liste):
            prod = {sid: 1.0 for sid in sids}
            for sg in liste:
                lr = bz.lr_zweit(sg, kopplung, sids, k)
                for sid in sids:
                    prod[sid] *= lr[sid]
            roh = {sid: prior[sid] * prod[sid] for sid in sids}
            return bz.largest_remainder_zweit(roh, 100)

        p1 = posterior(signale)
        p2 = posterior(list(reversed(signale)))
        assert sum(p1.values()) == 100
        assert all(float(v).is_integer() for v in p1.values())
        assert p1 == p2
