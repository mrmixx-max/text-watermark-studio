"""SynthID scorer wrapper CLI.

Run by the adapter (score_synthid) inside the reverse-SynthID checkout's
venv. It imports the upstream src/ package at runtime and prints a JSON
verdict. The upstream code is loaded from REVERSE_SYNTHID_DIR and remains
under its own non-commercial Research License — it is NOT bundled here.

Usage:
    <checkout>/.venv/bin/python score_synthid_cli.py IMAGE.png
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _run(image_path: str) -> dict:
    checkout = Path(os.environ.get("REVERSE_SYNTHID_DIR", "")).expanduser()
    src = checkout / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    codebook = checkout / "artifacts" / "spectral_codebook_v4.npz"
    if not codebook.exists():
        return {"error": "codebook_missing", "path": str(codebook)}

    # Upstream package layout varies; attempt the documented entry points.
    try:
        from reverse_synthid import score_image  # type: ignore

        result = score_image(str(Path(image_path)), str(codebook))
        return {"score": result} if not isinstance(result, dict) else result
    except ImportError:
        pass
    # Fallback: a module named after the scorer in src/
    try:
        import synthid_score as mod  # type: ignore

        fn = getattr(mod, "score", None) or getattr(mod, "score_image", None)
        if fn is None:
            return {
                "error": "upstream_scorer_entrypoint_not_found",
                "hint": "inspect the reverse-SynthID src/ package for the scoring API",
            }
        result = fn(str(Path(image_path)), str(codebook))
        return {"score": result} if not isinstance(result, dict) else result
    except ImportError:
        return {
            "error": "upstream_scorer_import_failed",
            "hint": "confirm the reverse-SynthID src/ package exposes a scoring entrypoint",
        }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(2)
