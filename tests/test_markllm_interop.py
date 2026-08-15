"""MarkLLM interop verification.

Proves that our MarkLLM-compatible PRF (`ai_watermark_toolkit.interop.markllm`)
produces byte-identical greenlists and identical z-scores to the reference
implementation (THU-BPM/MarkLLM, EMNLP 2024).

Skipped when `markllm`/`torch` are not installed
(pip install text-watermark-studio[markllm]).
"""

import pytest

pytest.importorskip("markllm")
pytest.importorskip("torch")

import torch  # noqa: E402

from ai_watermark_toolkit.interop.markllm import (  # noqa: E402
    DEFAULT_GAMMA,
    DEFAULT_HASH_KEY,
    DEFAULT_PREFIX_LENGTH,
    DEFAULT_VOCAB_SIZE,
    _f_time,
    _greenlist_ids,
    _score_ids,
    detect_markllm,
)
from markllm.utils.transformers_config import TransformersConfig  # noqa: E402
from markllm.watermark.kgw.kgw import KGWConfig, KGWUtils  # noqa: E402


def _reference_utils():
    """Build MarkLLM KGWUtils with a stub config (no model needed for PRF math)."""
    cfg = KGWConfig(
        None,  # default config file: markllm/config/KGW.json (gamma 0.5, hash_key 15485863)
        TransformersConfig(
            model=None,
            tokenizer=None,
            vocab_size=DEFAULT_VOCAB_SIZE,
            device="cpu",
            gen_kwargs={},
        ),
    )
    return KGWUtils(cfg)


def test_prf_matches_reference():
    utils = _reference_utils()
    prf_ours = torch.randperm(DEFAULT_VOCAB_SIZE, generator=torch.Generator().manual_seed(DEFAULT_HASH_KEY))
    assert torch.equal(prf_ours, utils.prf), "base randperm PRF must be identical"


def test_greenlist_matches_reference():
    utils = _reference_utils()
    contexts = [
        [154, 291, 1024],
        [13, 3000],
        [0, 1, 2, 3, 4],
        [50256, 1, 50256],
        [7],
    ]
    for ctx in contexts:
        ref = utils.get_greenlist_ids(torch.tensor(ctx, device="cpu"))
        ours = _greenlist_ids(
            ctx,
            gamma=DEFAULT_GAMMA,
            hash_key=DEFAULT_HASH_KEY,
            prefix_length=DEFAULT_PREFIX_LENGTH,
            vocab_size=DEFAULT_VOCAB_SIZE,
        )
        assert set(ref.tolist()) == ours, f"greenlist mismatch for context {ctx}"


def test_f_time_matches_reference():
    utils = _reference_utils()
    for ctx in [[154, 291, 1024], [13, 3000], [0, 1, 2, 3, 4], [50256]]:
        ref = utils._f(torch.tensor(ctx, device="cpu"))
        ours = _f_time(
            ctx,
            DEFAULT_PREFIX_LENGTH,
            utils.prf,
            DEFAULT_VOCAB_SIZE,
        )
        assert int(ref) == ours, f"_f_time mismatch for context {ctx}"


def test_score_matches_reference_z():
    utils = _reference_utils()
    # A token sequence marked with the reference greenlist -> both z-scores agree
    marked = [154, 291, 1024, 50256, 13, 3000, 7, 1, 2, 3, 4, 5, 6, 8, 9]
    ref_z, ref_flags = utils.score_sequence(torch.tensor(marked, device="cpu"))
    green_ours, n_ours, z_ours = _score_ids(
        marked,
        gamma=DEFAULT_GAMMA,
        hash_key=DEFAULT_HASH_KEY,
        prefix_length=DEFAULT_PREFIX_LENGTH,
        vocab_size=DEFAULT_VOCAB_SIZE,
    )
    assert n_ours == len(marked) - DEFAULT_PREFIX_LENGTH
    assert green_ours == sum(1 for f in ref_flags if f == 1)
    assert abs(ref_z - z_ours) < 1e-6


def test_detect_returns_consistent_shape():
    text = "The quick brown fox jumps over the lazy dog near the river bank at dawn."
    res = detect_markllm(text)
    assert set(res) >= {
        "z_score", "p_value", "green_count", "n_tokens",
        "green_rate", "verdict", "signal", "scheme", "parameters",
    }
    assert res["scheme"] == "markllm_kgw"
    # Plain text, non-watermarked with the reference scheme -> no_signal expected
    assert res["verdict"] in ("no_signal", "weak_signal")
