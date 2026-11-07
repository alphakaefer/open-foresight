"""Explain what the open-foresight engine is doing, in plain words, and check every number.

Steps
  1. TRACE   Run the repo's engine (read-only) and collect: which indicators changed, the drivers they
             affect, the coupling values, the boost per scenario, and the probabilities before and after.
             Every number comes from the engine's own functions (see SOURCES); this script only selects,
             rounds for display (2 decimals) and labels.
  2. CLAUDE  Send only the trace to the Claude API (model claude-opus-5-5) and ask for a short,
             plain-language explanation as JSON. Claude must not add any number that is not in the trace.
  3. CHECK   check_numbers.py checks that every number in the explanation appears in the trace.
             If the check fails, the script retries ONCE, telling Claude which numbers were wrong.
             A text that still fails is saved with a FAILED NUMBER CHECK banner.

Modes
  --whatif A05 (default)  HYPOTHETICAL: indicator A05 is assumed to switch ON. Not a forecast.
  --real                  Today's real snapshot (currently: nothing changed since the base model).
  --dry-run               Build trace and prompt, run the checker self-tests. No API call, no cost.

API key: read only from the ANTHROPIC_API_KEY environment variable by the Anthropic SDK. It is never
printed, logged, passed as an argument or written to a file.

Exit codes: 0 ok, 1 setup error, 2 engine gate failed, 3 repo changed, 4 number check failed after the
retry, 5 API error or refusal.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True  # never write __pycache__ into the repo

import argparse
import copy
import hashlib
import json
import os
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_numbers as cn  # noqa: E402

DEFAULT_REPO = Path("C:/Users/navee/open-foresight")
MODEL_ID = "claude-opus-5-5"
EFFORT = "medium"
MAX_TOKENS = 16000
FALLBACK_BETA = "server-side-fallback-2026-07-01"
BIG_TOP_N = 3          # big changes per horizon ...
BIG_MIN_PP = 0.5       # ... of at least this many percentage points (unrounded)
HYPO = "HYPOTHETICAL what-if - not a forecast"
DIRECTION_EN = {"bestaetigend": "confirming", "widersprechend": "contradicting", "neutral": "neutral",
                "neu": "unclassified"}
REGIME_LABEL = {-2: "much cheaper", -1: "cheaper", 0: "neutral", 1: "more expensive", 2: "much more expensive"}

SOURCES = {
    "meta.k": "model/world_model.de.json bayes.k_daempfung, as returned by engine/tagesstand.py aus_status() (k_daempfung)",
    "meta.probability_floor_percent": "model/world_model.de.json zufluss.ungerundet.p_min_prozent (used by engine/zufluss.py untergrenze())",
    "changed_indicators[].status_*": "engine/tagesstand.py tagesstand() -> pruefe() / gilt(); fields anzeichen[].stufe_basis / stufe_jetzt",
    "changed_indicators[].latest": "engine/tagesstand.py tagesstand() anzeichen[].zuletzt (last value of the data series)",
    "changed_indicators[].text/rule/series": "model/world_model.en.json anzeichen[] (text), .de.json (rule, series)",
    "signals[].direction/strength": "engine/tagesstand.py anzeichen_signal() from model anzeichen[].wirkung",
    "signals[].weight": "engine/zufluss.py gewichte() via engine output signale[].gewicht",
    "signals[].coupling": "model/world_model.de.json treiber_kopplung[driver][scenario]",
    "signals[].mean_coupling_per_scenario": "engine/bayes.py coupling_mean()",
    "signals[].boost_per_scenario": "engine/bayes.py log_likelihoods() (exp) via engine output signale[].likelihood",
    "probabilities.*.before": "engine/tagesstand.py aus_status() szenarien[].p_basis (= model wahrscheinlichkeit)",
    "probabilities.*.after": "engine/tagesstand.py aus_status() szenarien[].p_tag (engine/bayes.py largest_remainder())",
    "probabilities.*.change_rounded": "engine/tagesstand.py aus_status() szenarien[].delta",
    "probabilities.*.after_unrounded": "engine/tagesstand.py rechne_am() -> engine/bayes.py _update_zufluss() posterior_exakt "
                                       "(engine/zufluss.py posterior()), rounded to 2 decimals here",
    "probabilities.*.change_unrounded": "after_unrounded minus model zufluss.p_basis, rounded to 2 decimals here",
    "big_changes": f"selected here: up to {BIG_TOP_N} per horizon with |change_unrounded| >= {BIG_MIN_PP}",
    "energy_price_mass": "sum over scenarios per model szenarien[].regime.energy_price (same rule as domains/lens.py scenarios())",
    "scenarios": "model/world_model.en.json szenarien[].name; regime from .de.json",
    "gaps": "engine/tagesstand.py aus_status() luecken (number indicators without data)",
    "known_limitations": "README.md 'Known limitations' and 'How the engine updates probabilities'; docs/process.md rules",
}

KNOWN_LIMITATIONS = [
    "The starting probabilities of the scenarios were typed in by a person (the model author). They are judgments, not measurements.",
    "The coupling values between drivers and scenarios are typed-in judgments.",
    "Each indicator's direction and strength are typed-in judgments.",
    "The damping k is a chosen parameter, not estimated from data. A larger k makes every signal move the probabilities more.",
    "The model has not been checked against real outcomes yet. Published versions are kept in a journal so they can be scored later.",
    "The horizons are updated separately, and each scenario gets the same boost in every horizon: today's evidence pushes the far horizon as hard as the near one.",
    "Statement indicators (patterns in news titles) are shown to people but never move a probability.",
    "The model computes for the world, not for one country, industry or company.",
    "Probabilities are rescaled with a minimum per scenario and rounded to whole percents, so small effects can disappear in the rounded numbers.",
]
HOW = ("Only indicators whose status changed since the base model create a signal. For each scenario: "
       "boost = exp(k x direction x strength x mean coupling of the signal's drivers to that scenario), with direction +1 "
       "for confirming and -1 for contradicting. New probability = old probability x boost; then all scenarios are "
       "rescaled so each horizon sums to 100 (with a minimum per scenario) and rounded to whole percents. A scenario "
       "with a boost of exactly 1 can still fall a little, only because the others grew.")

SYSTEM_PROMPT = """You explain the output of a transparent foresight model to beginners.
The user message contains a TRACE in JSON. It was produced by the model's own code and is the only source of facts.

Rules:
1. Use only facts that are in the TRACE. Do not add real-world facts, news, prices or events that are not in it.
2. Every number you write must be copied exactly as it appears in the TRACE, with the same digits and decimals. Do not compute, round, add, subtract, average or convert numbers, and do not write ratios, differences or sums that are not in the TRACE. Avoid number words and quantity words such as "two", "twice", "half", "a third" or "doubled". For a negative change you may write "fell by" followed by the number without its minus sign.
3. Identifiers such as S04, A05 or G3 may be used freely; give the scenario or driver name next to them.
4. what_is_happening: a short paragraph on what changed and what moved, in plain words.
5. big_changes: exactly one item for every entry in TRACE.big_changes, with the same scenario_id and horizon. Explain the chain: which indicator changed, which driver it affects, how strongly that scenario is coupled to the driver, its boost, and the probability before and after. If the boost is close to 1, explain that the scenario moved mainly because the others were rescaled.
6. uncertainties: up to five short points based on TRACE.known_limitations and TRACE.gaps. Make clear that the starting probabilities, couplings and strengths are typed-in human judgments and that the model has not been checked against real outcomes.
7. hypothetical_notice: if TRACE.meta.is_hypothetical is true, write one sentence that starts with "HYPOTHETICAL:" and says this is a what-if, not a forecast, and which indicator was assumed. Otherwise use an empty string.
8. If nothing changed, say so plainly and leave big_changes empty.
Keep it short and simple: what_is_happening up to about 120 words, each big_changes explanation up to about 80 words."""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "hypothetical_notice": {"type": "string"},
        "what_is_happening": {"type": "string"},
        "big_changes": {"type": "array", "items": {
            "type": "object",
            "properties": {"scenario_id": {"type": "string"}, "horizon": {"type": "string"},
                           "explanation": {"type": "string"}},
            "required": ["scenario_id", "horizon", "explanation"], "additionalProperties": False}},
        "uncertainties": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["hypothetical_notice", "what_is_happening", "big_changes", "uncertainties"],
    "additionalProperties": False,
}


class Stop(Exception):
    """An engine gate failed."""


def r2(x: float) -> float:
    return round(x, 2) + 0.0  # + 0.0 turns -0.0 into 0.0


def git(repo: Path, *args) -> str:
    try:
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()
    except Exception as e:
        return f"<git unavailable: {e}>"


# --- step 1: the trace -----------------------------------------------------------------

class Engine:
    def __init__(self, repo: Path):
        sys.path.insert(0, str(repo))
        from engine import bayes, io, stufen, tagesstand as ts  # read-only use of the repo's engine
        self.bayes, self.io, self.stufen, self.ts = bayes, io, stufen, ts
        snap = io.RADAR_SNAPSHOT
        self.paths = {"world_model.de.json": io.MODEL_DE, "world_model.en.json": io.MODEL_EN,
                      "wissensstand.json": snap / "wissensstand.json", "weltlage.json": snap / "weltlage.json"}
        self.model = io.load_world_model("de")
        self.en = io.load_world_model("en")
        self.ws = io.load_json(self.paths["wissensstand.json"])
        self.published = io.load_json(self.paths["weltlage.json"])
        self.heute = datetime.fromisoformat(self.published["stand"].replace("Z", "+00:00"))


def make_signals(eng: Engine, basis: dict, now: dict) -> list:
    """The signals aus_status() builds for these statuses (same branch as engine/tagesstand.py aus_status())."""
    ts, model, out = eng.ts, eng.model, []
    je = model.get("stufen") or {}
    for a in model["anzeichen"]:
        if a["art"] == "aussage":
            continue
        st = je.get(a["id"])
        kv, kn = ts._stufe(a["id"], basis.get(a["id"]), st), ts._stufe(a["id"], now.get(a["id"]), st)
        if kv is not None and kn is not None and kv != kn and a.get("wirkung"):
            out.append(ts.anzeichen_signal(a, kn >= 1, eng.heute) if max(kv, kn) <= 1
                       else eng.stufen.signal(a, st, kv, kn, eng.heute))
    return out


def build_trace(eng: Engine, whatif: str | None) -> tuple[dict, dict]:
    ts, model = eng.ts, eng.model
    horizons, sids = model["meta"]["horizonte"], [s["id"] for s in model["szenarien"]]
    gates = []

    real = ts.tagesstand(model, eng.ws, eng.heute)
    pub = {s["id"]: s["p_tag"] for s in eng.published["szenarien"]}
    ok = all(s["p_tag"] == pub[s["id"]] for s in real["szenarien"])
    gates.append(("engine reproduces the published p_tag in weltlage.json (all horizons)", ok))
    if not ok:
        raise Stop("the engine does not reproduce radar/snapshot/weltlage.json")

    zahl = [a for a in real["anzeichen"] if a["art"] != "aussage"]
    basis = {a["id"]: a["stufe_basis"] for a in zahl}
    jetzt = {a["id"]: a["stufe_jetzt"] for a in zahl}
    zuletzt = {a["id"]: a["zuletzt"] for a in zahl}
    if whatif:
        if whatif not in basis:
            raise Stop(f"{whatif} is not a number indicator of the model")
        if basis[whatif] != 0 or jetzt[whatif] != 0:
            raise Stop(f"{whatif} must be OFF at the base date and today for a what-if (base={basis[whatif]}, "
                       f"today={jetzt[whatif]})")
        now = dict(jetzt)
        now[whatif] = 1
        lage = ts.aus_status(model, basis, now, eng.heute, zuletzt=zuletzt, radar_stand=eng.ws.get("stand"))
    else:
        now, lage = jetzt, real
    signals = make_signals(eng, basis, now)
    r = ts.rechne_am(model, signals, eng.heute)
    gates.append(("signals rebuilt here == signals in the engine output", len(signals) == len(lage["signale"])))
    p_tag = {h: {s["id"]: s["p_tag"][h] for s in lage["szenarien"]} for h in horizons}
    gates.append(("rechne_am() posterior == aus_status() p_tag", r["posterior"] == p_tag))
    exact = r.get("posterior_exakt")
    gates.append(("unrounded posterior_exakt present", exact is not None))
    if exact is None:
        raise Stop("no posterior_exakt (zufluss.ungerundet is switched off)")
    gates.append(("rounded probabilities sum to 100 per horizon", all(sum(p_tag[h].values()) == 100 for h in horizons)))
    gates.append(("unrounded probabilities sum to 100 per horizon",
                  all(abs(sum(exact[h].values()) - 100) < 1e-4 for h in horizons)))
    gates.append(("bayes.largest_remainder(unrounded) == published rounding",
                  all(eng.bayes.largest_remainder(exact[h], 100) == p_tag[h] for h in horizons)))
    for name, ok in gates:
        if not ok:
            raise Stop(f"gate failed: {name}")

    en_ind = {a["id"]: a for a in eng.en["anzeichen"]}
    de_ind = {a["id"]: a for a in model["anzeichen"]}
    drv_name = {t["id"]: t["name"] for t in eng.en["treiber"]}
    sc_name = {s["id"]: s["name"] for s in eng.en["szenarien"]}
    regime = {s["id"]: s["regime"].get("energy_price") for s in model["szenarien"]}
    zufluss = model.get("zufluss") or {}
    p0 = zufluss.get("p_basis") or {h: {s["id"]: s["wahrscheinlichkeit"][h] for s in model["szenarien"]} for h in horizons}

    changed = []
    for a in lage["anzeichen"]:
        if a["art"] == "aussage" or a.get("stufe_basis") == a.get("stufe_jetzt"):
            continue
        z = a.get("zuletzt") or {}
        entry = {"id": a["id"], "text": en_ind[a["id"]]["text"], "rule": de_ind[a["id"]].get("regel"),
                 "series": de_ind[a["id"]].get("reihe"),
                 "latest": {"month": z.get("t"), "value": z.get("wert")} if z else None,
                 "status_at_base": a["status_basis"], "status_today": a["status_jetzt"],
                 "change": "switched on" if a["status_jetzt"] else "switched off"}
        if whatif and a["id"] == whatif:
            entry["hypothetical"] = True
            entry["status_today_in_real_data"] = bool(jetzt[a["id"]])
        changed.append(entry)

    kopplung = model["treiber_kopplung"]
    sig_out = []
    for s, contrib in zip(signals, lage["signale"]):
        sig_out.append({
            "indicator": s.get("anzeichen"),
            "drivers": [{"id": t, "name": drv_name.get(t, t)} for t in s["treiber_ids"]],
            "direction": DIRECTION_EN.get(s["richtung"], s["richtung"]),
            "strength": s["staerke"],
            "weight": contrib.get("gewicht", 1.0),
            "coupling": {t: {sid: kopplung[t][sid] for sid in sids if sid in kopplung.get(t, {})}
                         for t in s["treiber_ids"]},
            "mean_coupling_per_scenario": {sid: round(eng.bayes.coupling_mean(s, kopplung, sid), 4) for sid in sids},
            "boost_per_scenario": contrib["likelihood"],
        })

    probs, big = {}, {}
    by_id = {s["id"]: s for s in lage["szenarien"]}
    for h in horizons:
        probs[h] = {}
        for sid in sids:
            e = by_id[sid]
            probs[h][sid] = {"before": e["p_basis"][h], "after": e["p_tag"][h], "change_rounded": e["delta"][h],
                             "after_unrounded": r2(exact[h][sid]), "change_unrounded": r2(exact[h][sid] - p0[h][sid])}
        ranked = sorted(sids, key=lambda sid: -abs(exact[h][sid] - p0[h][sid]))
        big[h] = {}
        for sid in ranked[:BIG_TOP_N]:
            p = probs[h][sid]
            if abs(exact[h][sid] - p0[h][sid]) >= BIG_MIN_PP:
                big[h][sid] = {"name": sc_name[sid], "before": p["before"], "after": p["after"],
                               "after_unrounded": p["after_unrounded"], "change_unrounded": p["change_unrounded"],
                               "direction": "up" if p["change_unrounded"] > 0 else "down"}
        if not big[h]:
            del big[h]

    mass = {}
    for h in horizons:
        mass[h] = {}
        for lev in sorted(REGIME_LABEL):
            members = [sid for sid in sids if regime[sid] == lev]
            if members:
                mass[h][REGIME_LABEL[lev]] = {"before": sum(probs[h][m]["before"] for m in members),
                                              "after": sum(probs[h][m]["after"] for m in members),
                                              "after_unrounded": r2(sum(exact[h][m] for m in members))}

    trace = {
        "meta": {
            "mode": HYPO if whatif else "real data",
            "is_hypothetical": bool(whatif),
            "what_if": ({"indicator": whatif, "assumption": f"{whatif} is assumed to switch ON today. In the real "
                         f"data it is OFF. Everything else is the real snapshot."} if whatif else None),
            "model_version": model["meta"]["version"], "model_date": model["meta"]["stand"],
            "world_state_date": eng.published["stand"], "radar_date": eng.ws.get("stand"),
            "k": lage["k_daempfung"], "horizons": horizons,
            "probability_floor_percent": (zufluss.get("ungerundet") or {}).get("p_min_prozent"),
        },
        "how_the_update_works": HOW,
        "changed_indicators": changed,
        "signals": sig_out,
        "scenarios": {sid: {"name": sc_name[sid], "energy_price_regime": regime[sid]} for sid in sids},
        "probabilities": probs,
        "big_changes": big,
        "energy_price_mass": mass,
        "gaps": [{"id": g, "text": en_ind[g]["text"]} for g in lage["luecken"]],
        "known_limitations": KNOWN_LIMITATIONS + ([f"This trace is a {HYPO}: indicator {whatif} was assumed to "
                                                   f"switch on."] if whatif else []),
    }
    run = {"created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "python": platform.python_version(), "repo_head": git(eng.paths["weltlage.json"].parents[2], "rev-parse", "HEAD"),
           "inputs_sha256": {n: hashlib.sha256(p.read_bytes()).hexdigest() for n, p in eng.paths.items()},
           "gates": [{"gate": n, "passed": ok} for n, ok in gates], "sources": SOURCES,
           "note": "Only the 'trace' part is sent to Claude. 'run' stays local."}
    return trace, run


# --- step 2: Claude ----------------------------------------------------------------------

def user_message(trace: dict, previous: dict | None = None, problems: list | None = None) -> str:
    text = "Write the explanation for this TRACE, following the rules.\n\nTRACE:\n" + json.dumps(trace, indent=1, ensure_ascii=False)
    if previous is not None:
        text += ("\n\nYOUR PREVIOUS ANSWER FAILED THE AUTOMATIC NUMBER CHECK. Problems found:\n"
                 + "\n".join(f"- {p}" for p in problems)
                 + "\n\nPrevious answer:\n" + json.dumps(previous, indent=1, ensure_ascii=False)
                 + "\n\nWrite a new, complete answer. Fix every problem. Copy every number exactly as written in the TRACE.")
    return text


def request_params(user_text: str) -> dict:
    return {"model": MODEL_ID, "max_tokens": MAX_TOKENS, "betas": [FALLBACK_BETA], "fallbacks": "default",
            "output_config": {"effort": EFFORT, "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
            "system": SYSTEM_PROMPT, "messages": [{"role": "user", "content": user_text}]}


def call_claude(user_text: str) -> dict:
    """One API call. Returns {'ok', 'explanation' | 'error', 'meta'}. The key is read by the SDK from the environment."""
    import anthropic

    client = anthropic.Anthropic()  # credentials from ANTHROPIC_API_KEY (checked by the caller)
    try:
        resp = client.beta.messages.create(**request_params(user_text))
    except anthropic.BadRequestError as e:
        return {"ok": False, "error": f"bad request: {e.message}"}
    except anthropic.AuthenticationError:
        return {"ok": False, "error": "authentication failed: check ANTHROPIC_API_KEY"}
    except anthropic.PermissionDeniedError:
        return {"ok": False, "error": "the API key lacks permission for this request"}
    except anthropic.RateLimitError:
        return {"ok": False, "error": "rate limited (the SDK already retried); try again later"}
    except anthropic.APIStatusError as e:
        return {"ok": False, "error": f"API error {e.status_code}: {e.message}"}
    except anthropic.APIConnectionError:
        return {"ok": False, "error": "network error: could not reach the API"}

    meta = {"request_id": resp._request_id, "model_that_answered": resp.model, "stop_reason": resp.stop_reason,
            "usage": resp.usage.to_dict() if hasattr(resp.usage, "to_dict") else str(resp.usage),
            "content_block_types": [b.type for b in resp.content]}
    if resp.stop_reason == "refusal":
        details = getattr(resp, "stop_details", None)
        meta["stop_details"] = details.to_dict() if hasattr(details, "to_dict") else str(details)
        return {"ok": False, "error": "the request was declined (refusal), also after the fallback", "meta": meta}
    if resp.stop_reason == "max_tokens":
        return {"ok": False, "error": "the answer hit max_tokens and is incomplete", "meta": meta}
    text = next((b.text for b in resp.content if b.type == "text"), None)
    try:
        return {"ok": True, "explanation": json.loads(text), "raw_text": text, "meta": meta}
    except (TypeError, json.JSONDecodeError):
        return {"ok": False, "error": "the answer was not valid JSON", "raw_text": text, "meta": meta}


# --- step 3: rendering --------------------------------------------------------------------

def render_md(trace: dict, expl: dict, check: dict, meta: dict) -> str:
    hypo = trace["meta"]["is_hypothetical"]
    names = {s: v["name"] for s, v in trace["scenarios"].items()}
    L = [f"# What the model is doing{' - ' + HYPO if hypo else ''}", ""]
    if not check["passed"]:
        L += ["> **FAILED NUMBER CHECK.** This text contains numbers that are not in the trace or are used in the "
              "wrong place. Do not use it. Problems:"] + [f"> - {f}" for f in check["failures"]] + [""]
    if expl.get("hypothetical_notice"):
        L += [f"**{expl['hypothetical_notice']}**", ""]
    L += ["## What is happening", "", expl.get("what_is_happening", ""), ""]
    if expl.get("big_changes"):
        L += ["## Why the big changes happened", ""]
        for it in expl["big_changes"]:
            L += [f"### {it['scenario_id']} {names.get(it['scenario_id'], '')} ({it['horizon']})", "", it["explanation"], ""]
    L += ["## What is uncertain", ""] + [f"- {u}" for u in expl.get("uncertainties", [])] + [""]
    c = check["counts"]
    L += ["---", f"_Written by {meta.get('model_that_answered', MODEL_ID)} (request {meta.get('request_id')}) from the "
          f"engine trace only. Number check: {'PASSED' if check['passed'] else 'FAILED'} "
          f"({', '.join(f'{k} {v}' for k, v in sorted(c.items())) or 'no numbers'}; {len(check['warnings'])} warnings). "
          f"See check_report.json._"]
    return "\n".join(L) + "\n"


# --- main ------------------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Explain the engine trace with Claude and check every number.")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--whatif", default="A05", help="indicator assumed to switch ON (HYPOTHETICAL); default A05")
    g.add_argument("--real", action="store_true", help="use today's real snapshot instead of a what-if")
    ap.add_argument("--dry-run", action="store_true", help="build trace + prompt and run self-tests; no API call")
    ap.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    ap.add_argument("--out", type=Path, default=HERE / "results")
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    repo = args.repo.resolve()
    whatif = None if args.real else args.whatif
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = args.out.resolve() / f"{stamp}_{'dryrun_' if args.dry_run else ''}{'real' if not whatif else 'whatif-' + whatif}"
    if out == repo or repo in out.parents:
        print("ERROR: --out must be outside the repo")
        return 1
    key_set = bool(os.environ.get("ANTHROPIC_API_KEY"))
    if not args.dry_run and not key_set:
        print("ERROR: ANTHROPIC_API_KEY is not set in this shell. Set it as an environment variable, then rerun.")
        return 1

    status_before = git(repo, "status", "--porcelain")
    out.mkdir(parents=True, exist_ok=True)

    def finish(code: int) -> int:
        after = git(repo, "status", "--porcelain")
        same = after == status_before
        print(f"\nRepo check: git status before {status_before!r}, after {after!r} -> {'UNCHANGED' if same else 'CHANGED'}")
        print(f"Files written to {out}")
        return code if same else 3

    try:
        eng = Engine(repo)
        trace, run = build_trace(eng, whatif)
    except Stop as e:
        print(f"STOPPED: {e}")
        (out / "stopped.txt").write_text(str(e) + "\n", encoding="utf-8")
        return finish(2)

    (out / "trace.json").write_text(json.dumps({"run": run, "trace": trace}, indent=2, ensure_ascii=False) + "\n",
                                    encoding="utf-8")
    params = request_params(user_message(trace))
    (out / "prompt.json").write_text(json.dumps(params, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"TRACE ({trace['meta']['mode']})  - only this part is sent to Claude")
    print("=" * 72)
    print(json.dumps(trace, indent=1, ensure_ascii=False))
    print("\nENGINE GATES")
    for g_ in run["gates"]:
        print(f"  {'PASS' if g_['passed'] else 'FAIL'}  {g_['gate']}")
    print("\nWHERE THE NUMBERS COME FROM")
    for k, v in SOURCES.items():
        print(f"  {k}: {v}")

    if args.dry_run:
        tests = cn.self_tests(trace)
        (out / "self_test.json").write_text(json.dumps(tests, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("\nNUMBER-CHECK SELF-TESTS (no API call)")
        for t in tests:
            extra = f"  (skipped: {t['skipped']})" if t.get("skipped") else \
                f"  -> check {'passed' if t['passed'] else 'failed'} as expected" if t["ok"] else \
                f"  -> UNEXPECTED: check {'passed' if t['passed'] else 'failed'}; {t.get('failures')}"
            print(f"  {'PASS' if t['ok'] else 'FAIL'}  {t['test']}{extra}")
        n_chars = len(params["system"]) + len(params["messages"][0]["content"])
        print(f"\nDRY RUN: no API call made. Prompt size {n_chars} characters "
              f"(about {n_chars // 4} tokens). Model {MODEL_ID}, effort {EFFORT}, fallbacks 'default'.")
        print(f"ANTHROPIC_API_KEY set in this shell: {'yes' if key_set else 'no'} (value never shown)")
        return finish(0 if all(t["ok"] for t in tests) else 1)

    # --- paid part: at most two calls (first attempt + one retry) ---
    previous, problems, result, check = None, None, None, None
    for attempt in (1, 2):
        result = call_claude(user_message(trace, previous, problems))
        (out / f"attempt{attempt}_response.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                                                             encoding="utf-8")
        if not result["ok"]:
            print(f"\nAPI attempt {attempt} failed: {result['error']}")
            return finish(5)
        check = cn.check(trace, result["explanation"])
        (out / f"attempt{attempt}_check.json").write_text(json.dumps(check, indent=2, ensure_ascii=False) + "\n",
                                                          encoding="utf-8")
        print(f"\nAttempt {attempt}: number check {'PASSED' if check['passed'] else 'FAILED'} {check['counts']}")
        for f in check["failures"]:
            print(f"  FAIL  {f}")
        for w in check["warnings"]:
            print(f"  warn  {w}")
        if check["passed"]:
            break
        previous, problems = result["explanation"], check["failures"]

    (out / "check_report.json").write_text(json.dumps(check, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md = render_md(trace, result["explanation"], check, result["meta"])
    (out / "explanation.md").write_text(md, encoding="utf-8")
    print("\n" + md)
    return finish(0 if check["passed"] else 4)


if __name__ == "__main__":
    raise SystemExit(main())
