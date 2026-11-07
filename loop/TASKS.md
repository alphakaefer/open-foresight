# Research loop: tasks

Top open task first. One task = one variant = one round (see `PROMPT.md`). Mark done with the round number.

## Open

1. **`core_set`**: update only with indicators whose series start before 2000, so the indicator set is the same
   in both windows. Tests whether indicators that start late add noise after 2013.
2. **`recalibrate`**: logistic recalibration of the published forecast, fitted on the training window
   (two numbers: intercept and slope). Tests whether the update is useful but badly scaled.
3. **`soft_threshold`**: an indicator counts in proportion to how far its series is past the threshold, instead of
   on/off. Build the soft rule inside `loop/variants.py`; the engine stays unchanged.
4. **`horizon_2032`**: use the 2032 probability of the below-normal-growth scenarios instead of 2028.
5. **`no_2008_fit`** (diagnostic): fit k on the training window without 2007-03 to 2009-12. Round 1 suggests that
   the training gain of a large k comes from the 2008 crisis alone.
6. **Energy outcome** (changes the question, needs the problem owner's OK first): forecast = the model's chance of
   dearer energy (scenarios with energy-price regime above neutral), outcome = a public energy price series
   higher 12 months later. Needs a second outcome in `check.py` and its own held-out ledger.

## Blocked

- **Prior frozen at a past date**: no earlier model version exists in this repo; the prior was set in 2026.
- **Point-in-time data**: the committed series are today's revised values. Needs a real-time (vintage) source per
  series; not yet searched.

## Done

- Round 0: `published`, the reference (see `JOURNAL.md`).
- Round 1: `k_fit`, damping k chosen on the training window.
