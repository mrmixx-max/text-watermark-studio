from __future__ import annotations

from dataclasses import asdict
from .markers.scanner import scan_markers
from .metrics.style_features import compute_style_features
from .metrics.ngram_bias import heuristic_ngram_bias
from .report import sha256_text
from .sanitize_unicode import analyze
from .transform.clean import clean_text
from .transform.dilute import dilute_text


def detect_text(text: str, lang: str = "auto", aggressive: bool = False) -> dict:
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
        "residual_risk": "Heuristic only for statistical signals; not a keyed watermark detector.",
    }


def run_pipeline(text: str, *, lang: str = "auto", nfkc: bool = False, fold_confusables: bool = False, intensity: str = "standard", aggressive: bool = False) -> tuple[str, dict]:
    before = detect_text(text, lang=lang, aggressive=aggressive)
    cleaned = clean_text(text, nfkc=nfkc, fold_confusables=fold_confusables, aggressive=aggressive)
    diluted = dilute_text(cleaned.text, intensity=intensity)
    after = detect_text(diluted.text, lang=lang, aggressive=aggressive)
    report = {
        "before": before,
        "clean": cleaned.to_dict(),
        "dilute": diluted.to_dict(),
        "after": after,
    }
    return diluted.text, report
