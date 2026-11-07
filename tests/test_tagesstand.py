"""Tagesstand: Regeln, Wechsel seit dem Basismodell, Bayes-Richtung."""
from datetime import datetime, timezone

from engine import io
from engine.tagesstand import gilt, tagesstand

HEUTE = datetime(2026, 9, 28, tzinfo=timezone.utc)


def monate(von_jahr, von_monat, n):
    aus, j, m = [], von_jahr, von_monat
    for _ in range(n):
        aus.append(f"{j}-{m:02d}")
        j, m = (j + 1, 1) if m == 12 else (j, m + 1)
    return aus


def weltmodell():
    return io.load_world_model()


def wissensstand(brent):
    """Brent als Monatsreihe {t: wert}, sonst nichts - Anzeichen ohne Daten bleiben offen."""
    return {"stand": "2026-09-28T05:30:00Z", "signale": [],
            "reihen": [{"id": "fred-brent", "punkte": [{"t": t, "wert": w} for t, w in sorted(brent.items())]}]}


def test_regeln():
    werte = [("2026-0%d" % i, w) for i, w in enumerate([1, 2, 3, 4, 5, 6], start=1)]
    assert gilt("mittel 2 > 5", werte) is True
    assert gilt("alle 3 > 3", werte) is True
    assert gilt("alle 4 > 3", werte) is False
    assert gilt("zwischen 3 4 6", werte) is True
    assert gilt("steigt 3", werte) is True and gilt("faellt 3", werte) is False
    assert gilt("mittel 7 > 1", werte) is None


def test_jahresrueckgang():
    fallend = [(t, 100 - i) for i, t in enumerate(monate(2023, 10, 36))]
    assert gilt("jahresrueckgang 2", fallend) is True
    assert gilt("jahresrueckgang 2", fallend[:30]) is None


def test_ohne_wechsel_bleibt_die_basis():
    brent = {t: 85.0 for t in monate(2024, 1, 33)}
    lage = tagesstand(weltmodell(), wissensstand(brent), HEUTE)
    assert lage["signale"] == []
    for s in lage["szenarien"]:
        assert s["p_tag"] == s["p_basis"]


def test_eingetretenes_anzeichen_hebt_sein_szenario():
    # Bis zum Basismodell (08/2026) ruhig, danach acht Monate ueber 110 $ -
    # A05 ("Brent ueber 110 $ fuer mehr als zwei Quartale") tritt ein.
    brent = {t: 85.0 for t in monate(2024, 1, 31)}
    brent.update({t: 120.0 for t in monate(2026, 8, 8)})
    lage = tagesstand(weltmodell(), wissensstand(brent), datetime(2027, 3, 31, tzinfo=timezone.utc))
    a05 = next(a for a in lage["anzeichen"] if a["id"] == "A05")
    assert a05["wechsel"] == "eingetreten"
    s04 = next(s for s in lage["szenarien"] if s["id"] == "S04")
    assert s04["p_tag"]["2032"] > s04["p_basis"]["2032"]
    for h in lage["horizonte"]:
        assert sum(s["p_tag"][h] for s in lage["szenarien"]) == 100
    g3 = next(t for t in lage["treiber"] if t["id"] == "G3")
    assert g3["bewegt"] == "bestaetigend"


def test_aussagen_bewegen_nichts():
    lage = tagesstand(weltmodell(), {"stand": "x", "reihen": [], "signale": [
        {"titel": "EZB will Inflationsziel lockern", "text": "", "datum": "2026-09-20T08:00:00Z",
         "url": "https://example.org", "quelleName": "Test"}]}, HEUTE)
    a09 = next(a for a in lage["anzeichen"] if a["id"] == "A09")
    assert len(a09["treffer"]) == 1
    assert lage["signale"] == []


def test_weltmodell_ohne_private_optionen():
    w = weltmodell()
    assert "optionen" not in w and "scoring" not in w and "segmentmischung" not in w



def test_aussensicht_und_journal_kommen_in_der_weltlage_an():
    """Seit 1.4.0 oeffentlich: Modell gegen Geschichte, und was es wann gesagt hat."""
    lage = tagesstand(weltmodell(), wissensstand({}), heute=HEUTE)
    sids = {s["id"] for s in lage["szenarien"]}
    assert lage["aussensicht"]["vergleiche"] and lage["journal"]
    for v in lage["aussensicht"]["vergleiche"] + lage["aussensicht"]["anker"]:
        assert set(v["szenarien"]) <= sids, v["id"]


def test_journal_ist_oeffentlich_unbedenklich():
    """Nur Szenarien und Wahrscheinlichkeiten - keine Option, kein Score."""
    text = str(weltmodell()["journal"])
    assert "P0" not in text and "X0" not in text and "CE_" not in text



def test_gleichstand_ist_kein_rueckgang_in_jeder_python_version():
    """1,1+0,9+0,9 = 0,9+1,0+1,0: exakt gleich, also faellt nichts (Python 3.12 rechnet sum() anders als 3.9)."""
    werte = [(f"2017-{m:02d}", w) for m, w in zip(range(9, 13), [1.1, 0.9, 0.9, 0.9])] + [("2018-01", 1.0), ("2018-02", 1.0)]
    assert gilt("faellt 3", werte) is False
    assert gilt("steigt 3", werte) is False
