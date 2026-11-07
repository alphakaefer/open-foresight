"""Energy-transition domain: the bottleneck model reproduces the upstream reference values."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("lens", ROOT / "domains" / "lens.py")
lens = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lens)

DOMAIN = json.loads((ROOT / "domains" / "energy-transition" / "domain.json").read_text(encoding="utf-8"))
BM = DOMAIN["bottleneck_model"]
REF = BM["reference_values"]


def test_ces_reference_values():
    x = [a["state_2026"] for a in BM["axes"]]
    assert round(lens.ces(x[:4], BM["rho"]), 4) == REF["usability_4_axes_ces"]
    assert round(sum(x[:4]) / 4, 4) == REF["usability_4_axes_linear"]
    assert round(lens.ces(x, BM["rho"]), 4) == REF["usability_5_axes_ces"]


def test_ces_is_dominated_by_the_weakest_axis():
    assert lens.ces([1.0, 1.0, 0.1], -3.0) < 0.2
    assert lens.ces([0.5, 0.5, 0.5], -3.0) == pytest.approx(0.5)


def test_permitting_is_the_binding_bottleneck():
    b = lens.bottleneck(BM)
    assert b["binding_bottleneck"] == "permitting"
    assert [g["gain_percent"] for g in b["marginal_gain"]] == sorted((g["gain_percent"] for g in b["marginal_gain"]), reverse=True)


def test_briefing_builds_and_links_exist():
    b = lens.briefing(ROOT / "domains" / "energy-transition")
    assert not [d for d in b["drivers"] if "error" in d]
    assert not [s for s in b["series"] if "error" in s]
    for h in DOMAIN["horizons"]:
        assert sum(b["scenarios"]["energy_price_mass"][h].values()) == 100
