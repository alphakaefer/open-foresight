"""k-sensitivity experiment for the open-foresight Bayes update (read-only on the repo).

Question: how much do the 2040 scenario probabilities change when the damping k
(model/world_model.de.json : bayes.k_daempfung, currently 0.15) is changed?

Cases
  A  real data from the radar snapshot, no changes (today's actual situation)
  B  HYPOTHETICAL shock: indicator A05 'Brent above 110 $ for more than two quarters' switches ON
  C  HYPOTHETICAL shock: indicator A13 'Brent below 70 $' switches ON
B and C are what-if inputs to test the formula. They are NOT forecasts.

Safety
  - The repo is only read. k is changed on an in-memory copy of the model.
  - Python bytecode writing is switched off, so no __pycache__ appears in the repo.
  - git status of the repo is recorded before and after; the script fails if it changed.

Gates (the script stops with exit code 2 if one fails, before any result is shown)
  1. Case A at every k reproduces the published p_tag in radar/snapshot/weltlage.json.
  2. At k = 0 every case equals the base model (rounded and unrounded).
  3. The unrounded path (rechne_am) rounds to exactly the same numbers as aus_status.

Usage
  python3 -B k_experiment/k_sensitivity.py [--repo .] [--out ../open-foresight-results/k_experiment]
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True  # must come before importing the repo's engine

import argparse
import copy
import hashlib
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_REPO = HERE.parent  # the script lives in the repo
DEFAULT_OUT = HERE.parent.parent / "open-foresight-results" / "k_experiment"  # outside the repo
K_VALUES = [0.0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.50]
K_CURRENT = 0.15
FOCUS = "2040"
TOL = 1e-9
HYPO = "HYPOTHETICAL SHOCK - not a forecast"

CASES = {
    "A": {"flip": None, "title": "Case A: real snapshot data, no indicator changed (actual situation)"},
    "B": {"flip": "A05", "title": f"Case B [{HYPO}]: A05 'Brent above 110 $ for more than two quarters' switched ON"},
    "C": {"flip": "A13", "title": f"Case C [{HYPO}]: A13 'Brent below 70 $' switched ON"},
}

SOURCES = {
    "k": "model/world_model.de.json : bayes.k_daempfung (line 2064, value 0.15); read by engine/tagesstand.py "
         "rechne_am() (line 262). Overridden here on an in-memory copy only.",
    "base": "model/world_model.de.json : szenarien[].wahrscheinlichkeit[h] (whole percent)",
    "base_exact": "model/world_model.de.json : zufluss.p_basis[h] (prior used on the active path)",
    "published": "radar/snapshot/weltlage.json : szenarien[].p_tag[h]",
    "rounded": "engine/tagesstand.py tagesstand() [case A] or aus_status() [B, C] -> rechne_am() -> "
               "engine/bayes.py update_probabilities() -> _update_zufluss() -> largest_remainder(); field p_tag",
    "exact": "engine/tagesstand.py rechne_am() -> engine/bayes.py _update_zufluss() -> engine/zufluss.py "
             "posterior() / untergrenze(); field posterior_exakt (before rounding)",
    "status": "engine/tagesstand.py tagesstand() -> pruefe() / gilt() / stufen.stufe(); anzeichen[].stufe_basis, stufe_jetzt",
    "signal": "engine/tagesstand.py anzeichen_signal(), from model anzeichen[].wirkung",
    "lr": "engine/bayes.py log_likelihoods() + coupling_mean() (exp taken), weight from engine/zufluss.py gewichte(); "
          "returned in weltlage signale[].likelihood / .gewicht",
    "regime": "model/world_model.de.json : szenarien[].regime.energy_price, summed per level in this script "
              "(same rule as domains/lens.py scenarios())",
    "names": "model/world_model.en.json : szenarien[].name (English labels only; numbers come from the .de file)",
    "metrics": "computed in this script from the values above",
}
REGIME_LABEL = {-2: "much cheaper", -1: "cheaper", 0: "neutral", 1: "more expensive", 2: "much more expensive"}


class Stop(Exception):
    """A gate failed: stop before showing results."""


# --- small helpers -------------------------------------------------------------

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(repo: Path, *args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()
    except Exception as e:  # git missing or not a repo
        return f"<git unavailable: {e}>"


def table(headers: list, rows: list) -> list:
    cells = [[str(h) for h in headers]] + [[str(c) for c in r] for r in rows]
    widths = [max(len(r[i]) for r in cells) for i in range(len(headers))]
    fmt = lambda r: "  ".join(c.ljust(w) if i < 2 else c.rjust(w) for i, (c, w) in enumerate(zip(r, widths)))
    return [fmt(cells[0]), "  ".join("-" * w for w in widths)] + [fmt(r) for r in cells[1:]]


def both(rounded, exact) -> str:
    return f"{rounded} ({exact:.3f})"


def movement(post: dict, prior: dict) -> float:
    """Total probability moved, in percentage points: half the sum of absolute changes."""
    return 0.5 * sum(abs(post[s] - prior[s]) for s in prior)


# --- experiment -------------------------------------------------------------------

class Experiment:
    def __init__(self, repo: Path):
        self.repo = repo
        sys.path.insert(0, str(repo))
        from engine import io, tagesstand as ts  # noqa: E402  (imported from the repo, read-only)
        self.io, self.ts = io, ts
        snap = io.RADAR_SNAPSHOT
        self.paths = {"world_model.de.json": io.MODEL_DE, "world_model.en.json": io.MODEL_EN,
                      "wissensstand.json": snap / "wissensstand.json", "weltlage.json": snap / "weltlage.json"}
        self.model = io.load_world_model("de")
        self.names = {s["id"]: s["name"] for s in io.load_world_model("en")["szenarien"]}
        self.ws = io.load_json(self.paths["wissensstand.json"])
        self.published = io.load_json(self.paths["weltlage.json"])
        self.heute = datetime.fromisoformat(self.published["stand"].replace("Z", "+00:00"))  # as tests/test_reproduce.py
        self.sids = [s["id"] for s in self.model["szenarien"]]
        self.horizons = self.model["meta"]["horizonte"]
        self.base = {h: {s["id"]: s["wahrscheinlichkeit"][h] for s in self.model["szenarien"]} for h in self.horizons}
        self.base_exact = {h: {s: float(v) for s, v in self.model["zufluss"]["p_basis"][h].items()} for h in self.horizons}
        self.regime = {s["id"]: s["regime"].get("energy_price") for s in self.model["szenarien"]}
        self.pub = {s["id"]: s["p_tag"] for s in self.published["szenarien"]}
        if self.model["bayes"]["k_daempfung"] != K_CURRENT:
            raise Stop(f"model k is {self.model['bayes']['k_daempfung']}, expected {K_CURRENT}")

    def with_k(self, k: float) -> dict:
        m = copy.deepcopy(self.model)
        m["bayes"]["k_daempfung"] = k
        return m

    def statuses(self, lage: dict) -> tuple[dict, dict]:
        """Indicator status (as level 0/1/2.., None = no data) at the base date and today, from tagesstand()."""
        zahl = [a for a in lage["anzeichen"] if a["art"] != "aussage"]
        return ({a["id"]: a["stufe_basis"] for a in zahl}, {a["id"]: a["stufe_jetzt"] for a in zahl})

    def run(self, case: str, k: float, basis: dict, jetzt: dict) -> dict:
        ts, m, flip = self.ts, self.with_k(k), CASES[case]["flip"]
        if flip is None:
            lage = ts.tagesstand(m, self.ws, self.heute)
            signals = []
        else:
            now = dict(jetzt)
            now[flip] = 1
            lage = ts.aus_status(m, basis, now, self.heute)
            a = next(x for x in m["anzeichen"] if x["id"] == flip)
            signals = [ts.anzeichen_signal(a, True, self.heute)]  # same call aus_status() makes for a 0 -> 1 change
        if len(lage["signale"]) != len(signals):
            raise Stop(f"case {case}, k={k}: engine produced {len(lage['signale'])} signals, expected {len(signals)}")
        r = ts.rechne_am(m, signals, self.heute)
        if "posterior_exakt" not in r:
            raise Stop("engine returned no posterior_exakt (zufluss.ungerundet switched off?)")
        rounded = {h: {s["id"]: s["p_tag"][h] for s in lage["szenarien"]} for h in self.horizons}
        exact = {h: dict(r["posterior_exakt"][h]) for h in self.horizons}
        return {"rounded": rounded, "exact": exact, "rechne_am_rounded": r["posterior"],
                "signals": [{k2: s.get(k2) for k2 in ("anzeichen", "titel", "treiber_ids", "richtung", "staerke",
                                                       "gewicht", "likelihood")} for s in lage["signale"]],
                "k_in_output": lage["k_daempfung"], "full_szenarien_equal_published": lage["szenarien"] == self.published["szenarien"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    repo, out = args.repo.resolve(), args.out.resolve()
    if out == repo or repo in out.parents:
        print("ERROR: --out must be outside the repo")
        return 1
    out.mkdir(parents=True, exist_ok=True)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    L: list[str] = []
    say = lambda *lines: L.extend(lines)
    raw: dict = {"status": "running"}

    def finish(code: int) -> int:
        after = git(repo, "status", "--porcelain")
        raw["git_status_after"] = after
        unchanged = after == raw.get("git_status_before")
        raw["repo_unchanged"] = unchanged
        say("", f"Repo check: git status before = {raw.get('git_status_before')!r}, after = {after!r} -> "
                + ("UNCHANGED" if unchanged else "CHANGED - investigate"))
        (out / "report.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
        (out / "raw_output.json").write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("\n".join(L))
        print(f"\nSaved: {out / 'report.txt'}\n       {out / 'raw_output.json'}")
        return code if unchanged else 3

    raw["git_status_before"] = git(repo, "status", "--porcelain")
    try:
        ex = Experiment(repo)
    except Stop as e:
        raw["status"] = f"STOPPED: {e}"
        say(f"STOPPED: {e}")
        return finish(2)

    raw["meta"] = {
        "run_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "python": platform.python_version(), "repo": str(repo), "repo_head": git(repo, "rev-parse", "HEAD"),
        "inputs_sha256": {n: sha256(p) for n, p in ex.paths.items()},
        "world_state_date_used_as_today": ex.published["stand"], "k_values": K_VALUES, "k_current": K_CURRENT,
        "focus_horizon": FOCUS, "cases": CASES, "sources": SOURCES,
        "note": "Cases B and C are HYPOTHETICAL shocks used to test the formula; they are not forecasts.",
    }
    say("k-SENSITIVITY EXPERIMENT (read-only on the repo)", "=" * 48,
        f"Run at {raw['meta']['run_at_utc']}, Python {raw['meta']['python']}, repo HEAD {raw['meta']['repo_head'][:10]}",
        f"'Today' = published world-state date {ex.published['stand']} (as tests/test_reproduce.py does)",
        f"k values: {K_VALUES}  (current k = {K_CURRENT})", "Input files (sha256, first 16 chars):",
        *[f"  {n:22s} {h[:16]}" for n, h in raw["meta"]["inputs_sha256"].items()],
        "", "WHERE EACH NUMBER COMES FROM", *[f"  [{key}] {txt}" for key, txt in SOURCES.items()],
        "", "Notation: '12 (11.874)' = rounded p_tag [rounded] (unrounded posterior_exakt [exact]), in percent.",
        "Cases B and C are HYPOTHETICAL shocks to test the formula, NOT forecasts.")

    # --- statuses at the current k (they do not depend on k) ---
    lage0 = ex.ts.tagesstand(ex.model, ex.ws, ex.heute)
    basis, jetzt = ex.statuses(lage0)
    for c in ("B", "C"):
        f = CASES[c]["flip"]
        if basis.get(f) != 0 or jetzt.get(f) != 0:
            raw["status"] = f"STOPPED: {f} is not OFF at base and today (base={basis.get(f)}, today={jetzt.get(f)})"
            say("", raw["status"])
            return finish(2)
    say("", f"[status] Indicators that are ON today: {sorted(i for i, v in jetzt.items() if v)}; "
            f"no data: {sorted(i for i, v in jetzt.items() if v is None)}; changed since base: "
            f"{sorted(i for i in jetzt if basis[i] != jetzt[i])}")

    results = {c: {k: ex.run(c, k, basis, jetzt) for k in K_VALUES} for c in CASES}
    raw["results"] = {c: {str(k): v for k, v in r.items()} for c, r in results.items()}

    # --- GATE 1: case A reproduces the published numbers at every k ---
    say("", "GATE 1 - Case A at every k must equal the published p_tag",
        f"  compares [rounded] for all {len(ex.horizons)} horizons against [published]")
    rows, ok1 = [], True
    for k in K_VALUES:
        r = results["A"][k]
        match = all(r["rounded"][h][s] == ex.pub[s][h] for h in ex.horizons for s in ex.sids)
        ok1 &= match and not r["signals"]
        rows.append([f"{k:.2f}", "case A", "yes" if match else "NO", len(r["signals"]),
                     "yes" if r["full_szenarien_equal_published"] else "no"])
    say(*["  " + x for x in table(["k", "case", "p_tag == published", "signals", "whole scenario block equal"], rows)])
    raw["gate1_case_A_equals_published"] = ok1
    if not ok1:
        raw["status"] = "STOPPED at gate 1: case A does not reproduce weltlage.json"
        say("", "STOPPED: case A does not reproduce the published numbers. No results are shown. See raw_output.json.")
        return finish(2)
    say("  PASS")

    # --- GATE 2: k = 0 equals the base model for every case ---
    say("", "GATE 2 - At k = 0 every case must equal the base model",
        "  [rounded] vs [base] and [exact] vs [base_exact], all horizons")
    rows, ok2 = [], True
    for c in CASES:
        r = results[c][0.0]
        m_r = all(r["rounded"][h][s] == ex.base[h][s] for h in ex.horizons for s in ex.sids)
        m_e = max(abs(r["exact"][h][s] - ex.base_exact[h][s]) for h in ex.horizons for s in ex.sids)
        ok2 &= m_r and m_e < TOL
        rows.append([c, HYPO if CASES[c]["flip"] else "real data", "yes" if m_r else "NO", f"{m_e:.1e}"])
    say(*["  " + x for x in table(["case", "kind", "rounded == base", "max |exact - base_exact|"], rows)])
    raw["gate2_k0_equals_base"] = ok2
    if not ok2:
        raw["status"] = "STOPPED at gate 2: k = 0 does not give the base model"
        say("", "STOPPED: k = 0 does not reproduce the base model. No results are shown.")
        return finish(2)
    say("  PASS")

    # --- GATE 3: the unrounded path rounds to the same numbers the engine publishes ---
    ok3 = all(results[c][k]["rechne_am_rounded"] == results[c][k]["rounded"] for c in CASES for k in K_VALUES)
    raw["gate3_exact_path_consistent"] = ok3
    say("", "GATE 3 - rechne_am() posterior == aus_status()/tagesstand() p_tag for every case and k: "
            + ("PASS" if ok3 else "FAIL"))
    if not ok3:
        raw["status"] = "STOPPED at gate 3"
        return finish(2)

    # --- the shock signals ---
    say("", "THE TWO HYPOTHETICAL SIGNALS (at current k = 0.15)", f"  source: [signal], [lr]")
    for c in ("B", "C"):
        s = results[c][K_CURRENT]["signals"][0]
        say(f"  Case {c} [{HYPO}]: {s['anzeichen']} -> drivers {s['treiber_ids']}, direction {s['richtung']}, "
            f"strength {s['staerke']}, weight {s['gewicht']}")
        say("    boost (likelihood ratio) per scenario: "
            + ", ".join(f"{sid} {v:.4f}" for sid, v in s["likelihood"].items()))
    say("  Note: A05 has strength 3, A13 strength 2, so C is the opposite direction but not an exact mirror of B.")

    # --- case A result ---
    say("", f"RESULT - {CASES['A']['title']}", f"  horizon {FOCUS}; source: [rounded], [exact], [published]",
        "  No indicator changed since the base model, so k has nothing to scale: identical at every k.")
    rA = results["A"][K_CURRENT]
    say(*["  " + x for x in table(["id", "scenario", "base", "published", "every k: rounded (unrounded)"],
          [[s, ex.names[s], ex.base[FOCUS][s], ex.pub[s][FOCUS], both(rA["rounded"][FOCUS][s], rA["exact"][FOCUS][s])]
           for s in ex.sids])])

    # --- cases B and C ---
    summary, csv_rows = {}, []
    for c in ("B", "C"):
        say("", "#" * 100, f"RESULT - {CASES[c]['title']}", "#" * 100,
            f"  {FOCUS} probability per scenario, rounded (unrounded), percent. source: [base], [rounded], [exact]")
        rows = []
        for s in ex.sids:
            rows.append([s, ex.names[s][:30], *[both(results[c][k]["rounded"][FOCUS][s], results[c][k]["exact"][FOCUS][s])
                                                for k in K_VALUES]])
        say(*["  " + x for x in table(["id", f"scenario  [{HYPO}]", *[f"k={k:.2f}" for k in K_VALUES]], rows)])
        mv_e = [movement(results[c][k]["exact"][FOCUS], ex.base_exact[FOCUS]) for k in K_VALUES]
        mv_r = [movement(results[c][k]["rounded"][FOCUS], ex.base[FOCUS]) for k in K_VALUES]
        big = []
        for k in K_VALUES:
            d = {s: results[c][k]["exact"][FOCUS][s] - ex.base_exact[FOCUS][s] for s in ex.sids}
            top = max(d, key=lambda s: abs(d[s]))
            big.append(f"{top} {d[top]:+.2f}" if abs(d[top]) > TOL else "none")
        say("", f"  Summary for case {c} [{HYPO}], horizon {FOCUS}. source: [metrics]",
            *["  " + x for x in table(["measure", "", *[f"k={k:.2f}" for k in K_VALUES]], [
                ["total moved, pp (unrounded)", "", *[f"{v:.2f}" for v in mv_e]],
                ["total moved, pp (rounded)", "", *[f"{v:.1f}" for v in mv_r]],
                ["largest single change (unrounded)", "", *big]])])
        # energy-price mass
        rows = []
        for lev in sorted(REGIME_LABEL):
            members = [s for s in ex.sids if ex.regime[s] == lev]
            rows.append([REGIME_LABEL[lev], f"{len(members)} scen.",
                         f"{sum(ex.base[FOCUS][s] for s in members)}",
                         *[both(sum(results[c][k]["rounded"][FOCUS][s] for s in members),
                                sum(results[c][k]["exact"][FOCUS][s] for s in members)) for k in K_VALUES]])
        say("", f"  {FOCUS} probability by energy-price regime, case {c} [{HYPO}]. source: [regime], [rounded], [exact]",
            *["  " + x for x in table(["energy price", "", "base", *[f"k={k:.2f}" for k in K_VALUES]], rows)])
        summary[c] = {"total_moved_pp_exact": dict(zip(map(str, K_VALUES), mv_e)),
                      "total_moved_pp_rounded": dict(zip(map(str, K_VALUES), mv_r))}
        for k in K_VALUES:
            for s in ex.sids:
                csv_rows.append([c, HYPO if c != "A" else "real data", k, s, ex.names[s], ex.base[FOCUS][s],
                                 ex.base_exact[FOCUS][s], results[c][k]["rounded"][FOCUS][s],
                                 round(results[c][k]["exact"][FOCUS][s], 6)])

        # 2028 vs 2040 at the current k
        r = results[c][K_CURRENT]
        lr = r["signals"][0]["likelihood"]
        rows = [[s, ex.names[s][:30], f"{lr[s]:.4f}",
                 f"{r['exact']['2028'][s] - ex.base_exact['2028'][s]:+.3f}",
                 f"{r['exact'][FOCUS][s] - ex.base_exact[FOCUS][s]:+.3f}",
                 f"{r['exact']['2028'][s] / ex.base_exact['2028'][s]:.4f}",
                 f"{r['exact'][FOCUS][s] / ex.base_exact[FOCUS][s]:.4f}"] for s in ex.sids]
        say("", f"  2028 vs {FOCUS} at k = {K_CURRENT}, case {c} [{HYPO}]: the same boost is applied to both horizons.",
            "  source: [lr], [exact], [base_exact]",
            *["  " + x for x in table(["id", "scenario", "boost", "change 2028 pp", f"change {FOCUS} pp",
                                       "new/old 2028", f"new/old {FOCUS}"], rows)])
    raw["summary"] = summary

    # plain-language conclusion
    say("", "PLAIN-LANGUAGE SUMMARY (unrounded, horizon 2040; B and C are HYPOTHETICAL shocks, not forecasts)")
    for c in ("B", "C"):
        t = summary[c]["total_moved_pp_exact"]
        say(f"  Case {c}: at k=0.15 about {t['0.15']:.2f} percentage points move in total; at k=0.30 {t['0.3']:.2f} "
            f"(x{t['0.3'] / t['0.15']:.2f}); at k=0.05 {t['0.05']:.2f}; at k=0.50 {t['0.5']:.2f}.")
    say("  Case A (real data): 0.00 at every k - no indicator changed since the base model.")

    # table view as CSV (the chart's data, for anyone who cannot read the chart)
    import csv
    with open(out / "table_2040.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["case", "kind", "k", "scenario_id", "scenario_name", "base_rounded", "base_unrounded",
                    "p2040_rounded", "p2040_unrounded"])
        w.writerows(csv_rows)

    charts = make_charts(ex, results, summary, out)
    raw["charts"] = charts
    say("", "Charts: " + (", ".join(charts) if charts else "skipped (matplotlib not available)"),
        f"Table view of the chart data: {out / 'table_2040.csv'}")
    raw["status"] = "ok"
    return finish(0)


# --- charts (light-mode reference palette from the dataviz skill) -------------------

def make_charts(ex, results, summary, out: Path) -> list:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return []
    SURF, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
    COL = {"B": "#2a78d6", "C": "#eb6834"}  # categorical slots 1 and 2
    LBL = {"B": "B: A05 Brent >110 $ for 2+ quarters ON", "C": "C: A13 Brent <70 $ ON"}
    plt.rcParams.update({"font.size": 10, "text.color": INK, "axes.labelcolor": INK2, "xtick.color": MUTED,
                         "ytick.color": MUTED, "axes.edgecolor": AXIS, "figure.facecolor": SURF, "axes.facecolor": SURF})

    def frame(ax):
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)

    files = []
    # 1. total movement vs k
    fig, ax = plt.subplots(figsize=(9, 5.4), dpi=150)
    frame(ax)
    ax.axvline(K_CURRENT, color=MUTED, linewidth=1, linestyle=(0, (4, 3)))
    for c in ("B", "C"):
        ys = [summary[c]["total_moved_pp_exact"][str(k)] for k in K_VALUES]
        ax.plot(K_VALUES, ys, color=COL[c], linewidth=2, marker="o", markersize=6,
                markeredgecolor=SURF, markeredgewidth=1.5, label=LBL[c])
        ax.annotate(f"{c}  {ys[-1]:.1f} pp", (K_VALUES[-1], ys[-1]), xytext=(8, 0), textcoords="offset points",
                    va="center", color=INK, fontsize=10)
        y15 = summary[c]["total_moved_pp_exact"][str(K_CURRENT)]
        ax.annotate(f"{y15:.1f}", (K_CURRENT, y15), xytext=(-8, 8), textcoords="offset points", ha="right",
                    color=INK2, fontsize=9)
    ax.plot(K_VALUES, [0] * len(K_VALUES), color=MUTED, linewidth=1.5, label="A: real data (no change)")
    ax.text(K_CURRENT + 0.005, ax.get_ylim()[1] * 0.55, "current k = 0.15", color=INK2, fontsize=9, va="center")
    ax.set_xlabel("damping k  (model/world_model.de.json : bayes.k_daempfung)")
    ax.set_ylabel("total 2040 probability moved, percentage points")
    ax.set_xlim(-0.01, 0.56)
    ax.set_ylim(bottom=0)
    fig.suptitle("HYPOTHETICAL shocks - not forecasts: how far 2040 probabilities move as k grows",
                 x=0.07, ha="left", fontsize=12, fontweight="bold")
    ax.set_title("Each line switches one oil-price indicator on in a what-if. Total moved = half the sum of absolute "
                 "changes (unrounded).\nSource: engine/bayes.py _update_zufluss -> engine/zufluss.py posterior; "
                 "base: world_model.de.json zufluss.p_basis",
                 loc="left", fontsize=8.5, color=INK2)
    ax.legend(frameon=False, loc="upper left", fontsize=9)
    fig.tight_layout()
    p = out / "k_total_movement_2040.png"
    fig.savefig(p, facecolor=SURF)
    plt.close(fig)
    files.append(str(p))

    # 2. small multiples: each scenario's 2040 probability vs k
    fig, axes = plt.subplots(3, 4, figsize=(12, 8), dpi=150, sharex=True, sharey=True)
    for ax, s in zip(axes.flat, ex.sids):
        frame(ax)
        ax.axvline(K_CURRENT, color=GRID, linewidth=1, linestyle=(0, (4, 3)))
        ax.axhline(ex.base_exact[FOCUS][s], color=MUTED, linewidth=1)
        for c in ("B", "C"):
            ax.plot(K_VALUES, [results[c][k]["exact"][FOCUS][s] for k in K_VALUES], color=COL[c], linewidth=2,
                    marker="o", markersize=3.5, label=LBL[c])
        ax.set_title(f"{s} {ex.names[s][:28]}", fontsize=8.5, loc="left", color=INK)
    for ax in axes[-1]:
        ax.set_xlabel("k", fontsize=9)
    for ax in axes[:, 0]:
        ax.set_ylabel("2040 prob., %", fontsize=9)
    handles, labels = axes.flat[0].get_legend_handles_labels()
    handles.append(plt.Line2D([], [], color=MUTED, linewidth=1))
    labels.append("base model (k = 0)")
    fig.legend(handles, labels, loc="lower center", ncol=3, frameon=False, fontsize=9)
    fig.suptitle("HYPOTHETICAL shocks - not forecasts: each scenario's 2040 probability vs k (unrounded)",
                 x=0.02, ha="left", fontsize=12, fontweight="bold")
    fig.text(0.02, 0.935, "Grey line = base model. Dashed = current k 0.15. Source: engine/zufluss.py posterior() via "
             "engine/tagesstand.py rechne_am(). Exact values: table_2040.csv", fontsize=8.5, color=INK2)
    fig.tight_layout(rect=(0, 0.05, 1, 0.93))
    p = out / "k_per_scenario_2040.png"
    fig.savefig(p, facecolor=SURF)
    plt.close(fig)
    files.append(str(p))
    return files


if __name__ == "__main__":
    raise SystemExit(main())
