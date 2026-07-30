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

# App launcher icon. Without this p4a falls back to its own default (a Kivy
# logo). p4a copies whatever file this points to straight into
# res/mipmap/icon.png with no format conversion, so it must already be a
# real PNG -- icon.ico (a Windows .ico) doesn't work here even though pygame
# can load it at runtime for the desktop window icon.
icon.filename = _internal/icon.png

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

# Pin python-for-android instead of tracking its master branch. p4a's
# bundled pygame recipe is stuck at 2.1.0, and that pygame release's
# generated _sdl2 module still references the private CPython header
# `longintrepr.h`, which was removed starting with Python 3.11 (confirmed:
# pinning to Python 3.11.5 via v2024.01.21 still hits
# "fatal error: 'longintrepr.h' file not found"). v2023.09.16 targets
# Python 3.10.10 with the same pygame 2.1.0 recipe, the last combination
# where that header still exists and the build succeeds.
p4a.branch = v2023.09.16


[buildozer]

log_level = 2
warn_on_root = 1
