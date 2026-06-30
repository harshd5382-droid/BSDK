# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for daios-worker.exe bootstrapper."""

import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parents[1]
LAUNCHER_SRC = ROOT / "apps" / "launcher" / "src"

a = Analysis(
    [str(LAUNCHER_SRC / "daios_launcher" / "bootstrap.py")],
    pathex=[str(LAUNCHER_SRC)],
    binaries=[],
    datas=[],
    hiddenimports=[
        "daios_launcher.bootstrap",
        "daios_launcher.settings",
        "daios_launcher.update",
        "daios_launcher.autostart_windows",
        "daios_launcher.platform_utils",
        "daios_protocol",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="daios-worker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
