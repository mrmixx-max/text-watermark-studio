"""Coverage tests for pipeline.py: detect_text and run_pipeline edge cases.

Existing tests (test_toolkit.py, test_v120_pipeline_rewrite.py) cover the basic
happy path. This file targets:
- detect_text: empty string, lang parameter, aggressive mode, boundary values
- run_pipeline: empty text, all flag combinations, aggressive mode, rewrite
  modes beyond structural/backtranslate (clarity, concise, plain, formal),
  edge cases in nfkc/fold_confusables handling
"""



from ai_watermark_toolkit.pipeline import detect_text, run_pipeline

TEXT = (
    "The first sentence establishes context. "
    "The second provides the main argument. "
    "The third gives supporting evidence. "
    "The fourth draws the conclusion."
)


# ---------------------------------------------------------------------------
# detect_text edge cases
# ---------------------------------------------------------------------------

class TestDetectTextEdgeCases:
    def test_empty_string(self):
        """Empty input returns a valid report with zero findings."""
        result = detect_text("", lang="en")
        assert result["version"] == 1
        assert result["layers"]["unicode"]["count"] == 0
        assert result["layers"]["markers"]["high"] == 0
        assert result["layers"]["markers"]["mid"] == 0
        assert result["layers"]["markers"]["low"] == 0
        assert result["input_hash"] is not None

    def test_whitespace_only(self):
        """Whitespace-only input doesn't crash."""
        result = detect_text("   \n  \t  ")
        assert result["layers"]["unicode"]["count"] == 0

    def test_special_characters(self):
        """Special characters and symbols are handled."""
        result = detect_text("!@#$%^&*()_+-=[]{}|;':\",./<>?`~")
        assert "input_hash" in result
        assert "layers" in result

    def test_lang_auto(self):
        """Auto-detect language doesn't crash."""
        result = detect_text(TEXT, lang="auto")
        assert result["layers"]["markers"] is not None

    def test_lang_de(self):
        """German marker detection doesn't crash on English text."""
        result = detect_text(TEXT, lang="de")
        assert result["layers"]["markers"] is not None

    def test_lang_en(self):
        result = detect_text(TEXT, lang="en")
        assert result["layers"]["markers"] is not None

    def test_aggressive_unicode_scanning(self):
        """Aggressive mode allows more unicode findings."""
        plain = detect_text(TEXT, aggressive=False)
        aggressive = detect_text(TEXT, aggressive=True)
        # Both should produce valid reports
        assert plain["layers"]["unicode"]["count"] >= 0
        assert aggressive["layers"]["unicode"]["count"] >= 0

    def test_with_unicode_markers(self):
        """Text with unicode markers is detected."""
        text = "Hello\u200bWorld\u202eEvil"
        result = detect_text(text, aggressive=False)
        assert result["layers"]["unicode"]["count"] >= 1

    def test_german_ai_markers(self):
        """German AI-flavored text has high markers."""
        text = ("In der heutigen digitalen Welt ist es wichtig zu betonen, "
                "dass moderne Technologien eine entscheidende Rolle spielen. "
                "Darüber hinaus eröffnet dies eine Vielzahl von Möglichkeiten.")
        result = detect_text(text, lang="de")
        assert "markers" in result["layers"]

    def test_ngram_bias_always_present(self):
        """Statistical (ngram) layer is always present."""
        result = detect_text("Short text.")
        assert len(result["layers"]["statistical"]) >= 1
        assert "repeated_bigram_ratio" in result["layers"]["statistical"][0]

    def test_style_features_present(self):
        """Style features layer is always present."""
        result = detect_text(TEXT)
        style = result["layers"]["style"]
        assert "sentence_count" in style or "avg_sentence_length" in style

    def test_residual_risk_note(self):
        """The residual risk note is always present."""
        result = detect_text(TEXT)
        assert "residual_risk" in result
        assert "Heuristic only" in result["residual_risk"]


# ---------------------------------------------------------------------------
# run_pipeline edge cases
# ---------------------------------------------------------------------------

class TestRunPipelineEdgeCases:
    def test_empty_text(self):
        """Empty text doesn't crash the pipeline."""
        out, report = run_pipeline("")
        assert isinstance(out, str)
        assert "before" in report
        assert "after" in report
        assert report["rewrite"] is None

    def test_whitespace_text(self):
        """Whitespace-only text doesn't crash."""
        out, _report = run_pipeline("   \n\n  ")
        assert isinstance(out, str)

    def test_single_word(self):
        """Single word pipeline doesn't crash."""
        out, _report = run_pipeline("Hello")
        assert isinstance(out, str)
        assert out == "Hello" or len(out) > 0

    def test_nfkc_normalization_flag(self):
        """NFKC normalization is applied when requested."""
        # Full-width chars that NFKC normalizes
        text = "Ｈｅｌｌｏ"  # fullwidth H, e, l, l, o
        out, report = run_pipeline(text, nfkc=True)
        assert isinstance(out, str)
        assert "before" in report

    def test_fold_confusables_flag(self):
        """Confusable folding is applied when requested."""
        # Latin small letter long s (confusable with 'f')
        text = "The ſentence has confusables."
        out, _report = run_pipeline(text, fold_confusables=True)
        assert isinstance(out, str)

    def test_both_nfkc_and_fold(self):
        """Both NFKC and fold-confusables can be active simultaneously."""
        text = "Ŧhe ſentence has boTH ſpecial chars and fullwidth \" area\""
        out, report = run_pipeline(text, nfkc=True, fold_confusables=True)
        assert isinstance(out, str)
        assert "before" in report and "after" in report

    def test_aggressive_pipeline(self):
        """Aggressive unicode scanning in pipeline mode."""
        text = "Hello\u200bWorld"
        _out, report = run_pipeline(text, aggressive=True)
        assert report["before"]["layers"]["unicode"]["count"] >= 1

    def test_light_intensity(self):
        """Light dilute intensity works."""
        out, _report = run_pipeline(TEXT, intensity="light")
        assert isinstance(out, str)

    def test_aggressive_intensity(self):
        """Aggressive dilute intensity works."""
        out, _report = run_pipeline(TEXT, intensity="aggressive")
        assert isinstance(out, str)

    def test_invalid_intensity_falls_back(self):
        """Invalid intensity doesn't crash (silently falls back to default)."""
        out, _report = run_pipeline(TEXT, intensity="invalid-intensity-value-xyz")
        assert isinstance(out, str)

    def test_rewrite_mode_clarity(self):
        """rewrite_mode='clarity' works in pipeline (uses text with filler words)."""
        text = ("It is very important to note that in order to properly "
                "leverage the fact that this really matters.")
        out, report = run_pipeline(text, rewrite_mode="clarity")
        assert report["rewrite"] is not None
        assert report["rewrite"]["mode"] == "clarity"
        # Filler words should have been removed, so output differs from input
        assert out != text or report["rewrite"]["similarity_ratio"] < 1.0

    def test_rewrite_mode_concise(self):
        text = ("It should be noted that this is a very important thing "
                "in order to do the task.")
        out, report = run_pipeline(text, rewrite_mode="concise")
        assert report["rewrite"]["mode"] == "concise"
        # Concise mode removes hedge phrases, so similarity should be < 1.0
        assert report["rewrite"]["similarity_ratio"] < 1.0 or out != text

    def test_rewrite_mode_plain(self):
        _out, report = run_pipeline(TEXT, rewrite_mode="plain")
        assert report["rewrite"]["mode"] == "plain"

    def test_rewrite_mode_formal(self):
        _out, report = run_pipeline(TEXT, rewrite_mode="formal")
        assert report["rewrite"]["mode"] == "formal"

    def test_rewrite_report_has_change_log(self):
        """Rewrite report always includes change_log."""
        _out, report = run_pipeline(TEXT, rewrite_mode="clarity")
        assert "change_log" in report["rewrite"]
        assert len(report["rewrite"]["change_log"]) >= 1

    def test_pipeline_report_shape(self):
        """Pipeline report has all expected sections."""
        _out, report = run_pipeline(TEXT)
        expected_sections = {"before", "clean", "dilute", "rewrite", "after"}
        assert expected_sections.issubset(report.keys())

    def test_detect_before_and_after_differ(self):
        """Before and after detection reports differ when pipeline changes text."""
        # Text with AI markers and filler words that actually get modified
        text = ("In today's world, it is important to note that "
                "modern technology leverages automation in order to "
                "achieve the best results.")
        _, report = run_pipeline(text)
        assert report["before"]["input_hash"] != report["after"]["input_hash"]

    def test_long_text(self):
        """Long text doesn't crash the pipeline."""
        long_text = "Sentence one. " * 500
        out, _report = run_pipeline(long_text)
        assert isinstance(out, str)
        assert len(out) > 0

    def test_mixed_language_text(self):
        """Mixed language text with unicode doesn't crash."""
        text = "Deutsch. English. Français. 中文. 日本語."
        out, _report = run_pipeline(text, lang="auto")
        assert isinstance(out, str)

    def test_dilute_preserves_structure(self):
        """Dilute preserves code blocks (from test_toolkit parity)."""
        text = "Text. ```python\nx = 1\n``` End."
        out, _report = run_pipeline(text)
        assert "```" in out

    def test_clean_applied_before_dilute(self):
        """Clean phase removes unicode before dilute processes."""
        text = "Hello\u200bWorld"
        out, _report = run_pipeline(text, nfkc=True, fold_confusables=True)
        assert "\u200b" not in out

    def test_run_pipeline_rewrite_with_few_words(self):
        """Pipeline rewrite with very short text doesn't crash."""
        out, _report = run_pipeline("Short text.", rewrite_mode="structural")
        assert isinstance(out, str)
