#!/usr/bin/env python3
"""Fetch per-region energy values from open sources into radar/regional/regional.json.

    python3 radar/fetch_regional.py

Sources (all open, no key):
  World Bank WDI   countries, latest available year per country (global map)
  Eurostat         EU/EEA countries, latest period per country (Europe map)
  MaStR            German states, units in operation, from the Bundesnetzagentur register (Germany map)

Every dataset carries its source, url, and the period each value refers to. A dataset that fails to download
is left out and reported; nothing is estimated or filled in. Output depends on the live sources, so this is not
part of CI (`make test` reads the committed file only).
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

OUT = Path(__file__).resolve().parent / "regional" / "regional.json"
UA = {"User-Agent": "open-foresight-fetch/1.0"}


def get_json(url: str, timeout: int = 90):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


# ---------- World Bank ----------
def world_bank(indicator: str) -> dict:
    countries = get_json("https://api.worldbank.org/v2/country?format=json&per_page=400")[1]
    real = {c["iso2Code"] for c in countries if c["region"]["id"] != "NA"}   # drops aggregates such as "World"
    rows = get_json(f"https://api.worldbank.org/v2/country/all/indicator/{indicator}?format=json&per_page=400&mrnev=1")[1]
    out = {}
    for r in rows:
        iso2 = r["country"]["id"]
        if r["value"] is None or iso2 not in real:
            continue
        out[iso2] = {"v": round(r["value"], 3), "p": r["date"]}
    return out


# ---------- Eurostat ----------
ES = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
ES_FIX = {"EL": "GR", "UK": "GB"}


def eurostat(code: str, **params) -> dict:
    q = urllib.parse.urlencode({"format": "JSON", "lang": "en", **params})
    d = get_json(f"{ES}/{code}?{q}")
    ids, sizes = d["id"], d["size"]
    cats = {i: d["dimension"][i]["category"]["index"] for i in ids}
    times = sorted(cats["time"], key=cats["time"].get)
    out = {}
    for geo, gpos in cats["geo"].items():
        key = ES_FIX.get(geo, geo)
        if len(key) != 2 or geo.startswith(("EU", "EA", "EE")) and geo != "EE":
            continue                                       # aggregates such as EU27_2020, EA20
        for t in reversed(times):
            idx, stride = 0, 1
            for dim, size in reversed(list(zip(ids, sizes))):
                pos = gpos if dim == "geo" else cats["time"][t] if dim == "time" else 0
                idx += pos * stride
                stride *= size
            v = d["value"].get(str(idx))
            if v is not None:
                out[key] = {"v": round(v, 4), "p": t}
                break
    return out


# ---------- MaStR ----------
MASTR = "https://www.marktstammdatenregister.de/MaStR/Einheit/EinheitJson/GetErweiterteOeffentlicheEinheitStromerzeugung"
STATE_IDS = range(1400, 1416)


def mastr_units(energy_carrier: str) -> dict:
    out = {}
    for sid in STATE_IDS:
        flt = f"Energieträger~eq~'{energy_carrier}'~and~Betriebs-Status~eq~'35'~and~Bundesland~eq~'{sid}'"
        q = urllib.parse.urlencode({"sort": "", "page": 1, "pageSize": 1, "group": "", "filter": flt})
        d = get_json(f"{MASTR}?{q}", timeout=120)
        if not d.get("Data"):
            continue
        out[d["Data"][0]["Bundesland"]] = {"v": d["Total"], "p": date.today().isoformat()}
    return out


DATASETS = [
    ("wb_res", "country", "World Bank WDI EG.FEC.RNEW.ZS", "https://data.worldbank.org/indicator/EG.FEC.RNEW.ZS",
     "Renewable share of final energy consumption", "%", lambda: world_bank("EG.FEC.RNEW.ZS")),
    ("wb_energy_pc", "country", "World Bank WDI EG.USE.PCAP.KG.OE", "https://data.worldbank.org/indicator/EG.USE.PCAP.KG.OE",
     "Energy use per capita", "kg oil equivalent", lambda: world_bank("EG.USE.PCAP.KG.OE")),
    ("es_res_elec", "country", "Eurostat nrg_ind_ren (REN_ELC)", "https://ec.europa.eu/eurostat/databrowser/view/nrg_ind_ren",
     "Renewable share of electricity", "%", lambda: eurostat("nrg_ind_ren", freq="A", nrg_bal="REN_ELC", unit="PC", sinceTimePeriod="2020")),
    ("es_import_dep", "country", "Eurostat nrg_ind_id (TOTAL)", "https://ec.europa.eu/eurostat/databrowser/view/nrg_ind_id",
     "Energy import dependency", "%", lambda: eurostat("nrg_ind_id", freq="A", siec="TOTAL", unit="PC", sinceTimePeriod="2020")),
    ("es_price_hh", "country", "Eurostat nrg_pc_204 (E7000, 2,500-4,999 kWh/yr, all taxes)", "https://ec.europa.eu/eurostat/databrowser/view/nrg_pc_204",
     "Household electricity price", "EUR/kWh", lambda: eurostat("nrg_pc_204", freq="S", siec="E7000", nrg_cons="KWH2500-4999", unit="KWH", tax="I_TAX", currency="EUR", sinceTimePeriod="2024-S1")),
    ("es_hicp_energy", "country", "Eurostat prc_hicp_manr (CP045, annual rate)", "https://ec.europa.eu/eurostat/databrowser/view/prc_hicp_manr",
     "Inflation of electricity, gas and other fuels", "% per year", lambda: eurostat("prc_hicp_manr", freq="M", unit="RCH_A", coicop="CP045", sinceTimePeriod="2025-01")),
    ("mastr_wind", "state", "Marktstammdatenregister (Bundesnetzagentur), Energieträger Wind, in operation", "https://www.marktstammdatenregister.de/",
     "Wind turbines in operation", "units", lambda: mastr_units("2497")),
    ("mastr_pv", "state", "Marktstammdatenregister (Bundesnetzagentur), Energieträger Solar, in operation", "https://www.marktstammdatenregister.de/",
     "Solar PV units in operation", "units", lambda: mastr_units("2495")),
]


def main() -> int:
    result = {"generated": date.today().isoformat(), "note": "Fetched by radar/fetch_regional.py. Values are as published by each source; none estimated.", "datasets": {}}
    failed = 0
    for did, geo, source, url, label, unit, fn in DATASETS:
        try:
            values = fn()
        except Exception as e:                              # noqa: BLE001 - report and continue
            print(f"  FAILED {did}: {e}", file=sys.stderr)
            failed += 1
            continue
        result["datasets"][did] = {"geo": geo, "label": label, "unit": unit, "source": source, "url": url, "values": values}
        print(f"  {did}: {len(values)} regions")
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    print(f"wrote {OUT}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
