"""Behavioral tests for the extended unicode classes + aggressive mode
(2026-08-13).

Contract: the standard scanner flags format controls (LRE/BOM/MVS and the
full bidi/zero-width family) but leaves legitimate script fillers (Braille
blank, Hangul fillers) untouched. Aggressive mode adds those fillers —
documented as potentially damaging to genuine content.
"""

from ai_watermark_toolkit.sanitize_unicode import analyze, sanitize


class TestStandardClasses:
    def test_lre_flagged(self):
        assert any(f.cp == "U+202A" for f in analyze("a\u202Ab"))

    def test_bom_flagged(self):
        assert any(f.cp == "U+FEFF" for f in analyze("\uFEFFhello"))

    def test_mongolian_vs_flagged(self):
        assert any(f.cp == "U+180E" for f in analyze("a\u180Eb"))

    def test_deprecated_format_chars_flagged(self):
        assert any(f.cp == "U+206A" for f in analyze("x\u206Ay"))

    def test_lrm_rlm_flagged(self):
        fs = analyze("l\u200Er\u200Fl")
        assert any(f.cp == "U+200E" for f in fs)
        assert any(f.cp == "U+200F" for f in fs)


class TestAggressiveMode:
    def test_braille_blank_not_flagged_by_default(self):
        assert not any(f.cp == "U+2800" for f in analyze("a\u2800b"))

    def test_braille_blank_flagged_aggressive(self):
        fs = analyze("a\u2800b", aggressive=True)
        assert any(f.cp == "U+2800" and f.category == "aggressive_filler" for f in fs)

    def test_hangul_filler_flagged_aggressive(self):
        fs = analyze("a\u3164b", aggressive=True)
        assert any(f.cp == "U+3164" for f in fs)

    def test_object_replacement_flagged_aggressive(self):
        fs = analyze("a\uFFFcb", aggressive=True)
        assert any(f.cp == "U+FFFC" for f in fs)

    def test_mongolian_variation_selector_flagged_aggressive(self):
        fs = analyze("a\u180Bb", aggressive=True)
        assert any(f.cp == "U+180B" for f in fs)

    def test_hangul_choseong_filler_flagged_aggressive(self):
        fs = analyze("a\u115Fb", aggressive=True)
        assert any(f.cp == "U+115F" for f in fs)


class TestSanitizeAggressive:
    def test_aggressive_sanitize_removes_fillers(self):
        text = "Hi\u2800there\u3164x\uFFFCend"
        res = sanitize(text, aggressive=True)
        assert "\u2800" not in res.text
        assert "\u3164" not in res.text
        assert "\uFFFC" not in res.text
        assert res.text == "Hitherexend"

    def test_default_sanitize_keeps_braille(self):
        # legit Braille content survives the standard sanitize
        res = sanitize("a\u2800b")
        assert "\u2800" in res.text
        assert not res.findings

    def test_standard_and_aggressive_counts_differ(self):
        text = "a\u200Bb\u2800c"
        std = len(analyze(text))
        agg = len(analyze(text, aggressive=True))
        assert agg == std + 1  # only the braille blank is extra
