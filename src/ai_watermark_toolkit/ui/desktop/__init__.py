"""Desktop UI — PySide6 shell around the Qt-free DesktopController.

Importing this package does NOT require PySide6: ``DesktopController`` is
pure core. The Qt shell is loaded lazily via :func:`main` (or directly
from ``ai_watermark_toolkit.ui.desktop.app``), so controller-only use
(and the controller tests) work in a plain CPython process.
"""

from .controller import DesktopController

__all__ = ["DesktopController", "main"]


def main(argv: list[str] | None = None) -> int:
    """Launch the desktop shell (requires PySide6, optional extra)."""
    from .app import main as _app_main

    return _app_main(argv)
