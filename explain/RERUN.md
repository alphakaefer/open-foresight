# explain_trace: plain-language explanation of the engine, with a number check

Read-only on the repo: no bytecode, `git status` compared before and after. Results go outside the repo, by default
to `../open-foresight-results/explain/` (next to your clone); `--out` must point outside the repo.

```bash
# from the repo root
python3 -B explain/explain_trace.py --whatif A05 --dry-run   # trace + prompt + checker self-tests; NO API call
python3 -B explain/explain_trace.py --real --dry-run
python3 -B explain/explain_trace.py --whatif A05             # PAID: 1 call, plus 1 retry only if the number check fails
python3 -B explain/explain_trace.py --real                   # PAID
python3 -B explain/check_numbers.py <run folder>/trace.json <explanation.json>   # re-check offline
python3 -B explain/check_numbers.py --self-test <run folder>/trace.json
```

Before a paid run:
- `pip install anthropic` (not needed for dry runs)
- set `ANTHROPIC_API_KEY` as an environment variable in the shell that runs the script. Never put it in a file.

Model `claude-opus-5-5`, effort `medium`, structured JSON output, server-side refusal fallback
(`fallbacks: "default"`, beta `server-side-fallback-2026-07-01`). The answering model is recorded in
`attemptN_response.json` (`model_that_answered`).

Per run, in `<out>/<UTC time>_<mode>/`: `trace.json` (`run` = local provenance, `trace` = the only part sent),
`prompt.json` (exact request, no key), `attemptN_response.json`, `attemptN_check.json`, `check_report.json`,
`explanation.md` (with a FAILED NUMBER CHECK banner if it still fails after the retry).

Exit codes: 0 ok, 1 setup error, 2 engine gate failed, 3 repo changed, 4 number check failed after retry,
5 API error or refusal.

What-if traces are HYPOTHETICAL: one indicator is assumed to switch on. They are not forecasts.
