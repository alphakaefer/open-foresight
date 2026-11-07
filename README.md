# open-foresight

An open, reproducible foresight stack: a **world model** of scenarios for 2028 / 2032 / 2040, a **radar** that
collects open data to monitor it, a **domain lens** that breaks the world model down to one concrete question,
and the **Foresight Studio** web app that walks a team through the full foresight process.

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
Foresight Studio (app/): evidence → key factors → scenarios → options
```

## Quick start (5 minutes)

```bash
git clone https://github.com/alphakaefer/open-foresight && cd open-foresight
python3 -m pip install -r requirements.txt     # only pytest; the engine is pure standard library
make test                                       # reproduces the published world state, checks the domain model
make energy                                     # writes domains/energy-transition/briefing.md
make app                                        # Foresight Studio on http://localhost:5173 (needs Node 20+)
```

Start reading at **[domains/energy-transition/briefing.md](domains/energy-transition/briefing.md)**.

## What is in here

| Path | What | Language |
|---|---|---|
| `model/world_model.de.json` | The public world model, exactly as published upstream (German original, authoritative) | data |
| `model/world_model.en.json` | English translation: same structure, same keys, same numbers | data |
| `model/glossary.md` | German keys and values → English | EN |
| `engine/` | Pure-Python engine: Bayes update (`bayes.py`), evidence inflow (`zufluss.py`), magnitude levels (`stufen.py`), range (`spanne.py`), daily world state (`tagesstand.py`) | code comments DE |
| `radar/snapshot/` | Radar snapshot (`wissensstand.json`) and the world state computed from it (`weltlage.json`) | data |
| `radar/SOURCES.md` | All radar sources and time series, generated from the snapshot | EN |
| `radar/collector/` | The PHP collector that builds the radar from open sources | code comments DE |
| `domains/lens.py` | Domain lens: world model → one domain question | EN |
| `domains/energy-transition/` | Domain config, generated briefing (md + json) | EN |
| `app/` | Foresight Studio web app (React, Vite, TypeScript, bring-your-own AI key) | UI DE, README EN |
| `docs/process.md` | The foresight process step by step, and where each step lives in this repo | EN |
| `tests/` | Reproducibility and model tests | |

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
- Engine identifiers, code comments and the app UI are still **German**; data is available in English.
  Translating the app UI is a good hackathon task.
- The radar snapshot omits news teaser texts (copyright); titles, links and dates remain. Statement indicators
  may therefore show a few fewer news hits than the live radar; no probability depends on them.
- The upstream model contains more (option scoring, private evaluations); only the public world model is here.

## Hackathon: where to start

See `domains/energy-transition/briefing.md`, section 6, and `docs/process.md`. Good first tasks:

1. Cite the primary source for the grid-connection numbers (marked `GAP`).
2. Replace the judgment axis states of the bottleneck model with measured indices.
3. Add a permitting / grid-connection data series to the radar.
4. Build domain scenarios: world scenario × bottleneck path.
5. Score domain options (permitting reform, storage subsidies, flexible tariffs) in the app's decision analysis.
6. English UI for the app.

## Licence

Code: MIT (`LICENSE`). Model data, domain data and documentation: CC BY 4.0 (`LICENSE-DATA.md`).
Radar time series remain under the licences of their original publishers (see `radar/SOURCES.md`).

Origin: the world model, engine and app are developed by Karl Hosang ([zukunftsgut.org](https://zukunftsgut.org)).
This repository is the open edition for collaboration.
