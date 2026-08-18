"""Tests for the BPE token level of the KGW detector (2026-08-13).

Contract: mark_greenlist(level='bpe') and detect_kgw(level='bpe') operate on
the same subword surface, so a mark at BPE level is found at BPE level, a
wrong key stays clean, and unmarked text stays clean. Word level remains the
backward-compatible default and keeps its own round-trip.
"""

from ai_watermark_toolkit.forensics.kgw import (
    bpe_tokenize,
    detect_kgw,
    mark_greenlist,
    tokenize,
)
from ai_watermark_toolkit.forensics.frequent_vocab import FREQUENT_VOCAB

KEY = "bpe-proof-key"
WRONG = "bpe-wrong-key"
GAMMA = 0.5

TEXT = (
    "Local AI models protect user privacy by processing information on the "
    "device instead of sending everything to a remote server. This approach "
    "reduces the amount of personal data shared with outside systems and "
    "gives people direct control over their information. The result is a "
    "lower risk of breaches and a stronger security posture. People trust "
    "systems that keep their data nearby and handle processing transparently. "
    "Organizations benefit because sensitive records never leave the building, "
    "and compliance becomes easier when data remains under local control. "
    "Small devices can now run capable models without depending on external "
    "services, which removes network latency and protects against outages. "
    "The same principle applies to healthcare, finance, and public services, "
    "where confidentiality is not optional but a legal requirement. Every "
    "layer of the system can be inspected, and the user decides what leaves "
    "the machine and what stays private. Over time this changes the default "
    "from constant sharing toward careful retention and measured disclosure."
)


class TestBpeTokenize:
    def test_bpe_splits_subwords(self):
        bpe = bpe_tokenize("The transformation")
        words = tokenize("The transformation")
        assert len(bpe) >= len(words)  # BPE is at least as granular
        # no leading-space artifacts: tokens are clean subword surfaces
        assert all(not t.startswith(" ") for t in bpe)

    def test_bpe_preserves_case(self):
        bpe = bpe_tokenize("Paris is the Capital")
        assert "Paris" in bpe
        assert "Capital" in bpe  # capital-C preserved, unlike word-level lowercase


class TestBpeRoundtrip:
    def test_bpe_mark_detected_at_bpe_level(self):
        emb = mark_greenlist(TEXT, KEY, GAMMA, vocab=FREQUENT_VOCAB, seed=3, level="bpe")
        assert emb["replacements"] > 10
        r = detect_kgw(emb["text"], KEY, GAMMA, level="bpe")
        assert r["verdict"] == "watermark_detected", r
        assert r["z_score"] >= 4.0

    def test_bpe_wrong_key_clean(self):
        emb = mark_greenlist(TEXT, KEY, GAMMA, vocab=FREQUENT_VOCAB, seed=3, level="bpe")
        r = detect_kgw(emb["text"], WRONG, GAMMA, level="bpe")
        assert r["verdict"] != "watermark_detected", r

    def test_bpe_control_unmarked_clean(self):
        r = detect_kgw(TEXT, KEY, GAMMA, level="bpe")
        assert r["verdict"] != "watermark_detected", r

    def test_word_level_regression_still_roundtrips(self):
        emb = mark_greenlist(TEXT, KEY, GAMMA, vocab=FREQUENT_VOCAB, seed=3, level="word")
        r = detect_kgw(emb["text"], KEY, GAMMA, level="word")
        assert r["verdict"] == "watermark_detected", r

    def test_bpe_level_scores_word_boundaries(self):
        # BPE level scores (last subword, first subword) pairs — one per word
        # boundary, so n_tokens tracks the word count, not raw BPE token count.
        b = detect_kgw(TEXT, KEY, GAMMA, level="bpe")
        w = detect_kgw(TEXT, KEY, GAMMA, level="word")
        assert b["n_tokens"] == w["n_tokens"]  # both score word boundaries
        assert b["n_tokens"] > 50  # text is long enough to be meaningful
