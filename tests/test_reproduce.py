"""Reproducibility: public model + public radar snapshot -> the published world state.

radar/snapshot/weltlage.json was computed by the live radar (zukunftsgut.org) from
model/world_model.de.json and radar/snapshot/wissensstand.json. Recomputing it here
must give the same scenario probabilities, driver states and indicator states.

Only two things may differ:
- 'stand' (the timestamp of the run),
- 'treffer' of statement indicators: the news hits shown to humans next to a
  statement. They move no probability. The snapshot in this repo omits news
  teaser texts (copyright), so a few text matches can be missing.
"""
from datetime import datetime

import pytest

from engine import io
from engine.tagesstand import tagesstand

SNAP = io.RADAR_SNAPSHOT


@pytest.fixture(scope="module")
def recomputed():
    published = io.load_json(SNAP / "weltlage.json")
    now = datetime.fromisoformat(published["stand"].replace("Z", "+00:00"))
    lage = tagesstand(io.load_world_model("de"), io.load_json(SNAP / "wissensstand.json"), now)
    return published, lage


def test_scenario_probabilities_are_reproduced(recomputed):
    published, lage = recomputed
    assert lage["basis"] == published["basis"]
    assert lage["szenarien"] == published["szenarien"]


def test_drivers_and_signals_are_reproduced(recomputed):
    published, lage = recomputed
    assert lage["treiber"] == published["treiber"]
    assert lage["signale"] == published["signale"]


def test_indicator_states_are_reproduced(recomputed):
    published, lage = recomputed
    strip = lambda a: {k: v for k, v in a.items() if k != "treffer"}  # noqa: E731
    assert [strip(a) for a in lage["anzeichen"]] == [strip(a) for a in published["anzeichen"]]


def test_everything_else_is_reproduced(recomputed):
    published, lage = recomputed
    skip = {"stand", "anzeichen"}
    assert {k: v for k, v in lage.items() if k not in skip} == {k: v for k, v in published.items() if k not in skip}


def test_probabilities_sum_to_100_per_horizon(recomputed):
    _, lage = recomputed
    for h in lage["horizonte"]:
        assert sum(s["p_tag"][h] for s in lage["szenarien"]) == 100


def test_public_model_has_no_private_sections():
    w = io.load_world_model("de")
    for key in ("optionen", "scoring", "segmentmischung", "meine_lage", "energiebeispiel_v12"):
        assert key not in w
