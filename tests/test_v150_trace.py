"""Tests for the sliding-window Z-score trajectory (forensics/trace.py).

Validated behavior:
* A document that is mostly clean with ONE embedded marked chapter must
  produce finding windows ONLY in the marked span — the whole-doc Z alone
  would miss it (that is the point of the feature).
* Windows too short for a Z-test stay in the trajectory with reliable=False.
* Adjacent finding windows merge into spans.
* CLI: `ai-wm trace` works end-to-end and reports the spike.
"""

import json
import subprocess
import sys

from ai_watermark_toolkit.forensics.kgw import mark_greenlist
from ai_watermark_toolkit.forensics.trace import (
    format_trace,
    trace_kgw,
)

KEY = "trace-test-key"
GAMMA = 0.5
WINDOW = 120  # words — small windows for a fast test doc


def _clean_text(n_words: int = 400) -> str:
    """Deterministic neutral text (no greenlist bias expected)."""
    words = []
    i = 0
    while len(words) < n_words:
        words.append(f"neutral word number {i} with ordinary phrasing here")
        i += 1
    return " ".join(words)


def _mark(text: str) -> str:
    """Greenlist-mark text, returning the marked text."""
    return mark_greenlist(text, KEY, gamma=GAMMA)["text"]


def test_marked_span_is_detected_in_clean_document():
    """Clean 400-word doc with a 120-word marked block in the middle."""
    clean = _clean_text(400)
    words = clean.split()
    # Mark ONLY the middle 120 words.
    marked = _mark(" ".join(words[140:260]))
    doc_words = words[:140] + marked.split() + words[260:]
    doc = " ".join(doc_words)

    # Small windows so the marked block lands inside its own window(s).
    trace = trace_kgw(doc, KEY, gamma=GAMMA, window=WINDOW, step=WINDOW, threshold=4.0)

    assert trace["total_windows"] >= 4, "expected several windows"
    assert trace["finding_windows"] >= 1, "marked block must produce a finding"
    # Every finding window must overlap the marked span (words 140..~260).
    for e in trace["windows"]:
        if e["finding"]:
            assert e["start_word"] < 300, f"finding outside marked span: {e}"
            assert e["end_word"] > 140, f"finding outside marked span: {e}"
    # Spans exist and cover the marked region.
    assert trace["spans"], "expected merged spans"
    assert all(s["peak_z"] is not None and s["peak_z"] >= 4.0 for s in trace["spans"])


def test_clean_document_has_no_findings():
    trace = trace_kgw(_clean_text(500), KEY, gamma=GAMMA, window=WINDOW, step=WINDOW, threshold=4.0)
    assert trace["finding_windows"] == 0, "clean text must not produce findings"
    assert trace["spans"] == []


def test_short_windows_are_unreliable_but_present():
    """Window too small for statistics -> z None + reliable False, still listed."""
    trace = trace_kgw("tiny text with only a few words here.", KEY, gamma=GAMMA, window=3, step=3)
    assert trace["total_windows"] >= 1
    for e in trace["windows"]:
        if e["end_word"] - e["start_word"] < 11:  # below the n>=10 minimum
            assert e["reliable"] is False
            assert e["z_score"] is None


def test_empty_text():
    trace = trace_kgw("", KEY, gamma=GAMMA, window=WINDOW)
    assert trace["windows"] == []
    assert trace["spans"] == []
    assert trace["total_windows"] == 0


def test_format_trace_contains_markers():
    clean = _clean_text(300)
    marked = _mark(clean)
    doc = " ".join(clean.split()[:150] + marked.split()[:120])
    trace = trace_kgw(doc, KEY, gamma=GAMMA, window=120, step=120, threshold=4.0)
    out = format_trace(trace, text=doc)
    assert "Z-score trajectory" in out
    assert "FINDING" in out or "Spans above threshold" in out


def test_cli_trace_reports_spike():
    """End-to-end: `ai-wm trace` (module invocation) on a marked doc."""
    clean = _clean_text(300)
    marked = _mark(clean)
    doc = " ".join(clean.split()[:150] + marked.split()[:120])
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai_watermark_toolkit.cli",
            "trace",
            "--key",
            KEY,
            "--window",
            "120",
            "--step",
            "120",
            "--stdin",
        ],
        input=doc,
        capture_output=True,
        text=True,
        cwd=".",
    )
    assert proc.returncode == 0, f"trace CLI failed: {proc.stderr}"
    assert "FINDING" in proc.stdout or "Spans above threshold" in proc.stdout


def test_cli_trace_json_output():
    clean = _clean_text(300)
    marked = _mark(clean)
    doc = " ".join(clean.split()[:150] + marked.split()[:120])
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai_watermark_toolkit.cli",
            "trace",
            "--key",
            KEY,
            "--window",
            "120",
            "--step",
            "120",
            "--json",
            "--stdin",
        ],
        input=doc,
        capture_output=True,
        text=True,
        cwd=".",
    )
    assert proc.returncode == 0, f"trace CLI failed: {proc.stderr}"
    data = json.loads(proc.stdout)
    assert "windows" in data and "spans" in data
    assert data["finding_windows"] >= 1
