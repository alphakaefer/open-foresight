# What-if demo page

A single static page (no framework, no build step, no server) that shows today's world state and lets you try
**hypothetical what-ifs**: switch any number indicator on or off, choose the damping `k`, and see how every scenario
moves and why.

It complements the other two interfaces: [`frontend/`](../frontend/) (React app for the energy lens) and [`ui/`](../ui/)
(map prototype). Its addition is **engine-computed what-ifs for every indicator** that has data and an effect
(currently 16 indicators × 7 values of `k`).

## Run

```bash
python3 -B whatif/build_data.py     # from the repo root: rebuilds whatif/data.js from the repo
```

Then open `whatif/index.html` in a browser (double-click works). To show it to others on the same network:
`python3 -m http.server 8000 --directory whatif`, then open `http://<your-ip>:8000`.

`data.js` is checked in so the page works right after cloning. Rebuild it after the model or the radar snapshot changes.

## What you can do

- **Horizon tabs** (2028 / 2032 / 2040): the chart re-sorts by the selected year.
- **Click a scenario:** plain-language description, start / today / what-if probability per horizon, revision range,
  regime values, and its indicators.
- **What if?** on an indicator: a HYPOTHETICAL banner, the new probabilities (grey line = today, ▲/▼ = change), and
  *why it moved*: the scenarios that gain and lose most, each with its coupling to the driver and its boost.
- **Damping k** (0 to 0.5): scales every what-if. Without a what-if it changes nothing, because today no indicator has
  changed since the base model; the page says so.
- **Energy section:** probability by energy-price regime for the selected horizon, today vs what-if; the binding
  bottleneck and its GAP source.
- **Shareable state:** the URL keeps the horizon, what-if, `k` and selected scenario, e.g.
  `index.html#h=2040&w=A05&s=S08`. The back button works.

## Where the numbers come from

Nothing is hard-coded and no model maths is re-implemented in JavaScript.

- `build_data.py` reads `radar/snapshot/weltlage.json`, `radar/snapshot/wissensstand.json`, `model/world_model.de.json`,
  `model/world_model.en.json` and `domains/energy-transition/briefing.json`.
- **Check first:** the engine must reproduce the published `weltlage.json` exactly; otherwise nothing is written.
- **What-ifs:** for every number indicator with data and an effect, its status is flipped (on ↔ off) and
  `engine/tagesstand.py` `aus_status()` recomputes all probabilities, for each `k`. Every result is checked to sum to
  100 per horizon. The page only looks results up.
- **Not simulated** (the page says why): indicators without data (AS03, AS09), indicators with no effect defined
  (A02, A11), and statements, which never move a probability.
- The only arithmetic in the page is summing scenario probabilities per energy-price regime, the same rule as
  `domains/lens.py`; for today's values it equals `briefing.json`.

## Limits

- One indicator at a time; combinations are not precomputed.
- What-ifs are **hypothetical, not forecasts**. Starting probabilities, couplings, rules and strengths are judgments by
  the model author, and the model has not yet been checked against real outcomes (see the README, "What kind of model
  is this?", and [`docs/analysis-tools.md`](../docs/analysis-tools.md)).
- English names are joined by `id` from `model/world_model.en.json`; display order and labels of the energy-price
  regimes are a small display setting in `app.js`.
