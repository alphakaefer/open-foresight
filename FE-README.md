# Frontend plan: Germany energy foresight demo

## The story to tell

**Question:** How fast can Germany turn installed renewable capacity into usable, affordable electricity by 2028, 2032, and 2040? What limits that progress?

The demo follows a simple path: **evidence -> possible futures -> bottlenecks -> decisions to investigate**. The world scenarios describe possible external conditions. The German energy lens connects those conditions to the energy question. It does not predict a single electricity price, generation total, or completion date.

This is a frontend plan, not an existing frontend implementation. The application can live in a separate repository, as the main README suggests.

## Recommended demo screen

Build one responsive dashboard with a visible year switcher (`2028 | 2032 | 2040`). Keep the first screen focused on the energy question rather than showing all 12 world scenarios at once.

| Order | Section | What to display | Interaction | Data |
|---|---|---|---|---|
| 1 | Header | The question, selected year, model version, radar timestamp, and an “About these numbers” link | Switch year | `briefing.domain`, `briefing.inputs` |
| 2 | Energy outlook | A 100% stacked bar for the five energy-price regimes, from much cheaper to much more expensive; show percentages and a text summary | Hover/focus a segment to see its scenarios | `briefing.scenarios.energy_price_mass[year]` |
| 3 | Scenario explorer | The 3 or 4 most relevant scenarios for the selected year, with name, probability, short description, and energy-price regime; “View all 12” opens the full list | Select a scenario for its detail panel; year switch re-sorts by probability | `briefing.scenarios.rows[]` |
| 4 | Evidence now | Four cards: renewable electricity share, installed solar capacity, battery storage capacity, and Brent oil price. Each card shows value, unit, observation date, 12-month change when available, and source link | Open source; optionally show a small time series if the raw radar points are wired in | `briefing.series[]`; optional `radar/snapshot/wissensstand.json` |
| 5 | What could change? | Relevant early-warning indicators with status: active, inactive, or no data. Show rule, latest observation, and whether it changed from the base state | Expand for rule and related driver | `briefing.indicators[]` |
| 6 | Bottleneck | Five-axis comparison: generation, storage, grid, control, permitting. Show the modeled gain in usable output from improving **one axis by 50%** and highlight the largest gain | Select an axis to see its starting value and modeled result | `briefing.bottleneck.marginal_gain[]` |
| 7 | Method and gaps | Concise explanation of world model vs. German lens; show judgment labels and missing-source/data badges | Open details | `briefing.drivers[]`, `briefing.bottleneck_evidence[]`, source files |

### Suggested layout

```text
Germany energy transition                  [2028] [2032] [2040]
Question + model/radar date

Energy-price outlook:  [much cheaper | cheaper | neutral | expensive | much more expensive]

Likely world scenarios              Evidence now
[scenario card]                     [renewables] [solar] [storage] [Brent]
[scenario card]
[View all 12]

Early-warning indicators
[active] [inactive] [no data]

What limits usable electricity?
[generation] [storage] [grid] [control] [permitting]
Modeled +50% improvement by axis -> change in usable output

Method, sources, judgments, and gaps
```

On mobile, stack these sections in the same order. Use color plus labels, not color alone, for regimes and indicator states. Make chart values readable by keyboard and screen reader; pair each chart with a short text/table equivalent.

## The 3-minute demo flow

1. **Frame the question (20 seconds):** Germany is adding renewable capacity, but usable electricity also depends on grid, storage, control, and permitting.
2. **Show the outlook (40 seconds):** Switch from 2028 to 2040. Explain that the bars sum probabilities of *world scenarios* by energy-price regime; they are not a forecast of German retail prices.
3. **Open one scenario (30 seconds):** Show its probability, short narrative, and regime. Point to the underlying assumptions.
4. **Show current evidence (40 seconds):** Use the dated renewable, solar, storage, and Brent cards; open one source link. Explain one warning indicator and its threshold.
5. **Show the bottleneck (40 seconds):** Compare a 50% improvement in permitting with a 50% improvement in generation. Explain that the current axis scores are expert judgments, so this is a model illustration, not a measured national forecast.
6. **Close with a decision question (10 seconds):** Which missing evidence should be collected next, and which intervention should the team test across scenarios?

## Frontend technology

**Proposed stack, not a repository requirement:** React + TypeScript + Vite, with plain CSS or the team's existing component library. A single-page app is enough for this demo. Use native SVG/CSS for the stacked bar and bottleneck bars; a chart package is optional. React and Vite both document a `react-ts` starter: [React setup](https://react.dev/learn/build-a-react-app-from-scratch), [Vite templates](https://vite.dev/guide/).

Suggested components: `HorizonPicker`, `EnergyRegimeBar`, `ScenarioCard`, `ScenarioDetail`, `EvidenceCard`, `IndicatorList`, `BottleneckComparison`, `MethodDrawer`. Keep a small data adapter between the JSON shape and UI components so the backend can change delivery without rewriting the screen.

## Data contract and team handoff

The **minimum frontend input** is [`domains/energy-transition/briefing.json`](domains/energy-transition/briefing.json). It already contains the scenario names and probabilities, regime totals, evidence summaries, indicators, bottleneck results, dates, and judgment/gap notes. Treat it as a static fixture first. If the backend offers an API later, it can serve this same JSON shape. Agree on transport and endpoint with the backend developer; no API endpoint exists in this repository today.

| Frontend need | Field / owner |
|---|---|
| Year switching | `domain.horizons`; `scenarios.energy_price_mass[year]`; each row's `p_today[year]` |
| Scenario detail | `scenarios.rows[]` (`id`, `name`, `short`, `regime`, `p_base`, `p_today`) |
| Evidence cards | `series[]` (`latest`, `year_ago`, `change_12m`, `unit`, `source`, `url`) |
| Warning indicators | `indicators[]` (`active_at_base`, `active_today`, `latest`, `rule`, `threshold`) |
| Bottleneck comparison | `bottleneck.marginal_gain[]`; `bottleneck.binding_bottleneck` |
| Provenance | `inputs`; `drivers[].judgment`; `bottleneck_evidence[]` |

**Backend developer:** regenerate/publish the briefing JSON and agree on a stable URL or API response, timestamp, error behavior, and CORS if hosted separately. If scenario option scoring becomes available, supply a separate, explicit result contract. **Data scientist:** check the interpretation of the regime totals and bottleneck calculation; identify which axis values are measured versus judged; validate any new option comparison. **Frontend developer:** build the data adapter, screen, responsive states, source links, and demo fallback using the checked-in JSON.

## Truthful display rules

- Use `p_today` for the displayed scenario probability and `p_base` for comparison. In the current snapshot they are the same because there are no new probability-changing signals. Show **“No probability change since the base model”** rather than fabricating movement.
- Scenario percentages are world-scenario probabilities for a selected horizon. Energy-price regime totals sum those scenarios; they are not probabilities that a particular German electricity price will occur.
- Show observation dates next to values. The radar timestamp is the collection time, not the date of every underlying measurement.
- Show `null` indicator status as **“No data”**, never “inactive.” Missing series should show an explicit empty state.
- Label the bottleneck axis scores as **judgment-based relative indices**. The +50% comparisons are model sensitivity calculations, not promised real-world gains.
- Keep the grid-connection claim marked **“Source needed”** until the team finds a primary source. Do not feature its uncited figures as a headline.
- If the backend adds simulated interventions, visibly label them **“What-if scenario”** and keep them separate from the published baseline. Do not change official scenario probabilities in the browser without a defined calculation from the data scientist/backend developer.

## Build order for a short hackathon

1. Load the checked-in briefing JSON, add a year switcher, energy-regime bar, and scenario cards.
2. Add evidence cards with source links and dates, plus indicator statuses.
3. Add the bottleneck comparison and short method/gap panel.
4. Polish responsive layout, keyboard access, loading/error states, and the 3-minute demo path.
5. Connect to the backend's published JSON only after its contract is stable. Keep the checked-in snapshot as an offline demo fallback, clearly labeled with its date.

**Demo-ready check:** Changing the year updates every probability view; regime segments total 100%; every evidence card has a source and observation date; missing data and judgments are visible; the page works at mobile and projector widths; the demo still runs from the dated snapshot if the API is unavailable.

## Source files

- [Energy briefing (human-readable)](domains/energy-transition/briefing.md)
- [Energy briefing (machine-readable)](domains/energy-transition/briefing.json)
- [Domain configuration and judgment inputs](domains/energy-transition/domain.json)
- [Foresight process](docs/process.md)
- [Radar sources](radar/SOURCES.md)
