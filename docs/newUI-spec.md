# newUI specification: energy foresight demo

**Status:** proposed UI, 2026-11-07

**Branch:** `newUI` (created from `develop` at `35e6dc2`)
**Audience:** hackathon judges and teammates who need to understand what the model says, what changes under an assumption, and why.

## Goal

Show the Germany energy transition outlook and make the newly added model explanation and sensitivity outputs understandable in one demo. A viewer should be able to answer:

1. What does the published snapshot say for 2028, 2032, or 2040?
2. What changes if an oil-price warning indicator is **assumed** to switch on?
3. Which indicator, driver, and model setting caused the change?
4. How much does the result depend on the chosen damping parameter `k`?

This is a scenario exploration interface. It does not claim to forecast a specific German electricity price or the date when the energy transition will finish.

## Single-page experience

### 1. Published outlook (default)

- Header: “Germany's energy transition”, the domain question, selected horizon (`2028`, `2032`, `2040`), model version, radar timestamp, and a visible **Published snapshot** label.
- Energy-price regime bar: five segments (much cheaper through much more expensive), percentages summing to 100 for the selected horizon.
- Scenario list: show the leading scenarios by `p_today[horizon]`, their short narratives, and their energy-price regimes; allow “View all 12”. Show base versus current probability only when there is an actual difference.
- Evidence strip: renewable share, solar capacity, battery capacity, and Brent, with each value's observation date, unit, 12-month change where available, and source link.
- Warning indicators: active, inactive, and **no data** as separate states.
- Bottleneck panel: compare the five judgment-based axis scores and the model's gain from raising one axis by 50%. Label this as a model sensitivity result.

In the checked-in snapshot, no indicator changed since the model base date. The default screen therefore says **“No probability change since the base model.”** It must not display a fake live delta.

### 2. What-if comparison

A clearly marked **Hypothetical what-if** control offers only the supported demo assumptions:

- `A05`: Brent above 110 USD for more than two quarters switches on.
- `A13`: Brent below 70 USD switches on.

After selection, show two aligned probability views for the selected horizon: **published snapshot** and **hypothetical result**. Use percentage-point deltas, not only color or animation. The regime bar and scenario list should update together. A persistent banner states: **“Assumed indicator switch; this is not observed data or a forecast.”** A “Reset to published” action restores the default view.

The interaction must use precomputed engine results or a backend calculation. The browser must not invent its own Bayesian formula. The `k_sensitivity.py` experiment already computes cases A (real), B (`A05`), and C (`A13`) for all three horizons and the seven supported `k` values.

### 3. Why did it change?

Beside the selected scenario, offer a **Why this changed** panel with a readable chain:

`assumed indicator -> affected driver -> direction and strength -> scenario boost -> probability before/after`

Show the signal's source rule and the relevant model judgments. The `explain_trace.py` trace contains `changed_indicators`, `signals`, `probabilities`, `big_changes`, `energy_price_mass`, `gaps`, and `known_limitations`. Render this structured trace as the reliable fallback. If a generated plain-language explanation is available, display it only when its number check passed. A failed check must never appear as a valid explanation.

For real data, the explanation should simply say that no indicator changed and no probability moved. The explanation trace is tied to the model's current `k = 0.15`; when the user explores a different `k`, show the numerical sensitivity result and hide or label the fixed-`k` prose accordingly.

### 4. How sensitive is the model?

An expandable **Model sensitivity** panel shows the seven tested values of `k`: `0`, `0.05`, `0.10`, `0.15`, `0.20`, `0.30`, `0.50`. Mark `0.15` as the model's current choice. For a selected hypothetical case, show:

- total probability movement versus `k` (2040 view, as in the experiment's chart/table);
- selected scenario probability versus `k`;
- the selected `k`'s probability distribution for the chosen horizon, from `raw_output.json`.

Use the experiment's exact values for the sensitivity chart and explain that displayed published scenario probabilities are rounded to whole percentages. Keep the main published outlook unchanged when `k` is explored. Label `k` as a **chosen model parameter, not a value estimated from data**.

### 5. Sources and limits

Provide a compact “How this works” panel with links to sources. State that base probabilities, driver couplings, indicator strengths, and bottleneck axis scores are judgments. Missing data is visible. The uncited grid-connection figures in the energy briefing must carry **Source needed** and stay out of headline cards.

## Screen hierarchy

```text
Header: question | model date | radar date | horizon
Published energy-price outlook + top scenarios
Evidence now + warning indicators
------------------------------------------------
What-if switch: Published | A05 assumed on | A13 assumed on
Published vs hypothetical scenario/regime comparison
Why this changed: indicator -> driver -> boost -> probability
Model sensitivity: k values, chart, selected scenario
------------------------------------------------
Energy bottleneck + methods, judgments, gaps, sources
```

On mobile, stack the sections in this order. The real/hypothetical label stays visible while scrolling. Every chart has a text summary or table. All controls work by keyboard; color is never the only signal for a probability change or status.

## Data and integration contract

| UI area | Existing source | Delivery expectation |
|---|---|---|
| Published energy view, evidence, bottleneck | `domains/energy-transition/briefing.json` | Checked-in static JSON is the offline fallback. |
| Real and hypothetical trace | `explain/explain_trace.py` output `trace.json` (`trace` object) | Precompute with `--real --dry-run` and `--whatif A05 --dry-run`; generate an `A13` trace if that explanation is offered. Use `--repo` and `--out` because the scripts' defaults point to the author's machine, and output must be outside this repo. |
| Optional prose explanation | `explanation.md` / explanation JSON plus `check_report.json` | Backend or build pipeline may supply it after a paid API run. Render only if `check_report.passed === true`. Never expose `ANTHROPIC_API_KEY` to the frontend. |
| `k` experiment | `k_experiment/k_sensitivity.py` output `raw_output.json`; `table_2040.csv` for a simpler chart feed | Precompute once with explicit `--repo` and `--out`; serve the resulting JSON/CSV as static assets or via backend. |
| Provenance | `trace.json.run`, `raw_output.json.meta`, briefing `inputs` | Show model version, input snapshot date, run date, and mode. Reject or visibly flag artifacts from a different model/snapshot version. |

No HTTP endpoint is defined in this repository. The backend developer should choose a stable way to publish these artifacts and confirm an artifact manifest or equivalent metadata before the frontend combines them. The frontend should normalize the files in one adapter rather than letting components depend on raw script shapes.

### Data safety checks in the adapter

- Require `raw_output.status === "ok"` and all three experiment gates to pass before showing sensitivity results.
- Require `trace.run.gates` to pass and `trace.meta.is_hypothetical` to match the selected mode.
- Require the same model version and radar/world-state snapshot across the published briefing and experiment/trace artifacts. If they differ, show “Results from different snapshots” and disable cross-artifact deltas.
- Derive each visible delta as `hypothetical - published` for the same scenario and horizon. Display **percentage points**.
- If an artifact is missing, keep the published dashboard usable and mark the affected panel “Unavailable for this snapshot.”

## Team handoff

- **Frontend:** build the responsive page, year and mode controls, chart/table views, data adapter, provenance badges, and fallback/error states.
- **Backend:** publish the briefing plus approved precomputed trace and sensitivity artifacts; provide stable URLs and a version/snapshot manifest. Keep paid explanation generation and API keys server-side if used.
- **Data scientist:** sign off on the interpretation of scenario probability, regime mass, `k` sensitivity, and the judgment labels. Review the what-if assumptions and any future scenario-option scoring.

## Demo acceptance checks

1. The default screen shows the checked-in published probabilities and says there is no new probability-changing signal.
2. Switching 2028/2032/2040 updates all scenario and regime numbers consistently; regime totals equal 100%.
3. Selecting `A05` or `A13` shows a persistent hypothetical label and before/after percentage-point changes; reset returns to published values.
4. The explanation panel points to the indicator, driver, boost, and probability fields in the same trace. No unchecked generated prose is displayed.
5. Changing `k` updates only the sensitivity view; `k = 0` returns base probabilities, and `k = 0.15` is marked current.
6. Every evidence card displays its observation date and source. Missing data, judgment inputs, and uncited claims are visibly identified.
7. The page works offline from dated static artifacts and remains readable on a phone and projector.

## Scope boundary for this branch

This file specifies the UI. The application code, generated experiment artifacts, and backend delivery are separate follow-up work. The existing [FE-README](../FE-README.md) remains the broader frontend plan; this spec defines the new comparison and explanation experience added on `develop`.
