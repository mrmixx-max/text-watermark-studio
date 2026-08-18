"""Micro-benchmarks for TWS hot paths — targeted, line-level measurements.

Focuses on the bottlenecks identified by profile_eighth_pass.py:
1. green_token SHA-256 hashing cost (per-token PRF)
2. mark_greenlist fallback shuffle cost
3. detect_kgw single-key detection cost
4. BPE tokenize per-call cost
5. _is_green closure overhead
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

from ai_watermark_toolkit.forensics.kgw import (
    DEFAULT_GAMMA,
    _BPE_WORD_CACHE,
    _bpe_encoding,
    _bpe_subwords_cached,
    bpe_tokenize,
    detect_kgw,
    green_token,
    mark_greenlist,
    tokenize,
)
from ai_watermark_toolkit.forensics.frequent_vocab import FREQUENT_VOCAB

WORD = "important"
KEY = "test-key-optimization-2026"
GAMMA = DEFAULT_GAMMA


def bench_green_token(n: int = 200_000) -> dict:
    """Measure raw green_token() cost — each call = 1 SHA-256 hash."""
    ctx = ["the"]
    t0 = time.perf_counter()
    for _ in range(n):
        green_token(WORD, ctx, KEY, GAMMA)
    elapsed = time.perf_counter() - t0
    return {
        "bench": "green_token (SHA-256 PRF per call)",
        "calls": n,
        "elapsed_sec": round(elapsed, 4),
        "us_per_call": round(elapsed / n * 1e6, 2),
        "notes": f"Each call hashes (key:ctx:token) with SHA-256. {n / elapsed:.0f} calls/sec",
    }


def bench_hashlib_direct(n: int = 200_000) -> dict:
    """Measure the lower bound: bare hashlib sha256 + hexdigest + int."""
    digest_str = f"{KEY}:the:{WORD}"
    encoded = digest_str.encode("utf-8")
    t0 = time.perf_counter()
    for _ in range(n):
        h = hashlib.sha256(encoded).hexdigest()
        int(h[:8], 16)
    elapsed = time.perf_counter() - t0
    return {
        "bench": "bare hashlib (sha256+hexdigest+int)",
        "calls": n,
        "elapsed_sec": round(elapsed, 4),
        "us_per_call": round(elapsed / n * 1e6, 2),
        "notes": "Lower bound: green_token adds ~2x overhead over this (dict, isinstance, format, division).",
    }


def bench_mark_shuffle_cost(n: int = 50_000) -> dict:
    """Measure random.shuffle cost — the #1 bottleneck in mark_greenlist."""
    fallback = [w for ws in FREQUENT_VOCAB.values() for w in ws]
    rng = random.Random(42)
    t0 = time.perf_counter()
    for _ in range(n):
        rng.shuffle(fallback)
    elapsed = time.perf_counter() - t0
    return {
        "bench": "random.shuffle(fallback list)",
        "calls": n,
        "fallback_size": len(fallback),
        "elapsed_sec": round(elapsed, 4),
        "us_per_call": round(elapsed / n * 1e6, 2),
        "notes": f"Per profile_eighth_pass: 4180 shuffle calls in 20 mark_greenlist runs = ~209/shuffle. Each shuffle is O(n) Fisher-Yates.",
    }


def bench_detect_kgw_single(text: str, repeats: int = 200) -> dict:
    """Measure detect_kgw (single key, word level) per-call cost."""
    t0 = time.perf_counter()
    for _ in range(repeats):
        detect_kgw(text, KEY, GAMMA, level="word", context=1)
    elapsed = time.perf_counter() - t0
    n_toks = len(tokenize(text, "word")) - 1
    return {
        "bench": "detect_kgw (single key, word level)",
        "repeats": repeats,
        "elapsed_sec": round(elapsed, 4),
        "ms_per_call": round(elapsed / repeats * 1000, 2),
        "scored_tokens": n_toks,
        "us_per_token": round(elapsed / repeats / max(1, n_toks) * 1e6, 2),
        "notes": f"500 words -> {n_toks} scored tokens. Each token hashes ctx+token via SHA-256.",
    }


def bench_bpe_cache_cold_vs_warm() -> dict:
    """Measure bpe_tokenize cold vs. warm cache."""
    words = list(FREQUENT_VOCAB.keys())
    text = " ".join(words) * 20  # repeated words -> cache should hit

    # Cold: clear cache
    _BPE_WORD_CACHE.clear()
    _bpe_encoding()  # ensure loaded
    t0 = time.perf_counter()
    bpe_tokenize(text)
    cold = time.perf_counter() - t0

    # Warm: cache populated
    t0 = time.perf_counter()
    bpe_tokenize(text)
    warm = time.perf_counter() - t0

    return {
        "bench": "bpe_tokenize cold vs warm",
        "text_words": len(text.split()),
        "unique_words": len(set(text.split())),
        "cold_ms": round(cold * 1000, 2),
        "warm_ms": round(warm * 1000, 2),
        "cache_entries": len(_BPE_WORD_CACHE),
        "notes": f"Cold includes first-time tiktoken decode per subword. Warm should be ~0 (no per-word cache used in tokenize())",
    }


def bench_bpe_subwords_cached(n: int = 100_000) -> dict:
    """Measure _bpe_subwords_cached — the per-word cache used in BPE marking."""
    word = "important"
    # Warm the cache
    _bpe_subwords_cached(word)
    t0 = time.perf_counter()
    for _ in range(n):
        _bpe_subwords_cached(word)
    elapsed = time.perf_counter() - t0
    return {
        "bench": "_bpe_subwords_cached (cached word)",
        "calls": n,
        "elapsed_sec": round(elapsed, 4),
        "us_per_call": round(elapsed / n * 1e6, 2),
        "notes": "Cache hit: dict.get lookup. Measures overhead of the cache layer itself.",
    }


def bench_mark_greenlist_breakdown(text: str, repeats: int = 50) -> dict:
    """Full mark_greenlist + cProfile breakdown by function."""
    import cProfile
    import io
    import pstats

    _BPE_WORD_CACHE.clear()
    profiler = cProfile.Profile()
    profiler.enable()
    t0 = time.perf_counter()
    for _ in range(repeats):
        mark_greenlist(text, KEY, gamma=GAMMA, vocab=FREQUENT_VOCAB, seed=42)
    elapsed = time.perf_counter() - t0
    profiler.disable()

    buf = io.StringIO()
    ps = pstats.Stats(profiler, stream=buf).sort_stats("tottime")
    ps.print_stats(12)

    return {
        "bench": "mark_greenlist full + breakdown",
        "repeats": repeats,
        "elapsed_sec": round(elapsed, 4),
        "ms_per_call": round(elapsed / repeats * 1000, 2),
        "breakdown": buf.getvalue(),
    }


def bench_evader(text: str, repeats: int = 30) -> dict:
    """Measure evader.evade cost (white-box KGW attack)."""
    from ai_watermark_toolkit.forensics.evader import evade

    # The text needs to be pre-marked for the evader to actually do work
    marked = mark_greenlist(text, KEY, gamma=GAMMA, vocab=FREQUENT_VOCAB, seed=42)["text"]
    t0 = time.perf_counter()
    for _ in range(repeats):
        evade(marked, KEY, gamma=GAMMA, seed=42)
    elapsed = time.perf_counter() - t0
    return {
        "bench": "evade (white-box KGW attack)",
        "repeats": repeats,
        "elapsed_sec": round(elapsed, 4),
        "ms_per_call": round(elapsed / repeats * 1000, 2),
        "input_words": len(marked.split()),
        "notes": "Each iteration re-runs detect_kgw after every edit (re-tokenize + re-hash).",
    }


def bench_trace_kgw(text: str) -> dict:
    """Measure trace_kgw (sliding window trajectory) cost."""
    from ai_watermark_toolkit.forensics.trace import trace_kgw

    t0 = time.perf_counter()
    trace_kgw(text, KEY, gamma=GAMMA, level="word", context=1, window=500, step=250)
    elapsed = time.perf_counter() - t0
    return {
        "bench": "trace_kgw (sliding window)",
        "elapsed_sec": round(elapsed, 4),
        "word_count": len(text.split()),
        "notes": "Each window calls detect_kgw from scratch (re-tokenize + re-hash entire window).",
    }


def generate_realistic_text(n_words: int = 500) -> str:
    """Generate realistic English text with frequent-vocab coverage."""
    rng = random.Random(42)
    words = list(FREQUENT_VOCAB.keys())
    content = ["the", "a", "is", "are", "was", "were", "has", "have", "had",
               "been", "in", "on", "at", "to", "of", "for", "with", "by", "from",
               "and", "but", "or", "not", "so", "as", "into", "through", "during"]
    sentences = []
    for _ in range(n_words // 12):
        w = rng.choice(words)
        sentences.append(f"{w.capitalize()} {rng.choice(content)} {rng.choice(words)} {rng.choice(content)} {rng.choice(words)} {rng.choice(content)} {rng.choice(words)}.")
    return " ".join(sentences)


if __name__ == "__main__":
    print("TWS v108 — Micro-Benchmark Hot Paths")
    print(f"Python: {sys.version.split()[0]}")
    print("=" * 70)

    results = []
    results.append(bench_hashlib_direct())
    results.append(bench_green_token())
    results.append(bench_mark_shuffle_cost())

    text = generate_realistic_text(500)
    results.append(bench_detect_kgw_single(text, repeats=200))
    results.append(bench_bpe_cache_cold_vs_warm())
    results.append(bench_bpe_subwords_cached(100_000))

    mg = bench_mark_greenlist_breakdown(text, repeats=50)
    results.append({
        "bench": mg["bench"],
        "repeats": mg["repeats"],
        "elapsed_sec": mg["elapsed_sec"],
        "ms_per_call": mg["ms_per_call"],
        "breakdown": mg["breakdown"],
    })

    results.append(bench_evader(text, repeats=30))
    results.append(bench_trace_kgw(text))

    for r in results:
        if "breakdown" in r:
            print(f"\n{'='*70}")
            print(f"{r['bench']}: {r['ms_per_call']}ms/call ({r['elapsed_sec']}s / {r['repeats']} reps)")
            print(r["breakdown"])
        else:
            print(f"\n{r['bench']}:")
            for k, v in r.items():
                if k != "bench":
                    print(f"  {k}: {v}")

    print(f"\n{'='*70}")
    print("DONE")
