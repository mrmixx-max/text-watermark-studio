"""SynthID pixel-scoring adapter.

Real SynthID detection needs the upstream research codebook (~220 MB,
non-commercial Research License) from aloshdenny/reverse-SynthID. We do
NOT bundle it. When an external checkout is available (REVERSE_SYNTHID_DIR
or --synthid-dir), this adapter shells out to the upstream scorer and
returns its verdict. Without a checkout it reports availability=false —
honest, not fake.

Detection/scoring only. Pixel-domain watermark REMOVAL is out of scope.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def synthid_available(synthid_dir: str | None = None) -> bool:
    d = Path(synthid_dir) if synthid_dir else Path(os.environ.get("REVERSE_SYNTHID_DIR", "") or "~/reverse-SynthID").expanduser()
    return (d / ".venv").exists() or (d / "artifacts" / "spectral_codebook_v4.npz").exists()


def score_synthid(image_path: str, synthid_dir: str | None = None) -> dict:
    """Run the upstream scorer if available. Returns {available, score?, ...}."""
    d = Path(synthid_dir) if synthid_dir else Path(os.environ.get("REVERSE_SYNTHID_DIR", "") or "~/reverse-SynthID").expanduser()
    venv_py = d / ".venv" / ("Scripts" if os.name == "nt" else "bin") / "python"
    if not venv_py.exists():
        return {"available": False, "reason": "reverse_synthid_checkout_not_found",
                "hint": "run setup_synthid.sh or set REVERSE_SYNTHID_DIR"}
    img = Path(image_path)
    if not img.exists():
        return {"available": True, "error": "image_not_found"}
    script = d / "scripts" / "score_synthid.py"
    if not script.exists():
        return {"available": True, "error": "upstream_scorer_script_missing"}
    try:
        proc = subprocess.run(
            [str(venv_py), str(script), str(img)],
            capture_output=True, text=True, timeout=300,
        )
        return {"available": True, "exit_code": proc.returncode,
                "stdout": proc.stdout.strip()[:2000],
                "stderr": proc.stderr.strip()[:500]}
    except subprocess.TimeoutExpired:
        return {"available": True, "error": "scorer_timeout"}
    except Exception as e:
        return {"available": True, "error": str(e)}
