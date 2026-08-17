"""Coverage tests for cli.py: helper functions, error paths, edge cases.

Targets functions and branches in cli.py that existing tests miss:
- _resolve_key_arg, _resolve_secret_arg (file-vs-inline priority)
- _resolve_key (key_id lookup vs raw secret, edge cases)
- _read (stdin vs file path)
- main_entry (error wrapper for FileNotFoundError, IsADirectoryError, ValueError)
- CLI subcommand error paths (detect, finding, trace, delta-z, etc.)
"""

import json
import os
import sys
import tempfile
import subprocess
from pathlib import Path

import pytest

from ai_watermark_toolkit.cli import (
    _resolve_key_arg,
    _resolve_secret_arg,
    _resolve_key,
    _read,
    main_entry,
)

TEXT = (
    "The first sentence establishes context. "
    "The second provides the main argument. "
    "The third gives supporting evidence. "
    "The fourth draws the conclusion."
)

CLI_MODULE = "ai_watermark_toolkit.cli"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_key_file(tmp_path):
    """Write a key secret to a temp file and return (path, secret)."""
    secret = "file-secret-42"
    f = tmp_path / "key.txt"
    f.write_text(secret + "\n", encoding="utf-8")
    return f, secret


@pytest.fixture
def temp_secret_file(tmp_path):
    """Write an HMAC secret to a temp file and return (path, secret)."""
    secret = "hmac-secret-99"
    f = tmp_path / "secret.txt"
    f.write_text(secret + "  \n", encoding="utf-8")  # trailing whitespace
    return f, secret


@pytest.fixture
def input_file(tmp_path):
    f = tmp_path / "input.txt"
    f.write_text(TEXT, encoding="utf-8")
    return f


# ---------------------------------------------------------------------------
# _resolve_key_arg  ( --key-file wins over --key )
# ---------------------------------------------------------------------------

class TestResolveKeyArg:
    def test_key_only(self):
        """--key returns the inline value."""
        args = argparse.Namespace(key="my-secret", key_file=None)
        assert _resolve_key_arg(args) == "my-secret"

    def test_key_file_only(self, temp_key_file):
        """--key-file reads and strips the file content."""
        f, secret = temp_key_file
        args = argparse.Namespace(key=None, key_file=str(f))
        assert _resolve_key_arg(args) == secret

    def test_key_file_overrides(self, temp_key_file):
        """--key-file overrides --key when both are set."""
        f, secret = temp_key_file
        args = argparse.Namespace(key="inline-key", key_file=str(f))
        assert _resolve_key_arg(args) == secret  # file wins

    def test_neither(self):
        """No key or key-file returns None."""
        args = argparse.Namespace(key=None, key_file=None)
        assert _resolve_key_arg(args) is None

    def test_key_file_missing_raises(self):
        """Missing --key-file should raise FileNotFoundError (caller handles it by main_entry)."""
        args = argparse.Namespace(key=None, key_file="/nonexistent/key.txt")
        with pytest.raises(FileNotFoundError):
            _resolve_key_arg(args)


# ---------------------------------------------------------------------------
# _resolve_secret_arg  ( --secret-file wins over --secret )
# ---------------------------------------------------------------------------

class TestResolveSecretArg:
    def test_secret_only(self):
        args = argparse.Namespace(secret="inline-secret", secret_file=None)
        assert _resolve_secret_arg(args) == "inline-secret"

    def test_secret_file_only(self, temp_secret_file):
        f, secret = temp_secret_file
        args = argparse.Namespace(secret=None, secret_file=str(f))
        assert _resolve_secret_arg(args) == secret

    def test_secret_file_overrides(self, temp_secret_file):
        f, secret = temp_secret_file
        args = argparse.Namespace(secret="inline", secret_file=str(f))
        assert _resolve_secret_arg(args) == secret

    def test_neither(self):
        args = argparse.Namespace(secret=None, secret_file=None)
        assert _resolve_secret_arg(args) is None

    def test_secret_file_strips_whitespace(self, tmp_path):
        """Leading/trailing whitespace and newlines are stripped."""
        f = tmp_path / "secret.txt"
        f.write_text("  my-secret  \n\n", encoding="utf-8")
        args = argparse.Namespace(secret=None, secret_file=str(f))
        assert _resolve_secret_arg(args) == "my-secret"


# ---------------------------------------------------------------------------
# _resolve_key  (key_id lookup vs raw secret)
# ---------------------------------------------------------------------------

class TestResolveKey:
    def test_key_id_lookup(self, monkeypatch):
        """key_id found in registry returns (dict, True)."""
        registry = MockRegistry([
            {"key_id": "demo-kgw-1", "family": "kgw", "secret": "demo-secret",
             "gamma": 0.25, "key_source": "registry"},
        ])
        key, from_registry = _resolve_key(registry, "demo-kgw-1")
        assert from_registry is True
        assert key["secret"] == "demo-secret"
        assert key["key_id"] == "demo-kgw-1"

    def test_raw_secret_masked(self, monkeypatch):
        """Raw secret returns a masked key_id so the secret never leaks."""
        registry = MockRegistry([])
        key, from_registry = _resolve_key(registry, "my-raw-secret-42")
        assert from_registry is False
        # The key_id uses the "secret:sha256-prefix" mask, so the raw
        # secret value itself should NOT appear in the key_id.
        assert "my-raw-secret-42" not in key["key_id"]
        assert key["key_id"].startswith("secret:")
        assert key["secret"] == "my-raw-secret-42"
        assert key["family"] == "kgw"
        assert key["gamma"] is None
        assert key["key_source"] == "raw_secret"

    def test_key_id_not_found_returns_raw_secret(self, monkeypatch):
        """A key_id-like string that doesn't exist in registry becomes a raw secret."""
        registry = MockRegistry([])
        key, from_registry = _resolve_key(registry, "nonexistent-key-99")
        assert from_registry is False
        assert key["secret"] == "nonexistent-key-99"


# ---------------------------------------------------------------------------
# _read  (stdin vs file path)
# ---------------------------------------------------------------------------

class TestRead:
    def test_file_path(self, input_file):
        """_read reads from a file when --stdin is not set."""
        args = argparse.Namespace(input=str(input_file), stdin=False)
        assert _read(args) == TEXT

    def test_stdin(self, monkeypatch):
        """_read reads from stdin when --stdin is True."""
        monkeypatch.setattr(sys, "stdin", io.StringIO(TEXT))
        args = argparse.Namespace(input=None, stdin=True)
        assert _read(args) == TEXT


# ---------------------------------------------------------------------------
# main_entry  (error wrapper)
# ---------------------------------------------------------------------------

class TestMainEntry:
    def test_file_not_found(self, monkeypatch):
        """FileNotFoundError returns 2 with a clean stderr message."""
        def _raise(*a, **kw):
            raise FileNotFoundError(2, "No such file or directory", "missing.txt")
        monkeypatch.setattr("ai_watermark_toolkit.cli.main", _raise)
        assert main_entry() == 2

    def test_is_a_directory(self, monkeypatch):
        """IsADirectoryError returns 2."""
        def _raise(*a, **kw):
            raise IsADirectoryError("some_dir")
        monkeypatch.setattr("ai_watermark_toolkit.cli.main", _raise)
        assert main_entry() == 2

    def test_value_error(self, monkeypatch):
        """ValueError returns 2."""
        def _raise(*a, **kw):
            raise ValueError("bad value")
        monkeypatch.setattr("ai_watermark_toolkit.cli.main", _raise)
        assert main_entry() == 2

    def test_success(self, monkeypatch):
        """Zero return code propagates."""
        def _ok(*a, **kw):
            return 0
        monkeypatch.setattr("ai_watermark_toolkit.cli.main", _ok)
        assert main_entry() == 0

    def test_finding_return_code(self, monkeypatch):
        """Return code 1 (findings) propagates."""
        def _findings(*a, **kw):
            return 1
        monkeypatch.setattr("ai_watermark_toolkit.cli.main", _findings)
        assert main_entry() == 1


# ---------------------------------------------------------------------------
# Subprocess-based CLI error path tests
# ---------------------------------------------------------------------------

def run_cli(args, stdin=None, cwd=None):
    """Run the CLI module as a subprocess, returning CompletedProcess."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"
    )
    base = [sys.executable, "-m", CLI_MODULE]
    cwd = cwd or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return subprocess.run(
        base + args, capture_output=True, text=True, input=stdin, env=env, cwd=cwd
    )


class TestCliDetectErrors:
    def test_e_value_requires_key(self, input_file):
        """--e-value without --key should return exit 2."""
        r = run_cli(["detect", str(input_file), "--e-value"])
        assert r.returncode == 2
        assert "error" in r.stderr.lower()
        assert "e-value" in r.stderr.lower() or "e_value" in r.stderr.lower()

    def test_signature_filter_requires_key(self, input_file):
        """--signature-filter without --key should return exit 2."""
        r = run_cli(["detect", str(input_file), "--signature-filter"])
        assert r.returncode == 2
        assert "error" in r.stderr.lower()

    def test_detect_nonexistent_file(self):
        """detect with nonexistent file should not crash."""
        r = run_cli(["detect", "/nonexistent/file.txt"])
        assert r.returncode != 0
        assert "Traceback" not in r.stderr

    def test_detect_empty_stdin(self):
        """detect --stdin with empty input returns 0 (no signal)."""
        r = run_cli(["detect", "--stdin"], stdin="")
        assert r.returncode == 0


class TestCliCleanErrors:
    def test_clean_nonexistent_file(self):
        r = run_cli(["clean", "/nonexistent/file.txt"])
        assert r.returncode != 0
        assert "Traceback" not in r.stderr

    def test_clean_empty_input_stdin(self):
        r = run_cli(["clean", "--stdin"], stdin="")
        assert r.returncode == 0
        assert r.stdout.strip() == ""

    def test_clean_with_report(self, tmp_path):
        f = tmp_path / "in.txt"
        f.write_text("Hello\u200bWorld", encoding="utf-8")
        report = tmp_path / "report.json"
        r = run_cli(["clean", str(f), "--report", str(report)])
        assert r.returncode == 0
        assert report.exists()


class TestCliDilute:
    def test_dilute_empty(self):
        r = run_cli(["dilute", "--stdin"], stdin="")
        assert r.returncode == 0

    def test_dilute_with_output(self, tmp_path):
        f = tmp_path / "in.txt"
        f.write_text(TEXT, encoding="utf-8")
        out = tmp_path / "out.txt"
        r = run_cli(["dilute", str(f), "-o", str(out)])
        assert r.returncode == 0
        assert out.exists()
        assert out.read_text(encoding="utf-8").strip()


class TestCliPipelineErrors:
    def test_pipeline_nonexistent_file(self):
        r = run_cli(["pipeline", "/nonexistent/file.txt"])
        assert r.returncode != 0
        assert "Traceback" not in r.stderr

    def test_pipeline_all_flags(self, tmp_path):
        """pipeline with all optional flags: nfkc, fold-confusables, aggressive, etc."""
        f = tmp_path / "in.txt"
        f.write_text("Hello\u200b World! It is important to note that this leverages automation.",
                     encoding="utf-8")
        out = tmp_path / "out.txt"
        report = tmp_path / "report.json"
        r = run_cli([
            "pipeline", str(f), "--nfkc", "--fold-confusables",
            "--intensity", "aggressive",
            "--rewrite-mode", "structural",
            "-o", str(out), "--report", str(report),
        ])
        assert r.returncode == 0
        assert out.exists()
        assert report.exists()
        data = json.loads(report.read_text(encoding="utf-8"))
        assert "before" in data
        assert "rewrite" in data

    def test_pipeline_without_rewrite(self, tmp_path):
        """pipeline without rewrite-mode runs successfully with rewrite: None."""
        f = tmp_path / "in.txt"
        f.write_text(TEXT, encoding="utf-8")
        out = tmp_path / "out.txt"
        r = run_cli(["pipeline", str(f), "-o", str(out)])
        assert r.returncode == 0


class TestCliEmbedErrors:
    def test_embed_nonexistent_key(self, tmp_path):
        f = tmp_path / "in.txt"
        f.write_text(TEXT, encoding="utf-8")
        r = run_cli(["embed", str(f), "--key", "nonexistent-key"])
        assert r.returncode == 2
        assert "error" in r.stderr.lower()


class TestCliWatchErrors:
    def test_watch_nonexistent_dir(self):
        r = run_cli(["watch", "/nonexistent/dir", "--once"])
        assert r.returncode != 0
        assert "Traceback" not in r.stderr

    def test_watch_invalid_interval(self, tmp_path):
        r = run_cli(["watch", str(tmp_path), "--interval", "-1"])
        assert r.returncode != 0  # argparse catches negative float? It doesn't, but watch_dir may reject it


class TestCliTui:
    def test_tui_help(self):
        """tui --help shows the help page without launching the TUI."""
        r = run_cli(["tui", "--help"])
        assert r.returncode == 0
        assert "tui" in r.stdout or "terminal" in r.stdout


class TestCliFileInspect:
    def test_file_inspect_nonexistent(self):
        r = run_cli(["file-inspect", "/nonexistent/file.txt"])
        assert r.returncode != 0
        assert "Traceback" not in r.stderr

    def test_file_inspect_text_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello", encoding="utf-8")
        r = run_cli(["file-inspect", str(f)])
        assert r.returncode == 0
        assert "format" in r.stdout or "type" in r.stdout or r.stdout.strip()

    def test_file_inspect_json(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello", encoding="utf-8")
        r = run_cli(["file-inspect", str(f), "--json"])
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert isinstance(data, dict)


class TestCliSimilarityErrors:
    def test_similarity_nonexistent_input(self):
        r = run_cli(["similarity", "/nonexistent.txt", "--corpus", "/tmp"])
        assert r.returncode == 2

    def test_similarity_no_corpus(self, tmp_path):
        f = tmp_path / "in.txt"
        f.write_text("test", encoding="utf-8")
        r = run_cli(["similarity", str(f), "--corpus", "/nonexistent-corpus"])
        assert "Traceback" not in (r.stderr + r.stdout)

    def test_similarity_with_json(self, tmp_path):
        f = tmp_path / "in.txt"
        f.write_text("The quick brown fox jumps over the lazy dog.", encoding="utf-8")
        r = run_cli(["similarity", str(f), "--corpus", str(tmp_path), "--json"])
        assert r.returncode in (0, 1)  # 0 no findings, 1 findings


class TestCliDeltaZErrors:
    def test_delta_z_no_key(self, tmp_path):
        f1 = tmp_path / "before.txt"
        f2 = tmp_path / "after.txt"
        f1.write_text("Hello world", encoding="utf-8")
        f2.write_text("Hello world", encoding="utf-8")
        r = run_cli(["delta-z", str(f1), str(f2)])
        assert r.returncode == 2
        assert "error" in r.stderr.lower()

    def test_delta_z_transform_with_after(self, tmp_path):
        f1 = tmp_path / "before.txt"
        f2 = tmp_path / "after.txt"
        f1.write_text("Hello world", encoding="utf-8")
        f2.write_text("Hello world", encoding="utf-8")
        r = run_cli([
            "delta-z", str(f1), str(f2),
            "--transform", "clean", "--key", "demo-kgw-1",
        ])
        assert r.returncode == 2
        assert "error" in r.stderr.lower()

    def test_delta_z_missing_before(self, tmp_path):
        r = run_cli([
            "delta-z", "--key", "demo-kgw-1",
        ])
        assert r.returncode == 2

    def test_delta_z_with_output_flag(self, tmp_path):
        f1 = tmp_path / "before.txt"
        f2 = tmp_path / "after.txt"
        f1.write_text("Hello world", encoding="utf-8")
        f2.write_text("Hello world", encoding="utf-8")
        out = tmp_path / "result.json"
        r = run_cli([
            "delta-z", str(f1), str(f2),
            "--key", "demo-kgw-1", "-o", str(out),
        ])
        # May succeed if key is valid, or fail if key has no secret
        if r.returncode == 0:
            assert out.exists()
        else:
            assert "error" in r.stderr.lower()


class TestCliFindingErrors:
    def test_finding_no_input(self):
        r = run_cli(["finding"])
        assert r.returncode == 2

    def test_finding_no_key(self, tmp_path):
        f = tmp_path / "in.txt"
        f.write_text(TEXT, encoding="utf-8")
        r = run_cli(["finding", str(f)])
        assert r.returncode == 2


class TestCliTraceErrors:
    def test_trace_no_input(self):
        r = run_cli(["trace"])
        assert r.returncode == 2

    def test_trace_no_key(self, tmp_path):
        f = tmp_path / "in.txt"
        f.write_text(TEXT, encoding="utf-8")
        r = run_cli(["trace", str(f)])
        assert r.returncode == 2

    def test_trace_with_json_and_output(self, tmp_path):
        f = tmp_path / "in.txt"
        f.write_text(TEXT, encoding="utf-8")
        out = tmp_path / "trace.json"
        r = run_cli(["trace", str(f), "--key", "demo-kgw-1",
                     "--json", "-o", str(out)])
        if r.returncode == 0:
            assert out.exists()
        else:
            assert "error" in r.stderr.lower()


class TestCliPayloadErrors:
    def test_payload_embed_no_input(self):
        r = run_cli(["payload", "embed", "--payload", "test123", "-o", "/dev/null"])
        assert r.returncode == 2

    def test_payload_extract_no_input(self):
        r = run_cli(["payload", "extract", "--reference", "/nonexistent"])
        assert r.returncode == 2

    def test_payload_extract_no_reference(self, tmp_path):
        f = tmp_path / "in.txt"
        f.write_text("test", encoding="utf-8")
        r = run_cli(["payload", "extract", str(f)])
        assert r.returncode == 2


class TestCliEvadeErrors:
    def test_evade_no_input(self):
        r = run_cli(["evade"])
        assert r.returncode == 2

    def test_evade_no_key(self, tmp_path):
        f = tmp_path / "in.txt"
        f.write_text(TEXT, encoding="utf-8")
        r = run_cli(["evade", str(f)])
        assert r.returncode == 2


class TestCliServe:
    def test_serve_help(self):
        r = run_cli(["serve", "--help"])
        assert r.returncode == 0


class TestCliUnknownCmd:
    def test_unknown_command(self):
        r = run_cli(["nonexistent-cmd"])
        assert r.returncode != 0
        assert "Traceback" not in r.stderr

    def test_no_command(self):
        r = run_cli([])
        assert r.returncode != 0


class TestCliSplash:
    def test_splash_basic(self):
        r = run_cli(["splash"])
        assert r.returncode == 0

    def test_splash_plain(self):
        r = run_cli(["splash", "--plain"])
        assert r.returncode == 0


class TestCliKgwSample:
    def test_kgw_sample_basic(self):
        r = run_cli(["kgw-sample", "--n-tokens", "10", "--seed", "42"])
        assert r.returncode == 0
        assert r.stdout.strip()

    def test_kgw_sample_json(self):
        r = run_cli(["kgw-sample", "--n-tokens", "10", "--seed", "42", "--json"])
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert "generated" in data
        assert "detected" in data

    def test_kgw_sample_custom_prefix(self):
        r = run_cli(["kgw-sample", "--n-tokens", "10", "--seed", "42",
                     "--prefix", "Hello world"])
        assert r.returncode == 0


class TestCliLlm:
    def test_llm_status(self):
        r = run_cli(["llm", "status"])
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert isinstance(data, dict)

    def test_llm_list(self):
        r = run_cli(["llm", "list"])
        assert r.returncode in (0, 1)
        assert "Traceback" not in r.stderr

    def test_llm_use_bad_model(self):
        r = run_cli(["llm", "use", "nonexistent-model-xyz"])
        assert r.returncode in (0, 1)
        assert "Traceback" not in r.stderr

    def test_llm_install_bad_model(self):
        r = run_cli(["llm", "install", "nonexistent-model-xyz"])
        assert r.returncode in (0, 1)
        assert "Traceback" not in r.stderr


class TestCliReportSignErrors:
    def test_report_sign_bad_json(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("not json", encoding="utf-8")
        r = run_cli(["report-sign", str(f)])
        assert r.returncode == 2
        assert "not valid JSON" in r.stderr

    def test_report_sign_non_object_array(self, tmp_path):
        f = tmp_path / "arr.json"
        f.write_text("[1, 2, 3]", encoding="utf-8")
        r = run_cli(["report-sign", str(f)])
        assert r.returncode == 2

    def test_report_sign_no_secret(self, tmp_path):
        f = tmp_path / "payload.json"
        f.write_text('{"test": true}', encoding="utf-8")
        r = run_cli(["report-sign", str(f)])
        assert r.returncode == 2
        assert "error" in r.stderr.lower()


class TestCliReportVerifyErrors:
    def test_report_verify_bad_json(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("not json", encoding="utf-8")
        r = run_cli(["report-verify", str(f)])
        assert r.returncode == 2

    def test_report_verify_no_input(self):
        r = run_cli(["report-verify", "/nonexistent"])
        assert r.returncode == 2


class TestCliReportKeygen:
    def test_report_keygen_no_crypto(self, tmp_path):
        """report-keygen without cryptography returns exit 1."""
        r = run_cli(["report-keygen", "--output-dir", str(tmp_path)])
        assert r.returncode in (0, 1)
        assert "Traceback" not in r.stderr


class TestCliReportWithKeyFile:
    def test_detect_with_key_file(self, tmp_path):
        """--key-file overrides --key for detect."""
        f = tmp_path / "in.txt"
        f.write_text(TEXT, encoding="utf-8")
        kf = tmp_path / "key.txt"
        kf.write_text("demo-kgw-secret-0001", encoding="utf-8")
        r = run_cli(["detect", str(f), "--key-file", str(kf)])
        assert r.returncode in (0, 1)
        assert "Traceback" not in r.stderr

    def test_rewrite_with_key_file_not_applicable(self, tmp_path):
        """rewrite doesn't accept --key-file, but shouldn't crash."""
        f = tmp_path / "in.txt"
        f.write_text(TEXT, encoding="utf-8")
        r = run_cli(["rewrite", str(f), "--mode", "structural"])
        assert r.returncode == 0


class TestCliImageScore:
    def test_image_score_nonexistent(self):
        r = run_cli(["image-score", "/nonexistent.png"])
        assert r.returncode != 0
        assert "Traceback" not in r.stderr

    def test_image_score_with_json(self, tmp_path):
        f = tmp_path / "test.png"
        f.write_text("not an image", encoding="utf-8")
        r = run_cli(["image-score", str(f), "--json"])
        assert r.returncode != 0
        assert "Traceback" not in r.stderr


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

import argparse
import io

class MockRegistry:
    """Minimal mock of KeyRegistry for _resolve_key tests."""
    def __init__(self, keys):
        self._keys = keys

    def list_keys(self):
        return self._keys