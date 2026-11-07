"""Loading the open world model (public edition).

In the private upstream repository the world model is built from data/ by
engine/export.py. In this open repository the public export itself is the
source of truth: model/world_model.de.json (German original, authoritative)
and model/world_model.en.json (English translation, identical numbers).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL_DE = ROOT / "model" / "world_model.de.json"
MODEL_EN = ROOT / "model" / "world_model.en.json"
RADAR_SNAPSHOT = ROOT / "radar" / "snapshot"


def load_json(path: Path | str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_world_model(lang: str = "de") -> dict:
    """lang='de' (original) or 'en' (translation)."""
    return load_json(MODEL_EN if lang == "en" else MODEL_DE)


def load_all():
    """Compatibility with the upstream signature (model, substitution, params).

    The public model carries its Bayes damping k under 'bayes'; substitution
    (segment data) is private upstream and therefore None here.
    """
    world = load_world_model()
    return world, None, {"bayes": dict(world["bayes"])}
