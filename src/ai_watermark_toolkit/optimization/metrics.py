"""Deterministic evaluation metrics for the prompt optimizer.

Every metric is computable offline (no LLM needed) so the evaluator loop is
reproducible and testable. protected-term preservation is a HARD guardrail:
a rewrite that drops any protected term scores 0 regardless of the rest.

Metrics (0..1 each):
  - protected_term_preservation : all terms (numbers, names, quotes) survive
  - length_ratio                : penalizes collapse or bloat vs. original
  - marker_reduction            : how much AI phrasing the rewrite removed
  - lexical_balance             : changed enough (paraphrase) but not drifted
"""

from __future__ import annotations

from typing import List


def protected_term_preservation(original: str, rewritten: str,
                                terms: List[str]) -> float:
    """1.0 if every protected term survives verbatim, else 0.0 (hard rule)."""
    if not terms:
        return 1.0
    rw_l = rewritten.lower()
    return 1.0 if all(t.lower() in rw_l for t in terms) else 0.0


def length_ratio(original: str, rewritten: str) -> float:
    """1.0 for ~equal length; decays toward 0 when the rewrite collapses
    (<40%) or bloats (>160%)."""
    if not original:
        return 0.0
    ratio = len(rewritten) / len(original)
    if 0.4 <= ratio <= 1.6:
        # linear falloff inside the acceptable band is flat=1.0; outside
        # decays. Simpler: distance from 1.0, clamped.
        return 1.0
    return max(0.0, 1.0 - abs(ratio - 1.0))


def marker_reduction(original: str, rewritten: str) -> float:
    """How many AI phrasing markers were removed by the rewrite (0..1)."""
    try:
        from ..pipeline import detect_text
    except Exception:
        return 0.0
    try:
        before = detect_text(original).get("layers", {})
        after = detect_text(rewritten).get("layers", {})
    except Exception:
        return 0.0

    def _count(d: dict) -> int:
        style = d.get("style_markers") or d.get("stylistic") or {}
        if isinstance(style, dict):
            hits = style.get("hits") or style.get("total") or 0
            try:
                return int(hits)
            except (TypeError, ValueError):
                return 0
        return 0

    b, a = _count(before), _count(after)
    if b == 0:
        return 1.0  # nothing to remove is a perfect score
    return max(0.0, min(1.0, (b - a) / b))


def lexical_balance(original: str, rewritten: str) -> float:
    """Rewritten enough to matter (Jaccard < 0.85) but not drifted
    (Jaccard >= 0.25). 1.0 inside the band, decaying outside."""
    def tokens(s: str) -> set:
        import re
        return {t.lower() for t in re.findall(r"[A-Za-z0-9\u00C0-\u024F]+", s)}
    o, r = tokens(original), tokens(rewritten)
    if not o:
        return 0.0
    jaccard = len(o & r) / len(o | r)
    if 0.25 <= jaccard <= 0.85:
        return 1.0
    if jaccard > 0.85:  # barely changed
        return max(0.0, (1.0 - jaccard) / 0.15)
    return max(0.0, jaccard / 0.25)


def composite(original: str, rewritten: str, terms: List[str]) -> dict:
    """Weighted composite with the hard guardrail applied first."""
    guard = protected_term_preservation(original, rewritten, terms)
    m = {
        "protected_term_preservation": guard,
        "length_ratio": length_ratio(original, rewritten),
        "marker_reduction": marker_reduction(original, rewritten),
        "lexical_balance": lexical_balance(original, rewritten),
    }
    weights = {"protected_term_preservation": 0.4,
               "length_ratio": 0.15,
               "marker_reduction": 0.25,
               "lexical_balance": 0.2}
    if guard < 1.0:
        score = 0.0  # hard guardrail: protected terms lost
    else:
        score = sum(m[k] * weights[k] for k in weights)
    return {"metrics": m, "score": round(score, 4), "guardrail_passed": guard >= 1.0}
