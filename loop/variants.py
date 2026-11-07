"""Forecast variants for the research loop. Each round of the loop adds exactly one function here.

A variant gets the context `ctx` (see check.py, class Ctx) and returns (forecaster, params):
  forecaster(stichtag, data) -> probability in [0, 1] that German manufacturing is lower 12 months after the
                                forecast date. `stichtag` is the month of the latest usable data (forecast date
                                minus the publication lag); `data` holds only months up to `stichtag`.
  params                     -> a small JSON-able dict that says what was chosen (written to the report and ledger).

Use only the public parts of ctx: ctx.model (the published model, do not change it in place), ctx.with_k(k),
ctx.engine(model), ctx.train_brier(forecaster), ctx.prior_only, ctx.crisis.
Anything a variant fits, it fits with ctx.train_brier, which sees only the training window.
Never read data files directly, never use the held-out window: check.py guards the data, this rule guards the rest.
"""
from __future__ import annotations

VARIANTS: dict = {}

# the damping values the what-if page offers (whatif/build_data.py K_VALUES), plus three stronger ones
K_GRID = [0.0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.50, 0.75, 1.0]


def variant(name: str, what: str):
    def register(fn):
        if name in VARIANTS:
            raise ValueError(f"variant {name!r} exists already")
        fn.variant_name, fn.what = name, what
        VARIANTS[name] = fn
        return fn
    return register


@variant("published", "the published model unchanged: damping k = 0.15, indicator data up to t - 2 months")
def published(ctx):
    return ctx.engine(ctx.model), {"k": ctx.model["bayes"]["k_daempfung"]}


@variant("k_fit", "damping k chosen on the training window from K_GRID (smallest training Brier, ties to the smaller k)")
def k_fit(ctx):
    scores = {k: ctx.train_brier(ctx.engine(ctx.with_k(k))) for k in K_GRID}
    best = min(K_GRID, key=lambda k: (scores[k], k))
    return ctx.engine(ctx.with_k(best)), {"k": best, "train_brier_by_k": {str(k): round(v, 6) for k, v in scores.items()}}
