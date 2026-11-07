"""Tests for the research loop (loop/check.py, loop/variants.py). Run: python3 -m pytest loop/test_loop.py -q"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


check = _load("loop_check", "check.py")


@pytest.fixture(scope="module")
def ctx():
    return check.Ctx(HERE.parent)


def test_add_months_and_brier():
    assert check.add_months("2011-12", 12) == "2012-12"
    assert check.add_months("2013-03", -2) == "2013-01"
    assert check.brier([0.5, 0.5], [0, 1]) == 0.25


def test_windows_are_disjoint_with_embargo(ctx):
    assert ctx.train and ctx.holdout
    assert not set(ctx.train) & set(ctx.holdout)
    # every training outcome is known before the first held-out forecast date
    assert check.add_months(ctx.train[-1], check.AHEAD) < ctx.holdout[0]
    assert len(ctx.train) >= 40 and len(ctx.holdout) >= 40


def test_known_data_stops_at_the_month(ctx):
    data = ctx.known("2005-06")
    assert data and all(t[:7] <= "2005-06" for rows in data.values() for t, _ in rows)


def test_published_reproduces_predict_proto(ctx):
    # docs/analysis-tools.md section 3: model 0.2403, prior-only 0.2456, baseline 0.2528, n = 102
    f, params = check.load_variants().VARIANTS["published"](ctx)
    rows = check.score(ctx, f, ctx.dates)
    b = check.briers(rows)
    assert len(rows) == 102 and params["k"] == 0.15
    assert round(b["variant"], 4) == 0.2403
    assert round(b["prior_only"], 4) == 0.2456
    assert round(b["baseline"], 4) == 0.2528
    assert all(0.0 <= r["variant"] <= 1.0 for r in rows)


def test_k_zero_is_prior_only(ctx):
    f = ctx.engine(ctx.with_k(0.0))
    st = check.add_months(ctx.train[0], -check.LAG)
    assert abs(f(st, ctx.known(st)) - ctx.prior_only) < 1e-12
    assert ctx.model["bayes"]["k_daempfung"] == 0.15  # with_k works on a copy


def test_k_fit_picks_from_the_grid_on_training_only(ctx, monkeypatch):
    V = check.load_variants()
    seen = []
    real = check.score
    monkeypatch.setattr(check, "score", lambda c, f, dates: seen.append(tuple(dates)) or real(c, f, dates))
    f, params = V.VARIANTS["k_fit"](ctx)
    assert params["k"] in V.K_GRID and len(params["train_brier_by_k"]) == len(V.K_GRID)
    assert seen and all(d == tuple(ctx.train) for d in seen)  # fitting never touched the held-out dates


def test_bootstrap_is_deterministic():
    d = [0.01 * ((i * 7) % 5 - 2) for i in range(48)]
    assert check.block_se(d) == check.block_se(d) > 0
    assert check.block_se([0.0] * 48) == 0.0


def test_holdout_only_once():
    rows = [{"variant": "a", "function_sha": "abc", "split": "holdout"}]
    assert not check.ledger_allows(rows, "a", "zzz")[0]   # same name
    assert not check.ledger_allows(rows, "b", "abc")[0]   # same code under a new name
    assert check.ledger_allows(rows, "b", "zzz")[0]


def test_goal():
    row = lambda n, beats: {"variant": n, "split": "holdout", "beats_prior_only": beats}
    assert not check.goal_status([row("published", "yes")])[0]       # the reference does not count
    assert check.goal_status([row("published", "no"), row("x", "yes")])[0]
    assert not check.goal_status([row(f"v{i}", "no") for i in range(9)])[0]
    assert check.goal_status([row(f"v{i}", "no") for i in range(10)])[0]


def test_ledger_is_well_formed():
    rows = check.read_ledger(check.LEDGER)
    names = [r["variant"] for r in rows]
    assert len(names) == len(set(names))
    assert all(r["split"] == "holdout" for r in rows)
