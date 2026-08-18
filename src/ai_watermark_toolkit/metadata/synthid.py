"""SynthID pixel-scoring adapter.

Real SynthID detection needs the upstream research codebook (~220 MB,
non-commercial Research License) from aloshdenny/reverse-SynthID. We do
NOT bundle it. When an external checkout is available (REVERSE_SYNTHID_DIR
or --synthid-dir), this adapter runs the upstream scorer via the checkout's
venv and returns its verdict. Without a checkout it reports availability=false
— honest, not fake.

Detection/scoring only. Pixel-domain watermark REMOVAL is out of scope.
"""

from __future__ import annotations

import os
import subprocess  # nosec B404 — used with list args only, no shell=True
import sys
from pathlib import Path

CODEBOOK_REL = os.path.join("artifacts", "spectral_codebook_v4.npz")


def _resolve(synthid_dir: str | None) -> Path:
    if synthid_dir:
        return Path(synthid_dir).expanduser()
    return Path(os.environ.get("REVERSE_SYNTHID_DIR", "") or "~/reverse-SynthID").expanduser()


def synthid_available(synthid_dir: str | None = None) -> bool:
    d = _resolve(synthid_dir)
    return (d / ".venv").exists() or (d / CODEBOOK_REL).exists()


def score_synthid(image_path: str, synthid_dir: str | None = None) -> dict:
    """Run the upstream scorer if its checkout is present."""
    d = _resolve(synthid_dir)
    venv_py = d / ".venv" / ("Scripts" if os.name == "nt" else "bin") / "python"
    codebook = d / CODEBOOK_REL
    if not venv_py.exists():
        return {
            "available": False,
            "reason": "reverse_synthid_checkout_not_found",
            "hint": "run scripts/setup_synthid.sh or set REVERSE_SYNTHID_DIR",
        }
    if not codebook.exists():
        return {
            "available": True,
            "error": "codebook_missing",
            "hint": f"expected at {codebook}; re-run setup_synthid.sh",
        }
    img = Path(image_path)
    if not img.exists():
        return {"available": True, "error": "image_not_found"}

    # Our scorer wrapper lives alongside this module; it imports the upstream
    # src/ package from the checkout venv at runtime.
    scorer = Path(__file__).resolve().parent / "score_synthid_cli.py"
    if not scorer.exists():
        return {"available": True, "error": "scorer_wrapper_missing"}

    env = dict(os.environ)
    env["REVERSE_SYNTHID_DIR"] = str(d)
    try:
        proc = subprocess.run(  # nosec B603 — list args, no shell=True, paths from internal resolution
            [sys.executable, str(scorer)],
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )
        return {
            "available": True,
            "exit_code": proc.returncode,
            "stdout": proc.stdout.strip()[:2000],
            "stderr": proc.stderr.strip()[:500],
        }
    except subprocess.TimeoutExpired:
        return {"available": True, "error": "scorer_timeout"}
    except Exception as e:
        return {"available": True, "error": str(e)}
