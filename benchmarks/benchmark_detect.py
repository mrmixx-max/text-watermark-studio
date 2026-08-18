"""Benchmark: detect_text() throughput.

Measures runtime + peak memory for the full detection pipeline
(unicode analysis, marker scanning, style features, n-gram bias)
over n synthetic texts.

Usage:
    python benchmarks/benchmark_detect.py [--n 1000] [--length 200] [--seed 42]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import tracemalloc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ai_watermark_toolkit.pipeline import detect_text  # noqa: E402


def generate_texts(n: int, length: int, seed: int) -> list[str]:
    """Generate n synthetic texts with ~`length` words each."""
    rng = __import__("random").Random(seed)
    words = [
        "the", "quick", "brown", "fox", "jumps", "over", "lazy", "dog",
        "furthermore", "moreover", "however", "therefore", "consequently",
        "significant", "results", "were", "observed", "experimental", "analysis",
        "confirmed", "hypothesis", "data", "shows", "clear", "pattern",
        "consistent", "previous", "studies", "indicate", "strong", "evidence",
        "supporting", "theoretical", "framework", "methodology", "approach",
        "provides", "robust", "foundation", "future", "research", "directions",
        "important", "note", "findings", "suggest", "novel", "interpretation",
        "careful", "consideration", "required", "before", "drawing", "conclusions",
    ]
    texts = []
    for _ in range(n):
        text = " ".join(rng.choices(words, k=length))
        texts.append(text)
    return texts


def main() -> int:
    ap = argparse.ArgumentParser(description="detect_text throughput benchmark")
    ap.add_argument("--n", type=int, default=1000, help="number of texts (default 1000)")
    ap.add_argument("--length", type=int, default=200, help="words per text (default 200)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--output", type=str, default=None, help="JSON output path")
    args = ap.parse_args()

    texts = generate_texts(args.n, args.length, args.seed)

    # Warmup
    detect_text(texts[0], lang="auto")

    # Benchmark
    tracemalloc.start()
    t0 = time.perf_counter()

    results = []
    for txt in texts:
        r = detect_text(txt, lang="auto")
        results.append(r)

    elapsed = time.perf_counter() - t0
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # Compute stats
    total_chars = sum(len(t) for t in texts)
    throughput = args.n / elapsed if elapsed > 0 else float("inf")

    report = {
        "benchmark": "detect",
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
