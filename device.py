"""Central device + DPI awareness for The Rubbish Game.

The desktop build renders 1:1 into its window and none of this matters. On a
phone, though, raw pixels lie: two handsets can share a 1080-tall panel while
one is a 4" pocket phone and the other a 7" tablet, so a control that is "56 px"
is a fat thumb target on one and a fingernail sliver on the other.

This module gives the rest of the game a single source of truth for the display
in *physical* terms:

  * ``dpi`` / ``density``   — the real pixel density, read from Android's
    ``DisplayMetrics`` where we can, estimated otherwise.
  * ``logical_height()``    — how tall the logical render surface should be so
    that one logical pixel maps to a fixed physical size (see ``DESIGN_DPI``),
    which is what makes the whole UI *DPI aware* rather than merely
    resolution-scaled.
  * ``dp()``                — density-independent pixels → logical canvas
    pixels, so touch targets can be specified in Android's ``dp`` units and come
    out the same real-world size on every device.

Everything degrades gracefully: if the density can't be read we fall back to a
sane phone default, and desktop stays exactly as it was.

Testing on a desktop: set ``RUBBISH_MOBILE=1`` to force the mobile layout, and
optionally ``RUBBISH_DPI=440`` to pretend the window has that density, so the
whole DPI-aware path can be exercised without a handset.
"""

import os


# ── Platform detection ───────────────────────────────────────────────────────
def _detect_android():
    # python-for-android sets these in the packaged app environment.
    return (
        "ANDROID_ARGUMENT" in os.environ
        or "ANDROID_APP_PATH" in os.environ
        or "ANDROID_PRIVATE" in os.environ
    )


IS_ANDROID = _detect_android()


def _env_flag(name):
    return os.environ.get(name, "").strip().lower() not in ("", "0", "false", "no")


def _env_float(name):
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return None


# ── Design constants ─────────────────────────────────────────────────────────
# The logical canvas is treated as a display of this density: one logical pixel
# is 1/DESIGN_DPI of a physical inch once the surface is scaled to the device.
# 135 keeps a 48-dp control (Android's minimum touch target) at ~40 logical px
# while still showing a useful slice of the isometric map.
DESIGN_DPI = 135.0

# Android's baseline density (mdpi): density == densityDpi / 160.
BASE_DPI = 160.0

# Clamp the computed logical height so a freak density reading can't leave the
# canvas unusably tiny (everything huge, no map) or so large the UI turns to
# fingernail-sized specks.
MIN_LOGICAL_H = 300
MAX_LOGICAL_H = 900

# Density assumed for a phone when the real value can't be read. A mid-range
# ~xxhdpi handset; better to over-magnify slightly than to ship specks.
FALLBACK_MOBILE_DPI = 420.0
DESKTOP_DPI = 96.0


def _query_android_dpi():
    """Read the display's ``densityDpi`` via pyjnius, or ``None`` if we can't.

    ``densityDpi`` is the bucketed density Android itself uses to define ``dp``,
    so it is exactly the number our dp-based sizing wants — and it is far more
    reliable across devices than the frequently-bogus ``xdpi``/``ydpi``.
    """
    try:
        from jnius import autoclass  # provided by pyjnius in the p4a build

        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        if activity is None:
            return None
        metrics = activity.getResources().getDisplayMetrics()
        dpi = float(metrics.densityDpi)
        if 60.0 <= dpi <= 900.0:
            return dpi
    except Exception:
        # No pyjnius, no activity, or a device that throws — fall back quietly.
        pass
    return None


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


class Metrics:
    """Immutable-ish snapshot of the display's physical characteristics."""

    def __init__(self):
        self.is_android = IS_ANDROID
        # Desktop can opt into the mobile layout for development/testing.
        self.simulated = _env_flag("RUBBISH_MOBILE")
        self.is_mobile = IS_ANDROID or self.simulated
        self.dpi = None
        self.source = "none"
        self._resolve_dpi()
        self.density = self.dpi / BASE_DPI

    def _resolve_dpi(self):
        override = _env_float("RUBBISH_DPI")
        if override:
            self.dpi, self.source = override, "env"
            return
        if IS_ANDROID:
            dpi = _query_android_dpi()
            if dpi:
                self.dpi, self.source = dpi, "android"
                return
            self.dpi, self.source = FALLBACK_MOBILE_DPI, "android-fallback"
            return
        if self.simulated:
            self.dpi, self.source = FALLBACK_MOBILE_DPI, "simulated"
            return
        self.dpi, self.source = DESKTOP_DPI, "desktop"

    # ------------------------------------------------------------------ sizing
    def logical_height(self, real_w, real_h):
        """Height for the logical render surface given the real display size.

        Desktop renders 1:1 (returns the real height). On mobile we pick a
        height so the surface, once scaled up to fill the screen, shows one
        logical pixel per 1/DESIGN_DPI inch — i.e. a physically consistent UI
        regardless of the panel's own density.
        """
        if not self.is_mobile:
            return int(real_h)
        # Physical size of the short (landscape height) edge, in inches.
        height_inches = real_h / float(self.dpi)
        logical = round(height_inches * DESIGN_DPI)
        return int(_clamp(logical, MIN_LOGICAL_H, MAX_LOGICAL_H))

    def dp(self, value):
        """Density-independent pixels → logical canvas pixels.

        1 dp == 1/160 inch; 1 logical px == 1/DESIGN_DPI inch; so one dp is
        ``DESIGN_DPI / 160`` logical pixels. Use this for touch-target sizing so
        controls come out the same real size on every device.
        """
        if not self.is_mobile:
            return value
        return value * (DESIGN_DPI / BASE_DPI)

    def font_scale(self):
        """Point-size multiplier for on-screen UI text.

        The DPI-aware canvas is already sized in physical terms, but a small
        extra bump renders glyphs a touch larger and crisper on a phone than a
        naive 1:1 mapping would.
        """
        return 1.2 if self.is_mobile else 1.0

    def describe(self):
        return (f"Metrics(mobile={self.is_mobile}, dpi={self.dpi:.0f}, "
                f"density={self.density:.2f}, source={self.source})")


_metrics = None


def metrics():
    """Return the process-wide :class:`Metrics`, building it once on first use."""
    global _metrics
    if _metrics is None:
        _metrics = Metrics()
    return _metrics


def reset():
    """Drop the cached metrics (tests that tweak the environment use this)."""
    global _metrics
    _metrics = None
