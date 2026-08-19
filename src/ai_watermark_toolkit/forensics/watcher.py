"""Watch a directory for new/changed files and report metadata + provenance
findings per file. Stdlib-only polling (no watchdog dependency).

`--once` runs a single scan pass and exits — this is also what the tests use.
"""

from __future__ import annotations

import json
import signal
import time
from pathlib import Path

from ..metadata.provenance import detect_provenance
from ..metadata.service import inspect

SKIP_SUFFIXES = {".pyc", ".tmp", ".lock"}


def _fingerprint(p: Path) -> str:
    try:
        st = p.stat()
        return f"{st.st_size}:{st.st_mtime_ns}"
    except OSError:
        return ""


def scan_file(path: Path, *, kgw_keys: list[dict] | None = None) -> dict:
    """Scan one file: metadata inspection + provenance detection.

    If kgw_keys is provided, also run KGW text detection on text files.
    """
    path.name.lower()
    result = {
        "path": str(path),
        "size": path.stat().st_size,
        "metadata": None,
        "provenance": None,
        "kgw": None,
    }
    data = path.read_bytes()
    try:
        report = inspect(data, path.name)
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

    # Optional KGW text detection (opt-in via --kgw flag)
    if kgw_keys and path.suffix.lower() in {".txt", ".md", ".html", ".htm", ".rst"}:
        try:
            from ..forensics.kgw import detect_multi_key

            text = data.decode("utf-8", errors="replace")
            kgw_result = detect_multi_key(text, kgw_keys, level="word", context=1)
            best = kgw_result.get("best") or {}
            result["kgw"] = {
                "verdict": best.get("verdict", "no_signal"),
                "z_score": best.get("z_score"),
                "green_rate": best.get("green_rate"),
                "key_id": best.get("key_id"),
                "tested_keys": kgw_result.get("tested_keys", 0),
            }
        except Exception as e:  # pragma: no cover
            result["kgw"] = {"error": type(e).__name__}

    return result


def watch_dir(directory: str, *, once: bool = False, interval: float = 5.0, out=print, kgw: bool = False) -> int:
    """Poll a directory; report new/changed files as JSON lines.

    If kgw=True, also run KGW text detection on text files (requires
    registered KGW keys with secrets).
    Returns number of files reported (once=True) or runs until interrupted.
    """
    d = Path(directory)
    if not d.is_dir():
        raise NotADirectoryError(directory)
    known: dict[str, str] = {}
    reported = 0
    stop = False

    # Graceful shutdown on SIGTERM/SIGINT — break the polling loop cleanly
    def _shutdown(signum, frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    # Resolve KGW keys once if --kgw is active
    kgw_keys = None
    if kgw:
        from ..forensics.key_registry import KeyRegistry

        registry = KeyRegistry("data/key_registry.json")
        kgw_keys = [k for k in registry.list_keys() if k.get("family") == "kgw" and k.get("secret")]
        if not kgw_keys:
            import warnings

            warnings.warn("watch --kgw: no KGW keys with secrets registered — KGW detection skipped", stacklevel=2)

    def pass_once():
        nonlocal reported
        current_paths: set[str] = set()
        for p in sorted(d.rglob("*")):
            if not p.is_file():
                continue
            if p.suffix.lower() in SKIP_SUFFIXES:
                continue
            fp = _fingerprint(p)
            current_paths.add(str(p))
            if known.get(str(p)) == fp:
                continue
            known[str(p)] = fp
            try:
                res = scan_file(p, kgw_keys=kgw_keys)
                out(json.dumps(res, ensure_ascii=False))
            except Exception as e:  # pragma: no cover — scan_file shouldn't raise, but be safe
                out(json.dumps({"path": str(p), "error": type(e).__name__}, ensure_ascii=False))
            reported += 1
        # Prune entries for files that no longer exist (prevents unbounded growth)
        for stale in set(known.keys()) - current_paths:
            del known[stale]

    pass_once()  # initial sweep
    if once:
        return reported

    while not stop:
        time.sleep(interval)
        pass_once()
    return reported


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="ai-wm watch")
    ap.add_argument("directory")
    ap.add_argument("--once", action="store_true", help="single scan pass, then exit")
    ap.add_argument("--interval", type=float, default=5.0, help="poll seconds (default 5)")
    ap.add_argument(
        "--kgw", action="store_true", help="also run KGW text detection on text files (requires registered KGW keys)",
    )
    args = ap.parse_args(argv)
    try:
        watch_dir(args.directory, once=args.once, interval=args.interval, kgw=args.kgw)
    except NotADirectoryError:
        return 2
    if args.once:
        pass
    return 0
