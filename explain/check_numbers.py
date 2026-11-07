"""Number check: every number in Claude's explanation must appear in the trace.

What it does
  1. Finds every number in every text field of the explanation (whole numbers, decimals, signs, %,
     decimal commas). Identifiers such as S04, A05, AS09, T8, OE1 are not numbers and are skipped.
     Dates (2026-10, 2026-11-07T11:16:17Z) are checked as whole dates.
  2. Builds the allowed set from every number in the trace (numeric values, numeric keys and numbers
     inside trace strings). Each allowed number remembers its path in the trace.
  3. Matches by exact value: "12" == 12.0, but "11.5" does not match 11.545.
     Status per number:  matched | matched_sign_dropped ("fell by 3.43" for -3.43)
                         | WRONG_SIGN ("+3.43" when only -3.43 exists) | NOT_IN_TRACE
  4. Scope check for each big_changes item: a number tied to a scenario must belong to THAT scenario
     (paths that name no scenario, such as k or an indicator's strength, are shared) -> WRONG_SCOPE.
  5. Direction check: rise/fall words in a big_changes item must agree with the sign of that change.
  6. Structure: every big change in the trace must be explained; a hypothetical trace needs a notice.
  7. Warnings (not failures): number words and implied amounts ("twice", "half", "doubled", ...).

Usage
  python check_numbers.py <trace.json> <explanation.json>     # explanation = Claude's JSON answer
  python check_numbers.py --self-test <trace.json>
Exit code 0 = passed, 1 = failed.
"""
from __future__ import annotations

import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

ID_RE = re.compile(r"\b[A-Z]{1,3}\d{1,2}\b")  # S04, A05, AS09, T8, OE1, G3, M2
DATE_RE = re.compile(r"\b\d{4}-\d{2}(?:-\d{2})?(?:T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?Z?)?")
NUM_RE = re.compile(r"(?<![0-9_.,])([+\-−]?)(\d+(?:[.,]\d+)?)(?![0-9])")
UP_RE = re.compile(r"\b(rise[sn]?|rose|rising|increase[sd]?|increasing|up|gain(?:s|ed)?|grow(?:s|n)?|grew|growing|"
                   r"higher|climb(?:s|ed)?|more likely)\b", re.I)
DOWN_RE = re.compile(r"\b(fall(?:s|en)?|fell|falling|decrease[sd]?|decreasing|drop(?:s|ped)?|down|lower|"
                     r"shrink(?:s)?|shrank|decline[sd]?|declining|lose[s]?|lost|less likely)\b", re.I)
QUANTITY_RE = re.compile(r"\b(zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|hundred|"
                         r"half|halve[sd]?|double[sd]?|doubling|twice|triple[sd]?|thrice|third|quarter|dozen|"
                         r"several|tenfold|fold)\b", re.I)


# --- parsing ----------------------------------------------------------------------

def _mask(text: str, regex: re.Pattern) -> str:
    return regex.sub(lambda m: " " * len(m.group(0)), text)


def _to_decimal(digits: str) -> Decimal | None:
    if "," in digits:
        head, tail = digits.split(",", 1)
        digits = head + tail if len(tail) == 3 else head + "." + tail  # 9,710 thousands; 6,53 decimal comma
    try:
        return Decimal(digits)
    except InvalidOperation:
        return None


def extract(text: str) -> tuple[list, list]:
    """(numbers, dates) found in text. numbers: [(raw, sign, Decimal, start)], dates: [(raw, start)]."""
    text = text or ""
    dates = [(m.group(0), m.start()) for m in DATE_RE.finditer(text)]
    clean = _mask(_mask(text, ID_RE), DATE_RE)
    nums = []
    for m in NUM_RE.finditer(clean):
        sign = {"": "", "+": "+", "-": "-", "−": "-"}[m.group(1)]
        val = _to_decimal(m.group(2))
        if val is not None:
            nums.append((m.group(0), sign, val, m.start()))
    return nums, dates


# --- allowed set -------------------------------------------------------------------

class Allowed:
    """Every number and date in the trace, with the trace paths where it occurs."""

    def __init__(self, trace: dict):
        self.values: dict[Decimal, list[tuple]] = {}
        self.dates: dict[str, list[tuple]] = {}
        self.scenarios = set((trace.get("scenarios") or {}).keys())
        self._walk(trace, ())

    def _add(self, v: Decimal, path: tuple):
        self.values.setdefault(v.normalize() if v != 0 else Decimal(0), []).append(path)

    def _walk(self, obj, path):
        if isinstance(obj, bool) or obj is None:
            return
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(k, str) and re.fullmatch(r"-?\d+(\.\d+)?", k):
                    self._add(Decimal(k), path + (k,))
                self._walk(v, path + (k,))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                self._walk(v, path + (i,))
        elif isinstance(obj, (int, float)):
            self._add(Decimal(repr(obj)), path)
        elif isinstance(obj, str):
            nums, dates = extract(obj)
            for raw, _ in dates:
                self.dates.setdefault(raw, []).append(path)
                self._add(Decimal(raw[:4]), path)  # the year of a date may be written alone
            for _, sign, v, _ in nums:
                self._add(-v if sign == "-" else v, path)

    def paths(self, v: Decimal) -> list:
        return self.values.get(v.normalize() if v != 0 else Decimal(0), [])

    def date_paths(self, raw: str) -> list:
        return [p for d, ps in self.dates.items() if d.startswith(raw) or raw.startswith(d) for p in ps]

    def in_scope(self, path: tuple, scenario: str) -> bool:
        named = {c for c in path if isinstance(c, str) and c in self.scenarios}
        return not named or scenario in named


# --- the check -----------------------------------------------------------------------

def _fields(expl: dict):
    """(field name, text, scope) for every text field of the explanation."""
    yield "hypothetical_notice", expl.get("hypothetical_notice") or "", None
    yield "what_is_happening", expl.get("what_is_happening") or "", None
    for i, item in enumerate(expl.get("big_changes") or []):
        yield f"big_changes[{i}].explanation", item.get("explanation") or "", item
    for i, u in enumerate(expl.get("uncertainties") or []):
        yield f"uncertainties[{i}]", u or "", None


def check(trace: dict, expl: dict) -> dict:
    al = Allowed(trace)
    numbers, failures, warnings = [], [], []
    for field, text, item in _fields(expl):
        scope = (item or {}).get("scenario_id")
        nums, dates = extract(text)
        for raw, start in dates:
            ps = al.date_paths(raw)
            status = "matched" if ps else "NOT_IN_TRACE"
            numbers.append({"field": field, "text": raw, "at": start, "kind": "date", "status": status,
                            "trace_paths": [_fmt(p) for p in ps[:3]]})
            if not ps:
                failures.append(f"{field}: date '{raw}' is not in the trace")
        for raw, sign, v, start in nums:
            signed = -v if sign == "-" else v
            exact, flipped = al.paths(signed), al.paths(-signed) if v != 0 else []
            if exact:
                status, ps = "matched", exact
            elif flipped and sign == "":
                status, ps = "matched_sign_dropped", flipped
            elif flipped:
                status, ps = "WRONG_SIGN", flipped
            else:
                status, ps = "NOT_IN_TRACE", []
            if scope and status in ("matched", "matched_sign_dropped"):
                scoped = [p for p in ps if al.in_scope(p, scope)]
                if not scoped:
                    status = "WRONG_SCOPE"
                ps = scoped or ps
            numbers.append({"field": field, "text": raw.strip(), "at": start, "kind": "number", "value": str(signed),
                            "status": status, "trace_paths": [_fmt(p) for p in ps[:3]]})
            if status == "NOT_IN_TRACE":
                failures.append(f"{field}: number '{raw.strip()}' is not in the trace")
            elif status == "WRONG_SIGN":
                failures.append(f"{field}: '{raw.strip()}' has the wrong sign (trace has {-signed})")
            elif status == "WRONG_SCOPE":
                failures.append(f"{field}: '{raw.strip()}' belongs to another scenario, not {scope}")
        for m in QUANTITY_RE.finditer(text):
            warnings.append(f"{field}: number/quantity word '{m.group(0)}' cannot be checked automatically")

    # direction and coverage of big changes
    big = trace.get("big_changes") or {}
    expected = {(h, s) for h, per in big.items() for s in per}
    got = []
    for i, item in enumerate(expl.get("big_changes") or []):
        h, s = item.get("horizon"), item.get("scenario_id")
        got.append((h, s))
        entry = (big.get(h) or {}).get(s)
        if entry is None:
            warnings.append(f"big_changes[{i}]: {s} {h} is not one of the trace's big changes")
            continue
        text = item.get("explanation") or ""
        up, down = bool(UP_RE.search(text)), bool(DOWN_RE.search(text))
        if entry["direction"] == "up" and down and not up or entry["direction"] == "down" and up and not down:
            failures.append(f"big_changes[{i}]: {s} {h} went {entry['direction']}, but the text only uses "
                            f"{'falling' if down else 'rising'} words")
        elif up and down:
            warnings.append(f"big_changes[{i}]: both rising and falling words; check that {s} {h} reads as "
                            f"'{entry['direction']}'")
        elif not up and not down:
            warnings.append(f"big_changes[{i}]: no rise/fall word found for {s} {h}")
    for h, s in sorted(expected - set(got)):
        failures.append(f"big change {s} {h} is in the trace but not explained")
    if len(got) != len(set(got)):
        warnings.append("some big changes are explained more than once")

    # hypothetical notice
    meta = trace.get("meta") or {}
    notice = (expl.get("hypothetical_notice") or "").strip()
    if meta.get("is_hypothetical") and "hypothetical" not in notice.lower():
        failures.append("the trace is a HYPOTHETICAL what-if, but hypothetical_notice does not say so")
    if not meta.get("is_hypothetical") and "hypothetical" in notice.lower():
        failures.append("the trace is real data, but the notice calls it hypothetical")

    counts = {}
    for n in numbers:
        counts[n["status"]] = counts.get(n["status"], 0) + 1
    return {"passed": not failures, "counts": counts, "failures": failures, "warnings": warnings, "numbers": numbers}


def _fmt(path: tuple) -> str:
    return "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in path).lstrip(".")


# --- self-tests (no API call) ----------------------------------------------------------

def _clean_explanation(trace: dict) -> dict:
    """An explanation written only with trace numbers, covering every big change."""
    meta, items = trace["meta"], []
    for h, per in (trace.get("big_changes") or {}).items():
        for s, e in per.items():
            verb = "rises" if e["direction"] == "up" else "falls"
            items.append({"scenario_id": s, "horizon": h,
                          "explanation": f"{e['name']} {verb} from {e['before']} to {e['after']} "
                                         f"({e['after_unrounded']} before rounding) in {h}."})
    return {"hypothetical_notice": f"This is a {meta['mode']}." if meta.get("is_hypothetical") else "",
            "what_is_happening": f"With k = {meta['k']} the model updates the horizons {', '.join(meta['horizons'])}.",
            "big_changes": items,
            "uncertainties": [f"Each scenario keeps at least {meta['probability_floor_percent']} percent."]}


def _unused_number(al: Allowed, start: str = "17.3") -> str:
    v = Decimal(start)
    while al.paths(v) or al.paths(-v):
        v += Decimal("0.1")
    return str(v)


def self_tests(trace: dict) -> list:
    al = Allowed(trace)
    big = [(h, s, e) for h, per in (trace.get("big_changes") or {}).items() for s, e in per.items()]
    res = []

    def run(name, expl, expect_pass, expect_status=None, expect_warning=None, expect_failure_text=None):
        r = check(trace, expl)
        ok = r["passed"] == expect_pass
        if expect_status:
            ok &= any(n["status"] == expect_status for n in r["numbers"])
        if expect_warning:
            ok &= any(expect_warning in w for w in r["warnings"])
        if expect_failure_text:
            ok &= any(expect_failure_text in f for f in r["failures"])
        res.append({"test": name, "ok": ok, "expected_pass": expect_pass, "passed": r["passed"],
                    "counts": r["counts"], "failures": r["failures"][:3], "warnings": r["warnings"][:3]})

    clean = _clean_explanation(trace)
    run("1 clean text using only trace numbers passes", clean, True)

    bad = json.loads(json.dumps(clean))
    invented = _unused_number(al)
    bad["what_is_happening"] += f" Oil-shock risk is now {invented}%."
    run(f"2 invented number {invented}% is flagged", bad, False, "NOT_IN_TRACE")

    ids = json.loads(json.dumps(clean))
    ids["what_is_happening"] = "S04, A05, AS09, T8 and OE1 are identifiers, not numbers."
    r = check(trace, ids)
    res.append({"test": "3 identifiers S04 A05 AS09 T8 OE1 are not counted as numbers",
                "ok": not any(n["field"] == "what_is_happening" for n in r["numbers"]),
                "expected_pass": True, "passed": r["passed"], "counts": r["counts"], "failures": [], "warnings": []})

    neg = next((e["change_unrounded"] for h, s, e in big if e["change_unrounded"] < 0
                and not al.paths(Decimal(repr(-e["change_unrounded"])))), None)
    if neg is not None:
        t = json.loads(json.dumps(clean))
        t["what_is_happening"] += f" One scenario fell by {-neg} points."
        run(f"4 'fell by {-neg}' for change {neg} is accepted as sign dropped", t, True, "matched_sign_dropped")
        t = json.loads(json.dumps(clean))
        t["what_is_happening"] += f" One scenario changed by +{-neg} points."
        run(f"5 '+{-neg}' when the trace has {neg} is flagged as wrong sign", t, False, "WRONG_SIGN")
    else:
        res.append({"test": "4/5 sign tests", "ok": True, "skipped": "no negative big change in this trace"})

    t = json.loads(json.dumps(clean))
    t["what_is_happening"] += " The shift roughly doubled."
    run("6 'doubled' gives a warning but does not fail", t, True, expect_warning="doubled")

    if len(big) >= 2:
        (h1, s1, e1) = big[0]
        other = next(((h, s, e) for h, s, e in big if s != s1), None)
        val = None
        if other:
            for key in ("after_unrounded", "change_unrounded"):
                cand = Decimal(repr(other[2][key]))
                if not any(al.in_scope(p, s1) for p in al.paths(cand)):
                    val = other[2][key]
                    break
        if val is not None:
            t = json.loads(json.dumps(clean))
            t["big_changes"][0]["explanation"] += f" It ends at {val}."
            run(f"7 value {val} of {other[1]} used inside the {s1} item is flagged as wrong scope", t, False,
                "WRONG_SCOPE")
        t = json.loads(json.dumps(clean))
        it = t["big_changes"][0]
        it["explanation"] = it["explanation"].replace("rises", "falls") if e1["direction"] == "up" \
            else it["explanation"].replace("falls", "rises")
        run(f"8 wrong direction word for {s1} {h1} is flagged", t, False,
            expect_failure_text="only uses")
        t = json.loads(json.dumps(clean))
        t["big_changes"] = t["big_changes"][1:]
        run(f"9 a missing big change ({s1} {h1}) is flagged", t, False, expect_failure_text="not explained")
    else:
        res.append({"test": "7-9 scope/direction/coverage tests", "ok": True, "skipped": "fewer than 2 big changes"})

    if trace["meta"].get("is_hypothetical"):
        t = json.loads(json.dumps(clean))
        t["hypothetical_notice"] = ""
        run("10 a hypothetical trace without the HYPOTHETICAL notice fails", t, False,
            expect_failure_text="HYPOTHETICAL")

    dump = {"hypothetical_notice": clean["hypothetical_notice"], "big_changes": clean["big_changes"],
            "what_is_happening": json.dumps(trace, ensure_ascii=False), "uncertainties": []}
    run("11 the trace's own text passes its own check", dump, True)

    if big:
        e = big[0][2]
        s = str(e["after_unrounded"])
        if "." in s:
            t = json.loads(json.dumps(clean))
            t["big_changes"][0]["explanation"] += f" (written with a decimal comma: {s.replace('.', ',')})"
            run(f"12 decimal comma {s.replace('.', ',')} matches {s}", t, True)
    return res


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if len(argv) == 2 and argv[0] == "--self-test":
        doc = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        res = self_tests(doc.get("trace", doc))
        for r in res:
            print(("PASS " if r["ok"] else "FAIL ") + r["test"] + (f"  (skipped: {r['skipped']})" if r.get("skipped") else ""))
        return 0 if all(r["ok"] for r in res) else 1
    if len(argv) != 2:
        print(__doc__)
        return 1
    doc = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    expl = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    r = check(doc.get("trace", doc), expl.get("explanation", expl))
    print(json.dumps({k: r[k] for k in ("passed", "counts", "failures", "warnings")}, indent=2, ensure_ascii=False))
    return 0 if r["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
