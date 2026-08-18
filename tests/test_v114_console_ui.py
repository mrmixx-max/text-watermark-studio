"""Behavioral tests for the console UI (2026-08-13).

Contract: JSON remains the default CLI output (scripts/tests depend on it).
The pretty layer is opt-in (--pretty / splash). The banner must never
contain REAL invisible unicode characters (that would be stego inside the
tool itself); U+200B/U+202E appear as literal text only.
"""

import json
import subprocess
import sys

from ai_watermark_toolkit.ui import __version__, render_banner, render_detect_report
from ai_watermark_toolkit.ui.banner import _PLAIN_LOGO


class TestBanner:
    def test_logo_has_tws_shape(self):
        assert "TEXT WATERMARK STUDIO" in render_banner(color=False)
        assert "███████" in _PLAIN_LOGO

    def test_plain_banner_has_no_ansi(self):
        out = render_banner(color=False)
        assert "\033[" not in out

    def test_color_banner_has_ansi(self):
        out = render_banner(color=True)
        assert "\033[" in out

    def test_banner_contains_no_real_invisible_unicode(self):
        out = render_banner(color=False)
        assert "\u200b" not in out
        assert "\u202e" not in out
        # the literal labels ARE present
        assert "U+200B" in out and "U+202E" in out

    def test_version_string_present(self):
        assert __version__ in render_banner(color=False)


class TestPrettyReport:
    def test_pretty_report_shows_findings(self):
        report = {
            "version": 1,
            "layers": {
                "unicode": {"count": 1, "items": [{"cp": "U+200B", "name": "ZERO WIDTH SPACE"}]},
                "markers": {"high": 2, "mid": 1, "low": 0},
                "markup": {"count": 0},
            },
        }
        out = render_detect_report(report, color=False)
        assert "WATERMARK SIGNALS FOUND" in out
        assert "[HIGH] 2" in out
        assert "U+200B" in out

    def test_pretty_report_clean_verdict(self):
        report = {
            "version": 1,
            "layers": {
                "unicode": {"count": 0, "items": []},
                "markers": {"high": 0, "mid": 0, "low": 0},
                "markup": {"count": 0},
            },
        }
        out = render_detect_report(report, color=False)
        assert "CLEAN" in out


class TestCliUiContract:
    def test_splash_plain_exits_zero(self):
        proc = subprocess.run(
            [sys.executable, "-m", "ai_watermark_toolkit.cli", "splash", "--plain"],
            capture_output=True,
            text=True,
            cwd=None,
            timeout=60,
        )
        assert proc.returncode == 0, proc.stderr
        assert "TEXT WATERMARK STUDIO" in proc.stdout

    def test_detect_default_stays_json(self):
        import os

        fixture = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "tests",
            "fixtures",
            "stego_zwsp.txt",
        )
        proc = subprocess.run(
            [sys.executable, "-m", "ai_watermark_toolkit.cli", "detect", fixture],
            capture_output=True,
            text=True,
            timeout=60,
        )
        # JSON contract: output parses as JSON even on signal exit code 1
        data = json.loads(proc.stdout)
        assert data["layers"]["unicode"]["count"] == 2

    def test_detect_pretty_shows_box(self):
        import os

        fixture = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "tests",
            "fixtures",
            "stego_zwsp.txt",
        )
        proc = subprocess.run(
            [sys.executable, "-m", "ai_watermark_toolkit.cli", "detect", fixture, "--pretty"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert "DETECT" in proc.stdout
        assert "U+200B" in proc.stdout
        assert "WATERMARK SIGNALS FOUND" in proc.stdout
