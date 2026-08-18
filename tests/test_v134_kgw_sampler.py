"""Tests for the generation-time KGW sampling-bias sampler (2026-08-13).

These tests are deterministic and do NOT call Ollama. They prove the bias
MECHANIC of a real generation-time watermark:

  - bias_logits adds the delta to greenlist logits deterministically;
  - sample_with_kgw_bias shifts the empirical green-rate far above gamma
    (bias=2.0, gamma=0.5 -> ~0.88) while the unbiased control stays ~gamma;
  - the greenlist is context-window dependent (c=2 vs c=1 mismatch collapses);
  - generate_marked_text round-trips through detect_kgw (z >> 4 with the
    right key; no signal for the wrong key or for zero bias).

This is a mechanics proof, not a production generator: post-hoc text
rewrite (mark_greenlist / embed_kgw) remains the standard embed path.
"""

import random

from ai_watermark_toolkit.forensics.kgw import detect_kgw, green_token
from ai_watermark_toolkit.generation.kgw_sampler import (
    bias_logits,
    default_vocab,
    generate_marked_text,
    sample_with_kgw_bias,
)

KEY = "sampler-proof-key"
WRONG = "sampler-wrong-key"
GAMMA = 0.5

# Small fixed vocabulary for the high-N empirical rate tests (fast + tight).
SMALL_VOCAB = {f"w{i}": 0.0 for i in range(100)}


def _green_rate(rng, vocab, ctx, bias, n=5000):
    """Empirical green-rate of `n` samples from sample_with_kgw_bias."""
    green = sum(
        1 for _ in range(n) if green_token(sample_with_kgw_bias(rng, vocab, KEY, ctx, GAMMA, bias), ctx, KEY, GAMMA)
    )
    return green / n


class TestBiasLogits:
    def test_adds_delta_to_green_logits_deterministically(self):
        logits = {"a": 1.0, "b": 2.0, "c": 0.5}
        out = bias_logits(logits, {"a", "c"}, bias_strength=1.5)
        assert out == {"a": 2.5, "b": 2.0, "c": 2.0}

    def test_zero_bias_is_unchanged_copy_and_no_mutation(self):
        logits = {"a": 1.0, "b": 2.0, "c": 0.5}
        out = bias_logits(logits, {"a", "c"}, 0.0)
        assert out == logits
        assert logits == {"a": 1.0, "b": 2.0, "c": 0.5}  # input never mutated

    def test_green_flags_forms_agree(self):
        logits = {"a": 1.0, "b": 2.0, "c": 0.5}
        expected = bias_logits(logits, {"a", "c"}, 1.5)
        assert bias_logits(logits, {"a": True, "b": False, "c": True}, 1.5) == expected
        assert bias_logits(logits, lambda t: t in {"a", "c"}, 1.5) == expected


class TestSampleWithKgwBias:
    def test_bias_pushes_green_rate_above_gamma(self):
        rng = random.Random(42)
        rate = _green_rate(rng, SMALL_VOCAB, ["c0", "c1"], bias=2.0)
        assert rate > 0.7, f"green_rate={rate:.4f} not above 0.7"

    def test_unbiased_control_stays_at_gamma(self):
        rng = random.Random(42)
        rate = _green_rate(rng, SMALL_VOCAB, ["c0", "c1"], bias=0.0)
        assert abs(rate - GAMMA) < 0.1, f"green_rate={rate:.4f} not ~= gamma"

    def test_context_window_changes_greenlist(self):
        # A token's green membership depends on the context window size.
        vocab = default_vocab()
        flips = [
            t
            for t in vocab
            if green_token(t, ["previous"], KEY, GAMMA) != green_token(t, ["earlier", "previous"], KEY, GAMMA)
        ]
        assert flips, "greenlist should differ between c=1 and c=2 contexts"


class TestGenerateMarkedText:
    def test_generate_detect_roundtrip(self):
        r = generate_marked_text(
            prefix="", vocab=default_vocab(), key=KEY, gamma=GAMMA, bias_strength=2.0, n_tokens=200, seed=1
        )
        d = detect_kgw(r["text"], KEY, GAMMA)
        assert d["verdict"] == "watermark_detected", d
        assert d["z_score"] >= 4.0, d

    def test_wrong_key_not_detected(self):
        r = generate_marked_text(
            prefix="", vocab=default_vocab(), key=KEY, gamma=GAMMA, bias_strength=2.0, n_tokens=200, seed=1
        )
        d = detect_kgw(r["text"], WRONG, GAMMA)
        assert d["z_score"] < 4.0, d

    def test_zero_bias_not_detected(self):
        r = generate_marked_text(
            prefix="", vocab=default_vocab(), key=KEY, gamma=GAMMA, bias_strength=0.0, n_tokens=200, seed=1
        )
        d = detect_kgw(r["text"], KEY, GAMMA)
        assert d["z_score"] < 4.0, d

    def test_context_window_mismatch_collapses(self):
        r = generate_marked_text(
            prefix="local models",
            vocab=default_vocab(),
            key=KEY,
            gamma=GAMMA,
            bias_strength=2.0,
            n_tokens=300,
            seed=3,
            context=2,
        )
        right = detect_kgw(r["text"], KEY, GAMMA, context=2)
        wrong = detect_kgw(r["text"], KEY, GAMMA, context=1)
        assert right["z_score"] >= 4.0, right
        assert wrong["z_score"] < 4.0, wrong

    def test_deterministic_with_seed(self):
        a = generate_marked_text(
            prefix="", vocab=default_vocab(), key=KEY, gamma=GAMMA, bias_strength=2.0, n_tokens=50, seed=7
        )
        b = generate_marked_text(
            prefix="", vocab=default_vocab(), key=KEY, gamma=GAMMA, bias_strength=2.0, n_tokens=50, seed=7
        )
        assert a["text"] == b["text"]
