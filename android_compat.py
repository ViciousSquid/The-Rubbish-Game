"""Android platform shim for The Rubbish Game.

The game is a desktop pygame title designed around a 1280x720 mouse-and-keyboard
UI.  On Android we want the exact same code to run, so instead of reworking the
whole interface we sit a thin adapter between the game and the device:

  * The real display is opened fullscreen at the phone's native resolution.
  * The game renders, exactly as on desktop, into a smaller *logical* surface
    sized to a fixed design height.  Because the design height is smaller than a
    modern phone's pixel height, the whole UI is effectively magnified when we
    scale the logical surface up to fill the screen -- so panels stay legible and
    toolbar buttons stay large enough to tap.
  * Finger taps and drags arrive as ordinary mouse events (SDL2 emulates them),
    which already drive selection, panning and the toolbar.  We only translate
    their coordinates from device space back into logical space.
  * Two-finger pinch has no desktop equivalent, so we detect it from the raw
    finger events and synthesise mouse-wheel events, which the game already maps
    to camera zoom.

On desktop ``setup()`` returns ``None`` and nothing here is used, so importing
this module is harmless everywhere.
"""

import os

import pygame


def _detect_android():
    # python-for-android sets ANDROID_ARGUMENT for the app; ANDROID_APP_PATH /
    # ANDROID_PRIVATE are also present in the packaged environment.
    return (
        "ANDROID_ARGUMENT" in os.environ
        or "ANDROID_APP_PATH" in os.environ
        or "ANDROID_PRIVATE" in os.environ
    )


IS_ANDROID = _detect_android()

# Logical design height.  Smaller values magnify the UI more (bigger touch
# targets) at the cost of showing less of the map.  720 matches the desktop
# baseline; 680 was too close to it to read as scaled up at all -- on a
# typical 1080px-tall landscape phone that's only ~1.6x, well under
# Android's 48dp minimum touch target once real screen density is factored
# in. 480 gives ~2.25x on a 1080px-tall phone and ~3x on a 1440px one.
LOGICAL_H = 480

# Pinch sensitivity: how far the two fingers must spread/close (as a ratio of the
# last measured distance) before we emit one zoom step.
_PINCH_IN = 1.06
_PINCH_OUT = 0.94


class AndroidPlatform:
    """Owns the real display and the scaled logical render surface."""

    def __init__(self):
        # Open the real display fullscreen at the device's native resolution.
        pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        self.real = pygame.display.get_surface()
        self.real_w, self.real_h = self.real.get_size()

        # Uniform scale keeps the aspect ratio, so the scaled logical surface
        # fills the screen exactly with no letterboxing or distortion.
        self.scale = self.real_h / float(LOGICAL_H)
        self.logical_w = max(1, round(self.real_w / self.scale))
        self.logical_h = LOGICAL_H
        self.logical = pygame.Surface((self.logical_w, self.logical_h)).convert()

        # Active touch points, keyed by finger id -> (norm_x, norm_y).
        self._fingers = {}
        self._pinch_dist = None

    # ---------------------------------------------------------------- present
    def present(self):
        """Scale the logical surface up onto the real display and flip."""
        pygame.transform.smoothscale(
            self.logical, (self.real_w, self.real_h), self.real
        )
        pygame.display.flip()

    # ------------------------------------------------------------ coordinates
    def _to_logical(self, pos):
        return (int(pos[0] / self.scale), int(pos[1] / self.scale))

    @property
    def _pinching(self):
        return len(self._fingers) >= 2

    # --------------------------------------------------------------- events
    def process(self, event):
        """Translate one raw event into zero or more game-space events.

        Returns a list because a single finger gesture can produce several
        synthetic wheel events (or none).
        """
        t = event.type

        if t in (pygame.FINGERDOWN, pygame.FINGERMOTION, pygame.FINGERUP):
            return self._handle_finger(event)

        # While two fingers are down we're pinching: drop the mouse events that
        # SDL2 synthesises from the first finger so the map doesn't pan/select
        # underneath the zoom gesture.
        if self._pinching and t in (
            pygame.MOUSEMOTION,
            pygame.MOUSEBUTTONDOWN,
            pygame.MOUSEBUTTONUP,
        ):
            return []

        if t == pygame.MOUSEMOTION:
            rel = event.rel
            new = pygame.event.Event(
                t,
                {
                    **event.dict,
                    "pos": self._to_logical(event.pos),
                    "rel": (
                        int(round(rel[0] / self.scale)),
                        int(round(rel[1] / self.scale)),
                    ),
                },
            )
            return [new]

        if t in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            new = pygame.event.Event(
                t, {**event.dict, "pos": self._to_logical(event.pos)}
            )
            return [new]

        # Keyboard / quit / everything else passes through untouched.
        return [event]

    # --------------------------------------------------------- finger helpers
    def _finger_px(self, norm):
        return (norm[0] * self.real_w, norm[1] * self.real_h)

    def _handle_finger(self, event):
        fid = getattr(event, "finger_id", getattr(event, "finger", 0))

        if event.type == pygame.FINGERUP:
            self._fingers.pop(fid, None)
            if not self._pinching:
                self._pinch_dist = None
            return []

        self._fingers[fid] = (event.x, event.y)

        if not self._pinching:
            self._pinch_dist = None
            return []

        # Distance between the two most recent fingers, in device pixels.
        (a, b) = list(self._fingers.values())[:2]
        ax, ay = self._finger_px(a)
        bx, by = self._finger_px(b)
        dist = ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5
        mid = self._to_logical(((ax + bx) / 2, (ay + by) / 2))

        if self._pinch_dist is None or dist <= 0:
            self._pinch_dist = dist
            return []

        ratio = dist / self._pinch_dist
        if ratio >= _PINCH_IN:
            self._pinch_dist = dist
            return [pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 4, "pos": mid})]
        if ratio <= _PINCH_OUT:
            self._pinch_dist = dist
            return [pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 5, "pos": mid})]
        return []


def setup():
    """Return an :class:`AndroidPlatform` on Android, else ``None``."""
    if not IS_ANDROID:
        return None
    return AndroidPlatform()
