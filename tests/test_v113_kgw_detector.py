"""Behavioral tests for the real KGW statistical detector (2026-08-13).

The generator below uses the SAME greenlist PRF as the detector. For every
position it picks a random token from the greenlist of (key, prev_token).
That yields a ~100% green rate -> a huge Z-score, which is exactly what a
watermarked text looks like. A normal text stays at the expected ~25% rate
-> Z near zero. A wrong key cannot explain the pattern, which is the whole
point of keyed watermarks.

Vocabulary is syllable-generated (820 pseudo-words) so the generated text
has enough DISTINCT (prev, token) pairs: with a tiny dictionary the same
pair repeats constantly and the wrong-key green rate collapses to a
constant (0% or 100% per repeated pair), which breaks the Z-test's
independence assumption. That exact failure was found during development.
"""

import random

from ai_watermark_toolkit.forensics.kgw import (
    detect_kgw,
    detect_multi_key,
    green_token,
    tokenize,
    DEFAULT_GAMMA,
)
from ai_watermark_toolkit.forensics.ensemble import ensemble_detect

_SIL1 = ("ba be bi bo bu ca ce ci co cu da de di do du fa fe fi fo fu "
         "ga ge gi go gu ka ke ki ko ku la le li lo lu ma me mi mo mu "
         "na ne ni no nu pa pe pi po pu ra re ri ro ru sa se si so su "
         "ta te ti to tu va ve vi vo vu wa we wi wo wu za ze zi zo zu").split()
_SIL2 = ("an en in on un ar er ir or ur al el il ol ul at et it ot ut "
         "as es is os us").split()
VOCAB = [s1 + s2 for s1 in _SIL1 for s2 in _SIL2]

KEY_A = "test-secret-alpha-001"
KEY_B = "test-secret-beta-002"
KEY_C = "test-secret-gamma-003"


def generate_watermarked(seed_token: str, key: str, n: int = 400, gamma: float = DEFAULT_GAMMA, seed: int = 7) -> str:
    """KGW generator: random token from the greenlist at every position."""
    rng = random.Random(seed)
    out = [seed_token]
    prev = seed_token
    for _ in range(n):
        green_cands = [c for c in VOCAB if green_token(c, prev, key, gamma)]
        chosen = rng.choice(green_cands) if green_cands else rng.choice(VOCAB)
        out.append(chosen)
        prev = chosen
    return " ".join(out)


class TestKgwDetector:
    def test_watermarked_text_gets_high_z(self):
        text = generate_watermarked("start", KEY_A)
        r = detect_kgw(text, KEY_A)
        assert r["verdict"] == "watermark_detected", r
        assert r["z_score"] >= 4.0, r
        assert r["green_rate"] > 0.9, r  # greedy generator is ~100% green

    def test_normal_text_gets_no_signal(self):
        # plain prose, not generated with any key
        text = (
            "The report summarizes current findings across several domains. "
            "Analysts reviewed the data and compared it with earlier results. "
            "Nothing in this document was produced with a watermarking scheme."
        ) * 30  # enough tokens for a stable Z
        r = detect_kgw(text, KEY_A)
        assert r["verdict"] in ("no_signal", "weak_signal"), r
        assert r["z_score"] < 2.0, r

    def test_wrong_key_cannot_explain_pattern(self):
        text = generate_watermarked("start", KEY_A)
        r = detect_kgw(text, KEY_B)
        assert r["verdict"] == "no_signal", r
        assert r["z_score"] < 2.0, r

    def test_too_short_text_reports_too_short(self):
        r = detect_kgw("one two three", KEY_A)
        assert r["verdict"] == "too_short"
        assert r["z_score"] is None

    def test_multi_key_finds_correct_key(self):
        text = generate_watermarked("start", KEY_B)
        keys = [
            {"key_id": "a", "family": "kgw", "secret": KEY_A},
            {"key_id": "b", "family": "kgw", "secret": KEY_B},
            {"key_id": "c", "family": "kgw", "secret": KEY_C},
        ]
        r = detect_multi_key(text, keys)
        assert r["tested_keys"] == 3
        assert r["best"]["key_id"] == "b", r
        assert r["best"]["verdict"] == "watermark_detected"
        assert r["best"]["z_score"] >= 4.0

    def test_multi_key_no_keys_registered(self):
        r = detect_multi_key("any text here", [{"key_id": "x", "family": "greenlist_bias"}])
        assert r["tested_keys"] == 0
        assert "no_kgw_keys_registered" in r["note"]

    def test_ensemble_uses_kgw_path(self):
        text = generate_watermarked("start", KEY_A)
        keys = [{"key_id": "a", "family": "kgw", "secret": KEY_A}]
        r = ensemble_detect(text, keys)
        assert r["per_key"][0]["family"] == "kgw"
        assert r["verdict"] == "strong_consistent_signal", r

    def test_tokenizer_word_level(self):
        tokens = tokenize("Hello, world! It's a test-case.")
        assert tokens == ["hello", "world", "it's", "a", "test-case"], tokens
