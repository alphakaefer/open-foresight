"""Tests for the number check. No API call. Run: python -B -m pytest -q -p no:cacheprovider test_check_numbers.py"""
import sys

sys.dont_write_bytecode = True

from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_numbers as cn  # noqa: E402
import explain_trace as et  # noqa: E402

MINI = {
    "meta": {"mode": "real data", "is_hypothetical": False, "k": 0.15, "horizons": ["2028", "2040"],
             "probability_floor_percent": 0.5, "world_state_date": "2026-11-07T11:16:17Z"},
    "scenarios": {"S04": {"name": "Stagflation"}, "S08": {"name": "Green Boom"}},
    "probabilities": {"2040": {"S04": {"before": 5, "after": 7, "after_unrounded": 6.53, "change_unrounded": 1.53},
                               "S08": {"before": 13, "after": 10, "after_unrounded": 9.57, "change_unrounded": -3.43}}},
    "big_changes": {"2040": {"S04": {"name": "Stagflation", "before": 5, "after": 7, "after_unrounded": 6.53,
                                     "change_unrounded": 1.53, "direction": "up"}}},
    "changed_indicators": [{"id": "A05", "text": "Brent above 110 $", "rule": "alle 7 > 110"}],
}


def expl(what="", item="Stagflation rises from 5 to 7.", notice=""):
    return {"hypothetical_notice": notice, "what_is_happening": what,
            "big_changes": [{"scenario_id": "S04", "horizon": "2040", "explanation": item}], "uncertainties": []}


def statuses(r):
    return {n["text"]: n["status"] for n in r["numbers"]}


def test_clean_passes():
    r = cn.check(MINI, expl("With k = 0.15 in 2040, nothing else moved. Data as of 2026-11-07."))
    assert r["passed"], r["failures"]


def test_invented_number_fails():
    r = cn.check(MINI, expl("Risk is now 17.3%."))
    assert not r["passed"] and statuses(r)["17.3"] == "NOT_IN_TRACE"


def test_more_precision_is_not_the_same_number():
    assert statuses(cn.check(MINI, expl("It ends at 6.5.")))["6.5"] == "NOT_IN_TRACE"
    assert statuses(cn.check(MINI, expl("It ends at 6.530.")))["6.530"] == "matched"


def test_identifiers_are_not_numbers():
    r = cn.check(MINI, expl("S04, A05, AS09, T8 and OE1 are identifiers."))
    assert not [n for n in r["numbers"] if n["field"] == "what_is_happening"]


def test_sign_dropped_and_wrong_sign():
    assert statuses(cn.check(MINI, expl("Green Boom fell by 3.43.")))["3.43"] == "matched_sign_dropped"
    r = cn.check(MINI, expl("Green Boom moved +3.43."))
    assert not r["passed"] and statuses(r)["+3.43"] == "WRONG_SIGN"
    assert statuses(cn.check(MINI, expl("It changed by −3.43.")))["−3.43"] == "matched"


def test_wrong_scope():
    r = cn.check(MINI, expl(item="Stagflation rises to 9.57."))
    assert not r["passed"] and any("another scenario" in f for f in r["failures"])


def test_direction_and_coverage():
    assert not cn.check(MINI, expl(item="Stagflation falls from 5 to 7."))["passed"]
    e = expl()
    e["big_changes"] = []
    assert any("not explained" in f for f in cn.check(MINI, e)["failures"])


def test_quantity_words_warn_only():
    r = cn.check(MINI, expl("The effect roughly doubled."))
    assert r["passed"] and any("doubled" in w for w in r["warnings"])


def test_dates_and_years():
    assert cn.check(MINI, expl("As of 2026-11-07 and in 2026."))["passed"]
    assert not cn.check(MINI, expl("As of 2025-03-01."))["passed"]


def test_hypothetical_notice_required():
    hyp = dict(MINI, meta=dict(MINI["meta"], is_hypothetical=True, mode="HYPOTHETICAL"))
    assert not cn.check(hyp, expl())["passed"]
    assert cn.check(hyp, expl(notice="HYPOTHETICAL: a what-if."))["passed"]


@pytest.fixture(scope="module")
def real_trace():
    eng = et.Engine(et.DEFAULT_REPO)
    return {mode: et.build_trace(eng, w)[0] for mode, w in (("whatif", "A05"), ("real", None))}


@pytest.mark.parametrize("mode", ["whatif", "real"])
def test_self_tests_on_engine_trace(real_trace, mode):
    bad = [t for t in cn.self_tests(real_trace[mode]) if not t["ok"]]
    assert not bad, bad
