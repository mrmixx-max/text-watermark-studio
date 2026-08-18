"""Core pipeline: detect, clean, dilute, and optionally rewrite text."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .markers.scanner import scan_markers
from .metrics.ngram_bias import heuristic_ngram_bias
from .metrics.style_features import compute_style_features
from .report import sha256_text
from .sanitize_unicode import analyze
from .transform.clean import clean_text
from .transform.dilute import dilute_text


def detect_text(
    text: str,
    lang: str = "auto",
    aggressive: bool = False,
) -> dict[str, Any]:
    """Run the full watermark detection pipeline over *text*.

    Scans Unicode suspicious characters, known LLM marker tokens, style
    features, and n-gram bias signals.  Returns a structured dict with
    per-layer findings and a residual-risk disclaimer.

    Args:
        text: The input string to analyse.
        lang: Language hint used by the marker scanner.  One of
            ``"auto"``, ``"de"``, ``"en"``.
        aggressive: When ``True``, also flag script-specific fillers such as
            Braille blanks and Hangul fillers that standard mode ignores.

    Returns:
        A dictionary with keys ``version``, ``input_hash``, ``layers``,
        ``actions_applied``, and ``residual_risk``.  The ``layers`` dict
        contains ``unicode``, ``markup``, ``markers``, ``style``, and
        ``statistical`` sub-reports.
    """
    unicode_findings = [asdict(x) for x in analyze(text, aggressive=aggressive)]
    markers = [m.to_dict() for m in scan_markers(text, lang=lang)]
    style = compute_style_features(text).to_dict()
    ngram = heuristic_ngram_bias(text).to_dict()
    return {
        "version": 1,
        "input_hash": sha256_text(text),
        "layers": {
            "unicode": {"count": len(unicode_findings), "items": unicode_findings},
            "markup": {"count": 0},
            "markers": {
                "high": sum(1 for m in markers if m["severity"] >= 3),
                "mid": sum(1 for m in markers if m["severity"] == 2),
                "low": sum(1 for m in markers if m["severity"] == 1),
                "spans": markers,
            },
            "style": style,
            "statistical": [ngram],
        },
        "actions_applied": [],
        "residual_risk": (
            "Heuristic only for statistical signals; not a keyed watermark detector."
        ),
    }


def run_pipeline(
    text: str,
    *,
    lang: str = "auto",
    nfkc: bool = False,
    fold_confusables: bool = False,
    intensity: str = "standard",
    aggressive: bool = False,
    rewrite_mode: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Run the full detect → clean → dilute → (optional rewrite) pipeline.

    Measures watermark strength **before** any transform, applies cleaning
    and dilution, optionally rewrites the diluted text, and measures strength
    **after** so the caller can verify the effect.

    Args:
        text: The input string to process.
        lang: Language hint for marker scanning (``"auto"``, ``"de"``,
            ``"en"``).
        nfkc: Apply NFKC Unicode normalisation as part of cleaning.
        fold_confusables: Fold confusable characters during cleaning.
        intensity: Dilution intensity — ``"light"``, ``"standard"``, or
            ``"aggressive"``.
        aggressive: Passed through to :func:`detect_text`; enables script-
            specific filler detection.
        rewrite_mode: Optional rule-based rewrite after dilution.  One of
            ``"structural"``, ``"backtranslate"``, ``"clarity"``,
            ``"concise"``, ``"plain"``, ``"formal"``.  ``None`` (default)
            skips this step.

    Returns:
        A ``(cleaned_diluted_rewritten_text, report_dict)`` pair.  The report
        contains ``before``, ``clean``, ``dilute``, ``rewrite``, and
        ``after`` keys.
    """
    before = detect_text(text, lang=lang, aggressive=aggressive)
    cleaned = clean_text(text, nfkc=nfkc, fold_confusables=fold_confusables, aggressive=aggressive)
    diluted = dilute_text(cleaned.text, intensity=intensity)
    rewritten = diluted.text
    rewrite_report = None
    if rewrite_mode in ("structural", "backtranslate", "clarity", "concise", "plain", "formal"):
        from .rewrite.service import RewriteService

        svc = RewriteService(llm_backend=False)
        r = svc.rewrite(diluted.text, mode=rewrite_mode, preserve=True, use_llm=False)
        rewritten = r["rewritten"]
        rewrite_report = {
            "mode": rewrite_mode,
            "similarity_ratio": r["metrics"]["similarity_ratio"],
            "change_log": r["change_log"],
        }
    after = detect_text(rewritten, lang=lang, aggressive=aggressive)
    report = {
        "before": before,
        "clean": cleaned.to_dict(),
        "dilute": diluted.to_dict(),
        "rewrite": rewrite_report,
        "after": after,
    }
    return rewritten, report
