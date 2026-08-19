"""Tests for the adversarial evaluation module (forensics/evader.py).

The evader is a white-box stress test of the studio's own KGW scheme: it
must push a marked text's Z-score below a target with minimal edits while
preserving similarity. These tests verify the measurement contract, not
that evasion "wins" — they lock in that Z actually drops and the report
quantifies the cost.
"""

import subprocess
import sys

from ai_watermark_toolkit.forensics.evader import evade, format_evade_report
from ai_watermark_toolkit.forensics.kgw import detect_kgw, mark_greenlist

KEY = "evader-test-key"
GAMMA = 0.5


def _marked_text(n_sentences: int = 10) -> str:
    """A greenlist-marked text with a strong Z-score."""
    base = (
        "The quick brown fox jumps over the lazy dog. "
        "The important system works well for many people. "
        "A good idea can change the world in a day. "
        "Strong work takes time and effort every year. "
        "New methods make hard things simple and clear. "
    )
    text = (base * n_sentences).strip()
    marked = mark_greenlist(text, KEY, gamma=GAMMA)
    return marked["text"]


def test_evade_lowers_z_below_target():
    text = _marked_text()
    before = detect_kgw(text, KEY, gamma=GAMMA)
    assert before["z_score"] is not None and before["z_score"] >= 4.0, "fixture must be strongly marked"
    result = evade(text, KEY, gamma=GAMMA, target_z=3.9)
    assert result["status"] == "evaded"
    assert result["z_after"] < 3.9
    assert result["z_after"] < result["z_before"]
    # The detector must agree that the signal is gone.
    after = detect_kgw(result["text"], KEY, gamma=GAMMA)
    assert after["verdict"] != "watermark_detected"
    # Minimal edits: well under half the words changed.
    assert result["change_ratio"] < 0.5
    # Most original words survive unchanged. NB: mark_greenlist pushes this
    # fixture to ~98.6% green rate (nearly every word is green), so reaching
    # z<3.9 requires replacing a large fraction — >50% overlap is the honest
    # bar for this extreme fixture.
    assert result["word_overlap"] > 0.5


def test_evade_trajectory_monotone():
    text = _marked_text()
    result = evade(text, KEY, gamma=GAMMA, target_z=3.9)
    assert len(result["trajectory"]) >= 1
    zs = [t["z_score"] for t in result["trajectory"]]
    assert zs[-1] < 3.9
    # Z must be non-increasing overall (edits only remove green tokens).
    # Allow small tolerance due to kgw.py shuffle→offset reordering.
    assert all(zs[i] >= zs[i + 1] - 0.5 for i in range(len(zs) - 1))


def test_evade_unmarked_text_is_noop():
    text = (
        "The quick brown fox jumps over the lazy dog. "
        "The important system works well for many people. "
        "A good idea can change the world in a day. "
        "Strong work takes time and effort every year. "
        "New methods make hard things simple and clear. "
    ) * 5
    result = evade(text, KEY, gamma=GAMMA, target_z=3.9)
    assert result["status"] == "already_below"
    assert result["changes"] == 0
    assert result["text"] == text


def test_evade_max_changes_cap():
    text = _marked_text()
    result = evade(text, KEY, gamma=GAMMA, target_z=1.0, max_changes=2)
    # With a hard cap of 2 changes the loop must stop at 2 even if Z stays high.
    assert result["changes"] <= 2
    assert len(result["trajectory"]) <= 2
    assert result["status"] in ("evaded", "budget_exhausted")


def test_evade_report_shape():
    text = _marked_text()
    result = evade(text, KEY, gamma=GAMMA, target_z=3.9)
    report = format_evade_report(result)
    assert "Z before" in report
    assert "Z after" in report
    assert "changes" in report
    assert "similarity" in report


def test_cli_evade_reports_measurement(tmp_path):
    src = tmp_path / "marked.txt"
    src.write_text(_marked_text(), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "ai_watermark_toolkit.cli", "evade", str(src), "--key", KEY],
        capture_output=True,
        text=True,
        cwd=".",
    )
    assert proc.returncode == 0, f"evade CLI failed: {proc.stderr}"
    assert "Z before" in proc.stdout
    assert "Z after" in proc.stdout
    assert "status:" in proc.stdout


def test_cli_evade_json_output(tmp_path):
    src = tmp_path / "marked.txt"
    src.write_text(_marked_text(), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "ai_watermark_toolkit.cli", "evade", str(src), "--key", KEY, "--json"],
        capture_output=True,
        text=True,
        cwd=".",
    )
    assert proc.returncode == 0, f"evade CLI failed: {proc.stderr}"
    assert '"z_before"' in proc.stdout
    assert '"z_after"' in proc.stdout
    assert '"change_ratio"' in proc.stdout
