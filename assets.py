"""Asset path resolution.

All bundled assets (fonts, images, icons) live in an ``_internal`` folder.
This mirrors PyInstaller 6+ one-folder layout, so the same call works in
development and in a frozen build:

    from assets import asset_path
    pygame.image.load(asset_path("truck.png"))
"""

import os
import sys


def asset_path(filename):
    """Return an absolute path to a bundled asset in the ``_internal`` folder.

    - Frozen (PyInstaller): sys._MEIPASS already points at the ``_internal``
      dir, so the file sits directly inside it.
    - Development: assets live in ``_internal`` next to the source tree.
    """
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        return os.path.join(base, filename)

    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "_internal", filename)
