# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for The Rubbish Game.

Produces a one-folder desktop build that works identically on Windows, macOS
and Linux. All bundled assets in ``_internal`` are copied to the root of the
frozen bundle (``sys._MEIPASS``), which is exactly where ``assets.asset_path``
looks for them when ``sys.frozen`` is set.

Build with:

    pyinstaller rubbishgame.spec
"""

import os
import sys

from PyInstaller.utils.hooks import collect_all

APP_NAME = "TheRubbishGame"

# Copy every bundled asset (fonts, images, icons) to the bundle root so that
# assets.asset_path() -> os.path.join(sys._MEIPASS, filename) resolves.
_internal_datas = [
    (os.path.join("_internal", f), ".")
    for f in os.listdir("_internal")
    if os.path.isfile(os.path.join("_internal", f))
]

# pyexcel-ods (used for spreadsheet import/export) relies on a plugin system
# that PyInstaller cannot discover automatically, so pull in everything.
datas, binaries, hiddenimports = [], [], []
for pkg in ("pyexcel_ods", "pyexcel_io", "pyexcel", "odf", "lml"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

datas += _internal_datas

# Platform-specific application icon.
if sys.platform.startswith("win"):
    app_icon = os.path.join("_internal", "icon.ico")
elif sys.platform == "darwin":
    app_icon = os.path.join("_internal", "icon.png")
else:
    app_icon = None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=app_icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)

# macOS: also wrap the one-folder build into a .app bundle.
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=APP_NAME + ".app",
        icon=app_icon,
        bundle_identifier="uk.viciousquid.rubbishgame",
    )
