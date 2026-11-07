# UX flow: energy foresight explorer (Berlin → Brandenburg → Germany → Europe → Global)

Written for: analysts and developers who want to understand or extend the UI prototype in `ui/`.

The prototype is a static page (`ui/`) that reads this repository's JSON. It computes nothing about the model.
Start it with `make ui` and open `http://localhost:8000/ui/`.

## Who it is for

| Persona | Wants | Where they spend time |
|---|---|---|
| Policy analyst | Which world is likely, which bottleneck decides the pace | Scenarios, Bottleneck (Germany) |
| Regional energy planner (Land or city) | Brandenburg or Berlin numbers | Mostly the GAP views and their data plan |
| Researcher | Where every number comes from | Provenance panel, table views |

## The flow

1. **Frame.** The header shows the question, model version and data timestamps.
2. **Pick a scale.** A breadcrumb lists `Global ▸ Europe ▸ Germany ▸ Brandenburg ▸ Berlin`. Each level says how much
   data it has: *full*, *proxy* or *GAP*. The default is Germany. The URL hash (`#germany/2028`) keeps the view shareable.
3. **Scenarios.** Pick a horizon (2028, 2032, 2040). Bars compare the base model with today, and a row shows the
   probability by energy-price regime.
4. **Bottleneck** (Germany only). Five axes, the weakest one marked, and what one improvement step on each would add.
5. **Early-warning indicators.** Each shows its rule, latest value, and whether it is active today.
6. **Drivers.** The world drivers linked to this level, with a one-line status.
7. **Radar series.** A line chart per series with hover values and a table view.
8. **Watchlist.** The open tasks from the domain file. Option scoring is stated as not yet part of the repository.
9. **Provenance** (button, always available). Lists every tagged block with its file path.

## Maps and interactions

- **Map per level** (world, Europe, Germany's states, and zoomed Brandenburg and Berlin). Outlines are in `ui/geo/`
  (Natural Earth, simplified; see `ui/geo/SOURCES.md`).
- **The colour shows data coverage, not a measured value.** The repo has no regional energy numbers, so a value
  map would be invented. Blue is data, lighter blue is national data only, purple is GAP, grey is nothing.
- **Region chips** above the map select any of the five regions directly, in sync with the breadcrumb.
- **Parameter selector and tiles.** Choose an energy parameter from a dropdown, or click a tile (value and 12-month
  change). The map then shows *where the parameter applies* plus a readout card with value, change, a mini trend and
  a Measured or Model-output tag. Click the tile again to go back to coverage.
  - Global: probability of more expensive energy (from the scenarios), Brent, US real yield.
  - Euro area: ECB rate, core inflation, GDP growth. Shown as an aggregate and not drawn per country, because the repo
    has no list of members.
  - Germany: renewable share, PV capacity, battery storage, industrial production. National values only.
  - Brandenburg and Berlin: wind capacity, grid queue, peak load, rooftop PV are listed as **GAP** with what data is needed.
  - Choosing a national parameter on the Berlin map says "None for Berlin" and labels the value inherited.
- **Comparison maps (colour-coded sub-regions).** Selecting a region shows its sub-regions coloured by a real
  per-region parameter, with a ranked list, a legend with value ranges, and hatching for regions with no value.
  - Global: countries by renewable share of final energy and energy use per person (World Bank).
  - Europe: countries by renewable electricity share, energy import dependency, household electricity price and
    energy inflation (Eurostat). The two World Bank parameters also work here.
  - Germany: states by wind turbines and solar PV units in operation (MaStR).
  - Brandenburg and Berlin: no sub-regions exist in the repo, so the state is outlined and ranked among the 16 German states.
  - Colour: five equal-sized groups by rank. Direction-aware (green is the favourable end; high renewables are green,
    high prices are red). Parameters with no good or bad end use a single blue ramp. A "Colour-blind safe" palette
    (red to blue) is one click away; values are also in tooltips and the list.
  - Hovering a region highlights its row in the list, and the reverse.
- **Click a highlighted region to zoom in** (Europe from the world map, Germany from the Europe map, Brandenburg or
  Berlin from the Germany map). Hover shows what exists for that region. Regions are keyboard-focusable
  (Tab, then Enter or Space). A "Zoom out" button goes up one level.
- **Click a scenario bar** to open its description, regime values and all three horizons. The URL records open
  scenarios (`#germany/2028/S01`), so a view can be shared.
- **What-if sliders** on the bottleneck chart. Move any axis and see the usable output change against the published
  value. The page checks its own formula against the published number on load and warns if they differ.
  The axis states are judgments, so this is an exploration, not a forecast.

## What each level shows

| Level | Content | Honest label |
|---|---|---|
| Global | 12 scenarios, Brent, US real yield, five drivers | full data |
| Europe | same scenarios, 'European Restart' highlighted, Eurozone GDP, core inflation, ECB rate, Brent | proxy: no European energy model exists |
| Germany | scenarios, bottleneck, six indicators, six series, six drivers | full data |
| Brandenburg | data plan, plus context inherited from Germany | GAP |
| Berlin | data plan, plus context inherited from Germany | GAP |

Rules the design follows:
- Every block carries one tag: **Measured** (a radar series), **Model output** (engine result), **Judgment**
  (a human decision in an editable file), **GAP** or **Inherited**.
- A child level may show its parent's context, but only under an *Inherited* tag, never as its own number.
- A missing number is a GAP, never an estimate.

## Where to change things

| To change | Edit |
|---|---|
| Which series, indicators or drivers a level shows | `ui/regions.json` |
| Which parameters the map offers, their scope, direction (good = high/low) and any caution | `ui/parameters.json` |
| Per-region numbers | `make regional` (writes `radar/regional/regional.json`) |
| English names for series | `ui/labels.en.json` |
| The numbers | not here: rerun `make energy` / `make worldstate` / `make snapshot` |
| Add real Brandenburg or Berlin data | add series to the radar, then list them in `ui/regions.json` and set `coverage` |

## Known limits

- Per-region numbers come from different years (see the period in each tooltip), and some small countries are not in the simplified outlines. MaStR counts are units, not capacity.
- Scenarios are global. Selecting a level does not change their probabilities.
- Brandenburg and Berlin have no measured data. The value there is the data plan.
- Series names in the snapshot are German; the English map must be kept up to date.
- Map outlines are simplified, for orientation only. Berlin is small inside Brandenburg on the Germany map; use the zoom.
- Verified in headless Chrome (all five maps, map and breadcrumb navigation, scenario expand, what-if sliders); not tested on mobile widths, other browsers, or screen readers.
