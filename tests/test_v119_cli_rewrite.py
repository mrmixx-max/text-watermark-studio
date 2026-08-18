"""Behavioral tests for the ai-wm rewrite CLI subcommand (2026-08-13).

Contract: `ai-wm rewrite <file> --mode <mode>` prints the rewritten text,
exit 0. --json prints the full report. --stdin works. Modes structural and
backtranslate reach the rewrite service.
"""

import json
import os
import subprocess
import sys

CLI = [sys.executable, "-m", "ai_watermark_toolkit.cli"] if False else None

TEXT = (
    "The first sentence establishes context. "
    "The second provides the main argument. "
    "The third gives supporting evidence. "
    "The fourth draws the conclusion."
)


def run_cli(args, stdin=None, cwd=None):
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
    base = [sys.executable, "-m", "ai_watermark_toolkit.cli"]
    return subprocess.run(base + args, capture_output=True, text=True, input=stdin,
                          env=env, cwd=cwd or os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestCliRewrite:
    def test_structural_mode_outputs_rewritten_text(self, tmp_path):
        f = tmp_path / "in.txt"
        f.write_text(TEXT, encoding="utf-8")
        r = run_cli(["rewrite", str(f), "--mode", "structural"])
        assert r.returncode == 0, r.stderr
        out = r.stdout.strip()
        assert out != TEXT
        assert out.startswith("The first sentence")

    def test_json_flag_outputs_report(self, tmp_path):
        f = tmp_path / "in.txt"
        f.write_text(TEXT, encoding="utf-8")
        r = run_cli(["rewrite", str(f), "--mode", "backtranslate", "--json"])
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert data["mode"] == "backtranslate"
        assert any("No-LLM path" in s for s in data["change_log"])

    def test_stdin_input(self):
        r = run_cli(["rewrite", "--stdin", "--mode", "structural"], stdin=TEXT)
        assert r.returncode == 0, r.stderr
        assert r.stdout.strip() != TEXT

    def test_output_flag_writes_file(self, tmp_path):
        f = tmp_path / "in.txt"
        f.write_text(TEXT, encoding="utf-8")
        out = tmp_path / "out.txt"
        r = run_cli(["rewrite", str(f), "--mode", "clarity", "-o", str(out)])
        assert r.returncode == 0, r.stderr
        assert out.exists()
        assert out.read_text(encoding="utf-8").strip()

    def test_invalid_mode_rejected(self, tmp_path):
        f = tmp_path / "in.txt"
        f.write_text(TEXT, encoding="utf-8")
        r = run_cli(["rewrite", str(f), "--mode", "nonsense"])
        assert r.returncode != 0  # argparse rejects unknown choice
