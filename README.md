# open-foresight

An open, reproducible foresight model: a **world model** of scenarios for 2028 / 2032 / 2040, a **radar** that
collects open data to monitor it, and a **domain lens** that breaks the world model down to one concrete question.
Applications built on top live in their own repositories (the Foresight Studio web app will follow later).

Hackathon focus (2026-11-07): **the energy transition (Energiewende) in Germany.**

```
world model (12 scenarios, 33 drivers, 23 early-warning indicators)
      │  Bayes update from indicator changes
      ▼
radar (open data: Energy-Charts, FRED, Destatis, Eurostat, ECB, OpenAlex, news feeds …)
      │  engine.tagesstand → today's world state
      ▼
domain lens (domains/lens.py + domains/energy-transition/domain.json)
      │  scenarios × energy-price regime, linked drivers, indicators, radar series, bottleneck model
      ▼
applications (separate repos), e.g. Foresight Studio: evidence → key factors → scenarios → options
```

## Quick start (5 minutes)

```bash
git clone https://github.com/alphakaefer/open-foresight && cd open-foresight
python3 -m pip install -r requirements.txt     # only pytest; the engine is pure standard library
make test                                       # reproduces the published world state, checks the domain model
make energy                                     # writes domains/energy-transition/briefing.md
```

Start reading at **[domains/energy-transition/briefing.md](domains/energy-transition/briefing.md)**.

## What is in here

| Path | What | Language |
|---|---|---|
| `model/world_model.de.json` | The public world model, exactly as published upstream (German original, authoritative) | data |
| `model/world_model.en.json` | English translation: same structure, same keys, same numbers | data |
| `model/glossary.md` | German keys and values → English | EN |
| `model/uebergaenge.json` | Transitions between scenarios (mean dwell time, main exits; judgment, partly marked as proposal) | data, DE |
| `engine/` | Pure-Python engine: Bayes update (`bayes.py`), evidence inflow (`zufluss.py`), magnitude levels (`stufen.py`), range (`spanne.py`), daily world state (`tagesstand.py`), scenario transitions as a Markov chain (`uebergaenge.py`), committor (`committor.py`) | code comments DE |
| `backtest/` | Backtest of the early-warning indicators against 2008, 2020, 2022: 14 public series back to 1947, script `pruefung/anzeichen_geschichte.py`, results, [report](backtest/indicators/REPORT.md) | EN report, data |
| `explain/` | Plain-language explanation of an engine run by the Claude API, with an offline number check: every number in the text must appear in the engine trace (`--dry-run` makes no API call). [How to rerun](explain/RERUN.md) | EN |
| `k_experiment/` | Sensitivity of the scenario probabilities to the damping `k`, with gates that must reproduce the published state first. [How to rerun](k_experiment/RERUN.md) | EN |
| `loop/` | Research loop: does the data-driven update forecast better than the prior alone? One round tests one variant on a training window (2000–2011) and once on a held-out window (2013–2025); `loop/check.py --goal` says when to stop. Start: [PROMPT.md](loop/PROMPT.md); results so far: [JOURNAL.md](loop/JOURNAL.md) | EN |
| `radar/snapshot/` | Radar snapshot (`wissensstand.json`) and the world state computed from it (`weltlage.json`) | data |
| `radar/SOURCES.md` | All radar sources and time series, generated from the snapshot | EN |
| `radar/collector/` | The PHP collector that builds the radar from open sources | code comments DE |
| `radar/regional/`, `radar/fetch_regional.py` | Per-country (World Bank, Eurostat) and per-state (MaStR) energy values for the UI map comparisons, with sources | data, code EN |
| `domains/lens.py` | Domain lens: world model → one domain question | EN |
| `domains/energy-transition/` | Domain config, generated briefing (md + json) | EN |
| `docs/process.md` | The foresight process step by step, and where each step lives in this repo | EN |
| `ui/`, `docs/ux-flow.md` | Prototype UI with maps, scenario drill-down and a bottleneck what-if (static HTML/JS, `make ui`) across Berlin, Brandenburg, Germany, Europe, Global; UX flow. Early-warning what-ifs and two extreme cases (`ui/whatif.js`, `ui/build_bundles.py`) reuse the engine results of `whatif/`. `ui/dash.js`: focus view (map, key number, switches) and a click-through tour; `#…/tour=N` opens stop N, arrow keys or a presenter clicker step through. Its last stop compares the model's past forecasts with what happened (`ui/build_history.py` → `ui/history.json`, from `loop/check.py`) | EN |
| `tests/` | Reproducibility and model tests | |

## What kind of model is this?

An honest classification, because a data scientist asked at the hackathon whether this is a model at all,
since it is mostly rules.

- It is a **judgment-based probabilistic scenario model**: expert-set prior probabilities, a rule-based monitoring
  layer on open data, and a Bayesian update. Structurally it is close to cross-impact analysis and Bayesian belief
  networks, not to a model fitted on data.
- **Set by judgment, not estimated from data:** the 36 base probabilities (12 scenarios × 3 horizons); the
  coupling matrix (33 drivers × 12 scenarios), derived upstream from judged driver loadings and scenario regime
  vectors; the rules and thresholds of the 23 early-warning indicators and their signal strengths; the damping
  `k = 0.15`; the transition matrix between scenarios (`model/uebergaenge.json`).
- **Measured:** 31 radar time series. Indicator states follow from them by rule; nothing else is fitted.
- **Checked against history:**
  - *Outside view* (`aussensicht` in the model): in 2028 the crisis load (scenarios with below-normal growth) is
    38%, 1.8 times the US base rate 1973–2025 (21% of years).
  - *Backtest of the indicators* ([report](backtest/indicators/REPORT.md)): no numeric indicator would have
    warned selectively and in time before 2008, 2020 and 2022. Hard thresholds are the weak spot.
- **Not done yet: calibration.** No Brier score exists so far. The tool is upstream, but the first quarterly
  forecast questions resolve from 2027-Q1. The three horizons are not linked: today's evidence moves 2040 as much
  as 2028.

### Hackathon track: from rules to estimates

1. **Soft thresholds:** make an indicator's likelihood a continuous function of its distance to the threshold
   (e.g. logistic) instead of on/off. The backtest series in `backtest/indicators/reihen/` are ready to fit on.
2. **Estimate coupling and `k` from data:** which values best explain the US years 1973–2025 and the backtest?
3. **A fair backtest:** today the backtest uses today's prior. Set a prior as of a cut-off date, roll forward,
   score with the Brier score (mean squared error of probability forecasts).
4. **Link the horizons** through the transition matrix (`engine/uebergaenge.py`, `engine/committor.py`).

## Transparency and reproducibility

- **One command reproduces the published numbers.** `tests/test_reproduce.py` recomputes today's world state from
  the public model and the radar snapshot and compares it with the state the live radar published:
  scenario probabilities, drivers, signals and indicator states must be identical.
- **Formulas and judgments are separated.** `engine/` contains only formulas. Every number that is a judgment
  (scenario probabilities of the base model, driver–scenario coupling, the damping `k`, the axis states of the
  bottleneck model) sits in a data file and is labelled as such.
- **Links from world to domain are judgments, and say so.** In `domains/energy-transition/domain.json` every
  linked driver carries `"judgment": true` and a one-line reason. Scenarios and indicators are selected by rules.
- **Gaps stay visible.** A number without a source is marked `GAP` (see the grid-connection evidence in the
  energy briefing) rather than silently dropped or invented.
- **No hidden state.** The world state is recomputed each day from base model + data, never carried forward.
- **The backtest reproduces byte for byte.** `make backtest` recomputes all result files in `backtest/indicators/`
  from the committed series; CI fails if anything differs.

### How the engine updates probabilities (short)

Each early-warning indicator is a testable rule on a data series (e.g. `mittel 1 > 115` = last value of Brent above
115 USD). When an indicator changes status since the base model, it becomes a signal on the drivers it affects.
For scenario *s* the signal's likelihood ratio is

```
LR(s) = exp( k · direction · strength · mean_coupling(drivers, s) )
P'(s) ∝ P(s) · LR(s), normalised to 100 per horizon (largest-remainder rounding)
```

`k` (damping, currently 0.15) is the only free parameter; `k = 0` switches updates off. Details: `engine/bayes.py`.
The horizons 2028, 2032 and 2040 are updated independently (a known limitation: the same evidence moves 2040 as
much as 2028).

## Known limitations

- The world model computes for the **world**, not for a country, an industry or a company. The domain lens adds
  that step explicitly and marks it as judgment.
- Engine identifiers and code comments are still **German**; the data is available in English
  (`model/world_model.en.json`, `model/glossary.md`).
- The radar snapshot omits news teaser texts (copyright); titles, links and dates remain. Statement indicators
  may therefore show a few fewer news hits than the live radar; no probability depends on them.
- The upstream model contains more (option scoring, private evaluations); only the public world model is here.

## Hackathon: where to start

See `domains/energy-transition/briefing.md`, section 6, and `docs/process.md`. Good first tasks:

1. Cite the primary source for the grid-connection numbers (marked `GAP`).
2. Replace the judgment axis states of the bottleneck model with measured indices.
3. Add a permitting / grid-connection data series to the radar.
4. Build domain scenarios: world scenario × bottleneck path.
5. Score domain options (permitting reform, storage subsidies, flexible tariffs) across the scenarios
   (expected value, worst case, minimax regret).
6. Build an application on top: the model's public JSON files are the interface.
7. **GDELT as a numeric news series:** turn statement indicator AS08 (cyberattack paralyses critical
   infrastructure in Germany) into a time series with the GDELT DOC 2.0 API (`mode=timelinevol`, share of all
   monitored coverage), compare it with the radar's feed hits, and backtest it from 2017. Mind the rate limit
   (one request every 5 seconds) and cite GDELT as its terms require.

## Licence

Code: MIT (`LICENSE`). Model data, domain data and documentation: CC BY 4.0 (`LICENSE-DATA.md`).
Radar time series remain under the licences of their original publishers (see `radar/SOURCES.md`).

Origin: the world model and engine are developed by Karl Hosang ([zukunftsgut.org](https://zukunftsgut.org)).
This repository is the open edition for collaboration.

Analysis tools added at the hackathon (k sensitivity, plain-language explanation with a number check, forecasting prototype): [docs/analysis-tools.md](docs/analysis-tools.md).
Web frontend for the energy lens (React, runs from checked-in data, no backend): [frontend/README.md](frontend/README.md).
