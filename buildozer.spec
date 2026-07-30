[app]

# ── Identity ──────────────────────────────────────────────────────────────
title = The Rubbish Game
package.name = rubbishgame
package.domain = uk.viciousquid
version = 1.0

# ── Sources ───────────────────────────────────────────────────────────────
# Package the whole source tree. main.py is the entry point p4a looks for.
source.dir = .
source.include_exts = py,png,jpg,jpeg,ttf,ico,txt,md
# Bundle the _internal assets folder (fonts, truck sprite, icon) so
# assets.asset_path() resolves at runtime on the device.
source.include_patterns = _internal/*
# Keep build/tooling files out of the APK.
source.exclude_dirs = bin, .buildozer, .git, .github, __pycache__

# ── Requirements ──────────────────────────────────────────────────────────
# Only pygame is needed. Pillow and pyexcel-ods are desktop-only extras that
# the game degrades gracefully without (truck sprite falls back to pygame's
# PNG loader; spreadsheet import/export and native file dialogs are disabled).
requirements = python3,pygame

# ── Display ───────────────────────────────────────────────────────────────
orientation = landscape
fullscreen = 1
# Menu/backdrop base colour, shown behind the splash while Python starts up.
android.presplash_color = #16181e

# ── Android build ─────────────────────────────────────────────────────────
android.api = 34
android.minapi = 24
android.ndk_api = 24
android.archs = arm64-v8a, armeabi-v7a
android.allow_backup = True

# SDL2 bootstrap is what gives pygame a window and translates touches into
# mouse events; it's selected automatically for a pygame requirement, but we
# pin it here so the build is explicit and reproducible.
p4a.bootstrap = sdl2
p4a.branch = v2024.01.21

# Pin python-for-android instead of tracking its master branch. Current
# master hardcodes CPython 3.14.2 for the on-device Python while still
# building its bundled pygame recipe at 2.1.0, and that pygame release
# predates Python 3.11's removal of the private `longintrepr.h` header, so
# the build fails with "fatal error: 'longintrepr.h' file not found" while
# compiling pygame's _sdl2 module. v2024.01.21 pairs Python 3.11.5 with the
# same pygame 2.1.0 recipe, a combination that builds cleanly.
p4a.branch = v2024.01.21


[buildozer]

log_level = 2
warn_on_root = 1
