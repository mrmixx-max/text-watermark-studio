"""Console UI: ASCII banner + colorized report rendering.

Design constraints:
- JSON is the DEFAULT output of every command (scripts and tests rely on
  it). The pretty layer is opt-in via `--pretty` or the `splash` command.
- ANSI colors are Windows-safe: enabled via the VT-sequence activation
  trick on win32 and only emitted when requested (--pretty/splash) or
  when stdout is a TTY.
- The banner never contains REAL invisible unicode characters (that would
  be stego in the banner itself). U+200B/U+202E appear as literal text.
"""

from __future__ import annotations

import sys

__version__ = "2.0.0"

TEAL = "\033[36m"
RED = "\033[31m"
GREEN = "\033[32m"
GOLD = "\033[33m"
WHITE = "\033[97m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"

_PLAIN_LOGO = r"""
        ████████╗██╗    ██╗███████╗
        ╚══██╔══╝██║    ██║██╔════╝
           ██║   ██║ █╗ ██║███████╗
           ██║   ██║███╗██║╚════██║
           ██║   ╚███╔███╔╝███████║
           ╚═╝    ╚══╝╚══╝ ╚══════╝
""".strip("\n")

_PLAIN_SCAN = '[ scan ]  "Hello" U+200B "World" U+202E " hidden"\n[ run  ]  5 markers (3 high) -> 0 markers\n'

_TAGLINE = "detect . clean . dilute . embed . rewrite"


def _ansi_on() -> None:
    """Enable ANSI on legacy Windows consoles (harmless elsewhere)."""
    if sys.platform == "win32":
        try:
            # Enable ANSI escape sequences on Windows 10+
            # Using ctypes instead of os.system("") for safety
            import ctypes

            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            # Enable ENABLE_VIRTUAL_TERMINAL_PROCESSING
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except (AttributeError, OSError):
            pass


def render_banner(color: bool = True) -> str:
    if color:
        _ansi_on()
        logo = "\n".join(TEAL + line + RESET for line in _PLAIN_LOGO.splitlines())
        scan = ""
        for line in _PLAIN_SCAN.splitlines():
            scan += (
                line.replace("U+200B", RED + "U+200B" + TEAL).replace("U+202E", RED + "U+202E" + TEAL) + RESET + "\n"
            )
        scan = scan.replace("[ scan ]", DIM + "[ scan ]" + RESET)
        scan = scan.replace("[ run  ]", DIM + "[ run  ]" + RESET)
        scan = scan.replace("0 markers", GREEN + "0 markers" + TEAL)
        return (
            logo
            + "\n"
            + BOLD
            + "  -- TEXT WATERMARK STUDIO"
            + RESET
            + DIM
            + "  v"
            + __version__
            + "  --"
            + RESET
            + "\n"
            + scan
            + DIM
            + "  "
            + _TAGLINE
            + RESET
        )
    return _PLAIN_LOGO + "\n" + "  -- TEXT WATERMARK STUDIO  v" + __version__ + "  --\n" + _PLAIN_SCAN + "  " + _TAGLINE


def render_detect_report(report: dict, color: bool = True) -> str:
    """Human-readable box for a detect report dict (the CLI JSON shape)."""
    layers = report.get("layers", {})
    markers = layers.get("markers", {})
    unicode_layer = layers.get("unicode", {})
    high = markers.get("high", 0)
    mid = markers.get("mid", 0)
    low = markers.get("low", 0)
    uni = unicode_layer.get("count", 0)
    lines = []
    if color:
        _ansi_on()
        lines.append(BOLD + TEAL + "  DETECT" + RESET)
        lines.append(DIM + "  " + "-" * 46 + RESET)
        lines.append(f"  [HIGH] {RED if high else DIM}{high}{RESET}")
        lines.append(f"  [MID ] {GOLD if mid else DIM}{mid}{RESET}")
        lines.append(f"  [LOW ] {DIM}{low}{RESET}")
        lines.append(f"  [UNI ] {RED if uni else DIM}{uni}{RESET}  invisible/bidi characters")
        if uni:
            for item in unicode_layer.get("items", [])[:5]:
                lines.append(f"         {RED}{item.get('cp', '')}{RESET} {DIM}{item.get('name', '')}{RESET}")
        verdict = "WATERMARK SIGNALS FOUND" if (high or mid or uni) else "CLEAN"
        vcolor = RED if (high or uni) else (GOLD if mid else GREEN)
        lines.append("")
        lines.append(f"  {vcolor}{BOLD}{verdict}{RESET}")
    else:
        lines.append("DETECT")
        lines.append("-" * 46)
        lines.append(f"[HIGH] {high}")
        lines.append(f"[MID ] {mid}")
        lines.append(f"[LOW ] {low}")
        lines.append(f"[UNI ] {uni} invisible/bidi characters")
        if uni:
            for item in unicode_layer.get("items", [])[:5]:
                lines.append(f"       {item.get('cp', '')} {item.get('name', '')}")
        verdict = "WATERMARK SIGNALS FOUND" if (high or mid or uni) else "CLEAN"
        lines.append("")
        lines.append(verdict)
    return "\n".join(lines)
