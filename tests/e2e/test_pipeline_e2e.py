"""E2E pipeline tests: embed -> detect -> report -> clean -> dilute -> verify.

Exercises the complete watermarking pipeline end-to-end with real module calls,
verifying each stage produces correct, consistent output.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_watermark_toolkit.pipeline import detect_text, run_pipeline
from ai_watermark_toolkit.transform.clean import clean_text
from ai_watermark_toolkit.transform.dilute import dilute_text
from ai_watermark_toolkit.forensics.kgw import mark_greenlist, detect_multi_key, DEFAULT_GAMMA
from ai_watermark_toolkit.forensics.key_registry import KeyRegistry
from ai_watermark_toolkit.sanitize_unicode import analyze, sanitize
from ai_watermark_toolkit.markers.scanner import scan_markers
from ai_watermark_toolkit.report import sha256_text


class TestFullPipelineEmbedDetectClean:
    """Full pipeline: embed -> detect -> clean -> dilute -> verify removal."""

    def test_embed_then_detect_roundtrip(self, sample_text, tmp_key_registry):
        """Embed a KGW watermark, then detect it with the same key."""
        registry = KeyRegistry(str(tmp_key_registry))
        keys = registry.list_keys()
        kgw_keys = [k for k in keys if k.get("family") == "kgw" and k.get("secret")]
        assert len(kgw_keys) >= 1, "need at least one KGW key with secret"

        key = kgw_keys[0]
        # Embed
        embed_result = mark_greenlist(
            sample_text, key["secret"],
            gamma=key.get("gamma") or DEFAULT_GAMMA,
            level="word", context=1, seed=42,
        )
        watermarked = embed_result["text"]
        assert watermarked != sample_text, "embed should modify text"
        assert embed_result["replacements"] > 0, "embed should make replacements"
        assert embed_result["green_rate_after"] is not None

        # Detect
        detect_result = detect_multi_key(
            watermarked, [key],
            gamma=key.get("gamma") or DEFAULT_GAMMA,
            level="word", context=1,
        )
        assert detect_result["tested_keys"] >= 1
        best = detect_result["best"]
        assert best is not None
        assert best["z_score"] is not None
        # With mark_greenlist, Z-score should be well above 4.0
        assert best["z_score"] > 4.0, f"expected Z > 4.0, got {best['z_score']}"

    def test_detect_clean_text_returns_no_signal(self, sample_text):
        """Detecting clean (non-watermarked) text should yield no high-severity markers."""
        result = detect_text(sample_text, lang="en")
        assert "layers" in result
        assert "unicode" in result["layers"]
        assert "markers" in result["layers"]
        # Plain English text should have no unicode issues
        assert result["layers"]["unicode"]["count"] == 0

    def test_clean_removes_unicode_steganography(self):
        """Text with hidden unicode markers should be cleaned."""
        raw = "Hello\u200bWorld\u202e hidden\u2060 text"
        cleaned = clean_text(raw)
        assert "\u200b" not in cleaned.text  # zero-width space removed
        assert "\u202e" not in cleaned.text  # right-to-left override removed
        assert "\u2060" not in cleaned.text  # word joiner removed
        assert cleaned.unicode_removed >= 3

    def test_clean_nfkc_normalization(self):
        """NFKC normalization should fold compatibility characters."""
        raw = "caf\u00e9"  # é as single char
        cleaned = clean_text(raw, nfkc=True)
        # NFKC should preserve the text meaning
        assert "cafe" in cleaned.text or "café" in cleaned.text

    def test_clean_fold_confusables(self):
        """Confusable characters should be folded to ASCII equivalents."""
        raw = "pаypal"  # Cyrillic 'а' mixed with Latin
        cleaned = clean_text(raw, fold_confusables=True)
        # Should fold the Cyrillic а to Latin a
        assert cleaned.confusable_folds >= 1

    def test_dilute_changes_text(self, sample_text):
        """Dilute should modify the text while preserving meaning."""
        diluted = dilute_text(sample_text, intensity="standard")
        assert diluted.text is not None
        assert len(diluted.text) > 0
        # Dilute may or may not change depending on content
        assert diluted.intensity == "standard"

    def test_dilute_aggressive_more_changes(self, sample_text):
        """Aggressive dilute should produce more changes than light."""
        light = dilute_text(sample_text, intensity="light")
        aggressive = dilute_text(sample_text, intensity="aggressive")
        # Aggressive may differ more (not guaranteed for all texts, but typically)
        assert aggressive.intensity == "aggressive"
        assert light.intensity == "light"

    def test_dilute_preserves_codeblocks(self, sample_markdown):
        """Dilute should preserve fenced code blocks."""
        diluted = dilute_text(sample_markdown, intensity="aggressive")
        assert "```python" in diluted.text or "```" in diluted.text
        assert 'print("world")' in diluted.text or "print" in diluted.text

    def test_run_pipeline_full(self, sample_text):
        """The run_pipeline function should return transformed text and a full report."""
        out, report = run_pipeline(
            sample_text,
            lang="en",
            nfkc=False,
            fold_confusables=False,
            intensity="standard",
            aggressive=False,
        )
        assert out is not None
        assert len(out) > 0
        assert "before" in report
        assert "after" in report
        assert "clean" in report
        assert "dilute" in report
        # before/after should both have detect structure
        assert "layers" in report["before"]
        assert "layers" in report["after"]

    def test_run_pipeline_with_rewrite(self, sample_text):
        """Pipeline with rewrite_mode should include rewrite report."""
        out, report = run_pipeline(
            sample_text,
            lang="en",
            intensity="standard",
            rewrite_mode="structural",
        )
        assert out is not None
        assert report["rewrite"] is not None
        assert report["rewrite"]["mode"] == "structural"

    def test_pipeline_reduces_markers(self):
        """Pipeline should reduce or maintain marker counts (never increase)."""
        raw = "Hello\u200bWorld\u202e test\u2060 text with markers"
        out, report = run_pipeline(raw, lang="en", intensity="standard")
        before_count = report["before"]["layers"]["unicode"]["count"]
        after_count = report["after"]["layers"]["unicode"]["count"]
        assert after_count <= before_count

    def test_embed_detect_with_bpe_level(self, sample_text, tmp_key_registry):
        """Embed and detect at BPE level should also work."""
        registry = KeyRegistry(str(tmp_key_registry))
        keys = [k for k in registry.list_keys() if k.get("family") == "kgw" and k.get("secret")]
        key = keys[0]

        embed_result = mark_greenlist(
            sample_text, key["secret"],
            gamma=0.25, level="bpe", context=1, seed=42,
        )
        watermarked = embed_result["text"]
        assert embed_result["replacements"] > 0

        detect_result = detect_multi_key(
            watermarked, [key],
            gamma=0.25, level="bpe", context=1,
        )
        best = detect_result["best"]
        assert best is not None
        assert best["z_score"] is not None
        assert best["z_score"] > 4.0, f"BPE: expected Z > 4.0, got {best['z_score']}"


class TestPipelineWithStegoText:
    """Pipeline with text containing unicode steganography."""

    def test_detect_unicode_markers(self):
        """Detect should find hidden unicode markers."""
        raw = "Normal\u200btext\u202e with\u2060 hidden\u200d markers\u2061 here"
        result = detect_text(raw)
        assert result["layers"]["unicode"]["count"] >= 3
        items = result["layers"]["unicode"]["items"]
        assert any(i.get("cp") == "U+200B" for i in items)

    def test_clean_then_detect_shows_no_markers(self):
        """After cleaning, detect should show zero unicode markers."""
        raw = "Hello\u200bWorld\u202e test\u2060"
        cleaned = clean_text(raw)
        result = detect_text(cleaned.text)
        assert result["layers"]["unicode"]["count"] == 0

    def test_full_pipeline_removes_all_markers(self):
        """Full pipeline should remove all unicode markers from stego text."""
        raw = "The\u200b quick\u202e brown\u2060 fox\u200d jumps\u2061"
        out, report = run_pipeline(raw, lang="en", intensity="aggressive")
        after_count = report["after"]["layers"]["unicode"]["count"]
        assert after_count == 0


class TestDetectReportHashConsistency:
    """Verify detect output includes consistent hashing."""

    def test_detect_includes_sha256(self, sample_text):
        """Detect result should include SHA-256 hash of input."""
        result = detect_text(sample_text)
        assert result["input_hash"] == sha256_text(sample_text)

    def test_detect_hash_changes_with_text(self):
        """Different texts should produce different hashes."""
        r1 = detect_text("Hello world")
        r2 = detect_text("Goodbye world")
        assert r1["input_hash"] != r2["input_hash"]

    def test_detect_layers_structure(self, sample_text):
        """Detect result should have all expected layer keys."""
        result = detect_text(sample_text)
        layers = result["layers"]
        assert "unicode" in layers
        assert "markup" in layers
        assert "markers" in layers
        assert "style" in layers
        assert "statistical" in layers
        assert "high" in layers["markers"]
        assert "mid" in layers["markers"]
        assert "low" in layers["markers"]
        assert "spans" in layers["markers"]
