"""Watch a directory for new/changed files and report metadata + provenance
findings per file. Stdlib-only polling (no watchdog dependency).

`--once` runs a single scan pass and exits — this is also what the tests use.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from ..metadata.service import inspect
from ..metadata.provenance import detect_provenance

SKIP_SUFFIXES = {".pyc", ".tmp", ".lock"}


def _fingerprint(p: Path) -> str:
    try:
        st = p.stat()
        return f"{st.st_size}:{st.st_mtime_ns}"
    except OSError:
        return ""


def scan_file(path: Path) -> dict:
    """Scan one file: metadata inspection + provenance detection."""
    name = path.name.lower()
    result = {
        "path": str(path),
        "size": path.stat().st_size,
        "metadata": None,
        "provenance": None,
    }
    data = path.read_bytes()
    try:
        cleaned, report = inspect(data, path.name)
        result["metadata"] = {
            "actions": report.get("actions", []),
            "format": report.get("format"),
        }
    except ValueError:
        # format not in the metadata layer's supported set — honest signal
        result["metadata"] = {"format": "unsupported", "actions": []}
    except Exception as e:  # pragma: no cover
        result["metadata"] = {"error": type(e).__name__}
    try:
        det = detect_provenance(data, path.name, secrets={})
        result["provenance"] = {
            "found": getattr(det, "found", None),
            "valid": getattr(det, "valid", None),
            "key_id": getattr(det, "key_id", None),
        }
    except Exception as e:  # pragma: no cover
        result["provenance"] = {"error": type(e).__name__}
    return result


def watch_dir(directory: str, *, once: bool = False, interval: float = 5.0,
              out=print) -> int:
    """Poll a directory; report new/changed files as JSON lines.

    Returns number of files reported (once=True) or runs until interrupted.
    """
    d = Path(directory)
    if not d.is_dir():
        raise NotADirectoryError(directory)
    known: dict[str, str] = {}
    reported = 0

    def pass_once():
        nonlocal reported
        for p in sorted(d.rglob("*")):
            if not p.is_file():
                continue
            if p.suffix.lower() in SKIP_SUFFIXES:
                continue
            fp = _fingerprint(p)
            if known.get(str(p)) == fp:
                continue
            known[str(p)] = fp
            res = scan_file(p)
            out(json.dumps(res, ensure_ascii=False))
            reported += 1

    pass_once()  # initial sweep
    if once:
        return reported

    while True:
        time.sleep(interval)
        pass_once()


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="ai-wm watch")
    ap.add_argument("directory")
    ap.add_argument("--once", action="store_true", help="single scan pass, then exit")
    ap.add_argument("--interval", type=float, default=5.0, help="poll seconds (default 5)")
    args = ap.parse_args(argv)
    try:
        n = watch_dir(args.directory, once=args.once, interval=args.interval)
    except NotADirectoryError as e:
        print(f"error: not a directory: {e}", file=__import__("sys").stderr)
        return 2
    if args.once:
        print(f"watch --once: {n} Datei(en) gemeldet.")
    return 0
