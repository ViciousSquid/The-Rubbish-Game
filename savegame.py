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

F5 quick-saves, F9 quick-loads (see main.py); the Data window has buttons too.
"""

import os
import pickle

from ambient import AmbientState

SNAPSHOT_VERSION = 2
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
        with open(path, "wb") as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
        return True, f"Saved: {os.path.basename(path)}"
    except Exception as e:
        return False, f"Save failed: {e}"
    finally:
        fleet.game = keep_game              # always reattach the live back-ref


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
        # to rebuild its road graph against the loaded city.
        game.ambient = AmbientState()
        game.fleet._roads_built_for = None

        # Reset transient UI so nothing dangles against the old objects.
        game.ui.windows.clear()
        game.ui._win_drag = None
        game.clear_selection()
    except Exception as e:
        return False, f"Load failed (corrupt save?): {e}"

    stale = "" if ver == SNAPSHOT_VERSION else " (older format)"
    return True, f"Loaded: {os.path.basename(path)}{stale}"
