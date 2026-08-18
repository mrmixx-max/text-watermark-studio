"""Eighth pass: comprehensive profiling of TWS hot paths.

Profiles:
1. mark_greenlist (embed hot loop)
2. detect_multi_key (detection path)
3. BPE cache hit rate
4. batch processing
5. watcher loop
6. Memory leaks via tracemalloc
"""
import cProfile
import io
import pstats
import random
import string
import sys
import time
import tracemalloc
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(r"C:\Users\webma\Downloads\tws-v108\text-watermark-studio-v108-deep-debug\src")))

from ai_watermark_toolkit.forensics.kgw import (
    mark_greenlist, detect_multi_key, detect_kgw, green_token,
    _bpe_subwords_cached, _BPE_WORD_CACHE, _bpe_encoding, bpe_tokenize,
    tokenize, _derive_seed
)
from ai_watermark_toolkit.forensics.frequent_vocab import FREQUENT_VOCAB


def generate_text(n_words=200):
    """Generate synthetic text with FREQUENT_VOCAB coverage."""
    words = list(FREQUENT_VOCAB.keys())
    vocab_extra = ["the", "a", "is", "are", "was", "were", "has", "have", "had",
                   "been", "being", "do", "does", "did", "will", "would", "could",
                   "should", "may", "might", "shall", "can", "need", "dare", "ought",
                   "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
                   "as", "into", "through", "during", "before", "after", "above",
                   "below", "between", "out", "off", "over", "under", "again",
                   "further", "then", "once", "and", "but", "or", "nor", "not", "so",
                   "yet", "both", "either", "neither", "each", "every", "all", "any",
                   "few", "more", "most", "other", "some", "such", "no", "only",
                   "own", "same", "than", "too", "very", "just", "because", "if",
                   "when", "while", "although", "though", "after", "before", "until",
                   "unless", "since", "although", "also", "still", "already", "even",
                   "quite", "rather", "enough", "almost", "just"]
    pool = words + vocab_extra
    return " ".join(random.choices(pool, k=n_words))


def profile_mark_greenlist():
    """Profile mark_greenlist — the embed hot loop."""
    print("=" * 70)
    print("1. PROFILING mark_greenlist (embed hot loop)")
    print("=" * 70)

    random.seed(42)
    text = generate_text(500)
    key = "test-key-optimization-2026"

    # Warm up BPE cache
    _BPE_WORD_CACHE.clear()

    profiler = cProfile.Profile()
    profiler.enable()
    start = time.perf_counter()
    for _ in range(20):
        result = mark_greenlist(text, key, gamma=0.25, vocab=FREQUENT_VOCAB, seed=42)
    elapsed = time.perf_counter() - start
    profiler.disable()

    print(f"  20 iterations over 500-word text: {elapsed:.3f}s")
    print(f"  Per iteration: {elapsed/20*1000:.1f}ms")
    print(f"  Replacements: {result['replacements']}")
    print(f"  Green rate after: {result['green_rate_after']}")

    buf = io.StringIO()
    ps = pstats.Stats(profiler, stream=buf).sort_stats('cumulative')
    ps.print_stats(20)
    print("\n  Top 20 functions (cumulative):")
    print("  " + "\n  ".join(buf.getvalue().split("\n")))

    # Also sort by internal time
    buf2 = io.StringIO()
    ps2 = pstats.Stats(profiler, stream=buf2).sort_stats('tottime')
    ps2.print_stats(15)
    print("\n  Top 15 functions (internal time):")
    print("  " + "\n  ".join(buf2.getvalue().split("\n")))

    return elapsed


def profile_bpe_cache():
    """Check BPE cache hit rate."""
    print("\n" + "=" * 70)
    print("2. BPE CACHE ANALYSIS")
    print("=" * 70)

    _BPE_WORD_CACHE.clear()

    random.seed(42)
    text = generate_text(1000)
    words = text.split()
    unique_words = set(words)

    # Simulate the cache behavior during mark_greenlist
    enc = _bpe_encoding()
    hits = 0
    misses = 0
    for word in unique_words:
        if word in _BPE_WORD_CACHE:
            hits += 1
        else:
            misses += 1
            _bpe_subwords_cached(word)

    total = hits + misses
    hit_rate = hits / total if total else 0
    print(f"  Unique words: {total}")
    print(f"  Cache hits: {hits}")
    print(f"  Cache misses: {misses}")
    print(f"  Hit rate: {hit_rate:.1%}")
    print(f"  Cache size: {len(_BPE_WORD_CACHE)} entries")
    print(f"  Cache memory (approx): {sum(len(k) + sum(len(v) for v in vs) for k, vs in _BPE_WORD_CACHE.items())} bytes")

    # Profile bpe_tokenize cost
    profiler = cProfile.Profile()
    profiler.enable()
    start = time.perf_counter()
    for _ in range(5):
        bpe_tokenize(text)
    elapsed = time.perf_counter() - start
    profiler.disable()

    print(f"\n  bpe_tokenize 5x over 1000-word text: {elapsed:.3f}s")
    print(f"  Per call: {elapsed/5*1000:.1f}ms")

    buf = io.StringIO()
    ps = pstats.Stats(profiler, stream=buf).sort_stats('tottime')
    ps.print_stats(10)
    print("\n  bpe_tokenize internals:")
    print("  " + "\n  ".join(buf.getvalue().split("\n")))


def profile_detect_multi_key():
    """Profile detect_multi_key path."""
    print("\n" + "=" * 70)
    print("3. PROFILING detect_multi_key")
    print("=" * 70)

    random.seed(42)
    text = generate_text(500)
    keys = [
        {"key_id": f"key-{i}", "secret": f"secret-{i}", "family": "kgw"}
        for i in range(5)
    ]

    profiler = cProfile.Profile()
    profiler.enable()
    start = time.perf_counter()
    for _ in range(50):
        result = detect_multi_key(text, keys, level="word", context=1)
    elapsed = time.perf_counter() - start
    profiler.disable()

    print(f"  50 iterations over 500-word text, 5 keys: {elapsed:.3f}s")
    print(f"  Per iteration: {elapsed/50*1000:.1f}ms")
    print(f"  Tested keys: {result['tested_keys']}")

    buf = io.StringIO()
    ps = pstats.Stats(profiler, stream=buf).sort_stats('tottime')
    ps.print_stats(15)
    print("\n  Top 15 functions (internal time):")
    print("  " + "\n  ".join(buf.getvalue().split("\n")))


def profile_batch():
    """Profile batch processing loop."""
    print("\n" + "=" * 70)
    print("4. PROFILING batch processing")
    print("=" * 70)

    import tempfile
    import json

    # Create temp dir with files
    tmpdir = Path(tempfile.mkdtemp(prefix="tws_profile_batch_"))
    input_dir = tmpdir / "input"
    output_dir = tmpdir / "output"
    input_dir.mkdir()

    random.seed(42)
    n_files = 200
    for i in range(n_files):
        text = generate_text(100)
        (input_dir / f"file_{i:04d}.txt").write_text(text, encoding="utf-8")

    # Profile process_batch
    from ai_watermark_toolkit.batch import process_batch

    profiler = cProfile.Profile()
    profiler.enable()
    start = time.perf_counter()
    result = process_batch(str(input_dir), str(output_dir), mode="detect")
    elapsed = time.perf_counter() - start
    profiler.disable()

    print(f"  process_batch: {result['count']} files in {elapsed:.3f}s")
    print(f"  Throughput: {result['count']/elapsed:.1f} files/s")
    print(f"  Per file: {elapsed/result['count']*1000:.1f}ms")

    buf = io.StringIO()
    ps = pstats.Stats(profiler, stream=buf).sort_stats('tottime')
    ps.print_stats(15)
    print("\n  Top 15 functions (internal time):")
    print("  " + "\n  ".join(buf.getvalue().split("\n")))

    # Cleanup
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


def profile_watcher():
    """Profile watcher loop."""
    print("\n" + "=" * 70)
    print("5. PROFILING watcher loop")
    print("=" * 70)

    import tempfile
    import shutil

    tmpdir = Path(tempfile.mkdtemp(prefix="tws_profile_watch_"))
    watch_dir_path = tmpdir / "watched"
    watch_dir_path.mkdir()

    random.seed(42)
    n_files = 500
    for i in range(n_files):
        text = generate_text(100)
        sub = watch_dir_path / f"watch_{i // 100:03d}"
        sub.mkdir(exist_ok=True)
        (sub / f"file_{i:04d}.txt").write_text(text, encoding="utf-8")

    from ai_watermark_toolkit.forensics.watcher import watch_dir

    profiler = cProfile.Profile()
    profiler.enable()
    start = time.perf_counter()
    reported = watch_dir(str(watch_dir_path), once=True)
    elapsed = time.perf_counter() - start
    profiler.disable()

    print(f"  watch_dir(once=True): {reported} files in {elapsed:.3f}s")
    print(f"  Throughput: {reported/elapsed:.1f} files/s")

    buf = io.StringIO()
    ps = pstats.Stats(profiler, stream=buf).sort_stats('tottime')
    ps.print_stats(15)
    print("\n  Top 15 functions (internal time):")
    print("  " + "\n  ".join(buf.getvalue().split("\n")))

    shutil.rmtree(tmpdir, ignore_errors=True)


def profile_memory():
    """Check for memory leaks with tracemalloc."""
    print("\n" + "=" * 70)
    print("6. MEMORY LEAK CHECK (tracemalloc)")
    print("=" * 70)

    random.seed(42)
    text = generate_text(500)
    key = "test-key-memory-2026"
    keys = [{"key_id": "k1", "secret": "s1", "family": "kgw"}]

    # Snapshot before
    tracemalloc.start()
    snapshot1 = tracemalloc.take_snapshot()

    # Run 100 iterations
    for _ in range(100):
        mark_greenlist(text, key, gamma=0.25, vocab=FREQUENT_VOCAB, seed=42)
        detect_multi_key(text, keys, level="word", context=1)

    snapshot2 = tracemalloc.take_snapshot()
    tracemalloc.stop()

    # Compare
    stats = snapshot2.compare_to(snapshot1, 'lineno')
    print("\n  Top 10 memory growth (lineno):")
    for stat in stats[:10]:
        print(f"    {stat}")

    # Check current vs peak
    tracemalloc.start()
    for _ in range(200):
        mark_greenlist(text, key, gamma=0.25, vocab=FREQUENT_VOCAB, seed=42)
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"\n  After 200 mark_greenlist calls:")
    print(f"    Current: {current/1024:.1f} KB")
    print(f"    Peak: {peak/1024:.1f} KB")
    print(f"    BPE cache entries: {len(_BPE_WORD_CACHE)}")


if __name__ == "__main__":
    print("TWS v108 — Eighth Pass: Performance Profiling")
    print(f"Python: {sys.version}")
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    profile_mark_greenlist()
    profile_bpe_cache()
    profile_detect_multi_key()
    profile_batch()
    profile_watcher()
    profile_memory()

    print("\n" + "=" * 70)
    print("PROFILING COMPLETE")
    print("=" * 70)
