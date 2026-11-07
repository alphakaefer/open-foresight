"""Build data.js for index.html from the open-foresight repo (read-only on the repo, no hard-coding).

    python3 -B whatif/build_data.py            # from the repo root; --repo defaults to the repo this folder is in

Reads: radar/snapshot/weltlage.json, radar/snapshot/wissensstand.json, model/world_model.de.json,
model/world_model.en.json, domains/energy-transition/briefing.json.

What-if results are computed HERE with the repo's own engine (engine/tagesstand.py aus_status / rechne_am), never
re-implemented in JavaScript: for every number indicator that has data, its status is flipped (on <-> off) and the
engine recomputes all probabilities, for each k in K_VALUES. The page only looks the results up.
Check first: the engine must reproduce the published weltlage.json exactly; otherwise nothing is written.
"""
import sys

sys.dont_write_bytecode = True  # no __pycache__ in the repo

import argparse
import copy
import json
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
K_VALUES = [0.0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.50]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, default=HERE.parent, help="open-foresight repo (default: the repo this folder is in)")
    repo = ap.parse_args().repo.resolve()
    sys.path.insert(0, str(repo))
    from engine import io, tagesstand as ts

    w = io.load_json(io.RADAR_SNAPSHOT / "weltlage.json")
    ws = io.load_json(io.RADAR_SNAPSHOT / "wissensstand.json")
    model = io.load_world_model("de")
    en = io.load_world_model("en")
    briefing = io.load_json(repo / "domains" / "energy-transition" / "briefing.json")
    heute = datetime.fromisoformat(w["stand"].replace("Z", "+00:00"))

    real = ts.tagesstand(model, ws, heute)
    if real["szenarien"] != w["szenarien"]:
        print("STOPPED: the engine does not reproduce radar/snapshot/weltlage.json; data.js not written.")
        return 2

    zahl = [a for a in real["anzeichen"] if a["art"] != "aussage"]
    basis = {a["id"]: a["stufe_basis"] for a in zahl}
    jetzt = {a["id"]: a["stufe_jetzt"] for a in zahl}
    k_now = model["bayes"]["k_daempfung"]

    def run(statuses: dict, k: float) -> dict:
        m = copy.deepcopy(model)
        m["bayes"]["k_daempfung"] = k
        lage = ts.aus_status(m, basis, statuses, heute)
        return {"p": {s["id"]: s["p_tag"] for s in lage["szenarien"]},
                "signals": [{"indicator": x.get("anzeichen"), "drivers": x["treiber_ids"], "direction": x["richtung"],
                             "strength": x["staerke"], "boost": x["likelihood"]} for x in lage["signale"]]}

    whatif, skipped = {}, {}
    for a in zahl:
        aid = a["id"]
        if jetzt[aid] is None:
            skipped[aid] = "no data: cannot be simulated"
            continue
        if not a.get("wirkung"):
            skipped[aid] = "no effect defined (moves nothing)"
            continue
        flipped = dict(jetzt)
        flipped[aid] = 0 if jetzt[aid] else 1
        whatif[aid] = {"switch_to": "off" if jetzt[aid] else "on",
                       "by_k": {format(k, "g"): run(flipped, k) for k in K_VALUES}}  # keys match JS String(k): "0", "0.15"
        for k, r in whatif[aid]["by_k"].items():
            for h in model["meta"]["horizonte"]:
                if sum(p[h] for p in r["p"].values()) != 100:
                    print(f"STOPPED: what-if {aid} k={k} {h} does not sum to 100")
                    return 2

    data = {
        "weltlage": w,
        "model": {"treiber_kopplung": model["treiber_kopplung"], "k": k_now,
                  "anzeichen": {a["id"]: {"wirkung": a.get("wirkung"), "regel": a.get("regel")} for a in model["anzeichen"]}},
        "en": {"szenarien": [{k: s.get(k) for k in ("id", "name", "kurz", "einfach", "these")} for s in en["szenarien"]],
               "anzeichen": [{"id": a["id"], "text": a["text"]} for a in en["anzeichen"]],
               "treiber": [{"id": t["id"], "name": t["name"]} for t in en["treiber"]]},
        "briefing": briefing,
        "whatif": {"k_values": K_VALUES, "k_now": k_now, "results": whatif, "skipped": skipped},
        "source": {"repo_files": ["radar/snapshot/weltlage.json", "radar/snapshot/wissensstand.json",
                                  "model/world_model.de.json", "model/world_model.en.json",
                                  "domains/energy-transition/briefing.json"],
                   "whatif_engine": "engine/tagesstand.py aus_status() -> rechne_am(), one indicator flipped at a time"},
    }
    (HERE / "data.js").write_text("window.FORESIGHT_DATA = " + json.dumps(data, ensure_ascii=False) + ";\n", encoding="utf-8")
    print(f"wrote data.js: world state {w['stand']}, model v{w['basis']['version']}, "
          f"{len(whatif)} indicators x {len(K_VALUES)} k values simulated by the engine, skipped {sorted(skipped)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
