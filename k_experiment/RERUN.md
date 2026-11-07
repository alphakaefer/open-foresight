# k-sensitivity experiment: how to rerun

Read-only on the repo. Nothing inside `open-foresight` is written (results go to `--out`, which must be outside the
repo; default `../open-foresight-results/k_experiment/`, next to your clone): k is changed on an in-memory copy of the
model, bytecode writing is switched off, and `git status` is compared before and after the run.

```bash
# from the repo root
python3 -B k_experiment/k_sensitivity.py                                  # defaults: --repo . --out ../open-foresight-results/k_experiment
python3 -B k_experiment/k_sensitivity.py --repo /path/to/open-foresight --out /tmp/k-results-other
```

Needs Python 3.9+; matplotlib is optional (without it the charts are skipped).

## Outputs (in `--out`)

| File | Content |
|---|---|
| `report.txt` | Everything printed: provenance list, the three gates, all tables |
| `raw_output.json` | All raw numbers (every case, k and horizon; rounded and unrounded; signals and boosts), input file hashes, repo HEAD, git status before/after |
| `table_2040.csv` | Table view of the chart data (2040, every case, k and scenario) |
| `k_total_movement_2040.png` | Total 2040 probability moved vs k |
| `k_per_scenario_2040.png` | Each scenario's 2040 probability vs k |

## Exit codes

`0` ok · `1` bad arguments · `2` a gate failed (case A does not reproduce `weltlage.json`, k = 0 does not give the
base model, or the unrounded path is inconsistent): no results are shown · `3` the repo's git status changed.

Cases B and C are **hypothetical shocks** used to test the formula. They are not forecasts.
To compare runs, check `meta.inputs_sha256` in `raw_output.json`: if the input hashes match, the numbers must match.
