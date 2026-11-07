"""Build ui/history.json: the published model's forecast of a downturn of German industry at every quarter-end since
2000, next to what really happened, for the last stop of the tour ("Would the model have warned?").

    python3 -B ui/build_history.py        # from the repo root

Same computation and windows as the research loop (loop/check.py): forecast = the 2028 probability of the
below-normal-growth scenarios, from indicator data up to t - 2 months only; outcome = German manufacturing production
lower 12 months after t. Scores: Brier (lower is better) for the model, the fixed prior and the historical base rate,
on the training window (2000-2011) and the held-out window (2013-2025). Nothing here is estimated by hand.
"""
import sys

sys.dont_write_bytecode = True

import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
# event months of backtest/indicators/REPORT.md
EVENTS = [{"t": "2008-09", "label": "Lehman"}, {"t": "2020-03", "label": "Pandemic"}, {"t": "2022-02", "label": "War in Ukraine"}]


def build() -> dict:
    spec = importlib.util.spec_from_file_location("loop_check", REPO / "loop" / "check.py")
    check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(check)
    ctx = check.Ctx(REPO)
    f = check.load_variants().VARIANTS["published"](ctx)[0]
    rows = check.score(ctx, f, ctx.dates)

    def window(dates):
        part = [r for r in rows if r["date"] in set(dates)]
        b = check.briers(part)
        return {"from": part[0]["date"], "to": part[-1]["date"], "n": len(part), "declines": sum(r["outcome"] for r in part),
                "brier": {k: round(v, 4) for k, v in b.items()}}

    out = {
        "_note": "Built by ui/build_history.py from loop/check.py (variant 'published'). Do not edit by hand.",
        "outcome": "German manufacturing production lower 12 months later (Eurostat, eurostat-industrie-de)",
        "forecast": "2028 probability of the below-normal-growth scenarios, indicator data up to t - 2 months",
        "prior": round(ctx.prior_only, 4),
        "events": EVENTS,
        "rows": [{"t": r["date"], "p": round(r["variant"], 4), "y": r["outcome"]} for r in rows],
        "score": {"all": window(ctx.dates), "train": window(ctx.train), "holdout": window(ctx.holdout)},
    }
    return out


def render(out: dict) -> str:
    return json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n"


def main() -> int:
    out = build()
    (HERE / "history.json").write_text(render(out), encoding="utf-8")
    s = out["score"]["holdout"]["brier"]
    print(f"ui/history.json: {len(out['rows'])} quarters, held-out Brier model {s['variant']}, prior {s['prior_only']}, base rate {s['baseline']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
