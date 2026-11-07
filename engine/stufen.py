"""Groessenstufen je Anzeichen (Spezifikation 7d): Vorschlag hinter einem Schalter.

Heute kennt ein Zahlen-Anzeichen nur "gilt" und "gilt nicht": Brent 120 $ und
140 $ sind fuer A12 dasselbe. Eine Stufe ist eine Regel mit eigener Staerke;
die Stufe eines Anzeichens ist die hoechste, deren Regel gilt (0: keine).

Wechselt die Stufe von i nach j, entsteht ein Signal mit

    staerke = |sigma_j - sigma_i|,  Richtung aus 'wirkung', wenn sigma_j > sigma_i,
                                     sonst die Gegenrichtung   (sigma_0 = 0).

Der Log-Likelihood-Quotient ist linear in der Staerke (bayes): Das Signal
verschiebt so, wie wenn das Basismodell auf Stufe i eingepreist waere und
heute Stufe j gilt. Stufe 1 ist die Regel des Anzeichens mit seiner Staerke;
mit nur dieser Stufe rechnet alles wie heute.

Die Stufen stehen in data/entwurf/anzeichen_stufen.json. Solange an: false
oder vorschlag: true gilt, wird hier nur geprobt (probe). Ist der Schalter an
und die Stufen entschieden, nimmt export.weltmodell sie als "stufen" in das
oeffentliche Weltmodell auf, und der Tagesstand rechnet mit ihnen. Laeuft
deshalb auf dem Server: nur Standardbibliothek, tagesstand erst in den
Funktionen (tagesstand importiert stufen).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

PFAD = Path(__file__).resolve().parent.parent / "data" / "entwurf" / "anzeichen_stufen.json"


def _ts():
    from . import tagesstand
    return tagesstand


def lade(pfad: Path | None = None) -> dict:
    p = Path(pfad or PFAD)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def wirksam(cfg: dict) -> bool:
    """Entschieden und eingeschaltet: an und kein Vorschlag mehr."""
    return bool(cfg.get("an")) and not cfg.get("vorschlag")


def oeffentlich(anzeichen: list, cfg: dict) -> dict | None:
    """{id: [{regel, staerke}]} fuer das Weltmodell, nur wenn wirksam; geprueft wie in pruefe()."""
    if not wirksam(cfg):
        return None
    return {aid: [{"regel": s["regel"], "staerke": s["staerke"]} for s in st]
            for aid, st in pruefe(anzeichen, cfg).items()} or None


def _schwelle(regel: str) -> tuple:
    t = regel.split()
    if t[0] not in ("mittel", "alle") or len(t) != 4 or t[2] not in (">", "<"):
        raise ValueError(f"Stufen gibt es nur fuer 'mittel'/'alle n > x' oder '< x', nicht: {regel}")
    return t[0], int(t[1]), t[2], float(t[3])


def pruefe(anzeichen: list, cfg: dict) -> dict:
    """{id: stufen} nach Pruefung; ValueError bei allem, was nicht zur Regel passt.

    Stufe 1 = Regel und Staerke des Anzeichens; alle Stufen dieselbe Art,
    dasselbe n und dieselbe Richtung, Schwellen streng geordnet (geschachtelt:
    gilt Stufe k, gilt auch k - 1), Staerken streng steigend, hoechstens 5.
    """
    nach_id = {a["id"]: a for a in anzeichen}
    aus = {}
    for aid, stufen in (cfg.get("stufen") or {}).items():
        a = nach_id.get(aid)
        if not a or a["art"] != "zahl" or not a.get("wirkung") or a.get("reihe2"):
            raise ValueError(f"{aid}: Stufen nur fuer Zahlen-Anzeichen mit Wirkung und einer Reihe")
        if not stufen or stufen[0]["regel"] != a["regel"] or stufen[0]["staerke"] != a["wirkung"]["staerke"]:
            raise ValueError(f"{aid}: Stufe 1 muss Regel und Staerke des Anzeichens sein")
        teile = [_schwelle(s["regel"]) for s in stufen]
        if len({t[:3] for t in teile}) != 1:
            raise ValueError(f"{aid}: alle Stufen brauchen dieselbe Art, dasselbe n und dieselbe Richtung")
        x = [t[3] for t in teile]
        geordnet = all(b > c for b, c in zip(x[1:], x)) if teile[0][2] == ">" else all(b < c for b, c in zip(x[1:], x))
        st = [s["staerke"] for s in stufen]
        if not geordnet or not all(b > c for b, c in zip(st[1:], st)) or st[-1] > 5:
            raise ValueError(f"{aid}: Schwellen muessen geschachtelt, Staerken steigend und hoechstens 5 sein")
        aus[aid] = stufen
    return aus


def stufe(stufen: list, werte: list) -> int | None:
    """Hoechste Stufe, deren Regel gilt; 0 keine; None, wenn die Werte nicht reichen."""
    ts = _ts()
    if ts.gilt(stufen[0]["regel"], werte) is None:
        return None
    k = 0
    for i, s in enumerate(stufen, 1):
        if ts.gilt(s["regel"], werte):
            k = i
    return k


def stufe_fuer_wert(stufen: list, wert: float) -> int:
    """Stufe, wenn die Reihe lange genug auf diesem Wert steht (fuer eine Was-waere-wenn-Frage)."""
    n = max(_schwelle(s["regel"])[1] for s in stufen)
    return stufe(stufen, [("", float(wert))] * n)


def signal(a: dict, stufen: list, vorher: int, nachher: int, heute: datetime) -> dict | None:
    """Das Signal beim Wechsel von Stufe vorher nach nachher; None ohne Wechsel."""
    def sigma(k):
        return 0 if k == 0 else stufen[k - 1]["staerke"]
    d = sigma(nachher) - sigma(vorher)
    if d == 0:
        return None
    s = _ts().anzeichen_signal(a, d > 0, heute, staerke=abs(d))
    s["titel"] = f"Anzeichen {a['id']} Stufe {vorher} -> {nachher}: {a['text']}"
    s["stufe"] = {"von": vorher, "nach": nachher}
    return s


def probe(weltmodell: dict, wissensstand: dict, cfg: dict, heute: datetime | None = None,
          vorschlaege: bool = False) -> dict:
    """Tagesstand mit Stufen, vorlaeufig: Signale und Wahrscheinlichkeiten, sonst nichts.

    Anzeichen ohne Stufen rechnen wie im Tagesstand. Solange cfg an: false
    oder vorschlag: true hat, nur mit vorschlaege=True.
    """
    ts = _ts()
    if not vorschlaege and not wirksam(cfg):
        raise ValueError("Die Groessenstufen sind ein Vorschlag (an: false); fuer eine Probe vorschlaege=True setzen")
    heute = heute or datetime.now(timezone.utc)
    stufen_je = pruefe(weltmodell["anzeichen"], cfg)
    reihen = ts.reihen_aus(wissensstand)
    basis_monat = weltmodell["meta"]["stand"][:7]
    signale = []
    for a in weltmodell["anzeichen"]:
        if a["art"] != "zahl" or not a.get("wirkung"):
            continue
        if a["id"] in stufen_je:
            st = stufen_je[a["id"]]
            alle = reihen.get(a["reihe"], [])
            vorher = stufe(st, [(t, w) for t, w in alle if t[:7] <= basis_monat])
            nachher = stufe(st, alle)
            s = signal(a, st, vorher, nachher, heute) if vorher is not None and nachher is not None else None
        else:
            vorher, _ = ts.pruefe(a, reihen, basis_monat)
            nachher, _ = ts.pruefe(a, reihen)
            s = (ts.anzeichen_signal(a, nachher, heute)
                 if vorher is not None and nachher is not None and vorher != nachher else None)
        if s:
            signale.append(s)
    r = ts.rechne(weltmodell, signale)
    return {"vorlaeufig": True, "signale": signale, "p_tag": r["posterior"], "delta": r["diff"]}
