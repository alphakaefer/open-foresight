"""Tagesstand der Weltlage: das Basismodell plus das, was seit ihm eingetreten ist.

Das Basismodell (data/model.json) ist geprueft und versioniert. Es aendert sich
nur, wenn Karl einen Stand uebernimmt. Der Tagesstand dagegen wird jeden Tag neu
gerechnet - nie fortgeschrieben - aus dem Basismodell und den Reihen des
Zukunftsradars. Deshalb kann er nicht still vom Repo weglaufen: gestern und
heute unterscheiden sich nur um das, was die Daten sagen.

Ablauf:

1. Jedes Anzeichen (data/anzeichen.json) wird zweimal geprueft: mit den Werten
   bis zum Monat des Basismodells, und mit allen.
2. Wo der Status wechselt, entsteht ein Signal an die Treiber unter 'wirkung':
   eingetreten mit dieser Richtung, entfallen mit der Gegenrichtung. Was beim
   Basismodell schon galt, ist dort eingepreist und bewegt nichts.
3. Die Signale laufen durch bayes.update_probabilities - dieselbe Rechnung wie
   bei jedem recherchierten Signal, gedaempft mit k aus parameters.json.

Groessenstufen (Spezifikation 7d): Bringt das Weltmodell "stufen" mit, zaehlt
fuer diese Anzeichen die Stufe statt nur "gilt"; Stufe 1 ist die Regel des
Anzeichens. Jedes Zahlen-Anzeichen traegt stufe_basis und stufe_jetzt (ohne
Stufen 0 oder 1).

Aussagen ("Zentralbank relativiert das Inflationsziel") werden nicht geprueft,
sondern mit ihren Treffern aus den Meldungen vorgelegt. Sie bewegen nichts,
bis ein Mensch sie bestaetigt.

Nur Standardbibliothek: laeuft auch auf dem Webspace, wo es kein numpy gibt.

    python3 -m engine.tagesstand --modell exports/weltmodell.json \\
        --wissensstand radar/wissensstand.json --ziel radar/weltlage.json
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import bayes, stufen

SCHEMA = "weltlage/v2"

GEGENRICHTUNG = {"bestaetigend": "widersprechend", "widersprechend": "bestaetigend"}


# --- Regeln -----------------------------------------------------------------

def gilt(regel: str, werte: list) -> bool | None:
    """True/False nach der Regel; None, wenn die Werte nicht reichen."""
    t = regel.split()
    xs = [w for _, w in werte]
    art = t[0]
    if art in ("mittel", "alle"):
        n, op, x = int(t[1]), t[2], float(t[3])
        if len(xs) < n:
            return None
        passt = (lambda w: w > x) if op == ">" else (lambda w: w < x)
        return passt(sum(xs[-n:]) / n) if art == "mittel" else all(passt(w) for w in xs[-n:])
    if art == "zwischen":
        n, a, b = int(t[1]), float(t[2]), float(t[3])
        return a <= sum(xs[-n:]) / n <= b if len(xs) >= n else None
    if art == "jahresrueckgang":
        n = int(t[1])
        if len(xs) < 12 * (n + 1):
            return None
        jahre = [sum(xs[len(xs) - 12 * (i + 1):len(xs) - 12 * i]) / 12 for i in range(n + 1)]
        return all(jahre[i] < jahre[i + 1] for i in range(n))
    if art in ("faellt", "steigt"):
        n = int(t[1])
        if len(xs) < 2 * n:
            return None
        jung, davor = sum(xs[-n:]) / n, sum(xs[-2 * n:-n]) / n
        return jung < davor if art == "faellt" else jung > davor
    raise ValueError(f"unbekannte Regel: {regel}")


def reihen_aus(wissensstand: dict) -> dict:
    """{reihen-id: [(t, wert)]} chronologisch, aus dem Wissensstand des Radars."""
    aus = {}
    for r in wissensstand.get("reihen", []):
        punkte = sorted((p["t"], float(p["wert"])) for p in r.get("punkte", []) if p.get("wert") is not None)
        aus[r["id"]] = punkte
    return aus


def pruefe(a: dict, reihen: dict, bis: str | None = None) -> tuple[bool | None, tuple | None]:
    """Status eines Zahlen-Anzeichens und sein letzter Wert; mit bis nur Werte bis zu diesem Monat.

    Einschliesslich: der Monat des Basismodells gehoert zum Basismodell. Sonst
    zaehlte ein Stand, der am Monatsende uebernommen wurde, am naechsten Tag
    noch einmal als Wechsel.
    """
    def werte(rid):
        return [(t, w) for t, w in reihen.get(rid, []) if bis is None or t[:7] <= bis]
    erste = werte(a["reihe"])
    status = gilt(a["regel"], erste)
    if status and a.get("reihe2"):
        status = gilt(a["regel2"], werte(a["reihe2"]))
    return status, (erste[-1] if erste else None)


# --- Abstand zur Schwelle (Spezifikation 7h) -----------------------------------------

ABSTAND_LEER = {"schwelle": None, "richtung_regel": None, "aktuell": None, "abstand": None,
                "abstand_vor_3_monaten": None, "naeher": None, "abstand_grund": None}
ABSTAND_STELLEN = 4
ABSTAND_GRUENDE = {
    "zwischen": "Die Regel hat zwei Grenzen und keine einzelne Schwelle.",
    "jahresrueckgang": "Die Regel vergleicht Jahresmittel und kennt keine Schwelle.",
    "faellt": "Die Regel vergleicht zwei Zeiträume und kennt keine Schwelle.",
    "steigt": "Die Regel vergleicht zwei Zeiträume und kennt keine Schwelle.",
}


def _einfache_regel(regel: str) -> tuple | None:
    """(art, n, op, x) bei 'mittel n > x', 'mittel n < x', 'alle n > x', 'alle n < x'; sonst None."""
    t = regel.split()
    if len(t) == 4 and t[0] in ("mittel", "alle") and t[2] in (">", "<"):
        try:
            return t[0], int(t[1]), t[2], float(t[3])
        except ValueError:
            return None
    return None


def _regel_wert(art: str, n: int, op: str, xs: list) -> float | None:
    """Der Wert, den die Regel zuletzt prueft: bei 'mittel' das Mittel der letzten n Werte, bei 'alle' der
    ungunstigste, also der Wert, der der Schwelle am naechsten liegt (bei > der kleinste, bei < der groesste)."""
    if len(xs) < n:
        return None
    letzte = xs[-n:]
    if art == "mittel":
        return sum(letzte) / n
    return min(letzte) if op == ">" else max(letzte)


def _monat_vor(heute: datetime, monate: int) -> str:
    """'JJJJ-MM' des Monats, der monate vor dem Monat von heute liegt."""
    m = heute.year * 12 + heute.month - 1 - monate
    return f"{m // 12:04d}-{m % 12 + 1:02d}"


def abstand(a: dict, reihen: dict, heute: datetime, stufen: list | None = None, stufe: int | None = None) -> dict:
    """Abstand eines Anzeichens zu seiner Schwelle (Spezifikation 7h): wie weit die Regel noch von 'gilt' ist.

    Nur fuer Regeln der Form 'mittel n > x', 'mittel n < x', 'alle n > x', 'alle n < x' aus einer Reihe.
    aktuell ist der Wert, den die Regel zuletzt prueft (Mittel der letzten n Werte, oder der Wert, der der
    Schwelle am naechsten liegt). abstand = Schwelle - aktuell bei 'ueber', aktuell - Schwelle bei 'unter':
    positiv heisst noch nicht erreicht, null oder negativ erreicht. abstand_vor_3_monaten ist derselbe Wert
    mit den Werten bis zum Monat drei Monate vor heute; naeher: ja, nein oder gleich, null ohne diesen Wert.
    Mit Groessenstufen (stufen, stufe heute) zaehlt die Schwelle der naechsthoeheren Stufe, auf der hoechsten
    Stufe die der hoechsten. Alles andere: abstand null und ein Grund.
    """
    aus = dict(ABSTAND_LEER)
    regel = a.get("regel")
    if a["art"] == "aussage":
        aus["abstand_grund"] = "Eine Aussage, keine Zahl."
        return aus
    if a.get("reihe2"):
        aus["abstand_grund"] = "Die Regel hat zwei Bedingungen aus zwei Reihen."
        return aus
    if stufen:
        aus["abstand_stufe"] = None
        if stufe is None:
            aus["abstand_grund"] = "Keine Daten für die Stufe."
            return aus
        ziel = min(stufe + 1, len(stufen))
        aus["abstand_stufe"] = ziel
        regel = stufen[ziel - 1]["regel"]
    teile = _einfache_regel(regel or "")
    if teile is None:
        aus["abstand_grund"] = ABSTAND_GRUENDE.get((regel or "").split(" ")[0], "Die Regel hat keine einfache Schwelle.")
        return aus
    art, n, op, x = teile
    aus["schwelle"], aus["richtung_regel"] = x, "ueber" if op == ">" else "unter"
    punkte = reihen.get(a["reihe"], [])

    def abst(werte):
        akt = _regel_wert(art, n, op, werte)
        return None if akt is None else (akt, (x - akt) if op == ">" else (akt - x))

    jetzt = abst([w for _, w in punkte])
    if jetzt is None:
        aus["abstand_grund"] = "Zu wenige Werte in der Reihe." if punkte else "Keine Werte für diese Reihe."
        return aus
    aus["aktuell"], aus["abstand"] = round(jetzt[0], ABSTAND_STELLEN), round(jetzt[1], ABSTAND_STELLEN)
    frueher = abst([w for t, w in punkte if t[:7] <= _monat_vor(heute, 3)])
    if frueher is not None:
        aus["abstand_vor_3_monaten"] = round(frueher[1], ABSTAND_STELLEN)
        d = aus["abstand"] - aus["abstand_vor_3_monaten"]
        aus["naeher"] = "ja" if d < 0 else "nein" if d > 0 else "gleich"
    return aus


def treffer(muster: str, meldungen: list, heute: datetime, tage: int = 30) -> list:
    """Meldungen der letzten Tage, deren Titel oder Anriss auf das Muster passt."""
    grenze = heute - timedelta(days=tage)
    aus = []
    for s in meldungen:
        try:
            neu = datetime.fromisoformat(s["datum"].replace("Z", "+00:00")) >= grenze
        except (KeyError, ValueError):
            continue
        if neu and re.search(muster, f"{s.get('titel', '')} {s.get('text', '')}", re.I):
            aus.append({"titel": s["titel"], "url": s.get("url"), "quelle": s.get("quelleName"), "datum": s["datum"][:10]})
    return sorted(aus, key=lambda x: x["datum"], reverse=True)[:5]


# --- Signale -----------------------------------------------------------------

def anzeichen_signal(a: dict, jetzt: bool, heute: datetime, staerke: float | None = None) -> dict:
    """Das Signal, das ein Zahlen-Anzeichen beim Wechsel gegenueber dem Basismodell ausloest.

    jetzt True: eingetreten, Richtung aus 'wirkung'; False: entfallen, Gegenrichtung.
    staerke ersetzt die Staerke aus 'wirkung' (Groessenstufen, Spezifikation 7d).
    """
    w = a["wirkung"]
    richtung = w["richtung"] if jetzt else GEGENRICHTUNG[w["richtung"]]
    return {
        "datum": heute.date().isoformat(),
        "titel": f"Anzeichen {'eingetreten' if jetzt else 'entfallen'}: {a['text']}",
        "quelle_url": None,
        "treiber_ids": w["treiber_ids"],
        "richtung": richtung,
        "staerke": w["staerke"] if staerke is None else staerke,
        "anzeichen": a["id"],
        # Anzeichen derselben Reihe in gleicher Richtung messen dieselbe
        # Zahl (Spezifikation 7a); zaehlt nur mit Entdoppeln an.
        "ereignis": f"reihe:{a['reihe']}:{richtung}",
    }


def rechne(weltmodell: dict, signale: list) -> dict:
    """bayes.update_probabilities auf die Signale, wie der Tagesstand sie rechnet.

    Schritt 1 (Spezifikation 7a): ohne Block "zufluss" im Export rechnet der
    Tagesstand wie bis v1.4.0. Mit ungerundet an zaehlen die Signale seit dem
    letzten Urteil mit; 'beitraege' enthaelt nur die uebergebenen Signale.
    """
    return rechne_am(weltmodell, signale, None)


def rechne_am(weltmodell: dict, signale: list, heute: datetime | None) -> dict:
    """rechne() an einem Tag. Mit Block "vergessen" (Spezifikation 7g, nur wenn
    Karl ihn einschaltet) sieht jeder Horizont L_h statt L; heute bestimmt den
    Abstand zu den Horizonten (ohne Angabe: jetzt). Ohne den Block ist heute egal.
    """
    z = weltmodell.get("zufluss")
    ungerundet = bool(z) and bool((z.get("ungerundet") or {}).get("an"))
    basis_signale = z.get("signale", []) if ungerundet else []
    vg = weltmodell.get("vergessen")
    if vg:
        from . import vergessen
        rechnung = vergessen.update(
            weltmodell, basis_signale + signale, weltmodell["bayes"]["k_daempfung"], vg["verweildauer_jahre"],
            heute or datetime.now(timezone.utc), vg.get("pi0"), vg.get("horizont_stichtag", vergessen.STICHTAG),
            zufluss=z, prior_exakt=z["p_basis"] if ungerundet else None)
    else:
        rechnung = bayes.update_probabilities(
            weltmodell, basis_signale + signale, weltmodell["bayes"]["k_daempfung"],
            zufluss=z, prior_exakt=z["p_basis"] if ungerundet else None)
    rechnung["beitraege"] = rechnung["beitraege"][len(basis_signale):]
    return rechnung


# --- Tagesstand ---------------------------------------------------------------

def tagesstand(weltmodell: dict, wissensstand: dict, heute: datetime | None = None) -> dict:
    """Weltlage aus dem Basismodell und den Reihen des Radars."""
    heute = heute or datetime.now(timezone.utc)
    reihen = reihen_aus(wissensstand)
    basis_monat = weltmodell["meta"]["stand"][:7]
    je = weltmodell.get("stufen") or {}
    basis, jetzt, zuletzt, gefunden, abstaende = {}, {}, {}, {}, {}
    for a in weltmodell["anzeichen"]:
        if a["art"] == "aussage":
            gefunden[a["id"]] = treffer(a["muster"], wissensstand.get("signale", []), heute)
            abstaende[a["id"]] = abstand(a, reihen, heute)
            continue
        basis[a["id"]], _ = pruefe(a, reihen, basis_monat)
        jetzt[a["id"]], z = pruefe(a, reihen)
        if a["id"] in je:
            # Stufe 1 ist die Regel des Anzeichens: Stufe >= 1 genau dann, wenn pruefe() True gibt
            alle = reihen.get(a["reihe"], [])
            basis[a["id"]] = stufen.stufe(je[a["id"]], [(t, w) for t, w in alle if t[:7] <= basis_monat])
            jetzt[a["id"]] = stufen.stufe(je[a["id"]], alle)
        zuletzt[a["id"]] = {"reihe": a["reihe"], "t": z[0], "wert": z[1]} if z else None
        abstaende[a["id"]] = abstand(a, reihen, heute, je.get(a["id"]), jetzt[a["id"]] if a["id"] in je else None)
    return aus_status(weltmodell, basis, jetzt, heute, zuletzt=zuletzt, treffer=gefunden,
                      radar_stand=wissensstand.get("stand"), abstand=abstaende)


def aus_status(weltmodell: dict, basis: dict, jetzt: dict, heute: datetime | None = None, *,
               zuletzt: dict | None = None, treffer: dict | None = None, radar_stand: str | None = None,
               abstand: dict | None = None) -> dict:
    """Weltlage aus dem Status je Zahlen-Anzeichen statt aus den Reihen.

    basis, jetzt: {anzeichen-id: True/False/None}, beim Basismodell und heute;
    fehlt ein Anzeichen, gilt None (keine Daten). Fuer ein Anzeichen mit
    Groessenstufen (weltmodell["stufen"]) darf statt des Status die Stufe
    stehen (0, 1, 2, ...); True gilt dort als Stufe 1. zuletzt und treffer reicht
    tagesstand() durch; ohne sie bleiben die Felder leer. Dieselbe Rechnung wie
    der Tagesstand, damit eine Probe ("was waere, wenn A05 eintritt") und die
    Weltlage nicht auseinanderlaufen.

    abstand (Spezifikation 7h): {anzeichen-id: Felder von abstand()}; ohne es fehlen die Felder
    beim Anzeichen, sonst stehen sie dort. Jedes Szenario bekommt "spanne", wenn das Weltmodell
    "spanne_massstab" mitbringt und engine/spanne.py da ist (Spezifikation 5b, 7h).
    """
    heute = heute or datetime.now(timezone.utc)
    je = weltmodell.get("stufen") or {}
    anzeichen, signale = [], []
    for a in weltmodell["anzeichen"]:
        # markt_p (Spezifikation 7h) geht nur durch: ein Vergleich, der nie mit rechnet
        eintrag = {k: a[k] for k in ("id", "bezug", "rolle", "art", "text", "hinweis", "warum", "markt_p", "regel") if k in a}
        eintrag["wirkung"] = a.get("wirkung")
        if a["art"] == "aussage":
            eintrag["treffer"] = (treffer or {}).get(a["id"], [])
            if abstand and a["id"] in abstand:
                eintrag.update(abstand[a["id"]])
            anzeichen.append(eintrag)
            continue
        st = je.get(a["id"])
        k_vorher, k_nachher = _stufe(a["id"], basis.get(a["id"]), st), _stufe(a["id"], jetzt.get(a["id"]), st)
        vorher = None if k_vorher is None else k_vorher >= 1
        nachher = None if k_nachher is None else k_nachher >= 1
        eintrag.update({"status_basis": vorher, "status_jetzt": nachher,
                        "stufe_basis": k_vorher, "stufe_jetzt": k_nachher,
                        "zuletzt": (zuletzt or {}).get(a["id"]), "wechsel": None})
        if abstand and a["id"] in abstand:
            eintrag.update(abstand[a["id"]])
        if vorher is not None and nachher is not None and vorher != nachher:
            eintrag["wechsel"] = "eingetreten" if nachher else "entfallen"
        if k_vorher is not None and k_nachher is not None and k_vorher != k_nachher and a.get("wirkung"):
            # Nur Stufe 0 und 1 im Spiel: dasselbe Signal wie ohne Stufen
            signale.append(anzeichen_signal(a, nachher, heute) if max(k_vorher, k_nachher) <= 1
                           else stufen.signal(a, st, k_vorher, k_nachher, heute))
        anzeichen.append(eintrag)

    rechnung = rechne_am(weltmodell, signale, heute)
    for s, beitrag in zip(signale, rechnung["beitraege"]):
        beitrag["anzeichen"] = s["anzeichen"]

    bewegt = {}
    for s in signale:
        for t in s["treiber_ids"]:
            bewegt[t] = s["richtung"]

    szenarien = []
    for s in weltmodell["szenarien"]:
        e = dict(s)
        e["p_basis"] = dict(s["wahrscheinlichkeit"])
        e["p_tag"] = {h: rechnung["posterior"][h][s["id"]] for h in rechnung["posterior"]}
        e["delta"] = {h: rechnung["diff"][h][s["id"]] for h in rechnung["diff"]}
        sp = _spanne(weltmodell, e["p_tag"])
        if sp:
            e["spanne"] = sp
        # Gegenzeichen (rolle "widerlegt", Spezifikation 7a) senken ihr Szenario beim Eintreten
        e["anzeichen"] = [a["id"] for a in anzeichen if a["bezug"] == s["id"] and a.get("rolle") != "widerlegt"]
        e["gegenzeichen"] = [a["id"] for a in anzeichen if a["bezug"] == s["id"] and a.get("rolle") == "widerlegt"]
        del e["wahrscheinlichkeit"]
        szenarien.append(e)

    treiber = []
    for t in weltmodell["treiber"]:
        e = dict(t)
        e["anzeichen"] = [a["id"] for a in anzeichen
                          if a["bezug"] == t["id"] or t["id"] in ((a.get("wirkung") or {}).get("treiber_ids") or [])]
        e["bewegt"] = bewegt.get(t["id"])
        treiber.append(e)

    return {
        "schema": SCHEMA,
        "stand": heute.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "radar_stand": radar_stand,
        "basis": {"version": weltmodell["meta"]["version"], "stand": weltmodell["meta"]["stand"]},
        # Die Ampel der Strukturpruefung, wenn das Modell sie mitbringt (export.weltmodell).
        **({"pruefung": weltmodell["pruefung"]} if weltmodell.get("pruefung") else {}),
        # Neu-Ermittlung: welche Szenarien endeten und wohin sie gingen (Bruchmarke im Radar)
        **({"beendet": [{k: b[k] for k in ("id", "name", "nachfolger", "bis_version")} for b in weltmodell["beendet"]]} if weltmodell.get("beendet") else {}),
        # Seit 1.4.0: Aussensicht (Modell gegen Geschichte und externe Anker) und
        # das Prognose-Journal, unveraendert durchgereicht.
        **({"aussensicht": weltmodell["aussensicht"]} if weltmodell.get("aussensicht") else {}),
        **({"journal": weltmodell["journal"]} if weltmodell.get("journal") else {}),
        "horizonte": weltmodell["meta"]["horizonte"],
        "k_daempfung": rechnung["k_daempfung"],
        "szenarien": szenarien,
        "treiber": treiber,
        "anzeichen": anzeichen,
        "signale": rechnung["beitraege"],
        "luecken": [a["id"] for a in anzeichen if a["art"] == "zahl" and a["status_jetzt"] is None],
    }


def _spanne(weltmodell: dict, p_tag: dict) -> dict | None:
    """{horizont: [unten, oben]} in Prozentpunkten, gerundet wie die Lesart ("2 bis 13 %"); Spezifikation 5b, 7h.

    Dieselbe Rechnung wie engine.spanne.spanne_prozent mit dem Massstab aus dem Weltmodell
    ("spanne_massstab", vom Export berechnet). Fehlt der Massstab oder engine/spanne.py auf dem
    Server, fehlt das Feld, und der Tagesstand rechnet wie zuvor.
    """
    eta = (weltmodell.get("spanne_massstab") or {}).get("je_horizont")
    if not eta:
        return None
    try:
        from . import spanne as sp
    except ImportError:
        return None
    aus = {}
    for h, p in p_tag.items():
        if h in eta:
            r = sp.spanne_prozent(p, eta[h])
            aus[h] = [r["von"], r["bis"]]
    return aus or None


def _stufe(aid: str, wert, st: list | None) -> int | None:
    """Status oder Stufe als Stufe: ohne Stufen 0 oder 1, mit Stufen 0 bis len(st)."""
    if wert is None:
        return None
    if not st:
        return int(bool(wert))
    k = int(wert)
    if not 0 <= k <= len(st):
        raise ValueError(f"{aid}: Stufe {wert} gibt es nicht (0 bis {len(st)})")
    return k


def main(argv: list | None = None) -> int:
    p = argparse.ArgumentParser(description="Tagesstand der Weltlage rechnen.")
    p.add_argument("--modell", help="weltmodell.json (public export); default: model/world_model.de.json")
    p.add_argument("--wissensstand", required=True, help="wissensstand.json des Zukunftsradars")
    p.add_argument("--ziel", required=True, help="wohin weltlage.json geschrieben wird")
    args = p.parse_args(argv)

    if args.modell:
        weltmodell = json.loads(Path(args.modell).read_text(encoding="utf-8"))
    else:
        from . import io
        weltmodell = io.load_world_model()
    wissensstand = json.loads(Path(args.wissensstand).read_text(encoding="utf-8"))

    lage = tagesstand(weltmodell, wissensstand)
    ziel = Path(args.ziel)
    zwischen = ziel.with_suffix(".neu")
    zwischen.write_text(json.dumps(lage, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    zwischen.replace(ziel)

    gewechselt = [a for a in lage["anzeichen"] if a.get("wechsel")]
    print(f"  Weltlage: Basis v{lage['basis']['version']} vom {lage['basis']['stand']}, "
          f"{len(gewechselt)} Anzeichen gewechselt, {len(lage['luecken'])} ohne Daten")
    for a in gewechselt:
        print(f"    {a['id']} {a['wechsel']}: {a['text']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
