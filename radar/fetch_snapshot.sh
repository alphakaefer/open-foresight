#!/usr/bin/env bash
# Fetch the latest public radar snapshot from the live radar and strip news teaser texts.
# Usage: bash radar/fetch_snapshot.sh [base-url]
set -euo pipefail
BASE="${1:-https://zukunftsgut.org/radar}"
DIR="$(cd "$(dirname "$0")" && pwd)/snapshot"
mkdir -p "$DIR"
curl -fsS -m 60 -o "$DIR/weltlage.json" "$BASE/weltlage.json"
curl -fsS -m 120 -o "$DIR/wissensstand.full.json" "$BASE/wissensstand.json"
python3 - "$DIR" <<'PY'
import json, sys, pathlib
d = pathlib.Path(sys.argv[1])
ws = json.loads((d / "wissensstand.full.json").read_text(encoding="utf-8"))
for s in ws.get("signale", []):
    if "text" in s: s["text"] = ""   # news teasers: copyright of the publishers (field kept: the app schema requires it)
(d / "wissensstand.json").write_text(json.dumps(ws, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
(d / "wissensstand.full.json").unlink()
print(f"  radar snapshot {ws['stand']}: {len(ws.get('signale', []))} items, {len(ws.get('reihen', []))} series")
PY
