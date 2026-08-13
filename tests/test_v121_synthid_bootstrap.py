"""Behavioral tests for the SynthID bootstrap paths (2026-08-13).

Contract: without a checkout the adapter reports available=false and points
at setup_synthid.sh. With a checkout but no codebook it reports
codebook_missing. The venv resolution handles both POSIX (bin/) and Windows
(Scripts/) layouts. The bootstrap script and Dockerfile exist in the repo.
"""

import os
from pathlib import Path

from ai_watermark_toolkit.metadata.synthid import (
    _resolve,
    score_synthid,
    synthid_available,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestResolve:
    def test_env_var_used(self, tmp_path, monkeypatch):
        d = tmp_path / "custom"
        monkeypatch.setenv("REVERSE_SYNTHID_DIR", str(d))
        assert _resolve(None) == d

    def test_explicit_dir_wins_over_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("REVERSE_SYNTHID_DIR", str(tmp_path / "env"))
        explicit = tmp_path / "explicit"
        assert _resolve(str(explicit)) == explicit


class TestCodebookLogic:
    def test_venv_without_codebook_reports_codebook_missing(self, tmp_path):
        d = tmp_path / "checkout"
        # match the adapter's OS-specific venv layout
        sub = "Scripts" if os.name == "nt" else "bin"
        (d / ".venv" / sub).mkdir(parents=True)
        (d / ".venv" / sub / "python").write_text("")
        img = tmp_path / "x.png"
        img.write_bytes(b"\x89PNG")
        r = score_synthid(str(img), synthid_dir=str(d))
        assert r["available"] is True
        assert r["error"] == "codebook_missing"

    def test_windows_venv_layout_detected(self, tmp_path):
        d = tmp_path / "wincheckout"
        (d / ".venv" / "Scripts").mkdir(parents=True)
        (d / ".venv" / "Scripts" / "python").write_text("")
        assert synthid_available(str(d))


class TestRepoArtifacts:
    def test_bootstrap_script_exists(self):
        p = REPO_ROOT / "scripts" / "setup_synthid.sh"
        assert p.exists()

    def test_dockerfile_exists(self):
        p = REPO_ROOT / "Dockerfile.synthid"
        assert p.exists()

    def test_scorer_wrapper_exists(self):
        p = REPO_ROOT / "src" / "ai_watermark_toolkit" / "metadata" / "score_synthid_cli.py"
        assert p.exists()

    def test_requirements_file_exists(self):
        p = REPO_ROOT / "scripts" / "requirements-synthid-scorer.txt"
        assert p.exists()

    def test_dockerfile_fetches_upstream_not_bundles(self):
        content = (REPO_ROOT / "Dockerfile.synthid").read_text()
        assert "git clone" in content
        assert "aloshdenny/reverse-SynthID" in content
        # does not COPY the codebook into the image from this repo
        assert "COPY artifacts" not in content
