# Analysis tools: k sensitivity, plain-language explanation, forecasting prototype

Three small tools around the world model, added at the hackathon on 2026-11-07. None of them changes a number in
the model. Each one only reads the repo, writes its results **outside** it (by default to
`../open-foresight-results/<tool>/`, next to your clone), runs with `python3 -B` (no `__pycache__`), and compares
`git status` before and after.

| Tool | Question it answers | Folder | Costs money? |
|---|---|---|---|
| [k sensitivity](#1-k_experiment-how-much-does-the-damping-k-matter) | How much do the 2040 probabilities change when the damping `k` changes? | [`k_experiment/`](../k_experiment/) | no |
| [Plain-language explanation](#2-explain-plain-language-explanation-with-a-number-check) | What is the model doing and why, in plain words, with every number checked? | [`explain/`](../explain/) | only without `--dry-run` (about 7 cents per call) |
| [Forecasting prototype](#3-predict_proto-can-it-predict-anything-prototype) | Does the model forecast anything measurable better than a simple baseline? | [`predict_proto/`](../predict_proto/) | no |

All commands below run from the repo root.

## Background in two minutes

The world model gives probabilities for 12 scenarios in 2028, 2032 and 2040. It is **judgment-based**: a person
set the starting probabilities, the coupling between 33 drivers and the scenarios, 23 indicator rules and the
damping `k = 0.15` (see the README, "What kind of model is this?"). Every day the engine checks the indicator rules
against open data. Only indicators that **changed** since the base model create a signal, and each signal moves
the probabilities:

```
boost(s)  = exp( k × direction × strength × mean coupling of the signal's drivers to scenario s )
P_new(s)  ∝ P_old(s) × boost(s), rescaled to 100 per horizon (minimum 0.5 %), rounded to whole percents
```

In the current snapshot no indicator has changed since the base model, so today's probabilities equal the starting
values. The what-if tools therefore switch one indicator on **hypothetically** to show the machinery working.

---

## 1. `k_experiment/`: how much does the damping k matter?

[`k_experiment/k_sensitivity.py`](../k_experiment/k_sensitivity.py) reruns the engine in memory for
`k` = 0, 0.05, 0.10, **0.15**, 0.20, 0.30, 0.50 and three cases: **A** real data, **B** HYPOTHETICAL shock A05
(Brent above 110 $ for more than two quarters), **C** HYPOTHETICAL shock A13 (Brent below 70 $).

**Checks before any result is shown** (the script stops otherwise): case A reproduces the published
`radar/snapshot/weltlage.json` at every `k`; `k = 0` gives the base model; the unrounded path rounds to the
published numbers.

**Result (2040, total probability moved, in percentage points):**

| k | 0 | 0.05 | 0.10 | **0.15** | 0.20 | 0.30 | 0.50 |
|---|---|---|---|---|---|---|---|
| B (HYPOTHETICAL) | 0 | 2.35 | 4.66 | **6.91** | 9.12 | 13.52 | 21.70 |
| C (HYPOTHETICAL) | 0 | 1.58 | 3.18 | **4.78** | 6.39 | 9.61 | 15.96 |

Doubling `k` roughly doubles the effect. Real data (case A) moves nothing at any `k`. Outputs: `report.txt`,
`raw_output.json`, `table_2040.csv`, two charts. Details: [`k_experiment/RERUN.md`](../k_experiment/RERUN.md).

```bash
python3 -B k_experiment/k_sensitivity.py
```

## 2. `explain/`: plain-language explanation with a number check

[`explain/explain_trace.py`](../explain/explain_trace.py) does three things:

1. **Trace:** runs the engine and collects the changed indicators, their drivers, the coupling values, the boost
   per scenario and the probabilities before and after. Every number comes from an engine function, and the trace
   records which one. Seven engine checks must pass first.
2. **Claude:** sends **only the trace** to the Claude API (`claude-opus-5-5`, structured JSON output, server-side
   refusal fallback) and asks for a short explanation: what is happening, why each big change happened, what is
   uncertain. Claude must copy numbers exactly and add none.
3. **Number check** ([`explain/check_numbers.py`](../explain/check_numbers.py)): every number in the text must
   appear in the trace (exact value), with the right sign, and inside a scenario's explanation it must belong to
   *that* scenario. It also checks rise/fall words, that every big change is explained, and the HYPOTHETICAL notice.
   If the check fails, the script retries once; a text that still fails gets a **FAILED NUMBER CHECK** banner.

**First paid run (HYPOTHETICAL A05):** passed on the first attempt. All 64 numbers were found in the trace
(2 with the sign dropped, e.g. "fell by 3.43"), with 1 harmless warning, for about 7 cents. A human read found the
reasoning correct, with two sentences that were Claude's own inference: the check verifies numbers, not reasoning.

```bash
python3 -B explain/explain_trace.py --whatif A05 --dry-run   # trace + self-tests, no API call, free
python3 -B explain/explain_trace.py --real --dry-run
python3 -B explain/explain_trace.py --whatif A05             # paid: needs ANTHROPIC_API_KEY and `pip install anthropic`
```

**API key:** set `ANTHROPIC_API_KEY` as an environment variable in your own shell. Never paste it into a chat,
an issue, a file or a commit. The script only checks that it is set and never prints it.

Tests: [`explain/test_check_numbers.py`](../explain/test_check_numbers.py) (unit tests plus self-tests on real
engine traces) runs as part of `make test`. Details: [`explain/RERUN.md`](../explain/RERUN.md).

## 3. `predict_proto/`: can it predict anything? (PROTOTYPE)

[`predict_proto/predict_proto.py`](../predict_proto/predict_proto.py) is the smallest honest forecasting test we
could build in an hour.

- **Outcome:** German manufacturing production is lower 12 months later, yes or no
  ([`backtest/indicators/reihen/eurostat-industrie-de.csv`](../backtest/indicators/reihen/eurostat-industrie-de.csv)).
- **Forecast dates:** every quarter-end from 2000-03 to 2025-06 (n = 102).
- **Three forecasters:**
  - *model:* the 2028 probability of the below-normal-growth scenarios (S03, S04, S09, S14, S17), from
    `lage_am()` in [`pruefung/anzeichen_geschichte.py`](../pruefung/anzeichen_geschichte.py), with indicator data
    only up to t − 2 months;
  - *prior-only:* the same without updates, always 38 %;
  - *historical baseline:* the share of declines among outcomes already known at t.
- **Score:** Brier (mean squared error of the probability, lower is better) and skill versus the baseline.
- **Checks first:** prior-only is exactly 38 %; the engine reproduces the committed
  [`backtest/indicators/tagesstand_rueckwaerts.csv`](../backtest/indicators/tagesstand_rueckwaerts.csv)
  (3,888 values, within rounding); `git status` is unchanged. If `lage_am()` fails, a fallback reads the model
  forecast from that CSV (without the lag) and says so.

**Result: PROTOTYPE, NOT PROOF** (the decline happened in 43 of 102 quarters):

| Forecast | Mean forecast | Brier | Skill vs baseline |
|---|---|---|---|
| model | 0.370 | **0.2403** | +0.049 |
| prior-only (38 %) | 0.380 | 0.2456 | +0.028 |
| historical baseline | 0.338 | 0.2528 | 0 |

**In simple words:** all three are only a little better than always saying 50 % (Brier 0.25). The model wins by a
hair, but mostly because its fixed 38 % was chosen in 2026 by someone who knew how history went. The indicator
updates help only slightly (Brier −0.0053), and the model never moves far from 38 % (between 30 % and 42 %). This
shows the test works; it does **not** show that the model predicts.

**Limits (printed at the top of every run):**

1. The prior was built with hindsight (model v1.4.0, 2026). Only model versus prior-only isolates the data-driven update.
2. "Below-normal growth" is used as "German industry falls", and the 2028 horizon as 12 months. Both are judgments made for this prototype.
3. The 12-month windows overlap: about 25 independent years and 3 large crises. Small Brier differences mean nothing.
4. The series are today's revised values; the 2-month lag only partly mimics what was known at the time.

```bash
python3 -B predict_proto/predict_proto.py --repo .     # about 1 second; results in ../open-foresight-results/predict_proto/
python3 -B predict_proto/predict_proto.py --repo . --out /tmp/predict-results
```

Outputs: `report.txt` (limits, checks, results), `forecasts.csv` (every quarter: outcome and the three
forecasts), `raw.json`. Exit codes: 0 ok, 1 bad arguments, 2 a check failed (no results shown), 3 the repo changed.

---

## What would make the model actually predict

Rough effort for one experienced person; it overlaps with the README's "Hackathon track: from rules to estimates":

1. Checkable outcome questions, not only 2040 scenarios (1–2 weeks).
2. A fair backtest with a prior frozen at a past date, scored against baselines (1–2 weeks).
3. Soft thresholds instead of on/off indicators (about 1 week).
4. Estimate `k` and the couplings from data, shrunk towards the judged values (2–4 weeks).
5. Link the horizons through the transition matrix (1–2 weeks).
6. A calibration check (about 1 week).
7. Live, dated forecasts scored every quarter. Proof takes **years**, whatever is built; the first upstream
   forecast questions resolve from 2027-Q1.

Licences as in the repo: code MIT, model data CC BY 4.0; the time series belong to their publishers.
