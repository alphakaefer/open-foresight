# Deployment: running open-foresight locally

Written for: developers and hackathon participants who want to run the model, the tests and the
energy-transition briefing on their own machine.

This repository has no production server. It has a small static UI prototype (`ui/`, see `docs/ux-flow.md`) served by Python's built-in web server. It is a set of Python scripts and data files
(`engine/`, `domains/`, `pruefung/`, `backtest/`) that run from the command line. The Foresight Studio web
app lives in a separate repository, which is not published yet. So "deploying locally" here means: install
Python, run the `make` targets, and read the generated files.

## 1. Prerequisites

| Tool | Version | Needed for |
|---|---|---|
| Python | 3.9 or newer (CI uses 3.12, tested locally with 3.13) | everything |
| `pip` and `venv` | ships with Python | installing `pytest` |
| `make` | any | the `make` targets |
| `git` | any | cloning, and CI-style checks with `git diff` |
| `curl` and `bash` | any | `make snapshot` only (fetches live radar data) |
| PHP 8+ | optional | only if you want to run the radar collector yourself (see section 6) |

The engine and the domain lens use only the Python standard library. The only third-party package is
`pytest`, listed in `requirements.txt`.

## 2. Get the code

```bash
git clone https://github.com/alphakaefer/open-foresight
cd open-foresight
```

## 3. Set up a Python environment

Using a virtual environment keeps `pytest` out of your system Python:

```bash
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
```

`.venv/` is git-ignored. To leave the environment later, run `deactivate`.

If you do not want a virtual environment, `python3 -m pip install -r requirements.txt` also works.

## 4. Verify the installation

```bash
make test
```

Expected result: all tests pass (55 at the time of writing). `make test` runs
`python3 -m pytest tests -q`. If `make` is not available, run that command directly.

If you are using the virtual environment and `python3` on your PATH is a different interpreter, use
`.venv/bin/python -m pytest tests -q` instead.

## 5. Run the main targets

| Command | What it does | Writes |
|---|---|---|
| `make energy` | Builds the energy-transition briefing from the world model and the radar snapshot | `domains/energy-transition/briefing.md`, `briefing.json` |
| `make worldstate` | Recomputes today's world state from the model and the radar snapshot | `radar/snapshot/weltlage.recomputed.json` (git-ignored) |
| `make backtest` | Reruns the early-warning backtest (2008, 2020, 2022) from the committed series | `backtest/indicators/*.csv`, `REPORT.md` inputs |
| `make sources` | Regenerates the radar source list | `radar/SOURCES.md` (print to stdout) |
| `make ui` | Serves the UI prototype; open `http://localhost:8000/ui/` (stop with Ctrl+C) | nothing |
| `make regional` | Fetches per-country and per-state values (World Bank, Eurostat, MaStR) for the map comparisons (needs internet) | `radar/regional/regional.json` |
| `make snapshot` | Downloads the latest public radar snapshot (needs internet) | `radar/snapshot/weltlage.json`, `wissensstand.json`, `wissensstand.full.json` (git-ignored) |

Start with `make energy`, then open `domains/energy-transition/briefing.md`.

Notes:

- The generated files are committed. After a run on unchanged code, `git status` should show no changes.
  If it does show changes, your output differs from the committed output. Check whether you edited
  something before assuming a bug.
- `make snapshot` replaces the committed snapshot with the live one. The published world state will then
  differ from the repo. Do this only if you want to test against current data, and do not commit the result
  unless that is the purpose of your change.
- `make worldstate` writes to `weltlage.recomputed.json` on purpose, so it does not overwrite the published
  `weltlage.json`.

## 6. Radar collector (optional, PHP)

`radar/collector/radar-sammeln.php` is written for a PHP web host. Its header says a daily cron job on the
host calls it over HTTP, and it writes `wissensstand.json`, which the app reads. PHP is not installed on
the machine this document was checked on, and the collector was not run here, so its command-line use is
unverified. Read the file header before trying it. It needs outbound internet access to the open-data
sources; `radar/SOURCES.md` lists them. Running the collector changes the radar snapshot, so keep that
change out of commits unless you intend it.

## 7. Run the CI checks locally

CI (`.github/workflows/ci.yml`) runs these steps. Run them before you push:

```bash
make test
make energy && git diff --exit-code domains/
make backtest && git diff --exit-code backtest/
```

Each `git diff --exit-code` fails if the generated output differs from what is committed.

## 8. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `No module named pytest` | Dependencies not installed, or a different Python is active | Activate `.venv`, then run `python -m pip install -r requirements.txt` |
| `make: command not found` (Windows) | `make` is not installed | Run the commands in the `Makefile` directly, or install `make` (e.g. via Chocolatey or WSL) |
| `FileNotFoundError` for `world_model.de.json` | Running a script from another directory | Run from the repository root, as the `make` targets do |
| `make snapshot` fails | No internet, or the radar host is down | Retry later; the committed snapshot is enough for `make test` and `make energy` |
| `git diff --exit-code` fails after `make energy` | Local edits to the model, the snapshot, or the domain files | Run `git diff` to see what changed; revert or commit it intentionally |
| Test failures after changing the model | The model and the published world state no longer agree | Read `tests/test_reproduce.py` to see which values it compares |

## 9. Clean up

```bash
rm -rf .venv .pytest_cache
rm -f radar/snapshot/weltlage.recomputed.json
find . -name __pycache__ -type d -exec rm -rf {} +
```

These files are all git-ignored; removing them does not change tracked files.

## 10. What this document does not cover

- **Hosting a web service:** `make ui` is a local development server only. The full app will live in its own repository.
- **Production deployment of the radar:** the collector is designed for a PHP web host with a daily cron job.
  Setting that up is a separate task and is not described here.
- **Secrets and API keys:** none are required for the steps above. `.env` files are git-ignored if you add one.
