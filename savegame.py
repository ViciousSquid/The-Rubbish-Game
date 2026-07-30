"""
savegame.py
===========

Full game-state save / load.

The sim state that matters lives in a handful of pure-Python objects
(``city``, ``fleet``, ``economy``, ``waste``) plus a little loose state on the
game (camera, speed). None of those hold pygame surfaces/fonts, so they pickle
cleanly -- the renderer, UI and ambient layer are *presentation* and are simply
kept / rebuilt on load rather than serialised.

Two wrinkles the loader handles:

  * ``fleet.game`` is a back-reference to the game object (which *does* hold a
    pygame Surface). It's detached to ``None`` during pickling and restored
    afterwards, so we never try to serialise the display.

  * ``game.camera`` is a dict the Renderer captured *by reference* at
    construction. On load we mutate that same dict in place rather than
    rebinding it, otherwise the camera and the renderer would drift apart.

Robustness:

  * Saves are written atomically (tmp file + os.replace) so a crash or power
    cut mid-save can never corrupt an existing save -- F5 is exactly the key
    people hammer right before things go wrong.

  * Because whole live objects are pickled, adding an attribute to Economy /
    FleetManager / Order between releases would otherwise make old saves
    explode with AttributeError mid-frame. ``_migrate`` runs after unpickling:
    versioned MIGRATIONS convert old semantics forward, and ``_backfill``
    defensively fills in any attributes added since the save was written.
    When you add a new attribute to a pickled class, add a matching default
    to ``_backfill`` (and a MIGRATIONS step if the *meaning* of old data
    changed).

F5 quick-saves, F9 quick-loads (see main.py); the Data window has buttons too.
"""

import os
import pickle

from ambient import AmbientState

SNAPSHOT_VERSION = 3
DEFAULT_NAME = "BoroughWaste_Save.sav"


# ---------------------------------------------------------------------------
#  File dialog (mirrors xmlio's approach; falls back to a fixed path)
# ---------------------------------------------------------------------------

def _default_path():
    return os.path.join(os.getcwd(), DEFAULT_NAME)


def _file_dialog(save, default_name=DEFAULT_NAME):
    """Native open/save dialog via tkinter. Returns a path, None (cancelled),
    or the sentinel 'NO_TK' when tkinter isn't available."""
    try:
        import tkinter
        from tkinter import filedialog
    except Exception:
        return "NO_TK"
    try:
        root = tkinter.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        opts = dict(
            filetypes=[("Borough save", "*.sav"), ("All files", "*.*")],
        )
        if save:
            path = filedialog.asksaveasfilename(
                defaultextension=".sav", initialfile=default_name,
                title="Save borough", **opts)
        else:
            path = filedialog.askopenfilename(title="Load borough", **opts)
        root.destroy()
        return path or None
    except Exception:
        return "NO_TK"


# ---------------------------------------------------------------------------
#  Save
# ---------------------------------------------------------------------------

def save_game(game, path=None):
    """Serialise the borough to `path` (or a chosen/one via dialog).
    Returns (ok, message)."""
    if path is None:
        path = _file_dialog(save=True)
        if path == "NO_TK":
            path = _default_path()          # headless / no-tk fallback
        elif path is None:
            return False, "Save cancelled."

    fleet = game.fleet
    keep_game = fleet.game
    fleet.game = None                       # don't drag the display into pickle
    tmp = path + ".tmp"
    try:
        data = {
            "version": SNAPSHOT_VERSION,
            "city": game.city,
            "fleet": fleet,
            "economy": game.economy,
            "waste": game.waste,
            "camera": dict(game.camera),
            "speed": game.speed,
            "show_areas": game.show_areas,
        }
        # Atomic write: dump to a sibling tmp file, then rename over the
        # target. os.replace is atomic on the same filesystem, so an existing
        # save can never be left half-written by a crash mid-dump.
        with open(tmp, "wb") as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, path)
        return True, f"Saved: {os.path.basename(path)}"
    except Exception as e:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        return False, f"Save failed: {e}"
    finally:
        fleet.game = keep_game              # always reattach the live back-ref


# ---------------------------------------------------------------------------
#  Migration -- old saves forward to the current snapshot version
# ---------------------------------------------------------------------------

def _ensure(obj, name, factory):
    """setattr(obj, name, factory()) if the attribute is missing."""
    if obj is not None and not hasattr(obj, name):
        setattr(obj, name, factory())


def _migrate_v2_to_v3(data):
    """v2 -> v3: procurement event delays used to be baked into
    Order.arrival_day at order time; they are now applied only when the event
    reveals itself (Order.trigger_event_if_due). Convert in-flight orders:
    strip the pre-applied delay back off so arrival_day is the quoted date,
    and record quoted_arrival."""
    fleet = data.get("fleet")
    for o in (getattr(fleet, "orders", None) or []):
        if hasattr(o, "quoted_arrival"):
            continue
        delay = getattr(o, "event_delay_days", 0) or 0
        if (delay and getattr(o, "pending_event", None)
                and not getattr(o, "event_triggered", False)):
            o.arrival_day -= delay
        o.quoted_arrival = o.arrival_day


# Each entry migrates FROM that version to the next. Applied in order.
MIGRATIONS = {
    2: _migrate_v2_to_v3,
}


def _backfill(data):
    """Fill in attributes added to pickled classes since the save was written.
    Runs for every load regardless of version -- cheap and defensive."""
    fleet = data.get("fleet")
    _ensure(fleet, "_dist_fields", dict)


def _migrate(data):
    """Bring an unpickled save dict up to SNAPSHOT_VERSION in place."""
    ver = data.get("version") or 1
    while ver < SNAPSHOT_VERSION:
        step = MIGRATIONS.get(ver)
        if step:
            step(data)
        ver += 1
    _backfill(data)
    data["version"] = SNAPSHOT_VERSION
    return data


# ---------------------------------------------------------------------------
#  Load
# ---------------------------------------------------------------------------

def load_game(game, path=None):
    """Restore the borough from `path` (or a chosen one via dialog) into the
    running `game`. Returns (ok, message)."""
    if path is None:
        path = _file_dialog(save=False)
        if path == "NO_TK":
            path = _default_path()
        elif path is None:
            return False, "Load cancelled."

    if not os.path.exists(path):
        return False, f"No save found: {os.path.basename(path)}"

    try:
        with open(path, "rb") as f:
            data = pickle.load(f)
    except Exception as e:
        return False, f"Load failed: {e}"

    if not isinstance(data, dict) or "city" not in data:
        return False, "Not a valid borough save."
    ver = data.get("version")

    try:
        _migrate(data)

        game.city = data["city"]
        game.fleet = data["fleet"]
        game.fleet.game = game                       # restore back-reference
        game.economy = data["economy"]
        game.waste = data["waste"]

        # Mutate the existing camera dict in place -- the renderer holds it by
        # reference; rebinding would desync it.
        game.camera.clear()
        game.camera.update(data.get("camera", {"x": 0, "y": 0, "zoom": 1}))
        game.speed = data.get("speed", 1)
        game.show_areas = data.get("show_areas", True)

        # Presentation: ambient is cosmetic, so start it fresh; force the fleet
        # to rebuild its road graph and route caches against the loaded city.
        game.ambient = AmbientState()
        game.fleet._roads_built_for = None
        game.fleet._dist_fields = {}

        # Reset transient UI so nothing dangles against the old objects.
        game.ui.windows.clear()
        game.ui._win_drag = None
        game.clear_selection()
    except Exception as e:
        return False, f"Load failed (corrupt save?): {e}"

    stale = "" if ver == SNAPSHOT_VERSION else " (older format)"
    return True, f"Loaded: {os.path.basename(path)}{stale}"
