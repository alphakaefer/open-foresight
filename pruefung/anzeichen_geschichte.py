"""Geschichte der Anzeichen (Idee d, 30.10.2026): Reihen rueckwaerts fuellen und pruefen, was die Regeln frueher gesagt haetten.

Vier Schritte, jede Pruefung mit dem Code des Tagesstands (engine/tagesstand.py: gilt, pruefe, aus_status),
keine eigene Regel:

1. reihen:    die Rohdateien der freien Quellen in CSV mit Quellenkopf bringen, so aufbereitet wie
              radar-sammeln.php (Monatsmittel, Jahresrate, Quartal unter dem ersten Monat, gleiche Rundung).
2. treffer:   je Anzeichen die Monate, in denen seine Regel galt, und die Episoden.
3. lage:      je Quartalsende der Tagesstand rueckwaerts: Basis ist das heutige Basismodell (v1.4.0), 'jetzt' der
              Stand der Reihen bis zum Stichtag. Grenze: der Prior ist von heute, nicht von damals.
4. committor: q0 je Stichtag (Spezifikation 12, Paare und Generator aus data/uebergaenge.json, vorlaeufig wie in
              pruefung/uebergaenge.py, Abschnitt e) mit der Verteilung aus Schritt 3.

Nur Standardbibliothek; die Reihen sind Werte von heute (spaetere Revisionen), ohne Veroeffentlichungsverzug.

    python3 pruefung/anzeichen_geschichte.py reihen  --roh ROHORDNER [--abruf JJJJ-MM-TT]
    python3 pruefung/anzeichen_geschichte.py rechnen [--radar .../wissensstand.json]
"""
from __future__ import annotations

import argparse
import csv
import io as _io
import json
import re
import struct
import sys
import zipfile
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

from engine import bayes, committor as cm, stufen, tagesstand as ts, uebergaenge as ub  # noqa: E402

ORDNER = WURZEL / "backtest" / "indicators"
REIHEN = ORDNER / "reihen"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="
EUROSTAT = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
OWID = "https://ourworldindata.org/grapher/%s.csv?v=1&csvType=full&useColumnShortNames=true"

# Ereignisse, an denen die Frage "haette es gewarnt" gemessen wird: Setzung dieser Sichtung, kein Urteil des Modells.
# 2008: Lehman-Insolvenz (15.09.2008; die Finanzkrise begann schon im August 2007), 2020: Pandemie, WHO 11.03.2020,
# 2022: Russlands Angriff auf die Ukraine (24.02.2022).
EREIGNISSE = {"2008": "2008-09", "2020": "2020-03", "2022": "2022-02"}
FENSTER_MONATE = 12


# --- Zahlen und Monate ---------------------------------------------------------------

def runde(x: float, n: int) -> float:
    """Wie PHP round(): halbe Werte weg von null."""
    return float(Decimal(repr(x)).quantize(Decimal(1).scaleb(-n), rounding=ROUND_HALF_UP))


def monat_nr(m: str) -> int:
    return int(m[:4]) * 12 + int(m[5:7]) - 1


def nr_monat(n: int) -> str:
    return f"{n // 12:04d}-{n % 12 + 1:02d}"


def monate(von: str, bis: str) -> list:
    return [nr_monat(n) for n in range(monat_nr(von), monat_nr(bis) + 1)]


def _zahl(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


# --- Schritt 1: Rohdateien -> Reihen (wie radar-sammeln.php) ------------------------------

def fred_werte(text: str, reihe: str) -> dict:
    """{JJJJ-MM-TT: wert}; wie fredReihe() im Radar: die Kopfzeile muss die Reihe nennen."""
    zeilen = list(csv.reader(text.strip().splitlines()))
    if len(zeilen[0]) < 2 or zeilen[0][1] != reihe:
        raise ValueError(f"{reihe}: keine CSV")
    return {z[0]: float(z[1]) for z in zeilen[1:] if len(z) > 1 and _zahl(z[1])}


def monatsmittel(tage: dict) -> dict:
    je: dict = {}
    for t, w in tage.items():
        je.setdefault(t[:7], []).append(w)
    return {m: sum(v) / len(v) for m, v in je.items()}


def inflation_jahresrate(cpi: dict) -> dict:
    index = {t[:7]: w for t, w in cpi.items()}
    aus = {}
    for m, w in index.items():
        vor = f"{int(m[:4]) - 1}{m[4:]}"
        if vor in index:
            aus[m] = (w / index[vor] - 1) * 100
    return aus


def zollsatz(zoll: dict, einfuhr: dict) -> dict:
    return {t[:7]: w / einfuhr[t] * 100 for t, w in zoll.items() if einfuhr.get(t)}


def eurostat_werte(text: str) -> dict:
    d = json.loads(text)
    aus = {}
    for t, i in d["dimension"]["time"]["category"]["index"].items():
        if str(i) in d["value"]:
            aus[t] = float(d["value"][str(i)])
    return aus


def quartale_unter_erstem_monat(werte: dict) -> dict:
    return {f"{t[:4]}-{(int(t[-1]) - 1) * 3 + 1:02d}": w for t, w in werte.items()}


def tfp_quartale(xlsx: bytes) -> dict:
    """Spalte dtfp, Blatt 2 (quarterly) der SF-Fed-Datei; Quartal unter seinem ersten Monat."""
    z = zipfile.ZipFile(_io.BytesIO(xlsx))
    texte = [re.sub(r"<[^>]+>", "", s) for s in re.findall(r"<si>(.*?)</si>", z.read("xl/sharedStrings.xml").decode(), re.S)]
    blatt = z.read("xl/worksheets/sheet2.xml").decode()
    spalte: dict = {}
    aus = {}
    for zeile in re.findall(r"<row [^>]*>(.*?)</row>", blatt, re.S):
        zellen = {}
        for name, attr, inhalt in re.findall(r'<c r="([A-Z]+)\d+"([^>]*?)(?:/>|>(.*?)</c>)', zeile, re.S):
            m = re.search(r"<v>(.*?)</v>", inhalt)
            v = m.group(1) if m else ""
            zellen[name] = (texte[int(v)] if 't="s"' in attr and v != "" else v)
        if not spalte and "date" in zellen.values():
            spalte = {v: k for k, v in zellen.items()}
            continue
        q = zellen.get(spalte.get("date", "A"), "")
        w = zellen.get(spalte.get("dtfp", ""), "")
        m = re.fullmatch(r"(\d{4}):Q([1-4])", q)
        if m and _zahl(w):
            aus[f"{m.group(1)}-{(int(m.group(2)) - 1) * 3 + 1:02d}"] = float(w)
    if not aus:
        raise ValueError("Spalte dtfp nicht gefunden")
    return aus


def dta_spalten(b: bytes, namen: list) -> dict:
    """Zahlenspalten einer Stata-Datei (Format 118, kleinstes Byte zuerst); wie dtaSpalten() im Radar."""
    def tag(name: str) -> int:
        i = b.find(f"<{name}>".encode())
        if i < 0:
            raise ValueError(f"dta: <{name}> fehlt")
        return i + len(name) + 2
    if b[tag("release"):tag("release") + 3] != b"118" or b[tag("byteorder"):tag("byteorder") + 3] != b"LSF":
        raise ValueError("dta: nur Format 118, kleinstes Byte zuerst")
    k = struct.unpack("<H", b[tag("K"):tag("K") + 2])[0]
    n = struct.unpack("<Q", b[tag("N"):tag("N") + 8])[0]
    karte = struct.unpack("<14Q", b[tag("map"):tag("map") + 112])
    typen = struct.unpack(f"<{k}H", b[karte[2] + len("<variable_types>"):][:2 * k])
    vn, vf = karte[3] + len("<varnames>"), karte[5] + len("<formats>")
    spalten, versatz = {}, 0
    breiten = {65526: 8, 65527: 4, 65528: 4, 65529: 2, 65530: 1, 32768: 8}
    for i, typ in enumerate(typen):
        breite = breiten.get(typ) or (typ if 1 <= typ <= 2045 else None)
        if breite is None:
            raise ValueError(f"dta: unbekannter Typ {typ}")
        name = b[vn + 129 * i:vn + 129 * (i + 1)].split(b"\0")[0].decode()
        fmt = b[vf + 57 * i:vf + 57 * (i + 1)].split(b"\0")[0].decode()
        spalten[name] = (typ, versatz, fmt)
        versatz += breite
    daten = karte[9] + len("<data>")
    aus = {}
    for name in namen:
        typ, off, _ = spalten[name]
        form, grenze = {65526: ("<d", 1e300), 65527: ("<f", 1e30)}.get(typ, (None, None))
        if form is None:
            raise ValueError(f"dta: Spalte {name} ist keine Kommazahl")
        breite = 8 if typ == 65526 else 4
        werte = {}
        for r in range(n):
            x = struct.unpack(form, b[daten + r * versatz + off:][:breite])[0]
            if x == x and abs(x) < grenze:
                werte[r] = float(x)
        aus[name] = werte
    if spalten["month"][2] != "%tm" and "month" in namen:
        raise ValueError("dta: month ist kein Monatsdatum")
    gemeinsam = set.intersection(*(set(w) for w in aus.values()))
    return {name: {r: w[r] for r in sorted(gemeinsam)} for name, w in aus.items()}


def gpr_deutschland(dta: bytes) -> dict:
    s = dta_spalten(dta, ["month", "GPRC_DEU"])
    aus = {}
    for r, m in s["month"].items():
        m = int(round(m))
        monat = (m % 12 + 12) % 12
        aus[f"{1960 + (m - monat) // 12:04d}-{monat + 1:02d}"] = s["GPRC_DEU"][r]
    return aus


def owid_land(text: str, code: str) -> dict:
    zeilen = list(csv.reader(text.strip().splitlines()))
    if zeilen[0][1] != "code" or zeilen[0][2] != "year":
        raise ValueError("OWID: unbekannte Spalten")
    return {f"{z[2]}-01": float(z[3]) for z in zeilen[1:] if len(z) > 3 and z[1] == code and _zahl(z[3])}


def cisa_je_monat(text: str) -> dict:
    """Wie der Radar: neue Eintraege je Monat ab 2022-06, ohne den laufenden Monat, leere Monate zaehlen null."""
    k = json.loads(text)
    laufend = str(k.get("dateReleased", ""))[:7]
    je: dict = {}
    for e in k["vulnerabilities"]:
        m = str(e.get("dateAdded", ""))[:7]
        if re.fullmatch(r"\d{4}-\d{2}", m) and "2022-06" <= m < laufend:
            je[m] = je.get(m, 0) + 1
    return {m: float(je.get(m, 0)) for m in monate("2022-06", nr_monat(monat_nr(laufend) - 1))}


# Je Reihe: Titel, Einheit, Nachkommastellen (wie im Radar), Adresse(n), Aufbereitung, Radar-Fundstelle, Quellenname.
# Die Adressen sind die der Rohdatei ohne die Begrenzung auf vier Jahre (cosd, lastTimePeriod), die der Radar setzt.
BESCHREIBUNG = {
    "fred-brent": ("Oelpreis Brent", "USD je Barrel", 2, [FRED + "DCOILBRENTEU"], "Monatsmittel der Tageswerte (monatsmittel)",
                   "quelleFred() ab Zeile 1698, Reihe Zeile 1718-1720", "FRED, Brent (DCOILBRENTEU), Federal Reserve Bank of St. Louis"),
    "fred-realrendite-10j": ("Reale Zehnjahresrendite USA", "%", 2, [FRED + "DFII10"], "Monatsmittel der Tageswerte",
                             "quelleFred() ab Zeile 1698, Reihe Zeile 1723-1725", "FRED, 10-jaehrige TIPS (DFII10)"),
    "fred-inflation-usa": ("Inflation USA", "%", 2, [FRED + "CPIAUCSL"], "Jahresrate aus dem Monatsindex (Index / Index des Vorjahresmonats - 1)",
                           "quelleFred() ab Zeile 1698, Reihe Zeile 1728-1742", "FRED, Verbraucherpreise (CPIAUCSL)"),
    "fred-zollsatz-usa": ("Effektiver US-Zollsatz (erhoben)", "%", 2, [FRED + "B235RC1Q027SBEA", FRED + "A255RC1Q027SBEA"],
                          "Zolleinnahmen / Wareneinfuhr * 100, Quartal unter dem ersten Monat", "quelleFred() ab Zeile 1698, Reihe Zeile 1745-1756",
                          "FRED, Zolleinnahmen je Wareneinfuhr (BEA)"),
    "sffed-tfp-usa": ("TFP-Wachstum USA", "% p. a.", 2, ["https://www.frbsf.org/wp-content/uploads/quarterly_tfp.xlsx (Blatt quarterly, Spalte dtfp)"],
                      "Quartal unter dem ersten Monat", "quelleTfp(), Zeile 1764-1805", "SF Fed, Fernald (dtfp)"),
    "eurostat-industrie-de": ("Industrieproduktion Deutschland (Eurostat)", "Index 2021=100", 2,
                              [EUROSTAT + "sts_inpr_m?geo=DE&nace_r2=C&s_adj=SCA&unit=I21&indic_bt=PRD"], "unveraendert, monatlich",
                              "quelleEurostatMakro() ab Zeile 1811, Adresse Zeile 1815, Reihe Zeile 1836", "Eurostat, Produktion im Verarbeitenden Gewerbe (sts_inpr_m)"),
    "eurostat-kerninflation-ea": ("Kerninflation Eurozone", "%", 2,
                                  [EUROSTAT + "prc_hicp_manr?geo=EA&coicop=TOT_X_NRG_FOOD", EUROSTAT + "prc_hicp_minr?geo=EA&coicop18=TOT_X_NRG_FOOD&unit=RCH_A"],
                                  "alte und neue Reihe zusammengefuehrt, die neue ersetzt die alte, wo beide Werte haben (array_replace)",
                                  "quelleEurostatMakro() ab Zeile 1811, Adressen Zeile 1817-1818, Reihe Zeile 1842", "Eurostat, HICP ohne Energie und Lebensmittel"),
    "eurostat-bip-ea": ("Wirtschaftswachstum Eurozone", "% zum Vorjahresquartal", 2,
                        [EUROSTAT + "namq_10_gdp?geo=EA&na_item=B1GQ&unit=CLV_PCH_SM&s_adj=SCA"], "Quartal unter dem ersten Monat",
                        "quelleEurostatMakro() ab Zeile 1811, Adresse Zeile 1819, Reihe Zeile 1851", "Eurostat, BIP preisbereinigt (namq_10_gdp)"),
    "gpr-deu": ("Geopolitisches Risiko in Deutschland (Zeitungsindex)", "% der Artikel", 3,
                ["https://www.matteoiacoviello.com/gpr_files/data_gpr_export.dta (Spalten month, GPRC_DEU)"], "Stata-Monate ab 1960-01 in Kalendermonate",
                "sorgenReihen() ab Zeile 1902, gpr-deu ab Zeile 1927", "Caldara und Iacoviello, Geopolitical Risk Index, Laender-Index Deutschland (GPRC_DEU), CC BY"),
    "vdem-libdem-de": ("Liberale Demokratie in Deutschland (V-Dem-Index)", "Index 0 bis 1", 3, [OWID % "liberal-democracy-index"],
                       "Zeilen mit Laendercode DEU, Jahr unter JJJJ-01", "sorgenReihen() ab Zeile 1902, vdem-libdem-de ab Zeile 1951",
                       "V-Dem Institute (Universitaet Goeteborg), Liberal Democracy Index, CC BY-SA 4.0, ueber Our World in Data"),
    "vdem-libdem-usa": ("Liberale Demokratie in den USA (V-Dem-Index)", "Index 0 bis 1", 3, [OWID % "liberal-democracy-index"],
                        "Zeilen mit Laendercode USA, Jahr unter JJJJ-01", "sorgenReihen() ab Zeile 1902, vdem-libdem-usa ab Zeile 1959",
                        "V-Dem Institute (Universitaet Goeteborg), Liberal Democracy Index, CC BY-SA 4.0, ueber Our World in Data"),
    "vdem-meinungsfreiheit-de": ("Meinungs- und Informationsfreiheit in Deutschland (V-Dem-Index)", "Index 0 bis 1", 3, [OWID % "freedom-of-expression-index"],
                                 "Zeilen mit Laendercode DEU, Jahr unter JJJJ-01", "sorgenReihen() ab Zeile 1902, vdem-meinungsfreiheit-de ab Zeile 1967",
                                 "V-Dem Institute (Universitaet Goeteborg), Freedom of Expression and Alternative Sources of Information Index, CC BY-SA 4.0, ueber Our World in Data"),
    "cisa-kev-monat": ("Ausgenutzte Sicherheitsluecken je Monat (CISA-Katalog)", "neue Eintraege", 0,
                       ["https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"],
                       "Eintraege je Monat nach dateAdded ab 2022-06 (davor Altbestand der Einfuehrung), ohne den laufenden Monat", "sorgenReihen() ab Zeile 1902, cisa-kev-monat ab Zeile 1975",
                       "CISA, Known Exploited Vulnerabilities Catalog, CC0"),
    "fed-dfa-top01": ("Vermoegensanteil der reichsten 0,1 % in den USA", "% des Nettovermoegens", 3, [FRED + "WFRBSTP1300"], "Quartal unter dem ersten Monat (wie geliefert)",
                      "sorgenReihen() ab Zeile 1902, fed-dfa-top01 ab Zeile 2007", "Board of Governors of the Federal Reserve System (US), Distributional Financial Accounts, ueber FRED"),
}


def reihen_aus_rohdateien(roh: Path) -> dict:
    """{reihen-id: {t: wert}} ungerundet aus den Rohdateien (Namen wie im Rohordner des Abrufs)."""
    lies = lambda n: (roh / n).read_text(encoding="utf-8")
    kern = {**eurostat_werte(lies("kern_alt.json")), **eurostat_werte(lies("kern_neu.json"))}
    return {
        "fred-brent": monatsmittel(fred_werte(lies("brent.csv"), "DCOILBRENTEU")),
        "fred-realrendite-10j": monatsmittel(fred_werte(lies("dfii10.csv"), "DFII10")),
        "fred-inflation-usa": inflation_jahresrate(fred_werte(lies("cpi.csv"), "CPIAUCSL")),
        "fred-zollsatz-usa": zollsatz(fred_werte(lies("zoll.csv"), "B235RC1Q027SBEA"), fred_werte(lies("einfuhr.csv"), "A255RC1Q027SBEA")),
        "sffed-tfp-usa": tfp_quartale((roh / "tfp.xlsx").read_bytes()),
        "eurostat-industrie-de": eurostat_werte(lies("industrie.json")),
        "eurostat-kerninflation-ea": kern,
        "eurostat-bip-ea": quartale_unter_erstem_monat(eurostat_werte(lies("bip.json"))),
        "gpr-deu": gpr_deutschland((roh / "gpr.dta").read_bytes()),
        "vdem-libdem-de": owid_land(lies("libdem.csv"), "DEU"),
        "vdem-libdem-usa": owid_land(lies("libdem.csv"), "USA"),
        "vdem-meinungsfreiheit-de": owid_land(lies("freiheit.csv"), "DEU"),
        "cisa-kev-monat": cisa_je_monat(lies("kev.json")),
        "fed-dfa-top01": {t[:7]: w for t, w in fred_werte(lies("dfa.csv"), "WFRBSTP1300").items()},
    }


def schreibe_reihe(rid: str, werte: dict, abruf: str, ziel: Path = REIHEN) -> Path:
    titel, einheit, stellen, adressen, aufbereitung, radar, quelle = BESCHREIBUNG[rid]
    ziel.mkdir(parents=True, exist_ok=True)
    pfad = ziel / f"{rid}.csv"
    kopf = [f"Reihe: {rid} ({titel}), Einheit: {einheit}", f"Quelle: {quelle}"]
    kopf += [f"Adresse: {a}" for a in adressen]
    kopf += [f"Abruf: {abruf}", f"Aufbereitung: {aufbereitung}; Rundung auf {stellen} Stellen wie im Radar",
             f"Radar: apps/foresight-studio/server/radar-sammeln.php, {radar} (zukunftsgut-studio, Stand 396d585); der Radar holt FRED und Eurostat nur vier Jahre zurueck, hier ohne diese Grenze",
             "Nutzung: Lizenz nicht selbst geprueft; Quelle nennen. Werte von heute (spaetere Revisionen), t = JJJJ-MM"]
    zeilen = ["# " + k for k in kopf] + ["t,wert"]
    for t in sorted(werte):
        zeilen.append(f"{t},{Decimal(repr(runde(werte[t], stellen))).quantize(Decimal(1).scaleb(-stellen))}")
    pfad.write_text("\n".join(zeilen) + "\n", encoding="utf-8")
    return pfad


def lese_reihe(pfad: Path) -> list:
    """[(t, wert)] chronologisch; Kopfzeilen mit # und die Spaltenzeile werden uebersprungen."""
    aus = []
    for z in pfad.read_text(encoding="utf-8").splitlines():
        if z and not z.startswith("#") and z != "t,wert":
            t, w = z.split(",")
            aus.append((t, float(w)))
    return sorted(aus)


def lese_reihen(ordner: Path = REIHEN) -> dict:
    return {p.stem: lese_reihe(p) for p in sorted(ordner.glob("*.csv"))}


def kopf_zeile(pfad: Path, schluessel: str) -> list:
    return [z[2 + len(schluessel) + 1:] for z in pfad.read_text(encoding="utf-8").splitlines() if z.startswith(f"# {schluessel}:")]


# --- Vergleich mit dem Radar ----------------------------------------------------------------

def zuletzt_vergleich(reihen: dict, weltlage: dict) -> list:
    """Je Anzeichen der Weltlage mit 'zuletzt': der Wert, den der Tagesstand zuletzt prueft, gegen unseren zum selben t."""
    aus, gesehen = [], set()
    for a in weltlage.get("anzeichen", []):
        z = a.get("zuletzt")
        if not z or z["reihe"] in gesehen or z["reihe"] not in reihen:
            continue
        gesehen.add(z["reihe"])
        unsere = dict(reihen[z["reihe"]])
        aus.append({"reihe": z["reihe"], "weltlage_t": z["t"], "weltlage_wert": float(z["wert"]), "unser_wert": unsere.get(z["t"]),
                    "unser_letzt_t": max(unsere), "gleich": z["t"] in unsere and abs(unsere[z["t"]] - float(z["wert"])) < 1e-6})
    return aus


def radar_vergleich(reihen: dict, wissensstand: dict) -> list:
    """Je Reihe des Radars: jungster Radar-Punkt, unser Wert zum selben t, und wie viele der gemeinsamen Punkte gleich sind."""
    aus = []
    for r in wissensstand.get("reihen", []):
        if r["id"] not in reihen:
            continue
        unsere = dict(reihen[r["id"]])
        radar = [(p["t"], float(p["wert"])) for p in r["punkte"] if p.get("wert") is not None]
        gemeinsam = [(t, w) for t, w in radar if t in unsere]
        gleich = [(t, w) for t, w in gemeinsam if abs(unsere[t] - w) < 1e-6]
        abweichend = [(t, w, unsere[t]) for t, w in gemeinsam if abs(unsere[t] - w) >= 1e-6]
        letzt_t, letzt_w = radar[-1]
        aus.append({"reihe": r["id"], "radar_letzt_t": letzt_t, "radar_letzt_wert": letzt_w, "unser_wert": unsere.get(letzt_t),
                    "gemeinsam": len(gemeinsam), "gleich": len(gleich), "abweichend": abweichend, "unser_letzt_t": max(unsere)})
    return aus


# --- Schritt 2: Treffer je Anzeichen --------------------------------------------------------

def reihen_des_anzeichens(a: dict) -> list:
    return [r for r in (a["reihe"], a.get("reihe2")) if r]


def zahlen_anzeichen(weltmodell: dict, reihen: dict | None = None) -> tuple:
    """(Anzeichen mit Regel und Reihe, deren Reihen alle da sind; Anzeichen, denen eine Reihe fehlt = Luecke)."""
    alle = [a for a in weltmodell["anzeichen"] if a["art"] == "zahl" and a.get("regel") and a.get("reihe")]
    if reihen is None:
        return alle, []
    da = [a for a in alle if all(reihen.get(r) for r in reihen_des_anzeichens(a))]
    return da, [a for a in alle if a not in da]


def status_je_monat(a: dict, reihen: dict, bis: str) -> dict:
    """{monat: True/False/None} nach ts.pruefe, von dem Monat an, in dem alle Reihen des Anzeichens begonnen haben, bis 'bis'."""
    start = max(reihen[r][0][0][:7] for r in reihen_des_anzeichens(a))
    return {m: ts.pruefe(a, reihen, m)[0] for m in monate(start, bis)}


def episoden(status: dict) -> list:
    """[(von, bis)] aufeinanderfolgender Monate mit True."""
    aus, von, vor = [], None, None
    for m in sorted(status):
        if status[m]:
            if von is None or monat_nr(m) != monat_nr(vor) + 1:
                if von is not None:
                    aus.append((von, vor))
                von = m
            vor = m
    if von is not None:
        aus.append((von, vor))
    return aus


def monate_laenge(e: tuple) -> int:
    return monat_nr(e[1]) - monat_nr(e[0]) + 1


def vor_ereignis(status: dict, ereignis: str, fenster: int = FENSTER_MONATE) -> dict:
    """Galt die Regel in den fenster Monaten vor dem Ereignismonat (ohne ihn)? Ab wann, wie viele Monate; und im Ereignismonat selbst.

    daten False: im Fenster hat die Regel noch keinen Status (die Reihe ist zu kurz oder fehlt).
    """
    n = monat_nr(ereignis)
    davor = [m for m in monate(nr_monat(n - fenster), nr_monat(n - 1)) if status.get(m) is not None]
    if not davor:
        return {"daten": False, "galt": None, "ab": None, "monate": 0, "voll": False, "im_ereignismonat": status.get(ereignis)}
    galt = [m for m in davor if status[m]]
    return {"daten": True, "galt": bool(galt), "ab": galt[0] if galt else None, "monate": len(galt),
            "voll": len(davor) == fenster, "im_ereignismonat": status.get(ereignis)}


# --- Schritt 3: Tagesstand rueckwaerts ------------------------------------------------------

def stand_je_anzeichen(weltmodell: dict, reihen: dict, bis: str) -> dict:
    """{id: Status oder Stufe} bis zum Monat bis, genau wie ts.tagesstand() sie bildet."""
    je = weltmodell.get("stufen") or {}
    aus = {}
    for a in weltmodell["anzeichen"]:
        if a["art"] == "aussage":
            continue
        aus[a["id"]], _ = ts.pruefe(a, reihen, bis)
        if a["id"] in je:
            aus[a["id"]] = stufen.stufe(je[a["id"]], [(t, w) for t, w in reihen.get(a["reihe"], []) if t[:7] <= bis])
    return aus


def signale_zwischen(weltmodell: dict, basis: dict, jetzt: dict, heute: datetime) -> list:
    """Die Signale, die ts.aus_status aus basis und jetzt bildet (dort nicht herausgereicht)."""
    je = weltmodell.get("stufen") or {}
    signale = []
    for a in weltmodell["anzeichen"]:
        if a["art"] == "aussage":
            continue
        st = je.get(a["id"])
        k_vorher, k_nachher = ts._stufe(a["id"], basis.get(a["id"]), st), ts._stufe(a["id"], jetzt.get(a["id"]), st)
        if k_vorher is not None and k_nachher is not None and k_vorher != k_nachher and a.get("wirkung"):
            nachher = k_nachher >= 1
            signale.append(ts.anzeichen_signal(a, nachher, heute) if max(k_vorher, k_nachher) <= 1
                           else stufen.signal(a, st, k_vorher, k_nachher, heute))
    return signale


def lage_am(weltmodell: dict, reihen: dict, stichtag: str, basis_monat: str | None = None) -> dict:
    """Weltlage am Stichtag (Monat JJJJ-MM): Basis = Stand der Reihen bis zum Monat des Basismodells, jetzt = bis zum Stichtag.

    Dieselbe Rechnung wie ts.tagesstand (aus_status); dazu der exakte Posterior je Horizont aus ts.rechne_am.
    """
    basis_monat = basis_monat or weltmodell["meta"]["stand"][:7]
    basis = stand_je_anzeichen(weltmodell, reihen, basis_monat)
    jetzt = stand_je_anzeichen(weltmodell, reihen, stichtag)
    heute = datetime(int(stichtag[:4]), int(stichtag[5:7]), 1, tzinfo=timezone.utc)
    lage = ts.aus_status(weltmodell, basis, jetzt, heute)
    signale = signale_zwischen(weltmodell, basis, jetzt, heute)
    rechnung = ts.rechne_am(weltmodell, signale, heute)
    for s in lage["szenarien"]:  # dieselbe Zahl wie aus_status, sonst ist hier etwas nachgebaut, das nicht stimmt
        for h in rechnung["posterior"]:
            if s["p_tag"][h] != rechnung["posterior"][h][s["id"]]:
                raise AssertionError(f"{stichtag} {s['id']} {h}: Signale nachgebaut weichen von aus_status ab")
    return {"lage": lage, "rechnung": rechnung, "signale": signale, "basis": basis, "jetzt": jetzt}


def quartalsenden(von_jahr: int, bis: str) -> list:
    return [m for m in monate(f"{von_jahr}-03", bis) if int(m[5:7]) % 3 == 0]


def gelten(jetzt: dict) -> list:
    return sorted(a for a, v in jetzt.items() if v)


def ohne_daten(jetzt: dict) -> list:
    return sorted(a for a, v in jetzt.items() if v is None)


# --- Schritt 4: Committor --------------------------------------------------------------------

def committor_q(model: dict, vorlage: dict) -> tuple:
    """(sids, Generator, {paar-id: {sid: q}}) mit den vorgeschlagenen Uebergaengen (vorlaeufig)."""
    sids, q = ub.aus_vorlage(model, vorlage, vorschlaege=True)
    return sids, q, {p["id"]: cm.committor(sids, q, p["A"], p["B"]) for p in vorlage["committor"]["paare"]}


def q0_aus(posterior_exakt: dict, qwerte: dict) -> float:
    return cm.heute(posterior_exakt, qwerte)


def hebel_liste(model: dict, anzeichen: list, pi: dict, qwerte: dict, k: float) -> list:
    return cm.hebel(model, anzeichen, pi, qwerte, k)


def zusammenfuehren(anzeichen: list, entwurf: list) -> list:
    """Anzeichen aus data/anzeichen.json und aus einem Entwurf, je Id einmal (die aus anzeichen.json gelten).

    AS01-AS10 stehen seit der Uebernahme (Frage 3, 15.10.2026) in data/anzeichen.json und noch in
    data/entwurf/anzeichen_sorgen.json; aneinandergehaengt zaehlte jede doppelt.
    """
    ids = {a["id"] for a in anzeichen}
    return list(anzeichen) + [a for a in entwurf if a["id"] not in ids]


def dubletten(liste: list) -> list:
    gesehen, doppelt = set(), []
    for a in liste:
        if a["id"] in gesehen and a["id"] not in doppelt:
            doppelt.append(a["id"])
        gesehen.add(a["id"])
    return doppelt


# --- Tabellen (aus den CSV dieses Ordners) ---------------------------------------------------

def lies_csv(name: str, ordner: Path = ORDNER) -> list:
    with open(ordner / name, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def perzentil(werte: list, x: float) -> float:
    """Anteil der Werte, die hoechstens so gross sind wie x (0 bis 1)."""
    return sum(1 for w in werte if w <= x + 1e-12) / len(werte)


def quartal_vor(stichtage: list, ereignis: str) -> str | None:
    """Letztes Quartalsende vor dem Ereignismonat."""
    davor = [m for m in stichtage if m < ereignis]
    return davor[-1] if davor else None


def quartal_ab(stichtage: list, ereignis: str) -> str | None:
    """Erstes Quartalsende im oder nach dem Ereignismonat."""
    ab = [m for m in stichtage if m >= ereignis]
    return ab[0] if ab else None


def committor_ereignisse(q0: dict, stichtage: list, ereignisse: dict | None = None) -> list:
    """Je Ereignis: q0 am Quartalsende davor, vier Quartale davor, die Veraenderung, q0 im Ereignisquartal und die Einordnung.

    q0 {stichtag: wert} nur ueber die Quartalsenden; Perzentile gegen alle Quartale und gegen alle Vier-Quartals-Aenderungen.
    Gekippt Richtung Krise, wenn q0 am Quartalsende vor dem Ereignis zu den niedrigsten zehn Prozent aller Quartale zaehlt.
    """
    ereignisse = ereignisse or EREIGNISSE
    quartale = [m for m in stichtage if m in q0]
    stufe4 = [q0[b] - q0[a] for a, b in zip(quartale, quartale[4:])]
    alle = [q0[m] for m in quartale]
    aus = []
    for name, e in ereignisse.items():
        davor, im = quartal_vor(quartale, e), quartal_ab(quartale, e)
        i = quartale.index(davor)
        vier = quartale[i - 4] if i >= 4 else None
        aus.append({"ereignis": e, "name": name, "davor": davor, "q0_davor": q0[davor], "vier_davor": vier,
                    "q0_vier_davor": q0.get(vier), "aenderung_4q": (q0[davor] - q0[vier]) if vier else None,
                    "perz_aenderung_4q": perzentil(stufe4, q0[davor] - q0[vier]) if vier else None,
                    "perz_niveau": perzentil(alle, q0[davor]), "ereignisquartal": im, "q0_ereignisquartal": q0[im],
                    "perz_niveau_ereignisquartal": perzentil(alle, q0[im]),
                    "aenderung_ins_ereignisquartal": q0[im] - q0[davor],
                    "gekippt": perzentil(alle, q0[davor]) <= 0.10})
    return aus


def kurz(liste: str) -> str:
    return liste.replace("|", ", ") or "keines"


def tabellen_markdown(ordner: Path = ORDNER) -> str:
    """Alle Tabellen der Sichtungsseite aus den CSV des Ordners."""
    wm = json.loads((WURZEL / "model" / "world_model.de.json").read_text(encoding="utf-8"))
    anz, luecken = zahlen_anzeichen(wm, lese_reihen(ordner / "reihen"))
    monate_csv = lies_csv("treffer_monate.csv", ordner)
    episoden_csv = lies_csv("treffer_episoden.csv", ordner)
    ereignisse_csv = lies_csv("treffer_vor_ereignissen.csv", ordner)
    zeilen = []

    # Tabelle 0: die Reihen
    rv = {r["reihe"]: r for r in lies_csv("radar_vergleich.csv", ordner)} if (ordner / "radar_vergleich.csv").exists() else {}
    wv = {r["reihe"]: r for r in lies_csv("weltlage_vergleich.csv", ordner)} if (ordner / "weltlage_vergleich.csv").exists() else {}
    reihen_ = lese_reihen(ordner / "reihen")
    zeilen += ["| Reihe | Anzeichen | Werte | Von | Bis | Radar-Wissensstand (15.10.) | Weltlage (29.10.) |", "|---|---|---|---|---|---|---|"]
    for rid, punkte in reihen_.items():
        ids = sorted({a["id"] for a in wm["anzeichen"] if rid in (a.get("reihe"), a.get("reihe2"))})
        r, w = rv.get(rid), wv.get(rid)
        rtext = (f"{r['radar_letzt_t']}: {float(r['radar_letzt_wert']):g} gegen {float(r['unser_wert_dort']):g}; {r['gleich']} von {r['gemeinsame_punkte']} gemeinsamen Punkten gleich"
                 if r else "nicht im Wissensstand")
        wtext = (f"{w['weltlage_t']}: {float(w['weltlage_wert']):g} gegen {float(w['unser_wert_dort']):g}" if w else "nicht als „zuletzt“")
        zeilen.append(f"| {rid} | {', '.join(ids)} | {len(punkte)} | {punkte[0][0]} | {punkte[-1][0]} | {rtext} | {wtext} |")
    zeilen.append("")

    # Tabelle 1
    st: dict = {}
    for r in monate_csv:
        st.setdefault(r["anzeichen"], {})[r["monat"]] = None if r["gilt"] == "" else r["gilt"] == "1"
    ep: dict = {}
    for r in episoden_csv:
        ep.setdefault(r["anzeichen"], []).append((r["von"], r["bis"], int(r["monate"])))
    zeilen += ["| Anzeichen | Reihe | Regel | Daten ab | Monate mit Treffer | Episoden (Beginn bis Ende) |", "|---|---|---|---|---|---|"]
    for a in anz:
        s_ = st[a["id"]]
        mit = [m for m, v in s_.items() if v is not None]
        regel = a["regel"] + (f" und {a['reihe2']}: {a['regel2']}" if a.get("reihe2") else "")
        treffer = sum(1 for v in s_.values() if v)
        e = ep.get(a["id"], [])
        if not e:
            eps = "keine"
        elif len(e) <= 4:
            eps = "; ".join(f"{v} bis {b} ({n})" for v, b, n in e)
        else:
            laengste = max(e, key=lambda x: x[2])
            eps = (f"{len(e)}, erste {e[0][0]} bis {e[0][1]}; längste {laengste[0]} bis {laengste[1]} ({laengste[2]}); "
                   f"letzte {e[-1][0]} bis {e[-1][1]} ({e[-1][2]})")
        zeilen.append(f"| {a['id']} | {a['reihe']}{' + ' + a['reihe2'] if a.get('reihe2') else ''} | {regel} | {mit[0]} | {treffer} von {len(mit)} | {eps} |")
    zeilen.append("")

    # Tabelle 2
    zeilen += ["| Anzeichen | " + " | ".join(f"vor {e}" for e in EREIGNISSE.values()) + " |", "|---|" + "---|" * len(EREIGNISSE)]
    je: dict = {}
    for r in ereignisse_csv:
        je.setdefault(r["anzeichen"], {})[r["ereignis"]] = r
    for a in anz:
        zellen = []
        for e in EREIGNISSE.values():
            r = je[a["id"]][e]
            if r["daten"] == "0":
                zellen.append("keine Daten")
                continue
            gleich = {"1": ", im Ereignismonat ja", "0": ", im Ereignismonat nein", "": ""}[r["galt_im_ereignismonat"]]
            n = int(r["monate_davor"] or 0)
            zellen.append(f"ja, ab {r['ab']} ({n} {'Monat' if n == 1 else 'Monate'}{gleich})" if r["galt_davor"] == "1" else f"nein{gleich}")
        zeilen.append(f"| {a['id']} | " + " | ".join(zellen) + " |")
    zeilen.append("")

    # Tabelle 3: je Quartalsende, was galt und was sich am stärksten bewegt
    hz = wm["meta"]["horizonte"]
    szen = [x["id"] for x in wm["szenarien"]]
    zeilen += ["| Stichtag | Es gelten | Gegen die Basis eingetreten | Gegen die Basis entfallen | " + " | ".join(f"stärkste Bewegung {h}" for h in hz) + " |",
               "|---|---|---|---|" + "---|" * len(hz)]
    for r in lies_csv("tagesstand_rueckwaerts.csv", ordner):
        bew = []
        for h in hz:
            d = {x: float(r[f"delta_{h}_{x}"]) for x in szen}
            top = max(d, key=lambda x: abs(d[x]))
            bew.append(f"{top} {d[top]:+.1f}")
        zeilen.append(f"| {r['stichtag']} | {kurz(r['gelten'])} | {kurz(r['eingetreten_gegen_basis'])} | {kurz(r['entfallen_gegen_basis'])} | " + " | ".join(bew) + " |")
    zeilen.append("")

    # Tabelle 4: q0
    q = lies_csv("committor_rueckwaerts.csv", ordner)
    zeilen += ["| Stichtag | " + " | ".join(f"q0 {p} {h}" for p in ("krise_aufbau", "klima", "gesellschaft") for h in ("2028",)) + " | q0 krise_aufbau 2032 | q0 krise_aufbau 2040 |",
               "|---|---|---|---|---|---|"]
    for r in q:
        zeilen.append(f"| {r['stichtag']} | {float(r['q0_krise_aufbau_2028']):.3f} | {float(r['q0_klima_2028']):.3f} | {float(r['q0_gesellschaft_2028']):.3f} "
                      f"| {float(r['q0_krise_aufbau_2032']):.3f} | {float(r['q0_krise_aufbau_2040']):.3f} |")
    zeilen.append("")

    # Tabelle 5: q0 vor den Ereignissen
    stichtage = [r["stichtag"] for r in q[1:]]
    q0 = {r["stichtag"]: float(r["q0_krise_aufbau_2028"]) for r in q[1:]}
    quartale = [m for m in stichtage if int(m[5:7]) % 3 == 0 and m <= max(stichtage) and m != stichtage[-1]]
    ev = committor_ereignisse(q0, quartale)
    zeilen += ["| Ereignis | q0 am Quartalsende davor | vier Quartale davor | Änderung | davon Rang unter allen Vier-Quartals-Änderungen | Rang des Niveaus unter allen Quartalen | q0 im Ereignisquartal | gekippt? |",
               "|---|---|---|---|---|---|---|---|"]
    for e in ev:
        zeilen.append(f"| {e['ereignis']} ({e['name']}) | {e['davor']}: {e['q0_davor']:.3f} | {e['vier_davor']}: {e['q0_vier_davor']:.3f} | {e['aenderung_4q']:+.3f} "
                      f"| {100 * e['perz_aenderung_4q']:.0f} % ≤ | {100 * e['perz_niveau']:.0f} % ≤ | {e['ereignisquartal']}: {e['q0_ereignisquartal']:.3f} "
                      f"({e['aenderung_ins_ereignisquartal']:+.3f}, Niveau {100 * e['perz_niveau_ereignisquartal']:.0f} % ≤) | {'ja' if e['gekippt'] else 'nein'} |")
    alle = [q0[m] for m in quartale]
    zeilen.append("")
    zeilen.append(f"Alle {len(alle)} Quartalsenden {quartale[0]} bis {quartale[-1]}: q0 (krise_aufbau, 2028) von {min(alle):.3f} bis {max(alle):.3f}, "
                  f"Mittel {sum(alle) / len(alle):.3f}, Median {sorted(alle)[len(alle) // 2]:.3f}; Basis {wm['meta']['stand'][:7]}: {float(q[0]['q0_krise_aufbau_2028']):.3f} "
                  f"({100 * perzentil(alle, float(q[0]['q0_krise_aufbau_2028'])):.0f} % der Quartale liegen darunter oder gleich).")
    zeilen.append("")

    # Tabelle 6: Krisen- und Aufbauwelten des Paares krise_aufbau an den Ereignis-Stichtagen, Punkte gegen die Basis
    paar = next(p for p in json.loads((WURZEL / "model" / "uebergaenge.json").read_text(encoding="utf-8"))["committor"]["paare"] if p["id"] == "krise_aufbau")
    zeilen += [f"| Stichtag | " + " | ".join(f"Krisenwelten {'+'.join(paar['A'])} {h}" for h in hz) + " | " + " | ".join(f"Aufbauwelten {'+'.join(paar['B'])} {h}" for h in hz) + " |",
               "|---|" + "---|" * (2 * len(hz))]
    tage = {r["stichtag"]: r for r in lies_csv("tagesstand_rueckwaerts.csv", ordner)}
    for e in EREIGNISSE.values():
        for m in (quartal_vor(stichtage, e), quartal_ab(stichtage, e)):
            r = tage[m]
            zeilen.append(f"| {m} | " + " | ".join(f"{sum(float(r[f'delta_{h}_{x}']) for x in paar['A']):+.1f}" for h in hz) + " | "
                          + " | ".join(f"{sum(float(r[f'delta_{h}_{x}']) for x in paar['B']):+.1f}" for h in hz) + " |")
    zeilen.append("")

    # Zusammenfassung Schritt 3
    zr = lies_csv("tagesstand_rueckwaerts.csv", ordner)
    ohne_heute = [r for r in zr if r["stichtag"] != zr[-1]["stichtag"]]
    wechsel = sum(1 for a, b in zip(ohne_heute, ohne_heute[1:]) if a["gelten"] != b["gelten"])
    groesste = sorted((max(abs(float(r[f"delta_2028_{x}"])) for x in szen), r["stichtag"]) for r in ohne_heute)
    zeilen.append(f"Schritt 3 über {len(ohne_heute)} Quartalsenden {ohne_heute[0]['stichtag']} bis {ohne_heute[-1]['stichtag']}: die Menge der geltenden Anzeichen wechselt "
                  f"in {wechsel} von {len(ohne_heute) - 1} Quartalsübergängen; stärkste Verschiebung eines Szenarios 2028 je Quartal: Median "
                  f"{groesste[len(groesste) // 2][0]:.1f}, höchstens {groesste[-1][0]:.1f} (Stichtag {groesste[-1][1]}) Punkte, mindestens {groesste[0][0]:.1f} (Stichtag {groesste[0][1]}).")
    return "\n".join(zeilen) + "\n"


# --- Ausgabe ---------------------------------------------------------------------------------

def lade_json(pfad: str) -> dict:
    return json.loads((WURZEL / pfad).read_text(encoding="utf-8"))


def kommando_reihen(roh: Path, abruf: str) -> int:
    reihen = reihen_aus_rohdateien(roh)
    for rid, werte in reihen.items():
        pfad = schreibe_reihe(rid, werte, abruf)
        print(f"  {pfad.relative_to(WURZEL)}: {len(werte)} Werte, {min(werte)} bis {max(werte)}")
    return 0


def kommando_rechnen(radar: Path | None, weltlage: Path | None = None) -> int:
    weltmodell = lade_json("model/world_model.de.json")
    reihen = lese_reihen()
    anz, luecken = zahlen_anzeichen(weltmodell, reihen)
    spaetest = max(t[:7] for r in reihen.values() for t, _ in r)
    basis_monat = weltmodell["meta"]["stand"][:7]
    ORDNER.mkdir(parents=True, exist_ok=True)

    if radar:
        vgl = radar_vergleich(reihen, json.loads(radar.read_text(encoding="utf-8")))
        with open(ORDNER / "radar_vergleich.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["reihe", "radar_letzt_t", "radar_letzt_wert", "unser_wert_dort", "unser_letzt_t", "gemeinsame_punkte", "gleich", "abweichend"])
            for v in vgl:
                w.writerow([v["reihe"], v["radar_letzt_t"], v["radar_letzt_wert"], v["unser_wert"], v["unser_letzt_t"], v["gemeinsam"], v["gleich"],
                            ";".join(f"{t}:{a}/{b}" for t, a, b in v["abweichend"])])

    if weltlage:
        with open(ORDNER / "weltlage_vergleich.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["reihe", "weltlage_t", "weltlage_wert", "unser_wert_dort", "unser_letzt_t", "gleich"])
            for v in zuletzt_vergleich(reihen, json.loads(weltlage.read_text(encoding="utf-8"))):
                w.writerow([v["reihe"], v["weltlage_t"], v["weltlage_wert"], v["unser_wert"], v["unser_letzt_t"], int(v["gleich"])])

    # Schritt 2
    with open(ORDNER / "treffer_monate.csv", "w", encoding="utf-8", newline="") as f, \
            open(ORDNER / "treffer_episoden.csv", "w", encoding="utf-8", newline="") as g, \
            open(ORDNER / "treffer_vor_ereignissen.csv", "w", encoding="utf-8", newline="") as h:
        wm, we, wh = csv.writer(f), csv.writer(g), csv.writer(h)
        wm.writerow(["anzeichen", "monat", "gilt"])
        we.writerow(["anzeichen", "von", "bis", "monate"])
        wh.writerow(["anzeichen", "ereignis", "fenster_von", "daten", "galt_davor", "ab", "monate_davor", "galt_im_ereignismonat"])
        for a in anz:
            st = status_je_monat(a, reihen, spaetest)
            for m, s in st.items():
                wm.writerow([a["id"], m, "" if s is None else int(s)])
            for e in episoden(st):
                we.writerow([a["id"], e[0], e[1], monate_laenge(e)])
            for name, ereignis in EREIGNISSE.items():
                v = vor_ereignis(st, ereignis)
                wh.writerow([a["id"], ereignis, nr_monat(monat_nr(ereignis) - FENSTER_MONATE), int(v["daten"]),
                             "" if v["galt"] is None else int(v["galt"]), v["ab"] or "", v["monate"],
                             "" if v["im_ereignismonat"] is None else int(v["im_ereignismonat"])])

    # Schritt 3 und 4
    model = lade_json("model/world_model.de.json")  # public edition: the world model carries szenarien, kopplung, horizonte
    vorlage = lade_json("model/uebergaenge.json")
    sids, _, qw = committor_q(model, vorlage)
    hz = weltmodell["meta"]["horizonte"]
    szen = [s["id"] for s in weltmodell["szenarien"]]
    basis_rechnung = ts.rechne_am(weltmodell, [], datetime(int(basis_monat[:4]), int(basis_monat[5:7]), 1, tzinfo=timezone.utc))
    basis_pi = {h: basis_rechnung["posterior_exakt"][h] for h in hz}
    stichtage = quartalsenden(2000, spaetest)
    if stichtage[-1] != spaetest:
        stichtage.append(spaetest)
    paare = [p["id"] for p in vorlage["committor"]["paare"]]
    with open(ORDNER / "tagesstand_rueckwaerts.csv", "w", encoding="utf-8", newline="") as f, \
            open(ORDNER / "committor_rueckwaerts.csv", "w", encoding="utf-8", newline="") as g:
        wf, wg = csv.writer(f), csv.writer(g)
        wf.writerow(["stichtag", "anzeichen_ohne_daten", "gelten", "eingetreten_gegen_basis", "entfallen_gegen_basis"]
                    + [f"delta_{h}_{s}" for h in hz for s in szen])
        wg.writerow(["stichtag"] + [f"q0_{p}_{h}" for p in paare for h in hz])
        wg.writerow([f"basis {basis_monat}"] + [f"{q0_aus(basis_pi[h], qw[p]):.4f}" for p in paare for h in hz])
        for st in stichtage:
            r = lage_am(weltmodell, reihen, st, basis_monat)
            ein = sorted(s["anzeichen"] for s in r["signale"] if s["titel"].startswith("Anzeichen eingetreten"))
            ent = sorted(s["anzeichen"] for s in r["signale"] if s["titel"].startswith("Anzeichen entfallen"))
            exakt = r["rechnung"]["posterior_exakt"]
            wf.writerow([st, "|".join(ohne_daten(r["jetzt"])), "|".join(map(str, gelten(r["jetzt"]))), "|".join(ein), "|".join(ent)]
                        + [f"{exakt[h][s] - basis_pi[h][s]:.3f}" for h in hz for s in szen])
            wg.writerow([st] + [f"{q0_aus(exakt[h], qw[p]):.4f}" for p in paare for h in hz])
    (ORDNER / "tabellen.md").write_text(tabellen_markdown(), encoding="utf-8")
    print(f"  Stichtage {stichtage[0]} bis {stichtage[-1]}, {len(anz)} Anzeichen mit Reihe, Luecken: "
          f"{', '.join(a['id'] + ' (' + a['reihe'] + ')' for a in luecken) or 'keine'}; Ergebnisse in {ORDNER.relative_to(WURZEL)}")
    return 0


def main(argv: list | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="kommando", required=True)
    r = sub.add_parser("reihen", help="CSV aus den Rohdateien bauen")
    r.add_argument("--roh", required=True, type=Path)
    r.add_argument("--abruf", default=datetime.now().strftime("%Y-%m-%d"))
    c = sub.add_parser("rechnen", help="Schritte 2 bis 4 rechnen")
    c.add_argument("--radar", type=Path, help="wissensstand.json des Radars fuer den Vergleich")
    c.add_argument("--weltlage", type=Path, help="weltlage.json des Radars (zuletzt je Anzeichen) fuer den Vergleich")
    a = p.parse_args(argv)
    return kommando_reihen(a.roh, a.abruf) if a.kommando == "reihen" else kommando_rechnen(a.radar, a.weltlage)


if __name__ == "__main__":
    raise SystemExit(main())
