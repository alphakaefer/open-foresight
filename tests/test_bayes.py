"""Bayes-Update: bewegt es die Wahrscheinlichkeiten in die richtige Richtung?"""
import pytest

from engine.bayes import largest_remainder, likelihood_ratios, update_probabilities
from engine.io import load_all


@pytest.fixture(scope="module")
def daten():
    return load_all()


def test_k_null_bewegt_nichts(daten):
    model, _, _ = daten
    sig = [{"datum": "2026-09-01", "titel": "Testsignal", "treiber_ids": ["T1"],
            "richtung": "bestaetigend", "staerke": 5}]
    res = update_probabilities(model, sig, k=0.0)
    assert all(d == 0 for diff in res["diff"].values() for d in diff.values())


def test_richtung_neu_bewegt_nichts(daten):
    model, _, _ = daten
    sig = [{"datum": "2026-09-01", "titel": "Unklassifiziert", "treiber_ids": ["T1"],
            "richtung": "neu", "staerke": 5}]
    res = update_probabilities(model, sig, k=0.5)
    assert all(d == 0 for diff in res["diff"].values() for d in diff.values())


def test_bestaetigendes_signal_hebt_stark_gekoppeltes_szenario(daten):
    model, _, _ = daten
    kopplung = model["treiber_kopplung"]["T1"]
    stark = max(kopplung, key=kopplung.get)
    schwach = min(kopplung, key=kopplung.get)
    sig = [{"datum": "2026-09-01", "titel": "T1 bestaetigt", "treiber_ids": ["T1"],
            "richtung": "bestaetigend", "staerke": 5}]
    res = update_probabilities(model, sig, k=0.3)
    h = model["meta"]["horizonte"][0]
    assert res["diff"][h][stark] >= res["diff"][h][schwach]


def test_widerspruch_kehrt_die_richtung_um(daten):
    model, _, _ = daten
    basis = {"datum": "2026-09-01", "titel": "T1", "treiber_ids": ["T1"], "staerke": 4}
    hoch = update_probabilities(model, [dict(basis, richtung="bestaetigend")], k=0.3)
    runter = update_probabilities(model, [dict(basis, richtung="widersprechend")], k=0.3)
    h = model["meta"]["horizonte"][0]
    sid = max(model["treiber_kopplung"]["T1"], key=model["treiber_kopplung"]["T1"].get)
    assert hoch["diff"][h][sid] > 0 > runter["diff"][h][sid]


def test_summe_bleibt_hundert(daten):
    model, _, _ = daten
    sig = [{"datum": "2026-09-01", "titel": "A", "treiber_ids": ["T1", "M3"],
            "richtung": "bestaetigend", "staerke": 3},
           {"datum": "2026-09-02", "titel": "B", "treiber_ids": ["G1"],
            "richtung": "widersprechend", "staerke": 2}]
    res = update_probabilities(model, sig, k=0.2)
    for h, post in res["posterior"].items():
        assert sum(post.values()) == 100, f"Horizont {h}"


def test_likelihood_ist_eins_ohne_kopplung(daten):
    model, _, _ = daten
    sig = {"treiber_ids": ["gibt-es-nicht"], "richtung": "bestaetigend", "staerke": 5}
    lr = likelihood_ratios(sig, model["treiber_kopplung"], ["S01"], k=0.3)
    assert lr["S01"] == pytest.approx(1.0)


def test_groesste_reste_verteilt_korrekt():
    assert sum(largest_remainder({"a": 1, "b": 1, "c": 1}, 100).values()) == 100
    assert sum(largest_remainder({"a": 33.3, "b": 33.3, "c": 33.4}, 100).values()) == 100
