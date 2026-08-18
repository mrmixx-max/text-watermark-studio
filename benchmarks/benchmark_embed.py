"""Benchmark: KGW watermark embedding throughput.

Measures runtime + peak memory for mark_greenlist() over n synthetic texts.
Uses the demo KGW key (secret="demo-kgw-secret-0001", gamma=0.25).

Usage:
    python benchmarks/benchmark_embed.py [--n 1000] [--length 200] [--seed 42]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import tracemalloc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ai_watermark_toolkit.forensics.kgw import mark_greenlist  # noqa: E402


def generate_texts(n: int, length: int, seed: int) -> list[str]:
    """Generate n synthetic texts with ~`length` words each."""
    rng = __import__("random").Random(seed)
    words = [
        "the", "quick", "brown", "fox", "jumps", "over", "lazy", "dog",
        "lorem", "ipsum", "dolor", "sit", "amet", "consectetur", "adipiscing",
        "elit", "sed", "do", "eiusmod", "tempor", "incididunt", "ut", "labore",
        "et", "dolore", "magna", "aliqua", "enim", "ad", "minim", "veniam",
        "quis", "nostrud", "exercitation", "ullamco", "laboris", "nisi",
        "aliquip", "ex", "ea", "commodo", "consequat", "duis", "aute", "irure",
        "in", "reprehenderit", "voluptate", "velit", "esse", "cillum", "fugiat",
        "nulla", "pariatur", "excepteur", "sint", "occaecat", "cupidatat",
        "non", "proident", "sunt", "culpa", "qui", "officia", "deserunt",
        "mollit", "anim", "id", "est", "laborum", "significant", "results",
        "were", "observed", "experimental", "analysis", "confirmed", "hypothesis",
        "data", "shows", "clear", "pattern", "consistent", "previous", "studies",
    ]
    texts = []
    for _ in range(n):
        text = " ".join(rng.choices(words, k=length))
        texts.append(text)
    return texts


def main() -> int:
    ap = argparse.ArgumentParser(description="KGW embed throughput benchmark")
    ap.add_argument("--n", type=int, default=1000, help="number of texts (default 1000)")
    ap.add_argument("--length", type=int, default=200, help="words per text (default 200)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--output", type=str, default=None, help="JSON output path")
    args = ap.parse_args()

    texts = generate_texts(args.n, args.length, args.seed)
    secret = "demo-kgw-secret-0001"
    gamma = 0.25

    # Warmup
    mark_greenlist(texts[0], secret, gamma=gamma, level="word", context=1)

    # Benchmark
    tracemalloc.start()
    t0 = time.perf_counter()

    results = []
    for txt in texts:
        r = mark_greenlist(txt, secret, gamma=gamma, level="word", context=1)
        results.append(r)

    elapsed = time.perf_counter() - t0
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # Compute stats
    total_chars = sum(len(t) for t in texts)
    throughput = args.n / elapsed if elapsed > 0 else float("inf")

    report = {
        "benchmark": "embed",
        "n": args.n,
        "words_per_text": args.length,
        "total_chars": total_chars,
        "elapsed_sec": round(elapsed, 4),
        "throughput_files_per_sec": round(throughput, 2),
        "avg_ms_per_file": round(elapsed / args.n * 1000, 3),
        "peak_memory_mb": round(peak / 1024 / 1024, 3),
        "current_memory_mb": round(current / 1024 / 1024, 3),
        "chars_per_sec": round(total_chars / elapsed, 0) if elapsed > 0 else 0,
    }

    print(json.dumps(report, indent=2))

    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
