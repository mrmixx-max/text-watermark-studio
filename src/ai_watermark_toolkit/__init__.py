"""Text Watermark Studio — Watermarking Lab Edition.

A taxonomy-driven watermarking laboratory with plugin families for Unicode,
lexical, syntactic, format/layout, sampling-bias, semantic/structure,
localized provenance and training-time ownership workflows.

Provides the public API for watermark detection, cleaning, dilution, and
the full pipeline through :func:`detect_text` and :func:`run_pipeline`.
"""

from __future__ import annotations

from .pipeline import detect_text, run_pipeline

__all__ = [
    "detect_text",
    "pipeline",
    "run_pipeline",
]
__version__ = "2.4.1"
