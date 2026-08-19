"""High-value tests for low-coverage modules in forensics/, metadata/, core/.

Targets the modules below the 70% coverage bar:

- forensics/audit.py            (57%)  — read_audit, corrupt-line handling, AuditLogger
- forensics/watcher.py          (56%)  — _fingerprint error path, scan_file kgw path,
                                        watch_dir kgw key resolution, main()
- metadata/score_synthid_cli.py (0%)   — _run() branches and __main__ entry
- metadata/synthid.py           (57%)  — score_synthid scored branches, synthid_available

Each test is self-contained: it monkeypatches module-level paths / subprocess calls
so no real filesystem or external service is required (other than the repo's own
demo KGW key, already seeded by the autouse conftest fixture).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
SCORE_CLI = SRC / "ai_watermark_toolkit" / "metadata" / "score_synthid_cli.py"


# --------------------------------------------------------------------------- #
# forensics/audit.py  (was 57%)
# --------------------------------------------------------------------------- #
class TestAuditModule:
    """Cover read_audit + AuditLogger.read (previously untested)."""

    @pytest.fixture(autouse=True)
    def _tmp_audit_log(self, tmp_path, monkeypatch):
        from ai_watermark_toolkit.forensics import audit

        monkeypatch.setattr(audit, "AUDIT_LOG", tmp_path / "audit.log")

    def test_read_audit_empty_when_no_file(self):
        from ai_watermark_toolkit.forensics.audit import read_audit

        assert read_audit() == []

    def test_append_then_read_roundtrip(self):
        from ai_watermark_toolkit.forensics.audit import append_audit, read_audit

        append_audit("login", {"user": "alice"})
        append_audit("logout", {"user": "alice"})
        entries = read_audit()
        assert len(entries) == 2
        assert entries[0]["event"] == "login"
        assert entries[0]["payload"] == {"user": "alice"}
        assert entries[1]["event"] == "logout"
        for e in entries:
            assert "timestamp" in e

    def test_read_audit_handles_corrupt_line(self):
        from ai_watermark_toolkit.forensics.audit import AUDIT_LOG, read_audit

        AUDIT_LOG.write_text(
            json.dumps({"event": "ok", "payload": {}, "timestamp": "x"}) + "\n"
            + "NOT VALID JSON\n"
            + json.dumps({"event": "ok2", "payload": {}, "timestamp": "y"}) + "\n",
            encoding="utf-8",
        )
        entries = read_audit()
        assert len(entries) == 3
        assert entries[0]["event"] == "ok"
        assert entries[1]["event"] == "corrupt_line"
        assert entries[1]["raw"] == "NOT VALID JSON"
        assert entries[2]["event"] == "ok2"

    def test_read_audit_limit(self):
        from ai_watermark_toolkit.forensics.audit import append_audit, read_audit

        for i in range(5):
            append_audit(f"evt{i}", {"i": i})
        entries = read_audit(limit=2)
        assert len(entries) == 2
        assert entries[-1]["event"] == "evt4"
        assert entries[-2]["event"] == "evt3"

    def test_audit_logger_write_and_read(self):
        from ai_watermark_toolkit.forensics.audit import AuditLogger

        logger = AuditLogger()
        logger.write({"event": "x", "payload": {"k": 1}})
        entries = logger.read()
        assert len(entries) == 1
        assert entries[0]["event"] == "x"


# --------------------------------------------------------------------------- #
# metadata/synthid.py  (was 57%)
# --------------------------------------------------------------------------- #
def _make_venv(d: Path) -> Path:
    """Create a fake checkout venv with a python executable (OS-aware layout)."""
    sub = "Scripts" if os.name == "nt" else "bin"
    venv_py = d / ".venv" / sub / "python"
    venv_py.parent.mkdir(parents=True, exist_ok=True)
    venv_py.write_text("fake venv python")
    return venv_py


def _make_codebook(d: Path) -> Path:
    cb = d / "artifacts" / "spectral_codebook_v4.npz"
    cb.parent.mkdir(parents=True, exist_ok=True)
    cb.write_text("fake codebook")
    return cb


class TestSynthidAdapter:
    def test_synthid_available_with_codebook(self, tmp_path):
        from ai_watermark_toolkit.metadata.synthid import synthid_available

        d = tmp_path / "checkout"
        _make_codebook(d)
        assert synthid_available(str(d)) is True

    def test_synthid_available_no_venv_no_codebook(self, tmp_path):
        from ai_watermark_toolkit.metadata.synthid import synthid_available

        d = tmp_path / "empty"
        assert synthid_available(str(d)) is False

    def test_score_synthid_image_not_found(self, tmp_path):
        from ai_watermark_toolkit.metadata.synthid import score_synthid

        d = tmp_path / "checkout"
        _make_venv(d)
        _make_codebook(d)
        r = score_synthid(str(tmp_path / "missing.png"), synthid_dir=str(d))
        assert r["available"] is True
        assert r["error"] == "image_not_found"

    def test_score_synthid_subprocess_success(self, tmp_path, monkeypatch):
        from ai_watermark_toolkit.metadata import synthid as synthid_mod
        from ai_watermark_toolkit.metadata.synthid import score_synthid

        d = tmp_path / "checkout"
        _make_venv(d)
        _make_codebook(d)
        img = tmp_path / "img.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n")

        fake = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="{\"watermarked\": true}", stderr=""
        )
        monkeypatch.setattr(synthid_mod, "subprocess", types.SimpleNamespace(run=lambda *a, **k: fake, TimeoutExpired=subprocess.TimeoutExpired))
        r = score_synthid(str(img), synthid_dir=str(d))
        assert r["available"] is True
        assert r["exit_code"] == 0
        assert "watermarked" in r["stdout"]

    def test_score_synthid_timeout(self, tmp_path, monkeypatch):
        from ai_watermark_toolkit.metadata import synthid as synthid_mod
        from ai_watermark_toolkit.metadata.synthid import score_synthid

        d = tmp_path / "checkout"
        _make_venv(d)
        _make_codebook(d)
        img = tmp_path / "img.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n")

        def _raise(*a, **k):
            raise subprocess.TimeoutExpired(cmd="x", timeout=300)

        fake_sub = types.SimpleNamespace(run=_raise, TimeoutExpired=subprocess.TimeoutExpired)
        monkeypatch.setattr(synthid_mod, "subprocess", fake_sub)
        r = score_synthid(str(img), synthid_dir=str(d))
        assert r["available"] is True
        assert r["error"] == "scorer_timeout"

    def test_score_synthid_exception(self, tmp_path, monkeypatch):
        from ai_watermark_toolkit.metadata import synthid as synthid_mod
        from ai_watermark_toolkit.metadata.synthid import score_synthid

        d = tmp_path / "checkout"
        _make_venv(d)
        _make_codebook(d)
        img = tmp_path / "img.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n")

        def _raise(*a, **k):
            raise RuntimeError("upstream crashed")

        fake_sub = types.SimpleNamespace(run=_raise, TimeoutExpired=subprocess.TimeoutExpired)
        monkeypatch.setattr(synthid_mod, "subprocess", fake_sub)
        r = score_synthid(str(img), synthid_dir=str(d))
        assert r["available"] is True
        assert r["error"] == "upstream crashed"


# --------------------------------------------------------------------------- #
# metadata/score_synthid_cli.py  (was 0%)
# --------------------------------------------------------------------------- #
def _checkout_with_codebook(tmp_path: Path) -> Path:
    d = tmp_path / "checkout"
    _make_codebook(d)
    return d


class TestScoreSynthidCli:
    def test_run_codebook_missing(self, tmp_path, monkeypatch):
        import importlib.util

        spec = importlib.util.spec_from_file_location("score_synthid_cli_dyn", str(SCORE_CLI))
        cli = importlib.util.module_from_spec(spec)
        monkeypatch.setenv("REVERSE_SYNTHID_DIR", str(tmp_path / "no_codebook"))
        saved = list(sys.path)
        try:
            spec.loader.exec_module(cli)
            r = cli._run(str(tmp_path / "x.png"))
        finally:
            sys.path[:] = saved
        assert r["error"] == "codebook_missing"

    def test_run_import_failure(self, tmp_path, monkeypatch):
        import importlib.util

        d = _checkout_with_codebook(tmp_path)
        monkeypatch.setenv("REVERSE_SYNTHID_DIR", str(d))
        monkeypatch.setitem(sys.modules, "reverse_synthid", None)
        monkeypatch.setitem(sys.modules, "synthid_score", None)

        spec = importlib.util.spec_from_file_location("score_synthid_cli_imp", str(SCORE_CLI))
        cli = importlib.util.module_from_spec(spec)
        saved = list(sys.path)
        try:
            spec.loader.exec_module(cli)
            r = cli._run(str(tmp_path / "x.png"))
        finally:
            sys.path[:] = saved
        assert r["error"] == "upstream_scorer_import_failed"

    def test_run_success_with_mocked_scorer(self, tmp_path, monkeypatch):
        import importlib.util

        d = _checkout_with_codebook(tmp_path)
        monkeypatch.setenv("REVERSE_SYNTHID_DIR", str(d))

        fake_mod = types.ModuleType("reverse_synthid")
        fake_mod.score_image = lambda img, cb: {"score": 0.88, "watermarked": True}
        monkeypatch.setitem(sys.modules, "reverse_synthid", fake_mod)

        spec = importlib.util.spec_from_file_location("score_synthid_cli_ok", str(SCORE_CLI))
        cli = importlib.util.module_from_spec(spec)
        saved = list(sys.path)
        try:
            spec.loader.exec_module(cli)
            r = cli._run(str(tmp_path / "x.png"))
        finally:
            sys.path[:] = saved
        assert r["score"] == 0.88
        assert r["watermarked"] is True

    def test_run_scorer_returns_non_dict(self, tmp_path, monkeypatch):
        """When score_image returns a non-dict, _run wraps it in {'score': result}."""
        import importlib.util

        d = _checkout_with_codebook(tmp_path)
        monkeypatch.setenv("REVERSE_SYNTHID_DIR", str(d))

        fake_mod = types.ModuleType("reverse_synthid")
        fake_mod.score_image = lambda img, cb: 0.42
        monkeypatch.setitem(sys.modules, "reverse_synthid", fake_mod)

        spec = importlib.util.spec_from_file_location("score_synthid_cli_nd", str(SCORE_CLI))
        cli = importlib.util.module_from_spec(spec)
        saved = list(sys.path)
        try:
            spec.loader.exec_module(cli)
            r = cli._run(str(tmp_path / "x.png"))
        finally:
            sys.path[:] = saved
        assert r == {"score": 0.42}

    def test_run_fallback_to_synthid_score(self, tmp_path, monkeypatch):
        """reverse_synthid unavailable but synthid_score.score_image present -> use it."""
        import importlib.util

        d = _checkout_with_codebook(tmp_path)
        monkeypatch.setenv("REVERSE_SYNTHID_DIR", str(d))
        monkeypatch.setitem(sys.modules, "reverse_synthid", None)
        fake_score = types.ModuleType("synthid_score")
        fake_score.score_image = lambda img, cb: {"score": 0.77}
        monkeypatch.setitem(sys.modules, "synthid_score", fake_score)

        spec = importlib.util.spec_from_file_location("score_synthid_cli_fb", str(SCORE_CLI))
        cli = importlib.util.module_from_spec(spec)
        saved = list(sys.path)
        try:
            spec.loader.exec_module(cli)
            r = cli._run(str(tmp_path / "x.png"))
        finally:
            sys.path[:] = saved
        assert r["score"] == 0.77

    def test_run_scorer_module_without_entrypoint(self, tmp_path, monkeypatch):
        """synthid_score module exists but lacks score/score_image -> hint error."""
        import importlib.util

        d = _checkout_with_codebook(tmp_path)
        monkeypatch.setenv("REVERSE_SYNTHID_DIR", str(d))
        monkeypatch.setitem(sys.modules, "reverse_synthid", None)
        fake_score = types.ModuleType("synthid_score")
        monkeypatch.setitem(sys.modules, "synthid_score", fake_score)

        spec = importlib.util.spec_from_file_location("score_synthid_cli_nf", str(SCORE_CLI))
        cli = importlib.util.module_from_spec(spec)
        saved = list(sys.path)
        try:
            spec.loader.exec_module(cli)
            r = cli._run(str(tmp_path / "x.png"))
        finally:
            sys.path[:] = saved
        assert r["error"] == "upstream_scorer_entrypoint_not_found"

    def test_main_no_args_exits_2(self):
        proc = subprocess.run(
            [sys.executable, str(SCORE_CLI)],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 2


# --------------------------------------------------------------------------- #
# forensics/watcher.py  (was 56%)
# --------------------------------------------------------------------------- #
class TestWatcherCoverage:
    def test_fingerprint_format_and_missing(self, tmp_path):
        from ai_watermark_toolkit.forensics.watcher import _fingerprint

        p = tmp_path / "a.txt"
        p.write_text("hello world", encoding="utf-8")
        fp = _fingerprint(p)
        assert ":" in fp
        assert str(p.stat().st_size) in fp

        missing = _fingerprint(tmp_path / "gone.txt")
        assert missing == ""

    def test_scan_file_unsupported_format(self, tmp_path):
        from ai_watermark_toolkit.forensics.watcher import scan_file

        p = tmp_path / "data.exe"
        p.write_bytes(b"binary")
        res = scan_file(p)
        assert res["metadata"] is not None
        # After the inspect() return-type fix, the real format is reported
        assert res["metadata"]["format"] == "exe"
        assert "unsupported_format" in res["metadata"]["actions"]
        assert res["provenance"] is not None
        assert res["provenance"]["found"] is False
        assert res["kgw"] is None

    def test_scan_file_kgw_detection_on_text(self, tmp_path):
        from ai_watermark_toolkit.forensics.watcher import scan_file

        # Enough word tokens (>=11) for detect_kgw to produce a real verdict.
        text = (
            "The system processes data through a pipeline of workers "
            "that handle jobs in parallel across many queues and streams "
            "with redis backing the shared cache for fast reads and writes "
            "by every consumer node in the cluster during normal operation."
        )
        p = tmp_path / "doc.txt"
        p.write_text(text, encoding="utf-8")
        keys = [{"key_id": "k1", "secret": "demo-kgw-secret-0001", "family": "kgw", "gamma": 0.25}]
        res = scan_file(p, kgw_keys=keys)
        assert res["kgw"] is not None
        assert "verdict" in res["kgw"]
        assert res["kgw"]["tested_keys"] == 1

    def test_watch_dir_kgw_true_finds_text_files(self, tmp_path):
        from ai_watermark_toolkit.forensics.watcher import watch_dir

        text = (
            "The system processes data through a pipeline of workers "
            "that handle jobs in parallel across many queues and streams."
        )
        (tmp_path / "doc.txt").write_text(text, encoding="utf-8")
        lines = []
        n = watch_dir(str(tmp_path), once=True, out=lines.append, kgw=True)
        assert n >= 1
        parsed = [json.loads(l) for l in lines]
        found = next(p for p in parsed if p["path"].endswith("doc.txt"))
        # kgw detection ran on the .txt file
        assert found["kgw"] is not None
        assert "verdict" in found["kgw"]

    def test_watch_dir_skips_ignored_suffixes(self, tmp_path):
        from ai_watermark_toolkit.forensics.watcher import watch_dir

        (tmp_path / "keep.txt").write_text("keep me", encoding="utf-8")
        (tmp_path / "cache.tmp").write_bytes(b"\x00" * 10)
        (tmp_path / "old.pyc").write_bytes(b"\x00" * 10)
        lines = []
        n = watch_dir(str(tmp_path), once=True, out=lines.append)
        assert n == 1
        assert "keep.txt" in lines[0]

    def test_watch_main_valid_dir_once(self, tmp_path):
        from ai_watermark_toolkit.forensics.watcher import main

        (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
        rc = main([str(tmp_path), "--once"])
        assert rc == 0

    def test_watch_main_not_a_directory_returns_2(self, tmp_path):
        from ai_watermark_toolkit.forensics.watcher import main

        rc = main([str(tmp_path / "does-not-exist")])
        assert rc == 2
