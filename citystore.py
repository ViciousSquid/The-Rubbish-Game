"""Persisted city maps.

Edited cities are saved as JSON in a writable ``cities`` folder next to the
game (or next to the executable in a frozen build) so new games can be started
in them. This is intentionally separate from the runtime savegame format — it
stores only the map geometry via CityGenerator.to_state()/from_state().
"""

import os
import re
import sys
import json
import time

from city import CityGenerator


def cities_dir():
    """Return (creating if needed) the writable folder holding saved cities."""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    d = os.path.join(base, "cities")
    os.makedirs(d, exist_ok=True)
    return d


def sanitize_name(name):
    """Reduce a user-typed name to a safe file stem."""
    name = re.sub(r"[^A-Za-z0-9 _-]", "", (name or "")).strip()
    return name[:40] or "city"


def save_city(city, name):
    """Write `city` to cities/<name>.json. Returns (ok, message)."""
    try:
        stem = sanitize_name(name)
        path = os.path.join(cities_dir(), stem + ".json")
        state = city.to_state()
        state["_name"] = stem
        state["_saved"] = time.time()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f)
        return True, f"Saved city '{stem}'."
    except Exception as e:                     # pragma: no cover - IO guard
        return False, f"Save failed: {e}"


def list_cities():
    """Return saved cities as [{'name', 'path', 'mtime'}], newest first."""
    out = []
    try:
        d = cities_dir()
        for fn in os.listdir(d):
            if not fn.endswith(".json"):
                continue
            path = os.path.join(d, fn)
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                mtime = 0
            out.append({"name": fn[:-5], "path": path, "mtime": mtime})
    except Exception:                          # pragma: no cover - IO guard
        return []
    out.sort(key=lambda e: e["mtime"], reverse=True)
    return out


def load_city(path):
    """Load a saved city file into a fresh CityGenerator. Raises on failure."""
    with open(path, "r", encoding="utf-8") as f:
        state = json.load(f)
    return CityGenerator.from_state(state)
