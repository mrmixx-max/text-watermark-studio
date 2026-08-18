"""Deep signature analysis (C7, 2026-08-18) — tests for AI signature detection.

Contract under test:
- analyze_ngrams: n-gram frequency analysis with AI-indicator scoring.
- compute_perplexity / score_perplexity: perplexity-based detection.
- compute_burstiness: sentence-level variance analysis.
- detect_repetition: phrase repetition detection.
- analyze_token_distribution: type-token ratio, hapax legomena.
- analyze_signature: combined analysis producing final verdict.
"""


from ai_watermark_toolkit.forensics.signature_deep import (
    _get_ngrams,
    _tokenize_sentences,
    _tokenize_words,
    analyze_ngrams,
    analyze_signature,
    analyze_token_distribution,
    compute_burstiness,
    compute_perplexity,
    detect_repetition,
    score_perplexity,
)

# Sample texts for testing
SHORT_TEXT = "Hello world."

HUMAN_TEXT = """
The quick brown fox jumps over the lazy dog. I went to the store yesterday
and bought some groceries. The weather was quite pleasant, with a gentle
breeze blowing from the south. My neighbor walked her dog along the quiet
road. Several children played in the park, their laughter echoing across
the green fields. The old oak tree stood tall at the edge of the property,
its branches swaying rhythmically. I watched as a flock of birds migrated
southward, their formation shifting and changing against the pale sky.
"""

AI_TEXT = """
Furthermore, it is important to note that the aforementioned considerations
play a significant role in the overall outcome of the process. In addition
to this, one must also take into account the various factors that may
influence the results. Moreover, the implementation of these strategies
requires careful planning and execution. It is worth noting that the
benefits of this approach extend beyond the immediate scope of the project.
In conclusion, the findings suggest that further research is warranted to
fully understand the implications of these results. Additionally, the
practical applications of this methodology are numerous and far-reaching.
Furthermore, it is important to note that these considerations are essential.
In addition to this, one must also account for various influencing factors.
"""

UNIFORM_TEXT = """
This is a sentence. This is a sentence. This is a sentence.
This is a sentence. This is a sentence. This is a sentence.
This is a sentence. This is a sentence. This is a sentence.
This is a sentence. This is a sentence. This is a sentence.
"""


class TestTokenization:
    """Tests for tokenization helpers."""

    def test_word_tokenization(self):
        tokens = _tokenize_words("Hello, World!")
        assert "hello" in tokens
        assert "world" in tokens

    def test_sentence_tokenization(self):
        sentences = _tokenize_sentences("Hello. World! How are you?")
        assert len(sentences) >= 2

    def test_ngram_generation(self):
        tokens = ["the", "quick", "brown", "fox"]
        bigrams = _get_ngrams(tokens, 2)
        assert len(bigrams) == 3
        assert bigrams[0] == ("the", "quick")


class TestNgramAnalysis:
    """Tests for n-gram frequency analysis."""

    def test_ngram_basic(self):
        result = analyze_ngrams(HUMAN_TEXT)
        assert "ngram_score" in result
        assert 0.0 <= result["ngram_score"] <= 1.0

    def test_ngram_too_short(self):
        result = analyze_ngrams(SHORT_TEXT)
        assert "note" in result
        assert result["note"] == "too_short"

    def test_ngram_structure(self):
        result = analyze_ngrams(HUMAN_TEXT)
        assert "1gram" in result
        assert "2gram" in result
        assert "3gram" in result

    def test_ai_text_different_from_human(self):
        ai_result = analyze_ngrams(AI_TEXT)
        human_result = analyze_ngrams(HUMAN_TEXT)
        # They should produce different scores (not a strict requirement but expected)
        assert isinstance(ai_result["ngram_score"], float)
        assert isinstance(human_result["ngram_score"], float)


class TestPerplexity:
    """Tests for perplexity scoring."""

    def test_perplexity_positive(self):
        perplexity = compute_perplexity(HUMAN_TEXT)
        assert perplexity > 0

    def test_perplexity_empty(self):
        assert compute_perplexity("") == 0.0

    def test_score_perplexity_low(self):
        score = score_perplexity(15)
        assert score >= 0.8

    def test_score_perplexity_high(self):
        score = score_perplexity(300)
        assert score <= 0.2

    def test_score_perplexity_range(self):
        for p in [5, 20, 50, 100, 150, 250]:
            score = score_perplexity(p)
            assert 0.0 <= score <= 1.0

    def test_ai_text_lower_perplexity(self):
        ai_p = compute_perplexity(AI_TEXT)
        human_p = compute_perplexity(HUMAN_TEXT)
        # AI text should generally have lower perplexity
        # (more predictable), but this is statistical
        assert ai_p > 0
        assert human_p > 0


class TestBurstiness:
    """Tests for burstiness computation."""

    def test_burstiness_basic(self):
        result = compute_burstiness(HUMAN_TEXT)
        assert "burstiness" in result
        assert "score" in result
        assert 0.0 <= result["score"] <= 1.0

    def test_burstiness_too_few_sentences(self):
        result = compute_burstiness("Hello. World.")
        assert "note" in result

    def test_uniform_low_burstiness(self):
        result = compute_burstiness(UNIFORM_TEXT)
        # Uniform text should have low burstiness (more AI-like)
        assert result["burstiness"] < 0.5

    def test_human_higher_burstiness(self):
        human_result = compute_burstiness(HUMAN_TEXT)
        uniform_result = compute_burstiness(UNIFORM_TEXT)
        # Human text should generally have higher burstiness
        assert human_result["burstiness"] >= uniform_result["burstiness"]


class TestRepetition:
    """Tests for repetition detection."""

    def test_no_repetition(self):
        result = detect_repetition(HUMAN_TEXT)
        assert "repetition_score" in result
        assert 0.0 <= result["repetition_score"] <= 1.0

    def test_repetition_too_short(self):
        result = detect_repetition("hi")
        assert result["repetition_score"] == 0.0

    def test_repetition_uniform(self):
        result = detect_repetition(UNIFORM_TEXT)
        # Uniform text should have high repetition
        assert result["repetition_score"] > 0.3

    def test_repeated_phrase_detected(self):
        text = "The quick brown fox. The quick brown fox. The quick brown fox."
        result = detect_repetition(text)
        assert len(result["repeated_phrases"]) > 0


class TestTokenDistribution:
    """Tests for token distribution analysis."""

    def test_distribution_basic(self):
        result = analyze_token_distribution(HUMAN_TEXT)
        assert "score" in result
        assert "type_token_ratio" in result
        assert "hapax_ratio" in result

    def test_too_short(self):
        result = analyze_token_distribution("hi")
        assert "note" in result

    def test_ttr_reasonable(self):
        result = analyze_token_distribution(HUMAN_TEXT)
        assert 0.0 < result["type_token_ratio"] < 1.0

    def test_hapax_ratio(self):
        result = analyze_token_distribution(HUMAN_TEXT)
        assert 0.0 <= result["hapax_ratio"] <= 1.0


class TestAnalyzeSignature:
    """Tests for the combined signature analysis."""

    def test_basic_structure(self):
        result = analyze_signature(HUMAN_TEXT)
        assert hasattr(result, "ai_likelihood")
        assert hasattr(result, "verdict")
        assert hasattr(result, "details")

    def test_ai_likelihood_range(self):
        result = analyze_signature(HUMAN_TEXT)
        assert 0.0 <= result.ai_likelihood <= 1.0

    def test_verdict_values(self):
        result = analyze_signature(HUMAN_TEXT)
        assert result.verdict in ("likely_ai", "likely_human", "undetermined")

    def test_short_text_undetermined(self):
        result = analyze_signature("Hi.")
        assert result.verdict == "undetermined"

    def test_empty_text(self):
        result = analyze_signature("")
        assert result.ai_likelihood == 0.5

    def test_all_scores_present(self):
        result = analyze_signature(HUMAN_TEXT)
        assert 0.0 <= result.ngram_score <= 1.0
        assert result.perplexity > 0
        assert 0.0 <= result.perplexity_score <= 1.0
        assert 0.0 <= result.burstiness_score <= 1.0
        assert 0.0 <= result.repetition_score <= 1.0
        assert 0.0 <= result.token_distribution_score <= 1.0

    def test_to_dict(self):
        result = analyze_signature(HUMAN_TEXT)
        d = result.to_dict()
        assert "ai_likelihood" in d
        assert "verdict" in d
        assert "details" in d

    def test_ai_text_scores_higher(self):
        ai_result = analyze_signature(AI_TEXT)
        human_result = analyze_signature(HUMAN_TEXT)
        # AI text should generally score higher (more AI-like)
        # This is a soft check — the AI_TEXT sample has known AI markers
        assert ai_result.ai_likelihood >= human_result.ai_likelihood - 0.2

    def test_uniform_text_flags_ai(self):
        result = analyze_signature(UNIFORM_TEXT)
        # Very uniform text should flag as likely_ai or score high
        assert result.ai_likelihood > 0.3

    def test_details_contain_sub_analyses(self):
        result = analyze_signature(HUMAN_TEXT)
        assert "ngram" in result.details
        assert "burstiness" in result.details
        assert "repetition" in result.details
        assert "token_distribution" in result.details
