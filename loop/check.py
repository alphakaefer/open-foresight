"""Research loop check: score one forecast variant (loop/variants.py) on the training or the held-out window.

Question   Does the world model's data-driven update forecast better than its prior alone?
Outcome    y(t) = 1 if German manufacturing production (eurostat-industrie-de) is lower 12 months after t, else 0
           (the same outcome as predict_proto/predict_proto.py).
Forecasts  at every quarter-end t from 2000-03 on, from indicator data up to t - 2 months only.
Windows    training: t <= 2011-12 (outcomes known by 2012-12). Held-out: t >= 2013-03. 2012 is a gap (embargo).
Score      Brier = mean (p - y)^2, lower is better. Compared with prior-only (the published prior, 38 %) and the
           historical base rate (share of declines among outcomes known at t). Uncertainty: moving-block bootstrap
           over 4 quarters (12-month outcomes overlap), 2000 draws, fixed seed.
Beats      Brier(variant) - Brier(prior-only) < -2 bootstrap standard errors on the held-out window.

Guards
- Data: a variant's forecaster only ever gets the series cut at t - 2 months (Ctx.known).
- Held-out once: --holdout writes one row to loop/ledger.tsv and refuses a second run of the same variant name
  or of the same code under a new name.
- Repo: nothing outside loop/ledger.tsv may change during a run (git status before and after).
- Results go outside the repo (default ../open-foresight-results/loop/ next to the clone).
- Known limit kept on purpose: the base state of the indicators (month of the published model, 2026-10) and the
  prior were set with hindsight. Only variant versus prior-only isolates the data-driven update.

    python3 -B loop/check.py --list
    python3 -B loop/check.py --variant k_fit              # training window, as often as needed
    python3 -B loop/check.py --variant k_fit --holdout    # held-out window, once per variant
    python3 -B loop/check.py --goal                       # exit 0 when the loop's goal is met

Exit codes: 0 ok (or goal met), 1 bad arguments (or goal not met), 2 a check failed, 3 the repo changed,
4 held-out run refused.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import copy
import csv
import hashlib
import importlib.util
import inspect
import json
import math
import random
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
LEDGER = HERE / "ledger.tsv"

HORIZON = "2028"
LAG = 2                   # months of publication lag
AHEAD = 12                # outcome horizon in months
OUTCOME_SERIES = "eurostat-industrie-de"
START = 2000
TRAIN_LAST = "2011-12"    # last training forecast date
HOLDOUT_FIRST = "2013-03" # first held-out forecast date
BLOCK, N_BOOT, SEED = 4, 2000, 20261107
GOAL_SE, GOAL_N = 2.0, 10
LEDGER_FIELDS = ["variant", "function_sha", "split", "n", "brier_variant", "brier_prior_only", "brier_baseline",
                 "diff_vs_prior_only", "se_vs_prior_only", "beats_prior_only", "diff_vs_baseline", "se_vs_baseline",
                 "params", "repo_head", "run_date"]


def add_months(m: str, n: int) -> str:
    k = int(m[:4]) * 12 + int(m[5:7]) - 1 + n
    return f"{k // 12:04d}-{k % 12 + 1:02d}"


def brier(ps: list, ys: list) -> float:
    return math.fsum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ys)


def block_se(diffs: list, block: int = BLOCK, n_boot: int = N_BOOT, seed: int = SEED) -> float:
    """Standard error of the mean of diffs by a moving-block bootstrap (deterministic for a fixed seed)."""
    n = len(diffs)
    if n < block:
        return 0.0
    rng, starts, means = random.Random(seed), n - block + 1, []
    for _ in range(n_boot):
        sample: list = []
        while len(sample) < n:
            s = int(rng.random() * starts)
            sample.extend(diffs[s:s + block])
        means.append(math.fsum(sample[:n]) / n)
    mu = math.fsum(means) / n_boot
    return math.sqrt(math.fsum((m - mu) ** 2 for m in means) / (n_boot - 1))


def git(*a) -> str:
    try:
        return subprocess.run(["git", "-C", str(REPO), *a], capture_output=True, text=True, check=True).stdout.strip()
    except Exception as e:
        return f"<git unavailable: {e}>"


def status_without_ledger() -> str:
    return "\n".join(l for l in git("status", "--porcelain").splitlines() if not l.endswith("loop/ledger.tsv"))


class Ctx:
    """Everything a variant may use. Public: model, crisis, prior_only, with_k, engine, train_brier
    (and, for check.py itself: dates, train, holdout, known, y)."""

    def __init__(self, repo: Path = REPO):
        sys.path.insert(0, str(repo))
        from engine import io, tagesstand as ts
        import pruefung.anzeichen_geschichte as ag
        self._ts, self._ag = ts, ag
        self.model = io.load_world_model("de")
        self._reihen = ag.lese_reihen()
        self.crisis = sorted(s["id"] for s in self.model["szenarien"] if s["regime"]["growth"] < 0)
        self._basis_monat = self.model["meta"]["stand"][:7]
        heute = datetime(int(self._basis_monat[:4]), int(self._basis_monat[5:7]), 1, tzinfo=timezone.utc)
        ex = ts.rechne_am(self.model, [], heute)["posterior_exakt"][HORIZON]
        self.prior_only = sum(ex[s] for s in self.crisis) / 100
        ind = dict(self._reihen[OUTCOME_SERIES])
        last = max(ind)
        self.y = {m: int(ind[add_months(m, AHEAD)] < ind[m]) for m in ind if add_months(m, AHEAD) in ind}
        self.dates = [d for d in ag.quartalsenden(START, last) if add_months(d, AHEAD) <= last and d in ind]
        self.train = [d for d in self.dates if d <= TRAIN_LAST]
        self.holdout = [d for d in self.dates if d >= HOLDOUT_FIRST]
        self._known: dict = {}

    def known(self, month: str) -> dict:
        """The series as they were up to month (later values removed)."""
        if month not in self._known:
            self._known[month] = {rid: [(t, w) for t, w in rows if t[:7] <= month] for rid, rows in self._reihen.items()}
        return self._known[month]

    def with_k(self, k: float) -> dict:
        m = copy.deepcopy(self.model)
        m["bayes"]["k_daempfung"] = k
        return m

    def engine(self, model: dict):
        """Forecaster of the engine for a (possibly changed) model: the 2028 probability of the below-normal-growth
        scenarios, the same computation as pruefung/anzeichen_geschichte.py lage_am()."""
        ts, ag, crisis = self._ts, self._ag, self.crisis
        basis = ag.stand_je_anzeichen(model, self._reihen, self._basis_monat)  # base state of the published model

        def forecaster(stichtag: str, data: dict) -> float:
            jetzt = ag.stand_je_anzeichen(model, data, stichtag)
            heute = datetime(int(stichtag[:4]), int(stichtag[5:7]), 1, tzinfo=timezone.utc)
            signale = ag.signale_zwischen(model, basis, jetzt, heute)
            ex = ts.rechne_am(model, signale, heute)["posterior_exakt"][HORIZON]
            return sum(ex[s] for s in crisis) / 100
        return forecaster

    def train_brier(self, forecaster) -> float:
        return briers(score(self, forecaster, self.train))["variant"]


def score(ctx: Ctx, forecaster, dates: list) -> list:
    rows = []
    for d in dates:
        st = add_months(d, -LAG)
        p = forecaster(st, ctx.known(st))
        if not 0.0 <= p <= 1.0:
            raise ValueError(f"{d}: forecast {p} is not a probability")
        known = [ctx.y[s] for s in ctx.y if add_months(s, AHEAD) <= d]
        rows.append({"date": d, "outcome": ctx.y[d], "variant": p, "prior_only": ctx.prior_only,
                     "baseline": sum(known) / len(known), "data_up_to": st})
    return rows


def briers(rows: list) -> dict:
    ys = [r["outcome"] for r in rows]
    return {k: brier([r[k] for r in rows], ys) for k in ("variant", "prior_only", "baseline")}


def compare(rows: list, other: str) -> tuple:
    """(Brier(variant) - Brier(other), bootstrap standard error of that difference)."""
    d = [(r["variant"] - r["outcome"]) ** 2 - (r[other] - r["outcome"]) ** 2 for r in rows]
    return math.fsum(d) / len(d), block_se(d)


def load_variants():
    spec = importlib.util.spec_from_file_location("loop_variants", HERE / "variants.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def function_sha(fn) -> str:
    """Hash of the function body without decorator and def line, so a rename does not change it."""
    lines = inspect.getsource(fn).splitlines()
    first = next(i for i, l in enumerate(lines) if l.lstrip().startswith("def "))
    return hashlib.sha256("\n".join(l.strip() for l in lines[first + 1:]).encode()).hexdigest()[:12]


def read_ledger(path: Path = LEDGER) -> list:
    if not path.is_file():
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def ledger_allows(rows: list, name: str, sha: str) -> tuple:
    for r in rows:
        if r["split"] != "holdout":
            continue
        if r["variant"] == name:
            return False, f"variant {name!r} was already scored on the held-out window"
        if r["function_sha"] == sha:
            return False, f"the same code was already scored on the held-out window as {r['variant']!r}"
    return True, ""


def goal_status(rows: list) -> tuple:
    tested = [r for r in rows if r["split"] == "holdout" and r["variant"] != "published"]
    wins = [r["variant"] for r in tested if r["beats_prior_only"] == "yes"]
    if wins:
        return True, f"GOAL MET: {', '.join(wins)} beat prior-only on the held-out window by more than {GOAL_SE:g} standard errors."
    if len(tested) >= GOAL_N:
        return True, f"GOAL MET (negative): {len(tested)} variants scored on the held-out window, none beat prior-only."
    return False, f"Goal not met: {len(tested)} of {GOAL_N} variants scored on the held-out window, none beat prior-only."


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="research loop check (read-only on the repo except loop/ledger.tsv)")
    ap.add_argument("--variant", help="name of a variant in loop/variants.py")
    ap.add_argument("--holdout", action="store_true", help="score on the held-out window (once per variant)")
    ap.add_argument("--goal", action="store_true", help="exit 0 if the loop's goal is met")
    ap.add_argument("--list", action="store_true", help="list the variants")
    ap.add_argument("--out", type=Path, help="results folder outside the repo; default ../open-foresight-results/loop")
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if args.goal:
        met, text = goal_status(read_ledger())
        print(text)
        return 0 if met else 1
    V = load_variants()
    if args.list or not args.variant:
        done = {r["variant"] for r in read_ledger()}
        for n, fn in V.VARIANTS.items():
            print(f"{n:<16} {'held-out done' if n in done else 'open':<14} {fn.what}")
        return 0 if args.list else 1
    if args.variant not in V.VARIANTS:
        print(f"ERROR: no variant {args.variant!r} in loop/variants.py")
        return 1
    out = (args.out or REPO.parent / "open-foresight-results" / "loop").resolve()
    if out == REPO or REPO in out.parents:
        print("ERROR: --out must be outside the repo")
        return 1

    fn = V.VARIANTS[args.variant]
    sha, split = function_sha(fn), ("holdout" if args.holdout else "train")
    if args.holdout:
        ok, why = ledger_allows(read_ledger(), args.variant, sha)
        if not ok:
            print(f"REFUSED: {why}. Each variant sees the held-out window once.")
            return 4
    before = status_without_ledger()
    ctx = Ctx()
    forecaster, params = fn(ctx)
    rows = score(ctx, forecaster, ctx.holdout if args.holdout else ctx.train)
    b = briers(rows)
    dp, sp = compare(rows, "prior_only")
    db, sb = compare(rows, "baseline")
    beats = "yes" if dp < -GOAL_SE * sp else "no"
    after = status_without_ledger()
    if after != before:
        print(f"STOPPED: the repo changed during the run.\nbefore: {before!r}\nafter:  {after!r}")
        return 3

    res = {"variant": args.variant, "function_sha": sha, "split": split, "n": len(rows),
           "brier_variant": f"{b['variant']:.4f}", "brier_prior_only": f"{b['prior_only']:.4f}",
           "brier_baseline": f"{b['baseline']:.4f}", "diff_vs_prior_only": f"{dp:+.4f}", "se_vs_prior_only": f"{sp:.4f}",
           "beats_prior_only": beats, "diff_vs_baseline": f"{db:+.4f}", "se_vs_baseline": f"{sb:.4f}",
           "params": json.dumps(params, sort_keys=True, separators=(",", ":")), "repo_head": git("rev-parse", "--short", "HEAD"),
           "run_date": datetime.now(timezone.utc).strftime("%Y-%m-%d")}
    window = f"{rows[0]['date']} to {rows[-1]['date']}"
    lines = [
        f"Research loop check · variant {args.variant} ({fn.what})",
        f"Window: {'HELD-OUT' if args.holdout else 'training'}, forecast dates {window}, quarterly, n = {len(rows)}; "
        f"outcome happened in {sum(r['outcome'] for r in rows)} of {len(rows)}.",
        f"Params: {res['params']}",
        "",
        f"  {'forecast':<26}{'mean':>8}{'Brier':>9}",
        f"  {'variant':<26}{sum(r['variant'] for r in rows) / len(rows):>8.3f}{b['variant']:>9.4f}",
        f"  {'prior-only':<26}{ctx.prior_only:>8.3f}{b['prior_only']:>9.4f}",
        f"  {'historical base rate':<26}{sum(r['baseline'] for r in rows) / len(rows):>8.3f}{b['baseline']:>9.4f}",
        "",
        f"  variant - prior-only: {dp:+.4f} (bootstrap SE {sp:.4f})  -> beats prior-only by > {GOAL_SE:g} SE: {beats}",
        f"  variant - base rate:  {db:+.4f} (bootstrap SE {sb:.4f})",
        f"  forecast range: {min(r['variant'] for r in rows):.3f} to {max(r['variant'] for r in rows):.3f}",
        "",
        "Limit: the prior and the base state of the indicators were set in 2026 with hindsight; only variant versus "
        "prior-only isolates the data-driven update. Three large crises, about 25 independent years.",
    ]
    folder = out / f"{args.variant}-{split}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (folder / "raw.json").write_text(json.dumps({**res, "params": params, "rows": rows}, indent=2) + "\n", encoding="utf-8")
    with open(folder / "rows.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    if args.holdout:
        new = not LEDGER.is_file()
        with open(LEDGER, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=LEDGER_FIELDS, delimiter="\t", lineterminator="\n")
            if new:
                w.writeheader()
            w.writerow(res)
        lines.append(f"\nWritten to loop/ledger.tsv. {goal_status(read_ledger())[1]}")
    print("\n".join(lines))
    print(f"\nSaved in {folder}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
