"""PROTOTYPE, not proof: does the world model forecast German industry better than a historical-frequency baseline?

Outcome    y(t) = 1 if German manufacturing production (eurostat-industrie-de) is LOWER 12 months after t, else 0.
Forecasts  at every quarter-end t from 2000-03 until the last t whose outcome is known (t + 12 <= last data month):
  model       sum of the unrounded 2028 probabilities of the below-normal-growth scenarios (regime.growth < 0),
              from pruefung/anzeichen_geschichte.py lage_am() with indicator data up to t - 2 (publication lag)
  prior-only  the same sum without any update (base model v1.4.0): 38 %
  baseline    share of y = 1 among all outcomes already known at t (start months s <= t - 12, from 1991-01)
Score      Brier = mean (p - y)^2, lower is better; skill = 1 - Brier / Brier(baseline), above 0 beats the baseline.

Read-only on the repo: imports only, bytecode off, git status compared before and after.
Fallback: if lage_am() raises, the model forecast is read from the committed tagesstand_rueckwaerts.csv (no lag).

    # from the repo root
    python3 -B predict_proto/predict_proto.py --repo .                       # results: ../open-foresight-results/predict_proto/
    python3 -B predict_proto/predict_proto.py --repo /path/to/open-foresight --out /tmp/predict-results
--out must be outside the repo; the default is open-foresight-results/predict_proto/ next to the clone.
Exit codes: 0 ok, 2 a check failed (no results shown), 3 the repo changed.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import csv
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HORIZON = "2028"
LAG = 2           # months of publication lag for the model's indicator data
AHEAD = 12        # outcome horizon in months
OUTCOME_SERIES = "eurostat-industrie-de"
START = 2000      # first forecast year (quarter-ends, as in tagesstand_rueckwaerts.csv)
TOL_CSV = 0.0006  # the CSV stores changes with 3 decimals

LIMITS = [
    "PROTOTYPE, NOT PROOF. Read the limits first:",
    "1. Prior built with hindsight: the base probabilities (model v1.4.0) were set in 2026 by someone who knew 2008, "
    "2020 and 2022. This favours 'model' and 'prior-only'. Only model vs prior-only isolates the data-driven update.",
    "2. Growth-equals-industry assumption: the forecast is the 2028 probability of the below-normal-growth scenarios, "
    "used as a 12-month probability that German industry falls. Both the mapping and the horizon are judgments made "
    "for this prototype.",
    "3. Overlapping windows: 12-month outcomes checked every quarter overlap; there are only about 25 independent "
    "years and 3 large crises. Small Brier differences mean nothing.",
    "4. Revised data: the series are today's revised values; a 2-month lag only partly mimics what was known then. "
    "The indicator states at the base date also use data up to 2026-10.",
]


class Stop(Exception):
    pass


def git(repo: Path, *a) -> str:
    try:
        return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, check=True).stdout.strip()
    except Exception as e:
        return f"<git unavailable: {e}>"


def add_months(m: str, n: int) -> str:
    k = int(m[:4]) * 12 + int(m[5:7]) - 1 + n
    return f"{k // 12:04d}-{k % 12 + 1:02d}"


def brier(ps: list, ys: list) -> float:
    return sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ys)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="PROTOTYPE Brier backtest (read-only on the repo)")
    ap.add_argument("--repo", type=Path, required=True, help="path to the open-foresight repo (read-only)")
    ap.add_argument("--out", type=Path, help="results folder outside the repo; default ../open-foresight-results/predict_proto")
    args = ap.parse_args(argv)
    repo = args.repo.resolve()
    out = (args.out or repo.parent / "open-foresight-results" / "predict_proto").resolve()
    if not (repo / "engine" / "tagesstand.py").is_file():
        print(f"ERROR: {repo} does not look like the open-foresight repo (engine/tagesstand.py missing)")
        return 1
    if out == repo or repo in out.parents:
        print("ERROR: --out must be outside the repo")
        return 1
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    out.mkdir(parents=True, exist_ok=True)
    status_before = git(repo, "status", "--porcelain")
    L = []
    say = L.extend

    def finish(code: int) -> int:
        after = git(repo, "status", "--porcelain")
        same = after == status_before
        say([f"", f"Repo check: git status before {status_before!r}, after {after!r} -> {'UNCHANGED' if same else 'CHANGED'}"])
        (out / "report.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
        print("\n".join(L))
        print(f"\nSaved in {out}")
        return code if same else 3

    say(["=" * 100, *LIMITS, "=" * 100, ""])

    sys.path.insert(0, str(repo))
    from engine import io, tagesstand as ts
    import pruefung.anzeichen_geschichte as ag  # read-only use: lese_reihen, lage_am, quartalsenden

    model = io.load_world_model("de")
    reihen = ag.lese_reihen()
    sids = [s["id"] for s in model["szenarien"]]
    crisis = sorted(s["id"] for s in model["szenarien"] if s["regime"]["growth"] < 0)
    basis_monat = model["meta"]["stand"][:7]
    base = ts.rechne_am(model, [], datetime(int(basis_monat[:4]), int(basis_monat[5:7]), 1, tzinfo=timezone.utc))
    base_exact = base["posterior_exakt"]
    prior_only = sum(base_exact[HORIZON][s] for s in crisis)
    say([f"Below-normal-growth scenarios (regime.growth < 0): {', '.join(crisis)}  [model/world_model.de.json]"])

    # --- check 1: prior-only is exactly 38 % ---
    ok1 = abs(prior_only - 38.0) < 1e-9
    say([f"CHECK 1  prior-only = {prior_only:.6f} %  (must be exactly 38)  -> {'PASS' if ok1 else 'FAIL'}"])
    if not ok1:
        say(["STOPPED: prior-only is not 38 %. No results shown."])
        return finish(2)

    # --- model forecasts; fallback to the committed CSV if lage_am misbehaves ---
    csv_rows = {r["stichtag"]: r for r in csv.DictReader(open(ag.ORDNER / "tagesstand_rueckwaerts.csv", encoding="utf-8"))}
    mode, cache = "engine", {}

    def model_p(stichtag: str) -> float:
        if stichtag not in cache:
            ex = ag.lage_am(model, reihen, stichtag, basis_monat)["rechnung"]["posterior_exakt"][HORIZON]
            cache[stichtag] = sum(ex[s] for s in crisis)
        return cache[stichtag]

    try:
        # --- check 2: without lag, the engine matches tagesstand_rueckwaerts.csv (all scenarios, all horizons) ---
        worst, n_cmp = 0.0, 0
        for st, row in csv_rows.items():
            ex = ag.lage_am(model, reihen, st, basis_monat)["rechnung"]["posterior_exakt"]
            for h in model["meta"]["horizonte"]:
                for s in sids:
                    worst = max(worst, abs((ex[h][s] - base_exact[h][s]) - float(row[f"delta_{h}_{s}"])))
                    n_cmp += 1
        ok2 = worst <= TOL_CSV
        say([f"CHECK 2  engine (no lag) vs backtest/indicators/tagesstand_rueckwaerts.csv: {len(csv_rows)} dates, "
             f"{n_cmp} values, largest difference {worst:.6f}  (must be <= {TOL_CSV})  -> {'PASS' if ok2 else 'FAIL'}"])
        if not ok2:
            say(["STOPPED: the engine does not reproduce the committed backtest. No results shown."])
            return finish(2)
    except (AssertionError, KeyError, ValueError, TypeError) as e:
        mode = "fallback"
        say([f"lage_am() MISBEHAVED ({type(e).__name__}: {e}). Using the FALLBACK: model forecast = 38 + committed "
             f"CSV changes of {', '.join(crisis)} in {HORIZON}, without the 2-month lag. CHECK 2 not applicable."])

        def model_p(stichtag: str) -> float:  # noqa: F811
            row = csv_rows[stichtag]
            return prior_only + sum(float(row[f"delta_{HORIZON}_{s}"]) for s in crisis)

    # --- check 3: git status unchanged so far ---
    now = git(repo, "status", "--porcelain")
    ok3 = now == status_before
    say([f"CHECK 3  git status unchanged so far ({now!r})  -> {'PASS' if ok3 else 'FAIL'}"])
    if not ok3:
        say(["STOPPED: the repo changed. No results shown."])
        return finish(3)

    # --- outcomes and forecasts ---
    ind = dict(reihen[OUTCOME_SERIES])
    months = sorted(ind)
    last = months[-1]
    y = {m: int(ind[add_months(m, AHEAD)] < ind[m]) for m in months if add_months(m, AHEAD) in ind}
    dates = [d for d in ag.quartalsenden(START, last) if add_months(d, AHEAD) <= last and d in ind]
    rows = []
    for d in dates:
        known = [y[s] for s in y if add_months(s, AHEAD) <= d]
        st = add_months(d, -LAG) if mode == "engine" else d
        rows.append({"date": d, "outcome": y[d], "model": model_p(st) / 100, "prior_only": prior_only / 100,
                     "baseline": sum(known) / len(known), "baseline_n_known": len(known), "model_data_up_to": st})
    ys = [r["outcome"] for r in rows]
    b = {k: brier([r[k] for r in rows], ys) for k in ("model", "prior_only", "baseline")}
    skill = {k: 1 - b[k] / b["baseline"] for k in ("model", "prior_only")}

    with open(out / "forecasts.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (out / "raw.json").write_text(json.dumps({"mode": mode, "limits": LIMITS, "crisis_scenarios": crisis,
                                              "brier": b, "skill_vs_baseline": skill, "n": len(rows),
                                              "repo_head": git(repo, "rev-parse", "HEAD"), "rows": rows}, indent=2) + "\n",
                                  encoding="utf-8")

    mean = lambda k: sum(r[k] for r in rows) / len(rows)
    say(["", f"RESULT - PROTOTYPE, NOT PROOF   (model forecasts from: {'engine, lage_am(), data up to t-2' if mode == 'engine' else 'FALLBACK CSV, no lag'})",
         f"Outcome: German manufacturing production lower {AHEAD} months later.  Forecast dates: {rows[0]['date']} to "
         f"{rows[-1]['date']}, quarterly, n = {len(rows)}.  Outcome happened in {sum(ys)} of {len(ys)} "
         f"({sum(ys) / len(ys):.1%}).", "",
         f"  {'forecast':<28}{'mean forecast':>15}{'Brier':>10}{'skill vs baseline':>20}",
         f"  {'-' * 73}",
         f"  {'model (prior + updates)':<28}{mean('model'):>15.3f}{b['model']:>10.4f}{skill['model']:>+20.3f}",
         f"  {'prior-only (always 38 %)':<28}{mean('prior_only'):>15.3f}{b['prior_only']:>10.4f}{skill['prior_only']:>+20.3f}",
         f"  {'historical-frequency base':<28}{mean('baseline'):>15.3f}{b['baseline']:>10.4f}{0:>+20.3f}",
         "", f"  Model vs prior-only (effect of the data-driven updates alone): Brier {b['model'] - b['prior_only']:+.4f} "
             f"({'better' if b['model'] < b['prior_only'] else 'worse' if b['model'] > b['prior_only'] else 'same'})",
         f"  Model forecast range: {min(r['model'] for r in rows):.3f} to {max(r['model'] for r in rows):.3f}",
         f"  Sources: outcome backtest/indicators/reihen/{OUTCOME_SERIES}.csv; model pruefung/anzeichen_geschichte.py "
         f"lage_am() -> engine rechne_am() posterior_exakt[{HORIZON}]; per-quarter values in forecasts.csv",
         "", "(Remember the limits printed at the top: PROTOTYPE, NOT PROOF.)"])
    return finish(0)


if __name__ == "__main__":
    raise SystemExit(main())
