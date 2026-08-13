"""Generation-time KGW sampling-bias generator (synthetic, deterministic).

This module implements the REAL generation-time half of the KGW
(Kirchenbauer et al.) statistical watermark: instead of rewriting an
already-written text post-hoc, it biases the sampling distribution DURING
autoregressive generation so that tokens whose hash lands in the greenlist
are preferred.

What this IS
------------
- A dependency-free, deterministic sampler that proves the bias MECHANIC:
  additive logit bias on greenlist tokens -> softmax -> sample. With a
  strong bias the green-rate rises far above gamma, and ``detect_kgw``
  (``forensics/kgw.py``) recovers the watermark (z >> 4) with the right key.
- A reference implementation of the sampling rule a real decoder would
  apply through a ``logit_bias`` table. The ``bias_logits`` step maps 1:1
  onto llama.cpp's ``logit_bias`` (or any OpenAI-style ``logit_bias``):
  greenlist token id -> +delta. See ``_LLAMACPP_INTEGRATION`` note below.

What this is NOT
----------------
- It does NOT load or run a real language model. ``vocab`` is a plain
  token -> logit table and generation is a controlled random walk, so the
  produced text is synthetic (readable English words, not fluent prose).
- It does NOT train or modify a model. The production path for real
  generation-time bias is llama.cpp with ``logit_bias`` over a GGUF model.

Honest limits
-------------
- This is a MECHANICS PROOF, not a production generator. The post-hoc
  text-rewrite path (``mark_greenlist``) remains the
  DEFAULT embedding method in the ``sampling_bias`` family. Measured
  2026-08-13: the real Ollama generator itself shows no greenlist bias
  (green_rate 0.49 ~= gamma) and Ollama's HTTP API exposes no logit_bias.

_LLAMACPP_INTEGRATION (documented path, not implemented here)
--------------------------------------------------------------
    import llama_cpp
    llm = llama_cpp.Llama(model_path="model.gguf", seed=seed, logits_all=True)
    # per generation step, for each token id in the greenlist:
    #   llama_cpp.LogitsProcessor -> add bias_strength to those logits
    # (llama-cpp-python needs a MSVC/CMake build on Windows; not a runtime
    #  dependency of this package. Add it as an optional extra when wired.)
"""

from __future__ import annotations

import math
import random

from ..forensics.kgw import green_token, tokenize

# The sampler defaults to gamma=0.5 — the same free KGW parameter the repo's
# end-to-end proof uses. Higher gamma raises the control baseline (unmarked
# text already shows ~gamma green rate) but a strong bias pushes generated
# text far above it, which is exactly what the detector measures.
SAMPLER_GAMMA = 0.5


def bias_logits(logits: dict[str, float], green_flags, bias_strength: float = 0.0) -> dict[str, float]:
    """Add ``bias_strength`` to the logit of every greenlist token.

    Deterministic, pure function: returns a NEW dict with the same key
    order; the input ``logits`` is never mutated.

    ``green_flags`` selects the green tokens and may be one of:

    - ``set[str]`` — membership test,
    - ``dict[str, bool]`` — flag lookup,
    - a callable ``token -> bool`` — arbitrary predicate (this is the form
      ``sample_with_kgw_bias`` uses internally, wrapping the KGW PRF).

    ``bias_strength`` is the additive logit delta (KGW's ``delta``). With
    delta=0 the function returns an unchanged copy (the unbiased control).
    A negative delta implements the mirror-image redlist (avoid green).
    """
    if callable(green_flags):
        def _is_green(t: str) -> bool:
            return bool(green_flags(t))
    elif isinstance(green_flags, set):
        def _is_green(t: str) -> bool:
            return t in green_flags
    else:
        def _is_green(t: str) -> bool:
            return bool(green_flags.get(t, False))

    return {t: (l + bias_strength if _is_green(t) else l) for t, l in logits.items()}


def _softmax_sample(rng: random.Random, logits: dict[str, float]) -> str:
    """Sample one token from a softmax over the logits (numerically stable)."""
    if not logits:
        raise ValueError("cannot sample from empty logits")
    tokens = list(logits)
    values = list(logits.values())
    mx = max(values)
    weights = [math.exp(v - mx) for v in values]
    total = sum(weights)
    r = rng.random() * total
    acc = 0.0
    for t, w in zip(tokens, weights):
        acc += w
        if r < acc:
            return t
    return tokens[-1]


def sample_with_kgw_bias(rng: random.Random, logits: dict[str, float], key: str,
                         context, gamma: float = SAMPLER_GAMMA,
                         bias_strength: float = 2.0) -> str:
    """Sample one token under greenlist bias for a given context.

    Green membership is decided by the SAME PRF the detector uses
    (``forensics.kgw.green_token``), so generation and detection share the
    greenlist exactly. ``context`` is a single previous token or a
    list/tuple of the up-to-``c`` preceding tokens.
    """
    biased = bias_logits(logits, lambda t: green_token(t, context, key, gamma), bias_strength)
    return _softmax_sample(rng, biased)


def default_vocab() -> dict[str, float]:
    """Build the default synthetic vocabulary: single-word tokens from the
    repo's frequency pool, with uniform base logits (deterministic, sorted).

    Multi-word phrases are dropped because they would tokenize into several
    words and break the word-level round-trip with ``detect_kgw``.
    """
    from ..forensics.frequent_vocab import FREQUENT_VOCAB
    words = sorted({w for ws in FREQUENT_VOCAB.values() for w in ws if " " not in w})
    return {w: 0.0 for w in words}


def generate_marked_text(prefix: str | list[str] = "", vocab: dict[str, float] | None = None,
                         key: str = "demo-sampling-bias-key", gamma: float = SAMPLER_GAMMA,
                         bias_strength: float = 2.0, n_tokens: int = 200, seed: int = 0,
                         context: int = 1) -> dict:
    """Autoregressively generate a synthetic greenlist-marked text.

    Applies the generation-time KGW bias: every token AFTER the first is
    sampled from a softmax whose greenlist tokens received an additive logit
    boost of ``bias_strength``. The greenlist context window mirrors
    ``detect_kgw(..., context=context)`` exactly: token ``i`` is hashed
    against the up-to-``context`` preceding tokens, so the generated text
    round-trips through the detector byte-for-byte on the greenlist level.

    Returns a dict: ``text`` (space-joined lowercase words), ``tokens``,
    ``n_tokens``, ``scored_tokens``, ``green_count``, ``green_rate``,
    ``seed``, ``bias_strength``, ``gamma``, ``context``. The first token of
    the whole sequence carries no greenlist (the detector never scores the
    first token), and an empty ``prefix`` therefore starts with one unbiased
    seed token.
    """
    if vocab is None:
        vocab = default_vocab()
    rng = random.Random(seed)
    history = tokenize(prefix) if isinstance(prefix, str) else list(prefix)
    generated: list[str] = []
    for _ in range(n_tokens):
        if history:
            ctx = history[max(0, len(history) - context):]
            tok = sample_with_kgw_bias(rng, vocab, key, ctx, gamma, bias_strength)
        else:
            # No predecessor -> detector will not score this token.
            tok = _softmax_sample(rng, vocab)
        generated.append(tok)
        history.append(tok)

    text = " ".join(history)
    n = len(history) - 1
    green = sum(
        1 for i in range(1, len(history))
        if green_token(history[i], history[max(0, i - context):i], key, gamma)
    ) if n > 0 else 0
    return {
        "text": text,
        "tokens": history,
        "n_tokens": len(history),
        "scored_tokens": n,
        "green_count": green,
        "green_rate": round(green / n, 4) if n else None,
        "seed": seed,
        "bias_strength": bias_strength,
        "gamma": gamma,
        "context": context,
    }
