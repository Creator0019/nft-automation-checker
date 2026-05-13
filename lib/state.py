"""Tiny JSON state store. Each script gets its own file under state/."""
import json
from pathlib import Path
from .config import STATE_DIR


def load(name: str) -> dict:
    path = STATE_DIR / f"{name}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


def save(name: str, data: dict) -> None:
    path = STATE_DIR / f"{name}.json"
    path.write_text(json.dumps(data, indent=2, sort_keys=True))
