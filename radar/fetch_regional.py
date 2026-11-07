#!/usr/bin/env python3
"""Fetch per-region energy values from open sources into radar/regional/regional.json.

    python3 radar/fetch_regional.py

Sources (all open, no key):
  World Bank WDI   countries, latest available year per country (global map)
  Eurostat         EU/EEA countries, latest period per country (Europe map)
  MaStR            German states, units in operation and their net rated capacity, from the Bundesnetzagentur
                   register (Germany, Brandenburg and Berlin maps); capacity sums come from the register's own
                   sum function, nothing is added up here
  Stromnetz Berlin annual peak load and energy at the medium-/low-voltage transformer level (Berlin open data,
                   CC BY); written to "local", one time series per place

Every dataset carries its source, url, and the period each value refers to. A dataset that fails to download
is left out and reported; nothing is estimated or filled in. Output depends on the live sources, so this is not
part of CI (`make test` reads the committed file only).
"""
from __future__ import annotations

import io
import json
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
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


MASTR_SUM = "https://www.marktstammdatenregister.de/MaStR/Einheit/EinheitJson/GetSummenDerLeistungswerte"


def mastr_capacity_mw(energy_carrier: str, extra: str = "") -> dict:
    """Net rated capacity (Nettonennleistung) of units in operation per state, in MW, summed by the register."""
    out = {}
    for sid in STATE_IDS:
        flt = f"Energieträger~eq~'{energy_carrier}'~and~Betriebs-Status~eq~'35'~and~Bundesland~eq~'{sid}'{extra}"
        q = urllib.parse.urlencode({"sort": "", "page": 1, "pageSize": 1, "group": "", "filter": flt})
        d = get_json(f"{MASTR}?{q}", timeout=120)
        if not d.get("Data"):
            continue
        s = get_json(f"{MASTR_SUM}?{urllib.parse.urlencode({'gridName': 'extSEE', 'filter': flt})}", timeout=300)
        kw = s.get("nettoleistungSumme")
        if kw is None:
            continue
        out[d["Data"][0]["Bundesland"]] = {"v": round(kw / 1000, 1), "p": date.today().isoformat(), "n": d["Total"]}
    return out


# ---------- Stromnetz Berlin (local series) ----------
SNB_PEAK = ("https://www.stromnetz.berlin/files/globalassets/dokumente/opendata/veroffentlichungspflichten/"
            "historie-jahreshoechstlast-mittelspannung-niederspannung-berlin.xlsx")
X = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _xlsx_head(data: bytes, rows: int = 8) -> dict:
    """First rows of every sheet of an .xlsx, read with the standard library: {sheet name: [[cell values]]}."""
    z = zipfile.ZipFile(io.BytesIO(data))
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(f"{X}si"):
            shared.append("".join(t.text or "" for t in si.iter(f"{X}t")))
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    out = {}
    for sh in ET.fromstring(z.read("xl/workbook.xml")).iter(f"{X}sheet"):
        target = rels[sh.get(f"{R}id")].lstrip("/")
        path = target if target.startswith("xl/") else "xl/" + target
        got = []
        with z.open(path) as f:
            for _, el in ET.iterparse(f):
                if el.tag != f"{X}row":
                    continue
                vals = []
                for c in el.iter(f"{X}c"):
                    v = c.find(f"{X}v")
                    if v is None:
                        continue
                    vals.append(shared[int(v.text)] if c.get("t") == "s" else float(v.text))
                got.append(vals)
                el.clear()
                if len(got) >= rows:
                    break
        out[sh.get("name")] = got
    return out


def berlin_peak_load() -> dict:
    req = urllib.request.Request(SNB_PEAK, headers=UA)
    with urllib.request.urlopen(req, timeout=180) as r:
        sheets = _xlsx_head(r.read())
    peak, energy = [], []
    for name, rows in sorted(sheets.items()):
        mx = next((row[1] for row in rows if row and row[0] == "Max in kW" and len(row) > 1), None)
        en = next((row[1] for row in rows if row and row[0] == "Arbeit in kWh" and len(row) > 1), None)
        if not name.isdigit() or mx is None or en is None:
            continue
        peak.append({"t": name, "wert": round(mx / 1000, 1)})
        energy.append({"t": name, "wert": round(en / 1e6, 1)})
    if not peak:
        raise ValueError("no year sheet with 'Max in kW' found")
    meta = {"quelleName": "Stromnetz Berlin, § 23c EnWG, annual peak load at the MV/LV transformer level (open data, CC BY)",
            "url": "https://www.stromnetz.berlin/uber-uns/veroffentlichungspflichten/energiewirtschaftsgesetz-enwg",
            "dataset": "daten.berlin.de: historie-ab-2020-jahreshoechstlast-mittelspannung-niederspannung-berlin",
            "file": SNB_PEAK,
            "scope": "Medium-/low-voltage transformer level only, not the whole Berlin grid; yearly values"}
    return {"berlin_peak_load": {**meta, "label": "Annual peak load, MV/LV level", "einheit": "MW", "punkte": peak},
            "berlin_mvlv_energy": {**meta, "label": "Energy through the MV/LV level", "einheit": "GWh", "punkte": energy}}


LOCAL = [("berlin", berlin_peak_load)]


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
    ("mastr_wind_mw", "state", "Marktstammdatenregister (Bundesnetzagentur), Energieträger Wind, in operation, sum of net rated capacity", "https://www.marktstammdatenregister.de/",
     "Wind capacity in operation", "MW", lambda: mastr_capacity_mw("2497")),
    ("mastr_pv_mw", "state", "Marktstammdatenregister (Bundesnetzagentur), Energieträger Solar, in operation, sum of net rated capacity", "https://www.marktstammdatenregister.de/",
     "Solar PV capacity in operation", "MW", lambda: mastr_capacity_mw("2495")),
    ("mastr_pv_roof_mw", "state", "Marktstammdatenregister (Bundesnetzagentur), Solar, Art der Solaranlage = Gebäudesolaranlage, in operation, sum of net rated capacity", "https://www.marktstammdatenregister.de/",
     "Solar PV on buildings, capacity in operation", "MW", lambda: mastr_capacity_mw("2495", "~and~Art der Solaranlage~eq~'853'")),
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
    result["local"] = {}
    for place, fn in LOCAL:
        try:
            series = fn()
        except Exception as e:                              # noqa: BLE001 - report and continue
            print(f"  FAILED local {place}: {e}", file=sys.stderr)
            failed += 1
            continue
        result["local"].update(series)
        print(f"  local {place}: {', '.join(series)}")
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    print(f"wrote {OUT}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
