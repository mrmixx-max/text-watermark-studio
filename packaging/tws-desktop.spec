# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — Text Watermark Studio desktop app (Windows).

Onefile, windowed (no console). Build from the repo root AFTER
``pip install -e .`` (the editable install makes ``ai_watermark_toolkit``
importable; PySide6 ships its own PyInstaller hooks, so no manual Qt
hook wiring is needed):

    pip install PySide6 pyinstaller
    pip install -e .
    pyinstaller packaging/tws-desktop.spec     # -> dist/tws-desktop.exe

The spec is deliberately thin: hiddenimports only cover the modules the
desktop controller touches (forensics + generation); the server stack
(fastapi/uvicorn/redis/arq/...) is excluded to keep the onefile honest
and small — this is a second CLIENT of the same core, not the API.
"""

import os

from PyInstaller.utils.hooks import collect_submodules

# Spec files get SPECPATH (the spec file's directory); the repo root is
# one level up. pathex is needed only when the editable install is absent.
ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))

hiddenimports = (
    collect_submodules("ai_watermark_toolkit.ui.desktop")
    + collect_submodules("ai_watermark_toolkit.forensics")
    + collect_submodules("ai_watermark_toolkit.generation")
)

a = Analysis(
    [os.path.join(ROOT, "packaging", "desktop_entry.py")],
    pathex=[os.path.join(ROOT, "src")],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Server/worker stack is out of scope for the desktop client; dropping
    # it cuts the onefile size drastically and keeps the surface honest.
    excludes=[
        "fastapi", "uvicorn", "redis", "arq", "prometheus_client",
        "python_multipart", "websockets", "httpx", "pytest", "textual",
        "tkinter", "torch", "transformers",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="tws-desktop",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # windowed: no console window on launch
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,              # no icon asset yet -> default PyInstaller icon
)
