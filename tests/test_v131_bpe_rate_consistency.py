"""Regression test: mark_greenlist(level='bpe') green_rate_after must equal
the rate detect_kgw(level='bpe') actually scores (2026-08-13).

Before the fix, mark_greenlist computed green_rate_after over ALL contiguous
BPE subword pairs (flat bpe_tokenize stream), while the detector scores only
word-boundary pairs (last subword of prev word, first subword of curr word).
API consumers reading green_rate_after as the detector's expected strength
were misled by up to ~-0.27 on a typical paragraph. The fix routes both
through the shared _score_bpe_boundaries helper so the two can never drift.

This test is filesystem-safe: it writes only into tmp_path (never data/).
"""

import pytest

from ai_watermark_toolkit.forensics.kgw import detect_kgw, mark_greenlist
from ai_watermark_toolkit.forensics.frequent_vocab import FREQUENT_VOCAB

KEY = "bpe-rate-consistency-key"
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
    "where confidentiality is not optional but a legal requirement."
)


class TestBpeRateConsistency:
    def test_mark_rate_equals_detect_rate(self, tmp_path):
        emb = mark_greenlist(TEXT, KEY, GAMMA, vocab=FREQUENT_VOCAB, seed=3, level="bpe")
        r = detect_kgw(emb["text"], KEY, GAMMA, level="bpe")

        # The detector has a meaningful sample to score.
        assert r["n_tokens"] > 10, r

        # Contract: the rate mark reports is the rate detect sees.
        assert emb["green_rate_after"] == pytest.approx(r["green_rate"], abs=1e-3), (
            emb["green_rate_after"],
            r["green_rate"],
        )

        # total_tokens now tracks the word count, one more than scored pairs.
        assert emb["total_tokens"] == r["n_tokens"] + 1, (emb, r)

        # The marked BPE text must actually be strongly green at boundaries.
        assert r["verdict"] == "watermark_detected", r
        assert emb["green_rate_after"] > 0.9, emb

        # Filesystem safety: exercise tmp_path only, never data/.
        out = tmp_path / "marked.txt"
        out.write_text(emb["text"], encoding="utf-8")
        assert out.read_text(encoding="utf-8") == emb["text"]

    def test_word_level_rate_still_consistent(self, tmp_path):
        # Word level is the backward-compatible path; its reported rate must
        # also match the detector (both already score word tokens).
        emb = mark_greenlist(TEXT, KEY, GAMMA, vocab=FREQUENT_VOCAB, seed=3, level="word")
        r = detect_kgw(emb["text"], KEY, GAMMA, level="word")
        assert emb["green_rate_after"] == pytest.approx(r["green_rate"], abs=1e-3), (
            emb["green_rate_after"],
            r["green_rate"],
        )
        assert r["verdict"] == "watermark_detected", r
        out = tmp_path / "marked_word.txt"
        out.write_text(emb["text"], encoding="utf-8")
        assert out.read_text(encoding="utf-8") == emb["text"]
