# Desktop GUI (Windows)

A thin PySide6 wrapper around the **same core forensics** used by CLI/API/TUI — no server, no network, no telemetry. The entry point for non-developers (law firms, institutions, editorial offices).

## Why PySide6

The desktop app uses PySide6 (Qt for Python) for a native Windows look and feel. The controller logic is Qt-free — `DesktopController` calls the same core functions as the CLI, so the PySide6 shell is swappable for any other UI framework.

## Features

- **Detect** — KGW Z-score + e-process (anytime-valid) against the chosen key or all registered keys; JSON result in the panel
- **Embed** — `mark_greenlist`: text is greenlist-marketed (guaranteed detectable, Z>4), result replaces editor text (undoable via Ctrl+Z)
- **Report** — self-contained HTML findings report (`build_report`) written to Downloads (fallback: Temp)
- **Sign/Verify** — sign findings JSON (HMAC-SHA256, registry secret; or ML-DSA quantum-safe via CLI) and verify
- **KGW Example** — synthetic generation-time bias demo (mechanics proof, no LLM)
- Key selection, status bar, JSON result panel, file dialog

## Run from source

```bash
pip install PySide6        # optional GUI-only dependency (core stays stdlib-first)
python -m ai_watermark_toolkit.ui.desktop.app
```

## Build (Windows)

```bash
pip install PySide6 pyinstaller
pip install -e .
pyinstaller packaging/tws-desktop.spec     # -> dist/tws-desktop.exe (onefile, windowed)
iscc packaging/tws-setup.iss              # -> dist/TWS-Setup.exe (Inno Setup)
```

CI: `.github/workflows/build-desktop.yml` (manual or tag `v*` on windows-latest: PyInstaller → choco Inno Setup → ISCC → Artifacts).

## Installation and the honest SmartScreen hurdle

`TWS-Setup.exe` installs to `%ProgramFiles%\TextWatermarkStudio`. Without a code-signing certificate the installer is **unsigned** — Windows SmartScreen shows "Unknown publisher" and requires "More info → Run anyway". This is expected and not a bug. A code-signing certificate (OV/EV, ~$100–300/year) removes the warning; that is a budget decision. The optional signing step is commented out in the workflow (certificate as secret `WINDOWS_CERT_BASE64`/`WINDOWS_CERT_PASSWORD`).

## Keys

The app reads `data/key_registry.json` (read-only, same contract as CLI/TUI). Keys are created via `POST /api/forensics/keys` (`ai-wm serve`) or by registry entry. Without a KGW key with secret, the app reports this honestly instead of silently creating a demo key. The installer creates no keys — the registry remains operator-side.

## Architecture

```
src/ai_watermark_toolkit/ui/desktop/
├── __init__.py
├── app.py            # PySide6 application shell
└── controller.py     # Qt-free DesktopController (calls core functions)
```

The controller is the bridge: it imports from `ai_watermark_toolkit.forensics`, `ai_watermark_toolkit.pipeline`, etc. — the same code paths as the CLI. The PySide6 `app.py` wires buttons to controller methods and displays results.

## Packaging

| File | Purpose |
|---|---|
| `packaging/tws-desktop.spec` | PyInstaller spec (onefile, windowed) |
| `packaging/tws-setup.iss` | Inno Setup script |
| `desktop/packaging/windows/build.ps1` | PowerShell build script |

## Notes

- The desktop layer talks directly to core functions — no HTTP, no FastAPI, no Redis.
- All core forensics are stdlib-first; PySide6 is the only GUI dependency.
- The app is intentionally thin: menus and buttons call core functions directly.
