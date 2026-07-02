# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the self-contained daios-worker.exe.

Bundles the Python runtime and all three BSDK packages (daios_launcher,
daios_node, daios_protocol) plus their runtime dependencies, so the exe needs no
system Python. The native GGML RPC binaries are bundled here *if present* at build
time (drop them in packaging/windows/bin/); otherwise the installer downloads and
SHA-256-verifies them at runtime.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

ROOT = Path(SPECPATH).resolve().parents[1]
LAUNCHER_SRC = ROOT / "apps" / "launcher" / "src"
NODE_SRC = ROOT / "apps" / "node" / "src"
PROTOCOL_SRC = ROOT / "packages" / "protocol" / "src"
PACKAGING = ROOT / "packaging" / "windows"

# Release manifest is always bundled so the runtime can locate/verify binaries.
datas = [(str(PACKAGING / "binaries-manifest.json"), ".")]

# Bundle native binaries if a maintainer placed them in packaging/windows/bin/.
binaries = []
prebuilt_bin = PACKAGING / "bin"
if prebuilt_bin.is_dir():
    for item in prebuilt_bin.iterdir():
        if item.is_file():
            # Land them under a "bin/" folder inside the bundle (_MEIPASS/bin).
            binaries.append((str(item), "bin"))

# Pull in submodules/data for packages PyInstaller cannot fully trace statically.
hiddenimports = [
    "daios_launcher.bootstrap",
    "daios_launcher.cli",
    "daios_launcher.app",
    "daios_launcher.settings",
    "daios_launcher.update",
    "daios_launcher.autostart_windows",
    "daios_launcher.firewall_windows",
    "daios_launcher.exe_update",
    "daios_launcher.platform_utils",
    "daios_launcher.paths",
    "daios_launcher.system_check",
    "daios_launcher.artifacts",
    "daios_launcher.prereqs",
    "daios_launcher.config_gen",
    "daios_launcher.process_manager",
    "daios_node.cli",
    "daios_node.app",
    "daios_protocol",
]
for pkg in ("uvicorn", "fastapi", "starlette", "zeroconf", "psutil", "httpx", "anyio",
            "huggingface_hub", "daios_node", "daios_protocol", "daios_launcher"):
    hiddenimports += collect_submodules(pkg)
for pkg in ("fastapi", "zeroconf", "certifi"):
    datas += collect_data_files(pkg)

a = Analysis(
    [str(LAUNCHER_SRC / "daios_launcher" / "bootstrap.py")],
    pathex=[str(LAUNCHER_SRC), str(NODE_SRC), str(PROTOCOL_SRC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy.testing"],
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
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    # Windowed: the background service must never show a console. Interactive
    # modes (install/uninstall/--check) attach or allocate one at runtime — see
    # bootstrap._ensure_console().
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
