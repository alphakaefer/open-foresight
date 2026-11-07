"""Geschichte der Anzeichen (pruefung/anzeichen_geschichte.py): Aufbereitung der Reihen wie im Radar, Treffer, Tagesstand rueckwaerts.

Die Prueflogik ist die des Tagesstands (engine/tagesstand.py); hier steht nur, was dieses Skript dazu tut.
"""
import importlib.util
import io
import json
import re
import struct
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from engine import tagesstand as ts

WURZEL = Path(__file__).resolve().parent.parent
PFAD = WURZEL / "pruefung" / "anzeichen_geschichte.py"
ORDNER = WURZEL / "backtest" / "indicators"


@pytest.fixture(scope="module")
def g():
    spec = importlib.util.spec_from_file_location("anzeichen_geschichte", PFAD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- Aufbereitung wie radar-sammeln.php ----------------------------------------------------

def test_runde_wie_php(g):
    assert g.runde(2.675, 2) == 2.68  # Python-round gaebe 2.67
    assert g.runde(-1.005, 2) == -1.01
    assert g.runde(1.5, 0) == 2.0 and g.runde(2.5, 0) == 3.0


def test_monatsmittel_und_fred(g):
    tage = g.fred_werte("observation_date,X\n2020-01-01,1\n2020-01-02,.\n2020-01-03,3\n2020-02-01,5\n", "X")
    assert tage == {"2020-01-01": 1.0, "2020-01-03": 3.0, "2020-02-01": 5.0}
    assert g.monatsmittel(tage) == {"2020-01": 2.0, "2020-02": 5.0}
    with pytest.raises(ValueError):
        g.fred_werte("observation_date,Y\n2020-01-01,1\n", "X")


def test_inflation_jahresrate_und_zollsatz(g):
    cpi = {"2020-03-01": 100.0, "2021-03-01": 103.0, "2021-04-01": 110.0}
    assert g.inflation_jahresrate(cpi) == {"2021-03": pytest.approx(3.0)}  # April 2020 fehlt, also keine Rate
    assert g.zollsatz({"2020-01-01": 5.0, "2020-04-01": 6.0}, {"2020-01-01": 100.0, "2020-04-01": 0.0}) == {"2020-01": 5.0}


def test_quartale_unter_dem_ersten_monat(g):
    assert g.quartale_unter_erstem_monat({"2026-Q1": 1.0, "2026-Q3": 2.0, "2025-Q4": 3.0}) == {"2026-01": 1.0, "2026-07": 2.0, "2025-10": 3.0}


def test_eurostat_json_stat(g):
    text = json.dumps({"dimension": {"time": {"category": {"index": {"2025-12": 0, "2026-01": 1, "2026-02": 2}}}}, "value": {"0": 2.5, "2": 2.4}})
    assert g.eurostat_werte(text) == {"2025-12": 2.5, "2026-02": 2.4}  # Monate ohne Wert fehlen


def test_owid_land_nimmt_nur_das_land(g):
    text = "entity,code,year,libdem,region\nGermany,DEU,2024,0.8,Europe\nGermany,DEU,2025,,Europe\nUnited States,USA,2025,0.57,NA\n"
    assert g.owid_land(text, "DEU") == {"2024-01": 0.8}
    assert g.owid_land(text, "USA") == {"2025-01": 0.57}
    with pytest.raises(ValueError):
        g.owid_land("a,b,c,d\n", "DEU")


def test_cisa_je_monat_zaehlt_ab_juni_2022_ohne_laufenden_monat(g):
    k = {"dateReleased": "2022-09-15T00:00:00Z", "vulnerabilities": [
        {"dateAdded": "2021-11-03"}, {"dateAdded": "2022-06-01"}, {"dateAdded": "2022-06-20"}, {"dateAdded": "2022-08-02"}, {"dateAdded": "2022-09-01"}]}
    assert g.cisa_je_monat(json.dumps(k)) == {"2022-06": 2.0, "2022-07": 0.0, "2022-08": 1.0}


def test_tfp_quartale_aus_dem_zweiten_blatt(g):
    # Kopfzeile: A = 'date' (Text), B = 'dtfp' (Text); danach Quartale als Text in einem eigenen Satz geteilter Texte
    texte = ["date", "dtfp", "1947:Q2", "2026:Q1", "kein Quartal"]
    sst = "<sst>" + "".join(f"<si><t>{t}</t></si>" for t in texte) + "</sst>"
    blatt = ('<worksheet><sheetData>'
             '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
             '<row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2"><v>1.25</v></c></row>'
             '<row r="3"><c r="A3" t="s"><v>3</v></c><c r="B3"><v>-0.5</v></c></row>'
             '<row r="4"><c r="A4" t="s"><v>4</v></c><c r="B4"><v>9</v></c></row>'
             '</sheetData></worksheet>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/sharedStrings.xml", sst)
        z.writestr("xl/worksheets/sheet2.xml", blatt)
    assert g.tfp_quartale(buf.getvalue()) == {"1947-04": 1.25, "2026-01": -0.5}


def _dta(monate: list, werte: list) -> bytes:
    """Kleinste Stata-Datei im Format 118 (kleinstes Byte zuerst) mit den Doppelspalten month (%tm) und GPRC_DEU."""
    n, k = len(monate), 2
    kopf = b"<stata_dta><header><release>118</release><byteorder>LSF</byteorder><K>" + struct.pack("<H", k) + b"</K><N>" + struct.pack("<Q", n) + b"</N></header>"
    teile = {}
    teile["map"] = b"<map>" + b"\0" * 112 + b"</map>"
    teile["types"] = b"<variable_types>" + struct.pack("<2H", 65526, 65526) + b"</variable_types>"
    namen = b"month".ljust(129, b"\0") + b"GPRC_DEU".ljust(129, b"\0")
    teile["names"] = b"<varnames>" + namen + b"</varnames>"
    teile["sort"] = b"<sortlist>" + b"\0" * 6 + b"</sortlist>"
    formate = b"%tm".ljust(57, b"\0") + b"%9.0g".ljust(57, b"\0")
    teile["formats"] = b"<formats>" + formate + b"</formats>"
    teile["x6"], teile["x7"], teile["x8"] = b"<value_label_names></value_label_names>", b"<variable_labels></variable_labels>", b"<characteristics></characteristics>"
    daten = b"".join(struct.pack("<2d", m, w) for m, w in zip(monate, werte))
    teile["data"] = b"<data>" + daten + b"</data>"
    reihenfolge = ["map", "types", "names", "sort", "formats", "x6", "x7", "x8", "data"]
    versatz, pos = {}, len(kopf)
    for name in reihenfolge:
        versatz[name] = pos
        pos += len(teile[name])
    # Karte: Index 2 = variable_types, 3 = varnames, 5 = formats, 9 = data (wie im Radar gelesen)
    karte = [0] * 14
    karte[2], karte[3], karte[5], karte[9] = versatz["types"], versatz["names"], versatz["formats"], versatz["data"]
    teile["map"] = b"<map>" + struct.pack("<14Q", *karte) + b"</map>"
    return kopf + b"".join(teile[n_] for n_ in reihenfolge) + b"</stata_dta>"


def test_gpr_deutschland_stata_monate_ab_1960(g):
    # Stata zaehlt Monate ab Januar 1960: 0 = 1960-01, 301 = 1985-02, -1 = 1959-12; Fehlwert (sehr gross) faellt weg
    dta = _dta([301.0, 302.0, -1.0, 303.0], [0.5, 1e307, 2.0, 0.25])
    assert g.gpr_deutschland(dta) == {"1985-02": 0.5, "1959-12": 2.0, "1985-04": 0.25}
    with pytest.raises(ValueError):
        g.gpr_deutschland(dta.replace(b"118", b"117", 1))


# --- Schreiben und Lesen der Reihen ------------------------------------------------------------

def test_csv_mit_quellenkopf_und_runder_zahl(g, tmp_path):
    pfad = g.schreibe_reihe("fred-brent", {"2026-09": 100.005, "2026-10": 124.8349}, "2026-10-30", tmp_path)
    text = pfad.read_text(encoding="utf-8")
    assert "# Quelle: FRED, Brent" in text and "# Adresse: https://fred.stlouisfed.org/graph/fredgraph.csv?id=DCOILBRENTEU" in text
    assert "# Abruf: 2026-10-30" in text
    assert g.lese_reihe(pfad) == [("2026-09", 100.01), ("2026-10", 124.83)]


def test_alle_abgelegten_reihen_haben_quelle_adresse_abruf():
    dateien = sorted((ORDNER / "reihen").glob("*.csv"))
    assert len(dateien) == 14
    for p in dateien:
        kopf = [z for z in p.read_text(encoding="utf-8").splitlines() if z.startswith("#")]
        for schluessel in ("Quelle:", "Adresse:", "Abruf:"):
            assert any(z.startswith(f"# {schluessel}") for z in kopf), f"{p.name}: {schluessel} fehlt"
        assert any(re.fullmatch(r"# Abruf: \d{4}-\d{2}-\d{2}", z) for z in kopf)


# --- Treffer und Episoden -------------------------------------------------------------------

def test_status_je_monat_ist_ts_pruefe(g):
    a = {"id": "T", "art": "zahl", "reihe": "r", "regel": "mittel 2 > 10"}
    reihen = {"r": [("2020-01", 5.0), ("2020-02", 12.0), ("2020-03", 15.0), ("2020-04", 1.0)]}
    st = g.status_je_monat(a, reihen, "2020-04")
    assert st == {m: ts.pruefe(a, reihen, m)[0] for m in ["2020-01", "2020-02", "2020-03", "2020-04"]}
    assert st == {"2020-01": None, "2020-02": False, "2020-03": True, "2020-04": False}


def test_status_beginnt_mit_der_spaeteren_von_zwei_reihen(g):
    a = {"id": "T", "art": "zahl", "reihe": "r", "regel": "mittel 1 > 0", "reihe2": "s", "regel2": "mittel 1 > 0"}
    reihen = {"r": [("2020-01", 1.0), ("2020-02", 1.0), ("2020-03", 1.0)], "s": [("2020-02", 1.0), ("2020-03", -1.0)]}
    assert g.status_je_monat(a, reihen, "2020-03") == {"2020-02": True, "2020-03": False}


def test_episoden_trennen_an_luecken_und_false(g):
    st = {"2020-01": True, "2020-02": True, "2020-03": False, "2020-04": True, "2020-05": None, "2020-06": True, "2021-01": True}
    assert g.episoden(st) == [("2020-01", "2020-02"), ("2020-04", "2020-04"), ("2020-06", "2020-06"), ("2021-01", "2021-01")]
    assert [g.monate_laenge(e) for e in g.episoden(st)] == [2, 1, 1, 1]
    assert g.episoden({"2020-01": False}) == []


def test_vor_ereignis_ohne_den_ereignismonat(g):
    monate = g.monate("2019-01", "2020-03")
    st = {m: False for m in monate}
    st["2020-03"] = True  # gilt erst im Ereignismonat: keine Warnung davor
    v = g.vor_ereignis(st, "2020-03")
    assert v["daten"] and v["galt"] is False and v["im_ereignismonat"] is True and v["voll"]
    st["2019-11"] = True
    v = g.vor_ereignis(st, "2020-03")
    assert v["galt"] is True and v["ab"] == "2019-11" and v["monate"] == 1
    assert g.vor_ereignis({"2020-03": True}, "2020-03")["daten"] is False  # nichts davor: keine Daten, keine Warnung


def test_monate_rechnen(g):
    assert g.monate("2019-11", "2020-02") == ["2019-11", "2019-12", "2020-01", "2020-02"]
    assert g.nr_monat(g.monat_nr("1999-12") + 1) == "2000-01"


# --- Committor-Auswertung an Ereignissen ----------------------------------------------------------

def test_perzentil_und_quartale(g):
    assert g.perzentil([1, 2, 3, 4], 2) == 0.5
    sts = ["2007-12", "2008-03", "2008-06", "2008-09", "2008-12"]
    assert g.quartal_vor(sts, "2008-09") == "2008-06" and g.quartal_ab(sts, "2008-09") == "2008-09"
    assert g.quartal_vor(sts, "2007-12") is None


def test_committor_ereignisse_kippt_bei_den_niedrigsten_zehn_prozent(g):
    quartale = g.quartalsenden(2000, "2010-12")
    q0 = {m: 0.60 + 0.001 * i for i, m in enumerate(quartale)}
    q0["2008-06"] = 0.40  # tief, gegen alle anderen Quartale
    e = g.committor_ereignisse(q0, quartale, {"x": "2008-09"})[0]
    assert e["davor"] == "2008-06" and e["gekippt"] is True and e["perz_niveau"] < 0.05
    assert e["aenderung_4q"] == pytest.approx(0.40 - q0["2007-06"])
    q0["2008-06"] = 0.65
    assert g.committor_ereignisse(q0, quartale, {"x": "2008-09"})[0]["gekippt"] is False


# --- Tagesstand rueckwaerts = Tagesstand, wo beide dasselbe meinen ---------------------------------------

@pytest.fixture(scope="module")
def weltmodell():
    return json.loads((WURZEL / "model" / "world_model.de.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def reihen(g):
    return g.lese_reihen(ORDNER / "reihen")


def test_lage_am_juengstem_monat_ist_der_tagesstand(g, weltmodell, reihen):
    spaet = max(t[:7] for r in reihen.values() for t, _ in r)
    wissensstand = {"stand": "test", "signale": [], "reihen": [{"id": rid, "punkte": [{"t": t, "wert": w} for t, w in r]} for rid, r in reihen.items()]}
    heute = datetime(int(spaet[:4]), int(spaet[5:7]), 1, tzinfo=timezone.utc)
    soll = ts.tagesstand(weltmodell, wissensstand, heute)
    ist = g.lage_am(weltmodell, reihen, spaet)["lage"]
    assert {s["id"]: s["p_tag"] for s in ist["szenarien"]} == {s["id"]: s["p_tag"] for s in soll["szenarien"]}
    assert {a["id"]: a.get("status_jetzt") for a in ist["anzeichen"]} == {a["id"]: a.get("status_jetzt") for a in soll["anzeichen"]}
    assert all(s["delta"][h] == 0 for s in ist["szenarien"] for h in s["delta"])  # Basis und jetzt gleich: nichts bewegt sich


def test_lage_am_frueher_stimmt_mit_aus_status_ueberein(g, weltmodell, reihen):
    r = g.lage_am(weltmodell, reihen, "2008-06")  # prueft intern, dass die nachgebauten Signale dieselbe Verteilung geben wie aus_status
    assert "A12" in g.gelten(r["jetzt"])  # Brent im Mai bis Juli 2008 ueber 115 (Monatsmittel)
    assert any(s["anzeichen"] == "A07" and s["titel"].startswith("Anzeichen entfallen") for s in r["signale"])
    assert r["rechnung"]["posterior_exakt"]["2028"]


def test_basis_ohne_signale_ist_der_prior(g, weltmodell):
    basis = ts.rechne_am(weltmodell, [], datetime(2026, 10, 1, tzinfo=timezone.utc))
    for h in weltmodell["meta"]["horizonte"]:
        assert sum(basis["posterior_exakt"][h].values()) == pytest.approx(100.0, abs=0.01)


def test_q0_der_basis_gleicht_pruefung_uebergaenge(g, weltmodell):
    """pruefung/uebergaenge.py (e) nennt q0 = 0,53 fuer krise_aufbau (naechster Horizont 2028, gerundete Prozente)."""
    model = json.loads((WURZEL / "model" / "world_model.de.json").read_text(encoding="utf-8"))
    vorlage = json.loads((WURZEL / "model" / "uebergaenge.json").read_text(encoding="utf-8"))
    _, _, qw = g.committor_q(model, vorlage)
    basis = ts.rechne_am(weltmodell, [], datetime(2026, 10, 1, tzinfo=timezone.utc))
    assert round(g.q0_aus(basis["posterior_exakt"]["2028"], qw["krise_aufbau"]), 2) == 0.53


# --- Dubletten in der Hebel-Liste ----------------------------------------------------------------------



# --- Abgelegte Ergebnisse sind in sich stimmig ------------------------------------------------------------

def test_abgelegte_episoden_folgen_aus_den_abgelegten_monaten(g):
    import csv
    monate, soll = {}, {}
    with open(ORDNER / "treffer_monate.csv", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            monate.setdefault(r["anzeichen"], {})[r["monat"]] = None if r["gilt"] == "" else r["gilt"] == "1"
    with open(ORDNER / "treffer_episoden.csv", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            soll.setdefault(r["anzeichen"], []).append((r["von"], r["bis"]))
    for aid, st in monate.items():
        assert g.episoden(st) == soll.get(aid, []), aid


def test_abgelegte_monate_folgen_aus_den_abgelegten_reihen(g, weltmodell, reihen):
    import csv
    anz, _ = g.zahlen_anzeichen(weltmodell, reihen)
    by = {a["id"]: a for a in anz}
    with open(ORDNER / "treffer_monate.csv", encoding="utf-8", newline="") as f:
        zeilen = list(csv.DictReader(f))
    for r in zeilen[::97]:  # Stichprobe quer durch alle Anzeichen
        soll = ts.pruefe(by[r["anzeichen"]], reihen, r["monat"])[0]
        assert ("" if soll is None else str(int(soll))) == r["gilt"], (r["anzeichen"], r["monat"])
