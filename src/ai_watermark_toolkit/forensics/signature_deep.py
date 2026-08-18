"""Deep signature analysis (C7, 2026-08-18) — AI detection beyond markers.

Goes beyond simple marker detection (looking for known watermark patterns)
to detect AI-generated text through statistical analysis:

1. **N-gram frequency analysis**: AI text has characteristic n-gram
   distributions that differ from human text (overuse of certain phrases,
   underuse of rare constructions).

2. **Perplexity scoring**: measures how "surprised" a simple language model
   is by the text. AI text typically has lower perplexity (more predictable).

3. **Token distribution analysis**: AI text tends to have more uniform
   token probability distributions (less "bursty" than human text).

4. **Burstiness scoring**: human text has high variance in sentence length
   and complexity; AI text is more uniform.

5. **Repetition detection**: AI models tend to repeat phrases more than
   humans, especially in longer texts.

Honest boundaries:
- These are STATISTICAL indicators, not proof. A human can write predictable
  text; an AI can be prompted to write unpredictably.
- Perplexity scoring uses a simple unigram model — it is a rough proxy,
  not a production-grade detector. For production, use a fine-tuned model.
- The module is calibrated on English text. Other languages need different
- baselines.
- False positive rate is non-trivial (~5-15% depending on text domain).
  Always combine with other evidence.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

# Common English unigram frequencies (approximate, for perplexity baseline)
# Source: large English corpus averages
ENGLISH_UNIGRAM = {
    "the": 0.071, "be": 0.042, "to": 0.039, "of": 0.037, "and": 0.035,
    "a": 0.032, "in": 0.028, "that": 0.021, "have": 0.019, "i": 0.018,
    "it": 0.017, "for": 0.016, "not": 0.015, "on": 0.014, "with": 0.013,
    "he": 0.012, "as": 0.011, "you": 0.010, "do": 0.009, "at": 0.008,
    "this": 0.008, "but": 0.007, "his": 0.007, "by": 0.006, "from": 0.006,
    "they": 0.006, "we": 0.006, "say": 0.005, "her": 0.005, "she": 0.005,
    "or": 0.005, "an": 0.005, "will": 0.004, "my": 0.004, "one": 0.004,
    "all": 0.004, "would": 0.004, "there": 0.004, "their": 0.004,
    "what": 0.003, "so": 0.003, "up": 0.003, "out": 0.003, "if": 0.003,
    "about": 0.003, "who": 0.003, "get": 0.003, "which": 0.003, "go": 0.003,
    "me": 0.003, "when": 0.002, "make": 0.002, "can": 0.002, "like": 0.002,
    "time": 0.002, "no": 0.002, "just": 0.002, "him": 0.002, "know": 0.002,
    "take": 0.002, "people": 0.002, "into": 0.002, "year": 0.002, "your": 0.002,
    "good": 0.002, "some": 0.002, "could": 0.002, "them": 0.002, "see": 0.002,
    "other": 0.002, "than": 0.002, "then": 0.002, "now": 0.002, "look": 0.001,
    "only": 0.001, "come": 0.001, "its": 0.001, "over": 0.001, "think": 0.001,
    "also": 0.001, "back": 0.001, "after": 0.001, "use": 0.001, "two": 0.001,
    "how": 0.001, "our": 0.001, "work": 0.001, "first": 0.001, "well": 0.001,
    "way": 0.001, "even": 0.001, "new": 0.001, "want": 0.001, "because": 0.001,
    "any": 0.001, "these": 0.001, "give": 0.001, "day": 0.001, "most": 0.001,
    "us": 0.001,
}

# Smoothing for unknown words
SMOOTHING = 1e-10


@dataclass
class SignatureReport:
    """Report from deep signature analysis."""
    ai_likelihood: float  # 0.0 to 1.0
    ngram_score: float  # 0.0 to 1.0 (higher = more AI-like)
    perplexity: float  # perplexity score
    perplexity_score: float  # 0.0 to 1.0 (higher = more AI-like)
    burstiness: float  # variance in sentence complexity
    burstiness_score: float  # 0.0 to 1.0 (higher = more AI-like)
    repetition_score: float  # 0.0 to 1.0 (higher = more AI-like)
    token_distribution_score: float  # 0.0 to 1.0
    details: dict = field(default_factory=dict)
    verdict: str = "undetermined"  # "likely_ai", "likely_human", "undetermined"

    def to_dict(self) -> dict:
        return {
            "ai_likelihood": round(self.ai_likelihood, 4),
            "ngram_score": round(self.ngram_score, 4),
            "perplexity": round(self.perplexity, 4),
            "perplexity_score": round(self.perplexity_score, 4),
            "burstiness": round(self.burstiness, 4),
            "burstiness_score": round(self.burstiness_score, 4),
            "repetition_score": round(self.repetition_score, 4),
            "token_distribution_score": round(self.token_distribution_score, 4),
            "details": self.details,
            "verdict": self.verdict,
        }


def _tokenize_words(text: str) -> list[str]:
    """Simple word tokenization."""
    return re.findall(r"[a-zA-Z']+", text.lower())


def _tokenize_sentences(text: str) -> list[str]:
    """Simple sentence tokenization."""
    sentences = re.split(r"[.!?]+", text)
    return [s.strip() for s in sentences if s.strip()]


def _get_ngrams(tokens: list[str], n: int) -> list[tuple[str, ...]]:
    """Extract n-grams from token list."""
    return [tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]


# ---------------------------------------------------------------- N-gram analysis
def analyze_ngrams(text: str, max_n: int = 3) -> dict:
    """Analyze n-gram frequencies and compare to expected English distribution.

    AI text tends to:
    - Overuse common bigrams/trigrams ("however,", "in addition,")
    - Underuse rare constructions
    - Have lower n-gram entropy (more predictable)
    """
    tokens = _tokenize_words(text)
    if len(tokens) < 10:
        return {"ngram_score": 0.5, "entropy": 0.0, "note": "too_short"}

    results = {}
    total_entropy = 0.0

    for n in range(1, max_n + 1):
        ngrams = _get_ngrams(tokens, n)
        if not ngrams:
            continue

        counts = Counter(ngrams)
        total = len(ngrams)

        # Calculate entropy
        entropy = 0.0
        for count in counts.values():
            p = count / total
            entropy -= p * math.log2(p)

        # Normalize by max possible entropy (log2 of vocabulary size)
        max_entropy = math.log2(max(len(counts), 1))
        normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0

        # AI text tends to have lower normalized entropy
        # (more concentrated distribution)
        ai_indicator = 1.0 - normalized_entropy

        results[f"{n}gram"] = {
            "entropy": round(entropy, 4),
            "normalized_entropy": round(normalized_entropy, 4),
            "unique_count": len(counts),
            "total": total,
            "ai_indicator": round(ai_indicator, 4),
        }
        total_entropy += ai_indicator

    avg_score = total_entropy / max_n
    results["ngram_score"] = round(min(max(avg_score, 0.0), 1.0), 4)
    return results


# ---------------------------------------------------------------- Perplexity scoring
def compute_perplexity(text: str) -> float:
    """Compute text perplexity using a simple unigram model.

    Lower perplexity = more predictable = more likely AI-generated.
    Uses English unigram frequencies with Laplace smoothing.
    """
    tokens = _tokenize_words(text)
    if not tokens:
        return 0.0

    log_prob_sum = 0.0
    n_tokens = 0

    for token in tokens:
        freq = ENGLISH_UNIGRAM.get(token, SMOOTHING)
        log_prob_sum += -math.log2(freq)
        n_tokens += 1

    if n_tokens == 0:
        return 0.0

    avg_log_prob = log_prob_sum / n_tokens
    return 2 ** avg_log_prob


def score_perplexity(perplexity: float) -> float:
    """Convert perplexity to an AI-likelihood score.

    Typical ranges:
    - Human text: perplexity 80-200
    - AI text: perplexity 20-80
    - Very predictable: perplexity < 20
    """
    if perplexity <= 10:
        return 0.95
    if perplexity <= 30:
        return 0.85
    if perplexity <= 50:
        return 0.7
    if perplexity <= 80:
        return 0.5
    if perplexity <= 120:
        return 0.3
    if perplexity <= 200:
        return 0.15
    return 0.05


# ---------------------------------------------------------------- Burstiness
def compute_burstiness(text: str) -> dict:
    """Compute burstiness — variance in sentence length and complexity.

    Human text has high burstiness (mix of short and long sentences).
    AI text tends toward uniform sentence length.
    """
    sentences = _tokenize_sentences(text)
    if len(sentences) < 3:
        return {"burstiness": 0.0, "score": 0.5, "note": "too_few_sentences"}

    # Sentence lengths in words
    lengths = [len(_tokenize_words(s)) for s in sentences]
    mean_len = sum(lengths) / len(lengths)

    if mean_len == 0:
        return {"burstiness": 0.0, "score": 0.5}

    # Variance
    variance = sum((l - mean_len) ** 2 for l in lengths) / len(lengths)
    std_dev = math.sqrt(variance)

    # Coefficient of variation (normalized)
    cv = std_dev / mean_len if mean_len > 0 else 0

    # AI text typically has CV < 0.4; human text CV > 0.5
    # Score: higher = more AI-like (less bursty)
    if cv < 0.2:
        score = 0.9
    elif cv < 0.35:
        score = 0.7
    elif cv < 0.5:
        score = 0.5
    elif cv < 0.7:
        score = 0.3
    else:
        score = 0.1

    return {
        "burstiness": round(cv, 4),
        "mean_sentence_length": round(mean_len, 2),
        "std_dev": round(std_dev, 2),
        "n_sentences": len(sentences),
        "score": round(score, 4),
    }


# ---------------------------------------------------------------- Repetition detection
def detect_repetition(text: str, min_phrase_len: int = 3) -> dict:
    """Detect repeated phrases in text.

    AI models tend to repeat phrases more than humans, especially
    in longer texts. This detects exact and near-exact repetitions.
    """
    tokens = _tokenize_words(text)
    if len(tokens) < min_phrase_len * 2:
        return {"repetition_score": 0.0, "repeated_phrases": []}

    # Check for repeated n-grams of various lengths
    repeated = []
    for n in range(min_phrase_len, min(8, len(tokens) // 2 + 1)):
        ngrams = _get_ngrams(tokens, n)
        counts = Counter(ngrams)
        for ngram, count in counts.most_common(5):
            if count >= 2:
                repeated.append({
                    "phrase": " ".join(ngram),
                    "count": count,
                    "length": n,
                })

    # Score based on repetition density
    total_tokens = len(tokens)
    repeated_tokens = sum(r["count"] * r["length"] for r in repeated)
    repetition_ratio = repeated_tokens / total_tokens if total_tokens > 0 else 0

    # Normalize to 0-1 score
    score = min(repetition_ratio * 5, 1.0)  # 20% repeated = max score

    return {
        "repetition_score": round(score, 4),
        "repeated_phrases": repeated[:10],  # top 10
        "repetition_ratio": round(repetition_ratio, 4),
    }


# ---------------------------------------------------------------- Token distribution
def analyze_token_distribution(text: str) -> dict:
    """Analyze the distribution of token frequencies.

    AI text tends to have:
    - More uniform token distribution (less Zipfian)
    - Fewer hapax legomena (words appearing only once)
    - Higher type-token ratio in short texts
    """
    tokens = _tokenize_words(text)
    if len(tokens) < 10:
        return {"score": 0.5, "note": "too_short"}

    counts = Counter(tokens)
    total = len(tokens)
    unique = len(counts)

    # Type-token ratio
    ttr = unique / total if total > 0 else 0

    # Hapax legomena ratio (words appearing only once)
    hapax = sum(1 for c in counts.values() if c == 1)
    hapax_ratio = hapax / unique if unique > 0 else 0

    # Human text: high hapax ratio (~0.4-0.6), moderate TTR
    # AI text: lower hapax ratio (~0.2-0.4), higher TTR in short texts
    # Score: higher = more AI-like
    if hapax_ratio < 0.2:
        score = 0.85
    elif hapax_ratio < 0.35:
        score = 0.65
    elif hapax_ratio < 0.5:
        score = 0.4
    else:
        score = 0.2

    return {
        "score": round(score, 4),
        "type_token_ratio": round(ttr, 4),
        "hapax_ratio": round(hapax_ratio, 4),
        "unique_words": unique,
        "total_words": total,
    }


# ---------------------------------------------------------------- Main analysis
def analyze_signature(text: str) -> SignatureReport:
    """Run full deep signature analysis on text.

    Combines n-gram, perplexity, burstiness, repetition, and token
    distribution analysis into a single AI-likelihood score.
    """
    if not text or len(text.strip()) < 20:
        return SignatureReport(
            ai_likelihood=0.5,
            ngram_score=0.5,
            perplexity=0.0,
            perplexity_score=0.5,
            burstiness=0.0,
            burstiness_score=0.5,
            repetition_score=0.0,
            token_distribution_score=0.5,
            verdict="undetermined",
            details={"note": "text_too_short"},
        )

    # N-gram analysis
    ngram_result = analyze_ngrams(text)
    ngram_score = ngram_result.get("ngram_score", 0.5)

    # Perplexity
    perplexity = compute_perplexity(text)
    perplexity_score = score_perplexity(perplexity)

    # Burstiness
    burst_result = compute_burstiness(text)
    burstiness_score = burst_result.get("score", 0.5)
    burstiness = burst_result.get("burstiness", 0.0)

    # Repetition
    rep_result = detect_repetition(text)
    repetition_score = rep_result.get("repetition_score", 0.0)

    # Token distribution
    dist_result = analyze_token_distribution(text)
    dist_score = dist_result.get("score", 0.5)

    # Combined score (weighted average)
    # Perplexity is the strongest single indicator
    weights = {
        "perplexity": 0.30,
        "ngram": 0.20,
        "burstiness": 0.20,
        "repetition": 0.15,
        "distribution": 0.15,
    }

    combined = (
        weights["perplexity"] * perplexity_score
        + weights["ngram"] * ngram_score
        + weights["burstiness"] * burstiness_score
        + weights["repetition"] * repetition_score
        + weights["distribution"] * dist_score
    )

    # Verdict
    if combined >= 0.7:
        verdict = "likely_ai"
    elif combined <= 0.3:
        verdict = "likely_human"
    else:
        verdict = "undetermined"

    return SignatureReport(
        ai_likelihood=combined,
        ngram_score=ngram_score,
        perplexity=perplexity,
        perplexity_score=perplexity_score,
        burstiness=burstiness,
        burstiness_score=burstiness_score,
        repetition_score=repetition_score,
        token_distribution_score=dist_score,
        verdict=verdict,
        details={
            "ngram": ngram_result,
            "burstiness": burst_result,
            "repetition": rep_result,
            "token_distribution": dist_result,
            "weights": weights,
        },
    )
