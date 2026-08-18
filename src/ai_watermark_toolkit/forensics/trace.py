"""Sliding-window Z-score trajectory for long documents.

A single KGW Z-test over a whole document averages away local signals: a
manuscript that is 80% human with one embedded, heavily watermarked AI
chapter still yields a modest global Z. ``trace_kgw`` slides a window over
the text and reports the Z-score per window, so the spike (or redlist drop)
becomes visible at the exact span where it happens.

Design notes:

* Windows are measured in WORDS, not characters, because KGW scores tokens.
  ``window`` words with ``step`` words of overlap produce a trajectory
  that maps 1:1 onto paragraphs/sections of the document.
* Statistics need n: a window of 10 words cannot carry a Z-test. The
  detector already returns ``verdict: too_short`` below 10 scored tokens;
  ``trace_kgw`` keeps those windows in the output (``z_score: None``) so the
  trajectory stays contiguous, but flags ``reliable: False``.
* Segment detection: a window is a ``finding`` when its Z-score crosses the
  threshold (default z >= 4, matching ``detect_kgw``'s watermark_detected).
  Adjacent finding windows are merged into spans so the report says "chapter
  12, words 1200-1600" instead of 9 separate windows.
* The whole-document Z is included for reference (``whole_doc``) so the user
  can see how much the global view diluted the local signal.
"""

from __future__ import annotations

from typing import Any

from .kgw import DEFAULT_GAMMA, detect_kgw, tokenize


def _windows(tokens: list[str], window: int, step: int) -> list[dict[str, Any]]:
    """Split token list into overlapping windows with word offsets."""
    out: list[dict[str, Any]] = []
    n = len(tokens)
    if n == 0:
        return out
    if window <= 0:
        window = 500
    if step <= 0:
        step = window
    start = 0
    idx = 0
    while start < n:
        end = min(start + window, n)
        out.append(
            {
                "index": idx,
                "start_word": start,
                "end_word": end,
                "text": " ".join(tokens[start:end]),
            }
        )
        idx += 1
        if end >= n:
            break
        start += step
    return out


def trace_kgw(
    text: str,
    key: str,
    gamma: float = DEFAULT_GAMMA,
    level: str = "word",
    context: int = 1,
    window: int = 500,
    step: int | None = None,
    threshold: float = 4.0,
    signature_filter: bool = False,
) -> dict[str, Any]:
    """Sliding-window KGW Z-score trajectory over a long text.

    Returns a dict with ``windows`` (one entry per window: index, word
    offsets, z_score, verdict, reliable), ``spans`` (merged adjacent finding
    windows), ``whole_doc`` (single Z-test over the full text), and summary
    counts. Windows too short for a Z-test carry ``z_score: None`` and
    ``reliable: False`` but remain in the trajectory.
    """
    tokens = tokenize(text, level=level)
    if not tokens:
        return {
            "windows": [],
            "spans": [],
            "whole_doc": None,
            "total_windows": 0,
            "finding_windows": 0,
            "window_words": window,
            "step_words": step or window,
            "threshold": threshold,
            "level": level,
        }
    step = step or window
    windows = _windows(tokens, window, step)
    results: list[dict[str, Any]] = []
    finding_windows: list[int] = []
    for w in windows:
        r = detect_kgw(
            w["text"],
            key,
            gamma=gamma,
            level=level,
            context=context,
            signature_filter=signature_filter,
        )
        z = r.get("z_score")
        reliable = r.get("verdict") != "too_short"
        is_finding = reliable and z is not None and z >= threshold
        if is_finding:
            finding_windows.append(w["index"])
        results.append(
            {
                "index": w["index"],
                "start_word": w["start_word"],
                "end_word": w["end_word"],
                "z_score": z,
                "verdict": r.get("verdict"),
                "reliable": reliable,
                "finding": bool(is_finding),
            }
        )
    # Merge adjacent finding windows into spans.
    spans: list[dict[str, Any]] = []
    if finding_windows:
        cur = [finding_windows[0]]
        for i in finding_windows[1:]:
            if i == cur[-1] + 1:
                cur.append(i)
            else:
                spans.append(_span_from_windows(cur, results))
                cur = [i]
        spans.append(_span_from_windows(cur, results))
    whole = detect_kgw(
        text,
        key,
        gamma=gamma,
        level=level,
        context=context,
        signature_filter=signature_filter,
    )
    return {
        "windows": results,
        "spans": spans,
        "whole_doc": whole,
        "total_windows": len(results),
        "finding_windows": len(finding_windows),
        "window_words": window,
        "step_words": step,
        "threshold": threshold,
        "level": level,
    }


def _span_from_windows(indexes: list[int], results: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a span (start/end word offsets + peak z) from window indexes."""
    entries = [r for r in results if r["index"] in indexes]
    if not entries:
        return {"start_word": 0, "end_word": 0, "peak_z": None, "windows": indexes}
    start = min(e["start_word"] for e in entries)
    end = max(e["end_word"] for e in entries)
    zs = [e["z_score"] for e in entries if e["z_score"] is not None]
    peak = max(zs) if zs else None
    return {
        "start_word": start,
        "end_word": end,
        "peak_z": peak,
        "windows": indexes,
    }


def format_trace(trace: dict[str, Any], text: str | None = None, context_chars: int = 80) -> str:
    """Human-readable trajectory report for CLI output."""
    lines: list[str] = []
    lines.append(
        f"KGW Z-score trajectory: {trace['total_windows']} windows"
        f" (window={trace['window_words']}w, step={trace['step_words']}w,"
        f" threshold z>={trace['threshold']})"
    )
    w = trace.get("whole_doc") or {}
    wz = w.get("z_score")
    lines.append(
        f"Whole document: z={wz} ({w.get('verdict')})"
        + (" — note how the global view dilutes local spikes" if wz is not None and wz < trace["threshold"] else "")
    )
    if not trace["windows"]:
        lines.append("(empty text)")
        return "\n".join(lines)
    # Compact per-window line: index, word range, z, marker.
    for e in trace["windows"]:
        z = e["z_score"]
        zs = f"{z:+.2f}" if z is not None else "  n/a"
        mark = "  <<< FINDING" if e["finding"] else ""
        lines.append(f"  w{e['index']:>3} words {e['start_word']:>5}-{e['end_word']:>5}  z={zs}{mark}")
    if trace["spans"]:
        lines.append("")
        lines.append("Spans above threshold:")
        for s in trace["spans"]:
            peak = f"{s['peak_z']:+.2f}" if s["peak_z"] is not None else "n/a"
            excerpt = ""
            if text is not None:
                excerpt = _excerpt(text, s["start_word"], s["end_word"], context_chars)
            lines.append(f"  words {s['start_word']}-{s['end_word']}  peak z={peak}  windows={s['windows']}")
            if excerpt:
                lines.append(f"    …{excerpt}…")
    else:
        lines.append("")
        lines.append("No window above threshold.")
    return "\n".join(lines)


def _excerpt(text: str, start_word: int, end_word: int, context_chars: int) -> str:
    """Return a short context window around the span in the original text."""
    words = text.split()
    span_words = words[start_word:end_word]
    if not span_words:
        return ""
    snippet = " ".join(span_words)
    if len(snippet) <= context_chars * 2:
        return snippet
    return snippet[:context_chars]
