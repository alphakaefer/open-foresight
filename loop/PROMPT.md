# Research loop: prompt for one round

Start in Claude Code from the repo root:

```
/goal python3 -B loop/check.py --goal exits with code 0
continue the goal described in loop/PROMPT.md
```

## The question

Does the world model's data-driven update forecast anything measurable better than its prior alone?
Outcome: German manufacturing production is lower 12 months later (yes or no), at every quarter-end since 2000.
Score: Brier (mean squared error of a probability, lower is better), against prior-only and the historical base rate.

## The goal (checked by `python3 -B loop/check.py --goal`)

A variant beats prior-only on the held-out window by more than 2 bootstrap standard errors,
or ten variants are scored on the held-out window without that. A negative result counts as a result.

## One round = one variant

Read first: `loop/JOURNAL.md` (all earlier rounds), `loop/TASKS.md`, `loop/ledger.tsv`.

1. **Read.** Take the top open task in `TASKS.md`. If it needs background, look for studies in
   `radar/snapshot/wissensstand.json` (OpenAlex items: title, link, date). Cite only what you opened and read.
2. **Propose.** One sentence each: what changes, why it might help, which result would refute it.
3. **Test first.** Add a test to `loop/test_loop.py` that fails before the variant exists
   (registered, returns probabilities, fits on the training window only).
4. **Build.** Add one function to `loop/variants.py` with `@variant(name, what)`. Use only the public parts of `ctx`.
5. **Training.** `python3 -B loop/check.py --variant NAME`, as often as needed.
6. **Held-out, once.** `python3 -B loop/check.py --variant NAME --holdout`. It writes one row to `loop/ledger.tsv`
   and refuses a second run of the same name or the same code under a new name.
7. **Record.** Append the round to `JOURNAL.md` (template there), update `TASKS.md`, add new tasks you found.
8. **Check and commit.** `python3 -m pytest loop/test_loop.py -q`, `make test`,
   `git diff --exit-code model/ domains/ backtest/`. Commit only files in `loop/`: `git add loop/<file>`.

## Never

- Never change the published model or its inputs: `model/`, `domains/`, `backtest/`, `engine/`, `pruefung/`, `radar/`.
- Never use data after the forecast date. A forecaster gets only the `data` argument; never read series files directly.
- Never tune on the held-out window, never run it twice, never rename a variant to run it again.
- Never start a paid API run (`explain/explain_trace.py` only with `--dry-run`).
- Never invent a number or a source. Every number in the journal comes from a `check.py` report.
- Report negative results exactly like positive ones.

## Known limits (do not hide them)

- The prior (38 %) and the base state of the indicators were set in 2026 with knowledge of 2008, 2020 and 2022.
  Only variant versus prior-only isolates the data-driven update.
- Three large crises, overlapping 12-month windows, about 25 independent years.
- The series are today's revised values; the 2-month lag only partly mimics what was known at the time.
- "Below-normal growth in 2028" is read as "German industry lower in 12 months". That mapping is a judgment.
