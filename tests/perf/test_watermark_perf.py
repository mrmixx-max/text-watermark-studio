"""Performance guardrails for the KGW core (2026-08-17).

These are NOT micro-benchmarks — they are hard latency budgets so a
regression in the hot path (embed → detect → trace) fails CI instead of
silently slowing every watermark operation.

Budgets are deliberately loose (5-10x the observed single-run cost) so
slow CI runners don't flake; they exist to catch asymptotic/algorithmic
regressions, not jitter.
"""

import time

from ai_watermark_toolkit.forensics.kgw import detect_kgw, mark_greenlist
from ai_watermark_toolkit.forensics.trace import trace_kgw

KEY = "benchmark-key-12345"
GAMMA = 0.5
WINDOW = 120


def _doc(n_words: int = 2000) -> str:
    return " ".join(f"neutral benchmark word {i} with ordinary phrasing" for i in range(n_words))


def test_mark_greenlist_latency_budget():
    doc = _doc(2000)
    t0 = time.perf_counter()
    marked = mark_greenlist(doc, KEY, gamma=GAMMA)["text"]
    dt = time.perf_counter() - t0
    assert len(marked.split()) >= 1900, "marking must not collapse the doc"
    assert dt < 30.0, f"mark_greenlist took {dt:.1f}s — regression?"


def test_detect_kgw_latency_budget():
    marked = mark_greenlist(_doc(2000), KEY, gamma=GAMMA)["text"]
    t0 = time.perf_counter()
    res = detect_kgw(marked, KEY, gamma=GAMMA)
    dt = time.perf_counter() - t0
    assert res["verdict"] == "watermark_detected", f"expected detection, got {res['verdict']}"
    assert res["z_score"] >= 4.0, f"expected z>=4, got {res['z_score']}"
    assert dt < 10.0, f"detect_kgw took {dt:.1f}s — regression?"


def test_trace_kgw_latency_budget():
    marked = mark_greenlist(_doc(2000), KEY, gamma=GAMMA)["text"]
    t0 = time.perf_counter()
    trace = trace_kgw(marked, KEY, gamma=GAMMA, window=WINDOW, step=WINDOW, threshold=4.0)
    dt = time.perf_counter() - t0
    assert trace["total_windows"] >= 10, f"expected >=10 windows, got {trace['total_windows']}"
    assert dt < 20.0, f"trace_kgw took {dt:.1f}s — regression?"


def test_embed_detect_roundtrip_deterministic():
    """Identical doc+key must produce identical marking (2026-08-17 fix)."""
    doc = _doc(500)
    a = mark_greenlist(doc, KEY, gamma=GAMMA)["text"]
    b = mark_greenlist(doc, KEY, gamma=GAMMA)["text"]
    assert a == b, "marking is not deterministic for identical doc+key"
