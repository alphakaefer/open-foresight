# Energy Futures frontend

A responsive React + TypeScript interface for the Germany energy-transition lens. It runs from checked-in, dated model artifacts, so the page works without a backend or paid explanation call.

## Run

```bash
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite. For a production build, run `npm run build`; the static site is written to `frontend/dist/`.
Asset paths are relative (`base: './'` in `vite.config.ts`), so `dist/` also works in a subfolder. The fonts are bundled
(Fontsource), so the page loads nothing from third-party servers. A hosted copy can show imprint and privacy links in the
footer by setting `VITE_IMPRINT_URL` and `VITE_PRIVACY_URL` at build time, for example in `.env.production.local`
(ignored by git). Without them the footer shows no legal links.

## Explanation trace from commit `35e6dc2`

That commit adds `explain/explain_trace.py` and `explain/check_numbers.py`. The script reruns the model and records a trace of changed indicators, affected drivers, scenario boosts, and probabilities before and after. It can optionally ask Claude to explain that trace, then checks every number in the generated text. It also adds `k_experiment/k_sensitivity.py` to show how the chosen damping value changes hypothetical results. These additions do not replace the published world model or create a new live API.

This frontend displays the deterministic, checked trace. For example, assuming `A05` switches on connects the Brent warning to driver `G3` (energy chokepoints); for scenario `S01` in 2028, the displayed boost is `1.2671x` and the probability moves from `26%` to `28%`. Assuming `A13` switches on gives a `0.8540x` boost for `S01` and moves it from `26%` to `24%`. Both are labeled hypothetical. The real snapshot has no changed signal, so its published probabilities do not move. The page does not display Claude-generated prose.

The sensitivity panel shows the separate `k` experiment. For the A05 assumption, total probability movement in 2040 is about `6.91` percentage points at the model's current `k = 0.15`, versus `13.52` at `k = 0.30`. The published view is held fixed while this control changes.

## Browser tests

```bash
npm run test:e2e
npx playwright show-report
```

Playwright starts a local Vite server and runs Chromium tests for the published outlook, year switching, A05 and A13 trace explanations, the sensitivity control, reset behavior, and a mobile viewport. The A05 test attaches a screenshot of its explanation card to the report. Browser binaries can be installed with `npx playwright install chromium` if missing. The tests compare UI values directly with the bundled trace JSON.

## Forecast check from commit `70c4ade`

The **Forecast check** section shows the new `predict_proto` result. It compares the model, fixed 38% prior, and a historical-frequency baseline for 102 quarterly forecasts of whether German manufacturing production fell 12 months later. A chart shows model and baseline probabilities; the quarter selector shows a specific forecast and its observed outcome. Brier scores are recomputed from the bundled rows by `npm run check:data`.

The result is marked **PROTOTYPE / NOT PROOF**. The prior was set in 2026 with knowledge of past crises, world-scenario growth is only a judged proxy for German manufacturing decline, and outcomes use revised data with overlapping 12-month windows. The frontend uses `src/data/prediction.json`, copied from `predict_proto/predict_proto.py`'s `raw.json` output on `70c4ade`. Refresh that file only after the script's checks pass.

## What the controls do

- The **year** selector changes all published scenario and energy-regime probabilities.
- **Published / Oil stays high / Oil eases** compares the real snapshot with an engine-computed hypothetical A05 or A13 signal. The published outlook stays visible and unchanged.
- Selecting a **scenario** shows its indicator → driver → boost → probability explanation from the checked engine trace.
- Selecting **k** changes only the sensitivity charts. The model's current setting is `0.15`; `k = 0` has no signal effect.
- Evidence cards link to their published sources. Missing data and judgment-based inputs are labeled.

## Bundled data

`src/data/` contains:

| File | Source |
|---|---|
| `briefing.json` | `domains/energy-transition/briefing.json` |
| `sensitivity.json` | `k_experiment/k_sensitivity.py` → `raw_output.json` |
| `trace-real.json` | `explain/explain_trace.py --real --dry-run` → `trace.json` |
| `trace-a05.json` | `explain/explain_trace.py --whatif A05 --dry-run` → `trace.json` |
| `trace-a13.json` | `explain/explain_trace.py --whatif A13 --dry-run` → `trace.json` |
| `prediction.json` | `predict_proto/predict_proto.py --repo .` → `raw.json` |

The trace files were generated without an AI API call. The UI uses their deterministic engine data and does not show AI-written prose. The sensitivity file passed its three engine gates. All artifacts use model v1.4.0 and the 2026-11-07 radar/world-state snapshot. At startup the app compares their input hashes and dates; it stops the comparison if they disagree.

When updating data, run the scripts from the repo root. By default their results go to `../open-foresight-results/<tool>/`, next to your clone; an `--out` folder must also be outside this repository. Copy the checked JSON outputs into `src/data/` only after the gate results pass, then run `npm run build`.

## Scope

This frontend was built on the `predictUI` branch and merged into `main` on 2026-11-07. There is no HTTP API in this repository. The page reflects the [UI spec](../docs/newUI-spec.md) and the broader [frontend plan](../FE-README.md). The model and radar values remain owned by the original data files.
