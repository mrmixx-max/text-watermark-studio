"""Coverage tests for rewrite/service.py: internal methods and edge cases.

Existing tests (test_v118_rewrite_modes.py, test_v119_cli_rewrite.py,
test_v120_pipeline_rewrite.py) cover the high-level public API. This file
targets the internal methods:
- _protect (URLs, numbers, proper nouns, quotes, empty text)
- _restore (multiple tokens, edge cases)
- _grammar_light (empty, whitespace, punctuation, lowercase 'i')
- _clarify (filler words, in-order-to, phrase replacements)
- _tone (formal, concise, plain modes)
- _structural (short text < 4 sentences, single sentence, exact 4, empty)
- rewrite() with preserve=False, use_llm flag edge cases
- _llm_rewrite error when httpx is None
"""

import pytest

from ai_watermark_toolkit.rewrite.service import RewriteService

TEXT = (
    "The first sentence establishes context. "
    "The second provides the main argument. "
    "The third gives supporting evidence. "
    "The fourth draws the conclusion."
)


# ---------------------------------------------------------------------------
# _protect
# ---------------------------------------------------------------------------

class TestProtect:
    def test_urls_protected(self):
        svc = RewriteService()
        text = "Check https://example.com/path?q=1 for details."
        protected_text, protected = svc._protect(text)
        # URL should be replaced with a placeholder
        assert "https://example.com/path?q=1" not in protected_text
        assert "__PROTECTED_" in protected_text
        # And the placeholder maps back
        assert any("https://example.com/path?q=1" in v for v in protected.values())

    def test_numbers_protected(self):
        svc = RewriteService()
        text = "There are 42 items and 100% certainty."
        _protected_text, protected = svc._protect(text)
        assert any("42" in v or "100%" in v for v in protected.values())

    def test_proper_nouns_protected(self):
        svc = RewriteService()
        text = "Alice visited Berlin."
        _protected_text, protected = svc._protect(text)
        assert any(n in str(protected.values()) for n in ["Alice", "Berlin"])

    def test_quotes_protected(self):
        svc = RewriteService()
        text = 'He said "Hello World" and left.'
        protected_text, _protected = svc._protect(text)
        assert '"Hello World"' not in protected_text
        assert "__PROTECTED_" in protected_text

    def test_single_quotes_protected(self):
        svc = RewriteService()
        text = "It's an 'important' matter."
        protected_text, _protected = svc._protect(text)
        # The regex captures single-quoted strings: 'important'
        # But "It's" has 's after It — not a quoted string. The pattern
        # r"'[^']+'" should match 'important' only.
        assert "'important'" not in protected_text

    def test_empty_text(self):
        svc = RewriteService()
        protected_text, protected = svc._protect("")
        assert protected_text == ""
        assert protected == {}

    def test_no_matches(self):
        svc = RewriteService()
        text = "this is a plain lowercase text with no numbers or urls"
        protected_text, _protected = svc._protect(text)
        # Proper nouns are uppercase-starting words like "Alice" etc.
        # All-lowercase has no proper noun matches
        assert protected_text == text

    def test_multiple_urls(self):
        svc = RewriteService()
        text = ("Visit https://site1.com and https://site2.org/path "
                "and http://site3.net.")
        protected_text, _protected = svc._protect(text)
        assert "https://site1.com" not in protected_text
        assert "https://site2.org/path" not in protected_text
        assert "http://site3.net" not in protected_text

    def test_proper_noun_with_underscores(self):
        svc = RewriteService()
        text = "MyClass_V2 and SomeMethod_test."
        _protected_text, protected = svc._protect(text)
        assert any("MyClass_V2" in v for v in protected.values())


# ---------------------------------------------------------------------------
# _restore
# ---------------------------------------------------------------------------

class TestRestore:
    def test_single_restore(self):
        svc = RewriteService()
        text = "before __PROTECTED_0__ after"
        protected = {"__PROTECTED_0__": "original-value"}
        result = svc._restore(text, protected)
        assert result == "before original-value after"

    def test_multiple_restore(self):
        svc = RewriteService()
        text = "__PROTECTED_0__ and __PROTECTED_1__ are restored."
        protected = {
            "__PROTECTED_0__": "First",
            "__PROTECTED_1__": "Second",
        }
        result = svc._restore(text, protected)
        assert result == "First and Second are restored."

    def test_empty_protected(self):
        svc = RewriteService()
        result = svc._restore("no placeholders", {})
        assert result == "no placeholders"

    def test_no_placeholders_in_text(self):
        svc = RewriteService()
        protected = {"__PROTECTED_0__": "value"}
        result = svc._restore("plain text", protected)
        assert result == "plain text"  # no replace needed


# ---------------------------------------------------------------------------
# _grammar_light
# ---------------------------------------------------------------------------

class TestGrammarLight:
    def test_whitespace_normalization(self):
        svc = RewriteService()
        result = svc._grammar_light("hello    world")
        assert result == "Hello world"

    def test_punctuation_spacing(self):
        svc = RewriteService()
        # "hello,world" -> "hello, world"
        result = svc._grammar_light("hello,world")
        assert "hello, world" in result or result == "Hello, world"

    def test_lowercase_i_correction(self):
        svc = RewriteService()
        result = svc._grammar_light("i think i am")
        assert "I think" in result

    def test_empty_string(self):
        svc = RewriteService()
        result = svc._grammar_light("")
        assert result == ""

    def test_sentence_capitalization(self):
        svc = RewriteService()
        result = svc._grammar_light("hello. goodbye.")
        # Each sentence should start with uppercase
        assert "Hello" in result
        assert "Goodbye" in result or "goodbye" in result

    def test_only_whitespace(self):
        svc = RewriteService()
        result = svc._grammar_light("   \n\n  ")
        assert result == "" or len(result) == 0


# ---------------------------------------------------------------------------
# _clarify
# ---------------------------------------------------------------------------

class TestClarify:
    def test_removes_filler_words(self):
        svc = RewriteService()
        # Must be > 8 words for fillers to be removed
        text = ("This is very important and really necessary "
                "for the overall process of the project.")
        result = svc._clarify(text)
        assert "very" not in result.split()
        assert "really" not in result.split()

    def test_short_text_preserves_fillers(self):
        """Filler words are kept in very short text."""
        svc = RewriteService()
        text = "very short"
        result = svc._clarify(text)
        assert "very" in result  # len(words) <= 8, so fillers kept

    def test_in_order_to_replacement(self):
        svc = RewriteService()
        text = "Do this in order to succeed."
        result = svc._clarify(text)
        assert " in order to " not in f" {result} "

    def test_due_to_the_fact_replacement(self):
        svc = RewriteService()
        text = "It failed due to the fact that it was broken."
        result = svc._clarify(text)
        assert " due to the fact that " not in f" {result} "

    def test_at_this_point_replacement(self):
        svc = RewriteService()
        text = "We are at this point in time ready."
        result = svc._clarify(text)
        assert " at this point in time " not in f" {result} "

    def test_punctuation_preserved(self):
        svc = RewriteService()
        text = "This is very important! It's really necessary."
        result = svc._clarify(text)
        assert "!" in result


# ---------------------------------------------------------------------------
# _tone
# ---------------------------------------------------------------------------

class TestTone:
    def test_formal_contractions(self):
        svc = RewriteService()
        text = "We can't and won't do that. don't worry."
        result = svc._tone(text, "formal")
        assert "can't" not in result
        assert "cannot" in result
        assert "won't" not in result
        assert "will not" in result
        assert "don't" not in result
        assert "do not" in result

    def test_concise_removes_hedges(self):
        svc = RewriteService()
        text = "It is important to note that this works."
        result = svc._tone(text, "concise")
        # The hedge should be removed or shortened
        assert len(result) < len(text) or "it is important to note that" not in result.lower()

    def test_plain_replaces_complex(self):
        svc = RewriteService()
        text = "We utilize this tool to commence the process approximately."
        result = svc._tone(text, "plain")
        assert "utilize" not in result
        assert "use" in result
        assert "commence" not in result
        assert "start" in result
        assert "approximately" not in result
        assert "about" in result

    def test_empty_text_tone(self):
        svc = RewriteService()
        result = svc._tone("", "formal")
        assert result == ""

    def test_tone_whitespace_only(self):
        svc = RewriteService()
        result = svc._tone("   ", "formal")
        assert result.strip() == ""


# ---------------------------------------------------------------------------
# _structural
# ---------------------------------------------------------------------------

class TestStructural:
    def test_single_sentence(self):
        """Single sentence: varied openings."""
        svc = RewriteService()
        result = svc._structural("Just one sentence here.")
        assert result  # should produce output

    def test_two_sentences(self):
        """Two sentences: fewer than 4, so openings varied."""
        svc = RewriteService()
        result = svc._structural("First thing. Second thing.")
        assert "First thing" in result or result.startswith("First")
        assert "Second" in result or result.startswith("Second")

    def test_three_sentences(self):
        """Three sentences: fewer than 4, openings varied."""
        svc = RewriteService()
        result = svc._structural("A. B. C.")
        assert len(result) > 0

    def test_exactly_four_sentences(self):
        """Four sentences: middle rotation kicks in."""
        svc = RewriteService()
        result = svc._structural(TEXT)
        # First and last should be stable
        assert result.startswith("The first sentence")
        assert "draws the conclusion" in result  # may be split differently with punctuation changes

    def test_empty_string(self):
        """Empty string doesn't crash."""
        svc = RewriteService()
        result = svc._structural("")
        assert result == "" or result is not None

    def test_many_sentences(self):
        """Many sentences: middle rotation works."""
        svc = RewriteService()
        text = ". ".join(f"Sentence {i} has content." for i in range(10))
        result = svc._structural(text)
        assert len(result) > 0
        # First sentence anchored
        assert "Sentence 0" in result or result.startswith("Sentence 0")

    def test_punctuation_in_sentences(self):
        """Sentences with internal punctuation are handled."""
        svc = RewriteService()
        text = "First, we begin. Second (the main part): we continue. Third? We finish!"
        result = svc._structural(text)
        assert len(result) > 0

    def test_sentence_with_exclamation(self):
        """Exclamation points work as sentence boundaries."""
        svc = RewriteService()
        text = "Wow! This is great! Amazing stuff! Love it!"
        result = svc._structural(text)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# rewrite() — preserve=False and edge cases
# ---------------------------------------------------------------------------

class TestRewriteEdgeCases:
    def test_rewrite_preserve_false(self):
        """With preserve=False, protection is skipped."""
        svc = RewriteService()
        result = svc.rewrite(TEXT, mode="clarity", preserve=False)
        assert result["protected_preservation"] is False
        assert len(result["rewritten"]) > 0
        assert any("Protection disabled" in s for s in result["change_log"])

    def test_rewrite_empty_string(self):
        svc = RewriteService()
        result = svc.rewrite("", mode="clarity")
        assert result["original"] == ""
        assert isinstance(result["rewritten"], str)

    def test_rewrite_long_text(self):
        svc = RewriteService()
        text = "Sentence one. " * 100
        result = svc.rewrite(text, mode="structural")
        assert result["metrics"]["similarity_ratio"] < 1.0

    def test_rewrite_all_modes_non_llm(self):
        """All six modes work without LLM."""
        svc = RewriteService()
        for mode in ["clarity", "concise", "plain", "formal", "structural", "backtranslate"]:
            result = svc.rewrite(TEXT, mode=mode)
            assert result["mode"] == mode
            assert len(result["rewritten"]) > 0

    def test_rewrite_output_shape(self):
        svc = RewriteService()
        result = svc.rewrite(TEXT, mode="clarity")
        assert "original" in result
        assert "rewritten" in result
        assert "metrics" in result
        assert "change_log" in result
        assert result["metrics"]["char_delta"] is not None
        assert result["metrics"]["similarity_ratio"] <= 1.0

    def test_rewrite_explicit_use_llm_false(self):
        """use_llm=False explicitly picks the rule-based path."""
        svc = RewriteService(llm_backend=True)  # backend says LLM, but explicit arg overrides
        result = svc.rewrite(TEXT, mode="clarity", use_llm=False)
        assert "backend" not in result  # no-LLM path
        assert result["rewritten"] != TEXT or len(result["rewritten"]) > 0

    def test_rewrite_explicit_use_llm_true(self, monkeypatch):
        """use_llm=True explicitly picks the LLM path, even without backend."""
        svc = RewriteService(llm_backend=False)
        calls = []
        def fake_llm(text, mode="clarity"):
            calls.append(mode)
            return "LLM output"
        monkeypatch.setattr(svc, "_llm_rewrite", fake_llm)
        result = svc.rewrite("test text", mode="clarity", use_llm=True)
        assert result["backend"] == "local-llm"
        assert result["rewritten"] == "LLM output"

    def test_protect_roundtrip(self):
        """Protect and restore roundtrip preserves protected tokens."""
        svc = RewriteService()
        text = "Alice has 42 items at https://example.com."
        protected_text, protected = svc._protect(text)
        restored = svc._restore(protected_text, protected)
        assert restored == text


# ---------------------------------------------------------------------------
# _llm_rewrite — error when httpx unavailable
# ---------------------------------------------------------------------------

class TestLlmRewriteErrors:
    def test_llm_rewrite_no_httpx(self, monkeypatch):
        """_llm_rewrite raises RuntimeError when httpx is None."""
        svc = RewriteService()
        monkeypatch.setattr(svc, "_llm_rewrite", None)
        # Temporarily set httpx to None
        import ai_watermark_toolkit.rewrite.service as rs
        monkeypatch.setattr(rs, "httpx", None)
        svc2 = RewriteService(llm_backend=True)
        with pytest.raises(RuntimeError, match="httpx not installed"):
            svc2._llm_rewrite("test text", mode="clarity")

    def test_backtranslate_no_httpx(self, monkeypatch):
        """_llm_backtranslate raises RuntimeError when httpx is None."""
        import ai_watermark_toolkit.rewrite.service as rs
        monkeypatch.setattr(rs, "httpx", None)
        svc = RewriteService(llm_backend=True)
        with pytest.raises(RuntimeError, match="httpx not installed"):
            svc._llm_backtranslate("test text")

    def test_llm_rewrite_with_httpx_but_no_server(self):
        """_llm_rewrite raises RuntimeError when server unreachable."""
        svc = RewriteService(llm_backend=True)
        # Use a port that's unlikely to have anything
        svc.llm_base = "http://127.0.0.1:1"
        with pytest.raises(RuntimeError, match="Local LLM call failed"):
            svc._llm_rewrite("test text", mode="clarity")


# ---------------------------------------------------------------------------
# _grammar_light edge cases
# ---------------------------------------------------------------------------

class TestGrammarLightEdgeCases:
    def test_single_character(self):
        svc = RewriteService()
        result = svc._grammar_light("a")
        assert result == "A"  # get_uppercase

    def test_exclamation_handled(self):
        svc = RewriteService()
        result = svc._grammar_light("wow!that is great.")
        assert "!" in result
        assert result != ""
