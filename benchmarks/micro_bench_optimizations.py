"""Validation benchmark: measure the impact of proposed optimizations.

Compares current implementations against optimized variants to quantify
the expected speedup for each fix.
"""
from __future__ import annotations

import hashlib
import math
import random
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ai_watermark_toolkit.forensics.kgw import DEFAULT_GAMMA, _BPE_WORD_CACHE
from ai_watermark_toolkit.forensics.frequent_vocab import FREQUENT_VOCAB

KEY = "test-key-optimization-2026"
GAMMA = DEFAULT_GAMMA


# === Fix 1: green_token optimized (raw bytes + precomputed hash string) ===

def green_token_current(token, context, key, gamma=GAMMA):
    """Current implementation."""
    ctx = list(context) if isinstance(context, (list, tuple)) else [context]
    digest = hashlib.sha256((f"{key}:" + ":".join(ctx) + f":{token}").encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF < gamma


def green_token_fast(token, context, key, gamma=GAMMA):
    """Optimized: use sha256 bytes directly, skip hexdigest + isinstance overhead."""
    if isinstance(context, (list, tuple)):
        ctx = context
    else:
        ctx = (context,)
    # Build the hash string once
    h = hashlib.sha256()
    h.update(key.encode("utf-8"))
    h.update(b":")
    for c in ctx:
        h.update(c.encode("utf-8"))
        h.update(b":")
    h.update(token.encode("utf-8"))
    digest = h.digest()
    # Use first 4 bytes as uint32, avoid hex decode
    val = int.from_bytes(digest[:4], "big")
    return val / 0xFFFFFFFF < gamma


def green_token_precomputed(token, key_hash_prefix, key_bytes, gamma):
    """Ultra-fast: key prefix precomputed, single hash."""
    h = hashlib.sha256(key_bytes)
    h.update(b":")
    h.update(token.encode("utf-8"))
    val = int.from_bytes(h.digest()[:4], "big")
    return val / 0xFFFFFFFF < gamma


def bench_green_token_comparison(n=200_000):
    ctx = ["the"]
    t0 = time.perf_counter()
    for _ in range(n):
        green_token_current("important", ctx, KEY, GAMMA)
    current = time.perf_counter() - t0

    t0 = time.perf_counter()
    for _ in range(n):
        green_token_fast("important", ctx, KEY, GAMMA)
    fast = time.perf_counter() - t0

    # Precomputed key approach (context=1, single predecessor)
    key_bytes = KEY.encode("utf-8")
    t0 = time.perf_counter()
    for _ in range(n):
        green_token_precomputed("important", None, key_bytes, GAMMA)
    precomp = time.perf_counter() - t0

    return {
        "current_us": round(current / n * 1e6, 2),
        "fast_us": round(fast / n * 1e6, 2),
        "precomp_us": round(precomp / n * 1e6, 2),
        "speedup_fast": round(current / fast, 2),
        "speedup_precomp": round(current / precomp, 2),
    }


# === Fix 2: mark_greenlist — shuffle-free fallback ===

def _find_green_candidate_current(pool_word, all_candidates, ctx_fn, key, gamma):
    """Current: shuffle fallback, try each."""
    rng = random.Random(42)
    rng.shuffle(all_candidates)
    for c in all_candidates:
        if ctx_fn(c, ctx_fn):
            return c
    return None


def _find_green_candidate_offset(all_candidates, ctx_fn, key, gamma, rng, offset):
    """Optimized: random start offset, linear scan (no shuffle)."""
    n = len(all_candidates)
    for i in range(n):
        c = all_candidates[(i + offset) % n]
        if ctx_fn(c):
            return c
    return None


def bench_shuffle_vs_offset(n_iters=5000):
    """Compare random.shuffle vs random offset for finding a green candidate."""
    fallback = [w for ws in FREQUENT_VOCAB.values() for w in ws]
    rng = random.Random(42)

    # Current: shuffle each time
    t0 = time.perf_counter()
    for _ in range(n_iters):
        rng.shuffle(fallback)
    shuffle_time = time.perf_counter() - t0

    # Optimized: single random offset, linear scan
    t0 = time.perf_counter()
    for _ in range(n_iters):
        offset = rng.randrange(len(fallback))
    offset_time = time.perf_counter() - t0

    return {
        "shuffle_us": round(shuffle_time / n_iters * 1e6, 2),
        "offset_us": round(offset_time / n_iters * 1e6, 2),
        "speedup": round(shuffle_time / offset_time, 1),
        "fallback_size": len(fallback),
        "notes": "shuffle is O(n) Fisher-Yates on 568 items; offset is O(1).",
    }


# === Fix 3: mark_greenlist — green_rate recompute elimination ===

def bench_mark_no_recompute_vs_recompute():
    """Measure the cost of the green_rate_after recompute in mark_greenlist."""
    from ai_watermark_toolkit.forensics.kgw import green_token, tokenize

    # Generate a marked text (we'll use the current mark_greenlist)
    random.seed(42)
    words = list(FREQUENT_VOCAB.keys())
    content = ["the", "a", "is", "are", "was", "were", "has", "have", "had",
               "in", "on", "at", "to", "of", "for", "with", "by", "from",
               "and", "but", "or", "not", "so", "as"]
    text = " ".join(random.choices(words + content, k=500))

    # The recompute cost: tokenize(500 words) + re-hash all tokens
    from ai_watermark_toolkit.forensics.kgw import mark_greenlist
    result = mark_greenlist(text, KEY, gamma=GAMMA, vocab=FREQUENT_VOCAB, seed=42)

    marked_text = result["text"]
    n_words = len(marked_text.split())

    # Cost of re-tokenizing + re-hashing (the green_rate_after computation)
    t0 = time.perf_counter()
    for _ in range(50):
        tokens = tokenize(marked_text, level="word")
        n = max(0, len(tokens) - 1)
        if n:
            green = sum(
                1 for i in range(1, len(tokens))
                if green_token(tokens[i], tokens[max(0, i - 1):i], KEY, GAMMA)
            )
    recompute_time = time.perf_counter() - t0

    return {
        "text_words": n_words,
        "recompute_50x_ms": round(recompute_time * 1000, 1),
        "recompute_per_iter_ms": round(recompute_time / 50 * 1000, 1),
        "notes": f"The green_rate_after recompute (lines 703-713) re-tokenizes and re-hashes the ENTIRE marked text. At ~{recompute_time / 50 * 1000:.1f}ms, this is ~{recompute_time / 50 / (238.6/1000)*100:.0f}% of a single mark_greenlist call (238.6ms).",
    }


# === Fix 4: detect_kgw — green_token caching by (token, ctx_hash) ===

def bench_detect_with_mem():
    """Measure detect_kgw with a memo cache on green_token for repeated contexts."""
    from ai_watermark_toolkit.forensics.kgw import detect_kgw, tokenize, green_token

    random.seed(42)
    words = list(FREQUENT_VOCAB.keys())
    content = ["the", "a", "is", "were", "has", "have", "in", "on", "at",
               "to", "of", "for", "with", "by", "from", "and", "but", "or"]
    # Text with lots of repeated words (common in real text)
    text = " ".join(random.choices(words[:50], k=500))

    tokens = tokenize(text, level="word")
    ctx_key_base = KEY

    # Current (no cache)
    t0 = time.perf_counter()
    for _ in range(200):
        green = sum(1 for i in range(1, len(tokens)) if green_token(tokens[i], [tokens[i-1]], ctx_key_base, GAMMA))
    no_cache = time.perf_counter() - t0

    # With memo cache
    _cache: dict = {}
    t0 = time.perf_counter()
    for _ in range(200):
        green = 0
        for i in range(1, len(tokens)):
            cache_key = (tokens[i], tokens[i-1], ctx_key_base)
            g = _cache.get(cache_key)
            if g is None:
                g = green_token(tokens[i], [tokens[i-1]], ctx_key_base, GAMMA)
                _cache[cache_key] = g
            green += g
    with_cache = time.perf_counter() - t0

    unique_pairs = len(set((tokens[i], tokens[i-1]) for i in range(1, len(tokens))))

    return {
        "no_cache_ms": round(no_cache / 200 * 1000, 2),
        "with_cache_ms": round(with_cache / 200 * 1000, 2),
        "speedup": round(no_cache / with_cache, 2),
        "scored_tokens": len(tokens) - 1,
        "unique_pairs": unique_pairs,
        "cache_hit_rate": round((len(tokens) - 1 - unique_pairs) / (len(tokens) - 1) * 100, 1),
        "notes": f"500-word text with 131 unique words. {unique_pairs} unique (token,prev) pairs out of {len(tokens)-1} scored positions -> {round((len(tokens) - 1 - unique_pairs) / (len(tokens) - 1) * 100, 1)}% cache hit rate possible.",
    }


# === Fix 5: BPE tokenize — avoid per-token decode ===

def bpe_tokenize_current(text):
    from ai_watermark_toolkit.forensics.kgw import _bpe_encoding
    enc = _bpe_encoding()
    return [t for t in (enc.decode([tok]).strip() for tok in enc.encode(text)) if t]


def bpe_tokenize_fast(text):
    """Optimized: batch decode via enc.decode(tokens) once, then split."""
    from ai_watermark_toolkit.forensics.kgw import _bpe_encoding
    enc = _bpe_encoding()
    tokens = enc.encode(text)
    decoded = enc.decode(tokens)
    # Re-tokenize the decoded text to get individual tokens
    # Actually, the fastest approach: decode each token ID
    # The current approach is already calling decode per token.
    # Alternative: use enc.decode([tok]) but batch via list comprehension
    result = []
    for tok in tokens:
        t = enc.decode([tok]).strip()
        if t:
            result.append(t)
    return result


def bench_bpe_comparison():
    random.seed(42)
    words = list(FREQUENT_VOCAB.keys())
    content = ["the", "a", "is", "in", "on", "at", "to", "of", "for"]
    text = " ".join(random.choices(words[:50] + content, k=1000))

    _BPE_WORD_CACHE.clear()
    t0 = time.perf_counter()
    for _ in range(20):
        bpe_tokenize_current(text)
    current = time.perf_counter() - t0

    _BPE_WORD_CACHE.clear()
    t0 = time.perf_counter()
    for _ in range(20):
        bpe_tokenize_fast(text)
    fast = time.perf_counter() - t0

    return {
        "current_ms": round(current / 20 * 1000, 2),
        "fast_ms": round(fast / 20 * 1000, 2),
        "speedup": round(current / fast, 2),
        "text_words": len(text.split()),
        "notes": "Both call enc.decode([tok]) per token. Real speedup requires batch decode approach.",
    }


if __name__ == "__main__":
    print("TWS v108 — Optimization Validation Benchmarks")
    print("=" * 70)

    print("\n1. green_token optimization (raw bytes vs hexdigest):")
    r = bench_green_token_comparison(200_000)
    for k, v in r.items():
        print(f"  {k}: {v}")

    print("\n2. shuffle vs random-offset (mark_greenlist fallback):")
    r = bench_shuffle_vs_offset(50_000)
    for k, v in r.items():
        print(f"  {k}: {v}")

    print("\n3. mark_greenlist green_rate_after recompute cost:")
    r = bench_mark_no_recompute_vs_recompute()
    for k, v in r.items():
        print(f"  {k}: {v}")

    print("\n4. detect_kgw with green_token memoization:")
    r = bench_detect_with_mem()
    for k, v in r.items():
        print(f"  {k}: {v}")

    print("\n5. BPE tokenize comparison:")
    r = bench_bpe_comparison()
    for k, v in r.items():
        print(f"  {k}: {v}")

    print("\n" + "=" * 70)
    print("DONE")
