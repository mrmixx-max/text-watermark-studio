"""MarkLLM-compatible KGW detection (interop layer).

Replicates the exact KGW greenlist scheme from the MarkLLM reference
toolkit (THU-BPM/MarkLLM, EMNLP 2024, Apache-2.0) so texts marked by the
reference implementation can be scored here with the same PRF.

Reference scheme (kgw.py, window_scheme="left", f_scheme="time"):

  f(context)    = product of the last `prefix_length` token ids
  seed          = (hash_key * f) % vocab_size
  permutation   = torch.randperm(vocab_size, generator=seed)
  greenlist     = permutation[: int(vocab_size * gamma)]

  z = (green_count - gamma * T) / sqrt(T * gamma * (1 - gamma))

Tokenization uses the gpt2 encoding (tiktoken), which produces the same
byte-level BPE ids as the GPT-2 tokenizer used in the MarkLLM pipeline.

This module is the *compatibility surface*: it does not require the
markllm package at runtime. The interop test (tests/test_markllm_interop.py)
proves the PRF matches the reference implementation exactly when markllm is
installed (pip install text-watermark-studio[markllm]).
"""

from __future__ import annotations

import math

# Defaults mirror markllm/config/KGW.json
DEFAULT_GAMMA = 0.5
DEFAULT_DELTA = 2.0
DEFAULT_HASH_KEY = 15485863
DEFAULT_PREFIX_LENGTH = 1
DEFAULT_Z_THRESHOLD = 4.0
DEFAULT_VOCAB_SIZE = 50257  # gpt2

_TIKTOKEN_ENC = None


def _tiktoken_gpt2():
    global _TIKTOKEN_ENC
    if _TIKTOKEN_ENC is None:
        try:
            import tiktoken
        except ImportError as e:  # pragma: no cover
            raise ImportError("MarkLLM interop needs tiktoken: pip install text-watermark-studio[bpe]") from e
        _TIKTOKEN_ENC = tiktoken.get_encoding("gpt2")
    return _TIKTOKEN_ENC


def _torch():
    try:
        import torch
    except ImportError as e:  # pragma: no cover
        raise ImportError("MarkLLM interop needs torch: pip install text-watermark-studio[markllm]") from e
    return torch


def _f_time(context_ids: list[int], prefix_length: int, prf, vocab_size: int) -> int:
    """MarkLLM _f_time: product of the last prefix_length token ids -> prf lookup."""
    product = 1
    for i in range(prefix_length):
        product *= context_ids[-1 - i]
    return int(prf[product % vocab_size])


def _greenlist_ids(
    context_ids: list[int],
    *,
    gamma: float = DEFAULT_GAMMA,
    hash_key: int = DEFAULT_HASH_KEY,
    prefix_length: int = DEFAULT_PREFIX_LENGTH,
    f_scheme: str = "time",
    window_scheme: str = "left",
    vocab_size: int = DEFAULT_VOCAB_SIZE,
) -> set[int]:
    """Compute the MarkLLM greenlist for a context, exactly as reference code."""
    torch = _torch()
    if f_scheme != "time" or window_scheme != "left":
        raise NotImplementedError(
            f"MarkLLM interop supports f_scheme='time' window_scheme='left'; got {f_scheme}/{window_scheme}"
        )
    rng = torch.Generator(device="cpu")
    # Reference: self.prf = randperm(vocab_size, seed=hash_key)
    rng.manual_seed(hash_key)
    prf = torch.randperm(vocab_size, generator=rng)
    f_val = _f_time(context_ids, prefix_length, prf, vocab_size)
    rng.manual_seed((hash_key * f_val) % vocab_size)
    perm = torch.randperm(vocab_size, generator=rng)
    green_size = int(vocab_size * gamma)
    return set(perm[:green_size].tolist())


def _score_ids(
    token_ids: list[int],
    *,
    gamma: float = DEFAULT_GAMMA,
    hash_key: int = DEFAULT_HASH_KEY,
    prefix_length: int = DEFAULT_PREFIX_LENGTH,
    f_scheme: str = "time",
    window_scheme: str = "left",
    vocab_size: int = DEFAULT_VOCAB_SIZE,
) -> tuple[int, int, float]:
    """Score token ids with the MarkLLM scheme. Returns (green_count, T, z_score)."""
    num_scored = len(token_ids) - prefix_length
    if num_scored < 1:
        raise ValueError(f"Must have at least 1 token to score after prefix_length={prefix_length}")
    green = 0
    for idx in range(prefix_length, len(token_ids)):
        context = token_ids[:idx]
        g = _greenlist_ids(
            context,
            gamma=gamma,
            hash_key=hash_key,
            prefix_length=prefix_length,
            f_scheme=f_scheme,
            window_scheme=window_scheme,
            vocab_size=vocab_size,
        )
        if token_ids[idx] in g:
            green += 1
    expected = gamma * num_scored
    denom = math.sqrt(num_scored * gamma * (1 - gamma))
    z = (green - expected) / denom
    return green, num_scored, z


def detect_markllm(
    text: str,
    *,
    gamma: float = DEFAULT_GAMMA,
    hash_key: int = DEFAULT_HASH_KEY,
    prefix_length: int = DEFAULT_PREFIX_LENGTH,
    z_threshold: float = DEFAULT_Z_THRESHOLD,
    f_scheme: str = "time",
    window_scheme: str = "left",
    vocab_size: int = DEFAULT_VOCAB_SIZE,
) -> dict:
    """Detect a MarkLLM-reference watermark in text.

    Returns the same result shape as :func:`ai_watermark_toolkit.forensics.kgw.detect_kgw`
    so the verdict/signal semantics stay consistent across detectors.
    """
    enc = _tiktoken_gpt2()
    token_ids = enc.encode(text)
    green, n, z = _score_ids(
        token_ids,
        gamma=gamma,
        hash_key=hash_key,
        prefix_length=prefix_length,
        f_scheme=f_scheme,
        window_scheme=window_scheme,
        vocab_size=vocab_size,
    )
    p_value = math.erfc(abs(z) / math.sqrt(2))
    rate = green / n if n else 0.0
    if z >= z_threshold:
        verdict, signal = "watermark_detected", "greenlist"
    elif z <= -z_threshold:
        verdict, signal = "redlist_detected", "redlist"
    elif z >= 2.0:
        verdict, signal = "weak_signal", "greenlist"
    elif z <= -2.0:
        verdict, signal = "weak_redlist_signal", "redlist"
    else:
        verdict, signal = "no_signal", None
    return {
        "z_score": round(z, 4),
        "p_value": round(p_value, 10),
        "green_count": green,
        "n_tokens": n,
        "green_rate": round(rate, 4),
        "verdict": verdict,
        "signal": signal,
        "scheme": "markllm_kgw",
        "parameters": {
            "gamma": gamma,
            "hash_key": hash_key,
            "prefix_length": prefix_length,
            "f_scheme": f_scheme,
            "window_scheme": window_scheme,
        },
    }
