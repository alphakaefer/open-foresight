# Research loop: journal

One entry per round, newest last. Every number comes from a `loop/check.py` report; the held-out rows are in
`loop/ledger.tsv`. Template:

```
## Round N · YYYY-MM-DD · variant `name`
Hypothesis: … Refuted if: …
Change: loop/variants.py, function …
Training (n = …): Brier variant …, prior-only …; difference … (SE …)
Held-out, once (n = …): Brier variant …, prior-only …, base rate …; difference … (SE …) -> beats / does not beat
What it means: …
Deviations from the protocol: …
Next: …
```

Windows: training = forecast dates 2000-03 to 2011-12 (n = 48, decline in 15), held-out = 2013-03 to 2025-06
(n = 50, decline in 27), 2012 left out so that no training outcome is known after the held-out window starts.

## Round 0 · 2026-11-07 · variant `published` (reference)

Hypothesis: none; this fixes the reference. The published model (k = 0.15, data up to t − 2 months).
Check first: on all 102 dates the loop reproduces `predict_proto` exactly (Brier 0.2403, prior-only 0.2456,
base rate 0.2528; test `test_published_reproduces_predict_proto`).
Training (n = 48): Brier 0.2035, prior-only 0.2194; difference −0.0159 (SE 0.0058).
Held-out, once (n = 50): Brier 0.2770, prior-only 0.2740, base rate 0.2838; difference +0.0030 (SE 0.0054)
-> does not beat prior-only.
What it means: the small advantage of the model on the full window comes from 2000 to 2011, that is from the
2008 crisis. After 2013 the updates do not help; the model is about as good as its fixed 38 %.

## Round 1 · 2026-11-07 · variant `k_fit`

Hypothesis: the damping k = 0.15 was set by judgement; a k fitted on data forecasts better.
Refuted if: the fitted k does not beat prior-only on the held-out window.
Change: `loop/variants.py`, function `k_fit` (grid 0 to 1, smallest training Brier).
Training (n = 48): k = 0.75 chosen (training Brier 0.1796 against 0.2035 at k = 0.15); difference to prior-only
−0.0398 (SE 0.0194).
Held-out, once (n = 50): Brier 0.3053, prior-only 0.2740, base rate 0.2838; difference +0.0313 (SE 0.0232)
-> does not beat prior-only. It is worse than prior-only and worse than the base rate.
What it means: refuted. A strong update fits the one crisis in the training window and then overreacts after
2013 (forecasts between 0.08 and 0.58). Fitting k on this little history overfits. The judged k = 0.15 is the more
cautious choice, but it does not help either (round 0).
Deviations from the protocol: in this first round the variant was written before its test
(`test_k_fit_picks_from_the_grid_on_training_only`); from round 2 on, test first.
Next: task 1 in `TASKS.md` (`core_set`); task 5 checks the 2008 explanation directly.
