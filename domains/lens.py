"""Domain lens: break the world model down to one domain question.

Reads
  model/world_model.en.json (falls back to world_model.de.json)   – drivers, scenarios, indicators
  radar/snapshot/weltlage.json                                      – today's world state (computed by engine.tagesstand)
  radar/snapshot/wissensstand.json                                  – radar time series
  domains/<domain>/domain.json                                      – the domain question and its links

Writes
  domains/<domain>/briefing.json   – everything below, machine-readable
  domains/<domain>/briefing.md     – the same for humans

Every number in the briefing comes from one of the input files or from a formula
in this file. Links between world and domain that are judgments are marked
"judgment" in domain.json and shown as such.

    python3 domains/lens.py energy-transition
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGIME_LABEL = {-2: "much cheaper", -1: "cheaper", 0: "neutral", 1: "more expensive", 2: "much more expensive"}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def world_model() -> tuple[dict, str]:
    en = ROOT / "model" / "world_model.en.json"
    if en.exists():
        return load(en), "en"
    return load(ROOT / "model" / "world_model.de.json"), "de"


# --- bottleneck model (CES) -------------------------------------------------

def ces(values: list[float], rho: float) -> float:
    """CES aggregate with equal weights: (mean(x^rho))^(1/rho)."""
    return (sum(v ** rho for v in values) / len(values)) ** (1.0 / rho)


def bottleneck(model: dict) -> dict:
    rho = model["rho"]
    step = model.get("step_for_marginal_gain", 0.5)
    axes = model["axes"]
    x = [a["state_2026"] for a in axes]
    u = ces(x, rho)
    gains = []
    for i, a in enumerate(axes):
        y = list(x)
        y[i] = x[i] * (1 + step)
        u_new = ces(y, rho)
        gains.append({"axis": a["id"], "label": a["label"], "from": x[i], "to": round(y[i], 4),
                      "usability": round(u_new, 4), "gain_percent": round((u_new / u - 1) * 100, 1)})
    gains.sort(key=lambda g: -g["gain_percent"])
    return {
        "rho": rho,
        "usability_ces": round(u, 4),
        "usability_linear": round(sum(x) / len(x), 4),
        "usability_ces_first_4_axes": round(ces(x[:4], rho), 4) if len(x) >= 4 else None,
        "marginal_gain": gains,
        "binding_bottleneck": gains[0]["axis"],
    }


# --- world → domain ---------------------------------------------------------

def scenarios(world: dict, state: dict | None, keys: list[str], horizons: list[str]) -> dict:
    today = {s["id"]: s for s in (state or {}).get("szenarien", [])}
    rows = []
    for s in world["szenarien"]:
        t = today.get(s["id"], {})
        rows.append({
            "id": s["id"], "name": s["name"], "short": s.get("kurz"),
            "regime": {k: s.get("regime", {}).get(k) for k in keys},
            "p_base": s["wahrscheinlichkeit"],
            "p_today": t.get("p_tag"),
        })
    # probability mass per energy-price regime (sum of scenario probabilities, per horizon)
    mass = {}
    for h in horizons:
        m = {}
        for r in rows:
            reg = r["regime"].get("energy_price")
            label = REGIME_LABEL.get(int(reg), str(reg)) if reg is not None else "unknown"
            p = (r["p_today"] or r["p_base"]).get(h, 0)
            m[label] = m.get(label, 0) + p
        mass[h] = m
    rows.sort(key=lambda r: -(abs(r["regime"].get("energy_price") or 0) + abs(r["regime"].get("climate_damage") or 0)))
    return {"rows": rows, "energy_price_mass": mass,
            "note": "p_today = today's world state (base model + early-warning signals since the base); "
                    "mass = sum of scenario probabilities per energy-price regime. Scenarios are mutually "
                    "exclusive within a horizon, so the sum is meaningful."}


def drivers(world: dict, links: list[dict]) -> list[dict]:
    by_id = {t["id"]: t for t in world["treiber"]}
    out = []
    for link in links:
        t = by_id.get(link["id"])
        if not t:
            out.append({"id": link["id"], "error": "not in world model"})
            continue
        out.append({"id": t["id"], "name": t["name"], "type": t.get("typ"), "question": t.get("frage"),
                    "status_2026": t.get("stand_2026"), "why_linked": link["why"],
                    "judgment": link.get("judgment", True)})
    return out


def indicators(world: dict, state: dict | None, driver_ids: set, series_ids: set, extra: list[str]) -> list[dict]:
    today = {a["id"]: a for a in (state or {}).get("anzeichen", [])}
    out = []
    for a in world["anzeichen"]:
        eff = (a.get("wirkung") or {}).get("treiber_ids") or []
        hit = (set(eff) & driver_ids) or a.get("reihe") in series_ids or a["id"] in extra or a.get("bezug") in driver_ids
        if not hit:
            continue
        t = today.get(a["id"], {})
        out.append({"id": a["id"], "text": a["text"], "series": a.get("reihe"), "rule": a.get("regel"),
                    "refers_to": a.get("bezug"), "affects_drivers": eff,
                    "active_at_base": t.get("status_basis"), "active_today": t.get("status_jetzt"),
                    "current": t.get("aktuell"), "threshold": t.get("schwelle"), "latest": t.get("zuletzt")})
    return out


def series(radar: dict | None, wanted: list[dict]) -> list[dict]:
    by_id = {r["id"]: r for r in (radar or {}).get("reihen", [])}
    out = []
    for w in wanted:
        r = by_id.get(w["id"])
        if not r or not r.get("punkte"):
            out.append({"id": w["id"], "label": w["label"], "error": "no data in snapshot"})
            continue
        pts = r["punkte"]
        last = pts[-1]
        year_ago = next((p for p in pts if p["t"] == f"{int(last['t'][:4]) - 1}{last['t'][4:]}"), None)
        out.append({"id": w["id"], "label": w["label"], "unit": r.get("einheit"), "source": r.get("quelleName"),
                    "url": r.get("url"), "latest": last, "year_ago": year_ago,
                    "change_12m": round(last["wert"] - year_ago["wert"], 3) if year_ago else None,
                    "points": len(pts)})
    return out


def briefing(domain_dir: Path) -> dict:
    domain = load(domain_dir / "domain.json")
    world, lang = world_model()
    snap = ROOT / "radar" / "snapshot"
    state = load(snap / "weltlage.json") if (snap / "weltlage.json").exists() else None
    radar = load(snap / "wissensstand.json") if (snap / "wissensstand.json").exists() else None
    links = domain["world_links"]
    drv = drivers(world, links["drivers"])
    series_ids = {s["id"] for s in domain["radar_series"]}
    return {
        "domain": {k: domain[k] for k in ("id", "title", "question", "status", "horizons")},
        "inputs": {"world_model": f"model/world_model.{lang}.json", "version": world["meta"]["version"],
                   "model_date": world["meta"]["stand"],
                   "world_state_date": (state or {}).get("stand"), "radar_date": (radar or {}).get("stand")},
        "scenarios": scenarios(world, state, links["scenario_rule"]["regime_keys"], domain["horizons"]),
        "drivers": drv,
        "indicators": indicators(world, state, {d["id"] for d in drv}, series_ids,
                                 links.get("indicator_rule", {}).get("extra_ids", [])),
        "series": series(radar, domain["radar_series"]),
        "bottleneck": bottleneck(domain["bottleneck_model"]),
        "bottleneck_evidence": domain["bottleneck_model"].get("evidence", []),
        "open_tasks": domain.get("open_tasks", []),
    }


# --- markdown ---------------------------------------------------------------

def markdown(b: dict) -> str:
    d, i = b["domain"], b["inputs"]
    hs = d["horizons"]
    L = [f"# Domain briefing: {d['title']}", "",
         f"> **Question:** {d['question']}", "",
         f"_{d['status']}_", "",
         f"Generated by `domains/lens.py` from {i['world_model']} (v{i['version']}, {i['model_date']}), "
         f"world state {i['world_state_date']}, radar {i['radar_date']}. Do not edit by hand – regenerate.", ""]

    L += ["## 1. World scenarios through the energy lens", "",
          "| id | scenario | energy price | climate damage | " + " | ".join(f"p {h} base → today" for h in hs) + " |",
          "|---|---|---|---|" + "---|" * len(hs)]
    for r in b["scenarios"]["rows"]:
        cells = []
        for h in hs:
            base = r["p_base"].get(h)
            today = (r["p_today"] or {}).get(h)
            cells.append(f"{base} → {today}" if today is not None and today != base else f"{base}")
        ep, cd = r["regime"].get("energy_price"), r["regime"].get("climate_damage")
        L.append(f"| {r['id']} | {r['name']} | {ep:+.0f} | {cd:+.0f} | " + " | ".join(cells) + " |")
    L += ["", "**Probability mass by energy-price regime** (percent, sum over scenarios):", "",
          "| regime | " + " | ".join(hs) + " |", "|---|" + "---|" * len(hs)]
    labels = sorted({k for m in b["scenarios"]["energy_price_mass"].values() for k in m},
                    key=lambda x: list(REGIME_LABEL.values()).index(x) if x in REGIME_LABEL.values() else 99)
    for lab in labels:
        L.append(f"| {lab} | " + " | ".join(str(b["scenarios"]["energy_price_mass"][h].get(lab, 0)) for h in hs) + " |")
    L += ["", f"_{b['scenarios']['note']}_", ""]

    L += ["## 2. World drivers linked to the domain", "",
          "Each link is a **judgment** (see `domain.json`), not model output.", "",
          "| id | driver | type | why linked |", "|---|---|---|---|"]
    for x in b["drivers"]:
        L.append(f"| {x['id']} | {x.get('name', '')} | {x.get('type', '')} | {x.get('why_linked', x.get('error', ''))} |")

    L += ["", "## 3. Early-warning indicators to watch", "",
          "| id | indicator | series | rule | active at base | active today | latest |", "|---|---|---|---|---|---|---|"]
    for a in b["indicators"]:
        lt = a.get("latest") or {}
        latest = f"{lt.get('t')}: {lt.get('wert')}" if lt else "–"
        L.append(f"| {a['id']} | {a['text']} | {a['series'] or '–'} | `{a['rule'] or 'statement'}` | "
                 f"{a['active_at_base']} | {a['active_today']} | {latest} |")

    L += ["", "## 4. Domain evidence from the radar", "",
          "| series | latest | 12 months earlier | change | unit | source |", "|---|---|---|---|---|---|"]
    for s in b["series"]:
        if "error" in s:
            L.append(f"| {s['label']} (`{s['id']}`) | {s['error']} | | | | |")
            continue
        ya = s["year_ago"]
        L.append(f"| {s['label']} (`{s['id']}`) | {s['latest']['t']}: {s['latest']['wert']} | "
                 f"{(ya['t'] + ': ' + str(ya['wert'])) if ya else '–'} | {s['change_12m'] if s['change_12m'] is not None else '–'} | "
                 f"{s['unit']} | [{s['source']}]({s['url']}) |")

    bn = b["bottleneck"]
    L += ["", "## 5. Domain key factors: the bottleneck model", "",
          f"Usable output U = CES aggregate of the axes with rho = {bn['rho']} (strong complements). "
          f"U = **{bn['usability_ces']}** with all axes, {bn['usability_ces_first_4_axes']} without permitting, "
          f"linear mean would be {bn['usability_linear']}.", "",
          "| axis | from | to (+50 %) | U after | gain |", "|---|---|---|---|---|"]
    for g in bn["marginal_gain"]:
        L.append(f"| {g['label']} | {g['from']} | {g['to']} | {g['usability']} | {g['gain_percent']} % |")
    L += ["", f"**Binding bottleneck:** `{bn['binding_bottleneck']}` – improving it raises usable output most.", ""]
    for e in b["bottleneck_evidence"]:
        L += [f"> Evidence ({e['for_axis']}): {e['text']}", ">",
              f"> Source: {e['source'] or '**' + e['source_status'] + '**'}", ""]

    L += ["## 6. Open tasks for the hackathon", ""] + [f"- [ ] {t}" for t in b["open_tasks"]] + [""]
    return "\n".join(L)


def main(argv: list[str]) -> int:
    name = argv[0] if argv else "energy-transition"
    domain_dir = ROOT / "domains" / name
    b = briefing(domain_dir)
    (domain_dir / "briefing.json").write_text(json.dumps(b, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (domain_dir / "briefing.md").write_text(markdown(b), encoding="utf-8")
    print(f"  wrote {domain_dir.relative_to(ROOT)}/briefing.md and briefing.json "
          f"(binding bottleneck: {b['bottleneck']['binding_bottleneck']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
