"""PyInstaller entry point for the desktop app.

The spec must NOT use ``app.py`` directly as the script: PyInstaller then
executes it as ``__main__`` without package context and the relative
import ``from .controller import ...`` fails. This entry imports the app
as a real package module instead — same code path as
``python -m ai_watermark_toolkit.ui.desktop.app``.
"""

from ai_watermark_toolkit.ui.desktop.app import main

if __name__ == "__main__":
    raise SystemExit(main())
