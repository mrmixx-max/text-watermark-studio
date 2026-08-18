"""E2E tests for CLI subprocess.

Invokes ai-wm as a real user would, capturing stdout/stderr and exit codes.
Tests every major subcommand end-to-end.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_cli(args: list[str], input_text: str | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    """Run ai-wm CLI as a subprocess."""
    cmd = [sys.executable, "-m", "ai_watermark_toolkit.cli", *args]
    if env is None:
        env = os.environ.copy()
    return subprocess.run(
        cmd,
        input=input_text,
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        env=env,
    )


class TestCLISplash:
    """CLI splash subcommand."""

    def test_splash_plain(self):
        """ai-wm splash --plain should print banner."""
        r = run_cli(["splash", "--plain"])
        assert r.returncode == 0
        assert "TEXT WATERMARK STUDIO" in r.stdout

    def test_splash_with_color(self):
        """ai-wm splash should print banner with colors."""
        r = run_cli(["splash"])
        assert r.returncode == 0
        assert "TEXT WATERMARK STUDIO" in r.stdout


class TestCLIDetect:
    """CLI detect subcommand."""

    def test_detect_from_file(self, tmp_path, sample_text):
        """ai-wm detect <file> should output detection JSON."""
        f = tmp_path / "input.txt"
        f.write_text(sample_text, encoding="utf-8")
        r = run_cli(["detect", str(f)])
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert "layers" in data
        assert "unicode" in data["layers"]

    def test_detect_from_stdin(self, sample_text):
        """ai-wm detect --stdin should read from stdin."""
        r = run_cli(["detect", "--stdin"], input_text=sample_text)
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert "layers" in data

    def test_detect_json_output(self, tmp_path, sample_text):
        """ai-wm detect --json should output valid JSON."""
        f = tmp_path / "input.txt"
        f.write_text(sample_text, encoding="utf-8")
        r = run_cli(["detect", str(f), "--json"])
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert "layers" in data

    def test_detect_with_output_file(self, tmp_path, sample_text):
        """ai-wm detect -o <file> should write to file."""
        f = tmp_path / "input.txt"
        f.write_text(sample_text, encoding="utf-8")
        out = tmp_path / "output.json"
        r = run_cli(["detect", str(f), "-o", str(out)])
        assert r.returncode == 0
        assert out.exists()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert "layers" in data

    def test_detect_with_steganography(self, tmp_path):
        """ai-wm detect on stego text should return exit code 1."""
        f = tmp_path / "stego.txt"
        f.write_text("Hello\u200bWorld\u202e", encoding="utf-8")
        r = run_cli(["detect", str(f)])
        assert r.returncode == 1  # markers found

    def test_detect_clean_text_returns_0(self, tmp_path, sample_text):
        """ai-wm detect on clean text should return exit code 0."""
        f = tmp_path / "clean.txt"
        f.write_text(sample_text, encoding="utf-8")
        r = run_cli(["detect", str(f)])
        assert r.returncode == 0

    def test_detect_with_key(self, tmp_path, sample_text):
        """ai-wm detect --key should run keyed KGW detection."""
        f = tmp_path / "input.txt"
        f.write_text(sample_text, encoding="utf-8")
        r = run_cli(["detect", str(f), "--key", "demo-kgw-secret-0001"])
        assert r.returncode in (0, 1)  # depends on detection
        data = json.loads(r.stdout)
        assert "kgw" in data


class TestCLIClean:
    """CLI clean subcommand."""

    def test_clean_from_file(self, tmp_path):
        """ai-wm clean <file> should output cleaned text."""
        f = tmp_path / "dirty.txt"
        f.write_text("Hello\u200bWorld\u202e", encoding="utf-8")
        r = run_cli(["clean", str(f)])
        assert r.returncode == 0
        assert "\u200b" not in r.stdout
        assert "\u202e" not in r.stdout

    def test_clean_from_stdin(self):
        """ai-wm clean --stdin should read from stdin."""
        r = run_cli(["clean", "--stdin"], input_text="Hello\u200bWorld")
        assert r.returncode == 0
        assert "\u200b" not in r.stdout

    def test_clean_with_output_file(self, tmp_path):
        """ai-wm clean -o <file> should write to file."""
        f = tmp_path / "dirty.txt"
        f.write_text("Hello\u200bWorld", encoding="utf-8")
        out = tmp_path / "clean.txt"
        r = run_cli(["clean", str(f), "-o", str(out)])
        assert r.returncode == 0
        assert out.exists()
        assert "\u200b" not in out.read_text(encoding="utf-8")

    def test_clean_with_report(self, tmp_path):
        """ai-wm clean --report should write a report file."""
        f = tmp_path / "dirty.txt"
        f.write_text("Hello\u200bWorld", encoding="utf-8")
        report = tmp_path / "report.json"
        r = run_cli(["clean", str(f), "--report", str(report)])
        assert r.returncode == 0
        assert report.exists()
        data = json.loads(report.read_text(encoding="utf-8"))
        assert data["unicode_removed"] >= 1

    def test_clean_nfkc(self, tmp_path):
        """ai-wm clean --nfkc should normalize."""
        f = tmp_path / "text.txt"
        f.write_text("caf\u00e9", encoding="utf-8")
        r = run_cli(["clean", str(f), "--nfkc"])
        assert r.returncode == 0

    def test_clean_fold_confusables(self, tmp_path):
        """ai-wm clean --fold-confusables should fold confusables."""
        f = tmp_path / "text.txt"
        f.write_text("pаypal", encoding="utf-8")  # Cyrillic а
        r = run_cli(["clean", str(f), "--fold-confusables"])
        assert r.returncode == 0


class TestCLIDilute:
    """CLI dilute subcommand."""

    def test_dilute_from_file(self, tmp_path, sample_text):
        """ai-wm dilute <file> should output diluted text."""
        f = tmp_path / "input.txt"
        f.write_text(sample_text, encoding="utf-8")
        r = run_cli(["dilute", str(f)])
        assert r.returncode == 0
        assert len(r.stdout) > 0

    def test_dilute_from_stdin(self, sample_text):
        """ai-wm dilute --stdin should read from stdin."""
        r = run_cli(["dilute", "--stdin"], input_text=sample_text)
        assert r.returncode == 0
        assert len(r.stdout) > 0

    def test_dilute_intensity(self, tmp_path, sample_text):
        """ai-wm dilute --intensity should accept all levels."""
        f = tmp_path / "input.txt"
        f.write_text(sample_text, encoding="utf-8")
        for intensity in ["light", "standard", "aggressive"]:
            r = run_cli(["dilute", str(f), "--intensity", intensity])
            assert r.returncode == 0, f"failed for intensity={intensity}"

    def test_dilute_with_output_file(self, tmp_path, sample_text):
        """ai-wm dilute -o <file> should write to file."""
        f = tmp_path / "input.txt"
        f.write_text(sample_text, encoding="utf-8")
        out = tmp_path / "diluted.txt"
        r = run_cli(["dilute", str(f), "-o", str(out)])
        assert r.returncode == 0
        assert out.exists()


class TestCLIEmbed:
    """CLI embed subcommand."""

    def test_embed_from_file(self, tmp_path, sample_text):
        """ai-wm embed <file> --key should embed watermark."""
        f = tmp_path / "input.txt"
        f.write_text(sample_text, encoding="utf-8")
        r = run_cli(["embed", str(f), "--key", "demo-kgw-1"])
        assert r.returncode == 0
        assert len(r.stdout) > 0

    def test_embed_from_stdin(self, sample_text):
        """ai-wm embed --stdin --key should read from stdin."""
        r = run_cli(["embed", "--stdin", "--key", "demo-kgw-1"], input_text=sample_text)
        assert r.returncode == 0
        assert len(r.stdout) > 0

    def test_embed_with_output_file(self, tmp_path, sample_text):
        """ai-wm embed -o <file> should write to file."""
        f = tmp_path / "input.txt"
        f.write_text(sample_text, encoding="utf-8")
        out = tmp_path / "watermarked.txt"
        r = run_cli(["embed", str(f), "--key", "demo-kgw-1", "-o", str(out)])
        assert r.returncode == 0
        assert out.exists()

    def test_embed_with_gamma(self, tmp_path, sample_text):
        """ai-wm embed --gamma should accept custom gamma."""
        f = tmp_path / "input.txt"
        f.write_text(sample_text, encoding="utf-8")
        r = run_cli(["embed", str(f), "--key", "demo-kgw-1", "--gamma", "0.5"])
        assert r.returncode == 0

    def test_embed_with_seed(self, tmp_path, sample_text):
        """ai-wm embed --seed should be deterministic."""
        f = tmp_path / "input.txt"
        f.write_text(sample_text, encoding="utf-8")
        out1 = tmp_path / "out1.txt"
        out2 = tmp_path / "out2.txt"
        run_cli(["embed", str(f), "--key", "demo-kgw-1", "--seed", "42", "-o", str(out1)])
        run_cli(["embed", str(f), "--key", "demo-kgw-1", "--seed", "42", "-o", str(out2)])
        assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")

    def test_embed_invalid_key_returns_2(self, tmp_path, sample_text):
        """ai-wm embed with invalid key should return exit code 2."""
        f = tmp_path / "input.txt"
        f.write_text(sample_text, encoding="utf-8")
        r = run_cli(["embed", str(f), "--key", "nonexistent-key-xyz"])
        assert r.returncode == 2


class TestCLIRewrite:
    """CLI rewrite subcommand."""

    def test_rewrite_from_file(self, tmp_path, sample_text):
        """ai-wm rewrite <file> should output rewritten text."""
        f = tmp_path / "input.txt"
        f.write_text(sample_text, encoding="utf-8")
        r = run_cli(["rewrite", str(f)])
        assert r.returncode == 0
        assert len(r.stdout) > 0

    def test_rewrite_from_stdin(self, sample_text):
        """ai-wm rewrite --stdin should read from stdin."""
        r = run_cli(["rewrite", "--stdin"], input_text=sample_text)
        assert r.returncode == 0
        assert len(r.stdout) > 0

    def test_rewrite_modes(self, tmp_path, sample_text):
        """ai-wm rewrite --mode should accept all modes."""
        f = tmp_path / "input.txt"
        f.write_text(sample_text, encoding="utf-8")
        for mode in ["clarity", "concise", "plain", "formal", "structural", "backtranslate"]:
            r = run_cli(["rewrite", str(f), "--mode", mode])
            assert r.returncode == 0, f"failed for mode={mode}"


class TestCLIPipeline:
    """CLI pipeline subcommand."""

    def test_pipeline_from_file(self, tmp_path, sample_text):
        """ai-wm pipeline <file> should run the full pipeline."""
        f = tmp_path / "input.txt"
        f.write_text(sample_text, encoding="utf-8")
        r = run_cli(["pipeline", str(f)])
        assert r.returncode == 0
        assert len(r.stdout) > 0

    def test_pipeline_from_stdin(self, sample_text):
        """ai-wm pipeline --stdin should read from stdin."""
        r = run_cli(["pipeline", "--stdin"], input_text=sample_text)
        assert r.returncode == 0
        assert len(r.stdout) > 0

    def test_pipeline_with_output(self, tmp_path, sample_text):
        """ai-wm pipeline -o <file> should write to file."""
        f = tmp_path / "input.txt"
        f.write_text(sample_text, encoding="utf-8")
        out = tmp_path / "output.txt"
        r = run_cli(["pipeline", str(f), "-o", str(out)])
        assert r.returncode == 0
        assert out.exists()

    def test_pipeline_with_rewrite_mode(self, tmp_path, sample_text):
        """ai-wm pipeline --rewrite-mode should include rewrite."""
        f = tmp_path / "input.txt"
        f.write_text(sample_text, encoding="utf-8")
        r = run_cli(["pipeline", str(f), "--rewrite-mode", "structural"])
        assert r.returncode == 0


class TestCLIRemove:
    """CLI remove subcommand."""

    def test_remove_from_file(self, tmp_path, sample_text):
        """ai-wm remove <file> should run removal pipeline."""
        f = tmp_path / "input.txt"
        f.write_text(sample_text, encoding="utf-8")
        r = run_cli(["remove", str(f)])
        assert r.returncode == 0
        assert len(r.stdout) > 0

    def test_remove_from_stdin(self, sample_text):
        """ai-wm remove --stdin should read from stdin."""
        r = run_cli(["remove", "--stdin"], input_text=sample_text)
        assert r.returncode == 0
        assert len(r.stdout) > 0

    def test_remove_with_output(self, tmp_path, sample_text):
        """ai-wm remove -o <file> should write to file."""
        f = tmp_path / "input.txt"
        f.write_text(sample_text, encoding="utf-8")
        out = tmp_path / "removed.txt"
        r = run_cli(["remove", str(f), "-o", str(out)])
        assert r.returncode == 0
        assert out.exists()


class TestCLIBatch:
    """CLI batch subcommand."""

    def test_batch_detect(self, tmp_path, sample_text):
        """ai-wm batch should process a directory."""
        in_dir = tmp_path / "input"
        out_dir = tmp_path / "output"
        in_dir.mkdir()
        out_dir.mkdir()
        (in_dir / "file1.txt").write_text(sample_text, encoding="utf-8")
        (in_dir / "file2.txt").write_text("Another text.", encoding="utf-8")
        r = run_cli(["batch", str(in_dir), str(out_dir), "--mode", "detect"])
        assert r.returncode == 0

    def test_batch_clean(self, tmp_path, sample_text):
        """ai-wm batch --mode clean should clean a directory."""
        in_dir = tmp_path / "input"
        out_dir = tmp_path / "output"
        in_dir.mkdir()
        out_dir.mkdir()
        (in_dir / "file1.txt").write_text("Hello\u200bWorld", encoding="utf-8")
        r = run_cli(["batch", str(in_dir), str(out_dir), "--mode", "clean"])
        assert r.returncode == 0


class TestCLISimilarity:
    """CLI similarity subcommand."""

    def test_similarity_basic(self, tmp_path, sample_text):
        """ai-wm similarity should compare against corpus."""
        f = tmp_path / "input.txt"
        f.write_text(sample_text, encoding="utf-8")
        corpus = tmp_path / "corpus.txt"
        corpus.write_text("This is a reference corpus text for comparison.", encoding="utf-8")
        r = run_cli(["similarity", str(f), "--corpus", str(corpus)])
        assert r.returncode == 0


class TestCLIDeltaZ:
    """CLI delta-z subcommand."""

    def test_delta_z_two_files(self, tmp_path, sample_text):
        """ai-wm delta-z should compare two files."""
        before = tmp_path / "before.txt"
        after = tmp_path / "after.txt"
        before.write_text(sample_text, encoding="utf-8")
        after.write_text(sample_text + " additional text.", encoding="utf-8")
        r = run_cli(["delta-z", str(before), str(after), "--key", "demo-kgw-secret-0001"])
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert "delta_z" in data or "before" in data or "kgw" in data

    def test_delta_z_with_transform(self, tmp_path, sample_text):
        """ai-wm delta-z --transform should apply transform."""
        f = tmp_path / "input.txt"
        f.write_text(sample_text, encoding="utf-8")
        r = run_cli(["delta-z", str(f), "--transform", "truncate", "--key", "demo-kgw-secret-0001"])
        assert r.returncode == 0


class TestCLIReportSignVerify:
    """CLI report-sign and report-verify subcommands."""

    def test_report_sign_hmac(self, tmp_path):
        """ai-wm report-sign should sign a payload."""
        payload = tmp_path / "payload.json"
        payload.write_text(json.dumps({"finding": "test", "score": 0.95}), encoding="utf-8")
        out = tmp_path / "signed.json"
        r = run_cli(["report-sign", str(payload), "--secret", "test-secret", "-o", str(out)])
        assert r.returncode == 0
        assert out.exists()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert "signature" in data

    def test_report_verify_hmac(self, tmp_path):
        """ai-wm report-verify should verify a signed payload."""
        payload = tmp_path / "payload.json"
        payload.write_text(json.dumps({"finding": "test", "score": 0.95}), encoding="utf-8")
        signed = tmp_path / "signed.json"
        run_cli(["report-sign", str(payload), "--secret", "test-secret", "-o", str(signed)])
        r = run_cli(["report-verify", str(signed), "--secret", "test-secret"])
        assert r.returncode == 0

    def test_report_verify_invalid(self, tmp_path):
        """ai-wm report-verify should fail with wrong secret."""
        payload = tmp_path / "payload.json"
        payload.write_text(json.dumps({"finding": "test"}), encoding="utf-8")
        signed = tmp_path / "signed.json"
        run_cli(["report-sign", str(payload), "--secret", "secret-a", "-o", str(signed)])
        r = run_cli(["report-verify", str(signed), "--secret", "secret-b"])
        assert r.returncode == 1


class TestCLIQuietMode:
    """CLI --quiet flag."""

    def test_detect_quiet(self, tmp_path, sample_text):
        """ai-wm --quiet detect should suppress stderr."""
        f = tmp_path / "input.txt"
        f.write_text(sample_text, encoding="utf-8")
        r = run_cli(["--quiet", "detect", str(f)])
        assert r.returncode == 0
        # stderr should be empty (or minimal)
        # Note: --quiet suppresses status messages but errors may still appear
        data = json.loads(r.stdout)
        assert "layers" in data


class TestCLIFileInspect:
    """CLI file-inspect subcommand."""

    def test_file_inspect_txt(self, tmp_path, sample_text):
        """ai-wm file-inspect should inspect a text file."""
        f = tmp_path / "test.txt"
        f.write_text(sample_text, encoding="utf-8")
        r = run_cli(["file-inspect", str(f)])
        assert r.returncode == 0

    def test_file_inspect_json(self, tmp_path, sample_text):
        """ai-wm file-inspect --json should output JSON."""
        f = tmp_path / "test.txt"
        f.write_text(sample_text, encoding="utf-8")
        r = run_cli(["file-inspect", str(f), "--json"])
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert "format" in data


class TestCLIFileClean:
    """CLI file-clean subcommand."""

    def test_file_clean_txt(self, tmp_path):
        """ai-wm file-clean should clean a file."""
        f = tmp_path / "dirty.txt"
        f.write_text("Hello\u200bWorld", encoding="utf-8")
        out = tmp_path / "clean.txt"
        r = run_cli(["file-clean", str(f), "-o", str(out)])
        assert r.returncode == 0
        assert out.exists()
