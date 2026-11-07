"""Build ui/whatif_bundles.json: engine-computed EXTREME what-ifs (several indicators switched at once) for the map UI.

    python3 -B ui/build_bundles.py        # from the repo root; needs whatif/data.js (python3 -B whatif/build_data.py)

Single what-ifs come from whatif/data.js. This adds two combinations, chosen by a fixed rule, not by hand:
  stress  every indicator whose single what-if (at the model's k) RAISES the share of scenarios with dearer energy
          in 2032 is switched at the same time;
  relief  every indicator whose single what-if LOWERS that share is switched at the same time.
The engine (engine/tagesstand.py aus_status) recomputes all probabilities for each k. Nothing is estimated in the page.
Check first: today's probabilities in whatif/data.js must equal domains/energy-transition/briefing.json; otherwise
nothing is written. These are HYPOTHETICAL stress tests, not forecasts: the model treats each signal on its own and
does not know how likely it is that they all happen together.
"""
import sys

sys.dont_write_bytecode = True

import copy
import json
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
HORIZONS = ["2028", "2032", "2040"]
RULE_HORIZON = "2032"


def main() -> int:
    sys.path.insert(0, str(REPO))
    from engine import io, tagesstand as ts

    raw = (REPO / "whatif" / "data.js").read_text(encoding="utf-8")
    data = json.loads(raw[raw.index("{"):raw.rstrip().rindex("}") + 1])
    briefing = json.loads((REPO / "domains" / "energy-transition" / "briefing.json").read_text(encoding="utf-8"))
    rows = briefing["scenarios"]["rows"]
    today = {s["id"]: s["p_tag"] for s in data["weltlage"]["szenarien"]}
    if any(today[r["id"]] != r["p_today"] for r in rows):
        print("STOPPED: whatif/data.js and briefing.json disagree on today's probabilities; rebuild whatif/data.js first.")
        return 2
    dear = {r["id"] for r in rows if r["regime"]["energy_price"] > 0}
    share = lambda p, h: sum(p[s][h] for s in dear)

    model = io.load_world_model("de")
    ws = io.load_json(io.RADAR_SNAPSHOT / "wissensstand.json")
    heute = datetime.fromisoformat(data["weltlage"]["stand"].replace("Z", "+00:00"))
    real = ts.tagesstand(model, ws, heute)
    if real["szenarien"] != data["weltlage"]["szenarien"]:
        print("STOPPED: the engine does not reproduce the world state in whatif/data.js.")
        return 2
    zahl = [a for a in real["anzeichen"] if a["art"] != "aussage"]
    basis = {a["id"]: a["stufe_basis"] for a in zahl}
    jetzt = {a["id"]: a["stufe_jetzt"] for a in zahl}

    k_now = format(data["whatif"]["k_now"], "g")
    singles = data["whatif"]["results"]
    effect = {aid: share(r["by_k"][k_now]["p"], RULE_HORIZON) - share(today, RULE_HORIZON) for aid, r in singles.items()}
    groups = {"stress": sorted(a for a, d in effect.items() if d > 0),
              "relief": sorted(a for a, d in effect.items() if d < 0)}

    def run(ids, k):
        st = dict(jetzt)
        for aid in ids:
            st[aid] = 0 if jetzt[aid] else 1
        m = copy.deepcopy(model)
        m["bayes"]["k_daempfung"] = k
        lage = ts.aus_status(m, basis, st, heute)
        p = {s["id"]: s["p_tag"] for s in lage["szenarien"]}
        for h in HORIZONS:
            if sum(v[h] for v in p.values()) != 100:
                raise SystemExit(f"STOPPED: {ids} k={k} {h} does not sum to 100")
        return {"p": p}

    out = {"_note": "HYPOTHETICAL stress tests computed by engine/tagesstand.py aus_status(); built by ui/build_bundles.py. "
                    "Not forecasts: the model does not know how likely a joint switch is.",
           "world_state": data["weltlage"]["stand"], "rule_horizon": RULE_HORIZON,
           "effect_single_k_now": effect, "bundles": {}}
    for key, ids in groups.items():
        out["bundles"][key] = {"ids": ids, "switch_to": {a: singles[a]["switch_to"] for a in ids},
                               "by_k": {format(k, "g"): run(ids, k) for k in data["whatif"]["k_values"]}}
    (HERE / "whatif_bundles.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for key, b in out["bundles"].items():
        p = b["by_k"][k_now]["p"]
        print(f"{key}: {len(b['ids'])} indicators {b['ids']} -> dearer-energy share {RULE_HORIZON}: "
              f"{share(today, RULE_HORIZON)} % today, {share(p, RULE_HORIZON)} % in this case (k={k_now})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
