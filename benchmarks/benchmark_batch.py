"""Benchmark: batch processing throughput.

Creates a directory with N synthetic .txt files and runs process_batch()
on them. Measures total runtime, throughput, and peak memory.

Usage:
    python benchmarks/benchmark_batch.py [--n 10000] [--length 100] [--mode detect] [--seed 42]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ai_watermark_toolkit.batch import process_batch  # noqa: E402


def generate_text(length: int, seed: int) -> str:
    rng = __import__("random").Random(seed)
    words = [
        "the", "quick", "brown", "fox", "jumps", "over", "lazy", "dog",
        "furthermore", "moreover", "however", "therefore", "consequently",
        "significant", "results", "were", "observed", "experimental", "analysis",
        "confirmed", "hypothesis", "data", "shows", "clear", "pattern",
        "consistent", "previous", "studies", "indicate", "strong", "evidence",
    ]
    return " ".join(rng.choices(words, k=length))


def create_files(directory: Path, n: int, length: int, seed: int) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        sub = directory / f"batch_{i // 1000:03d}"
        sub.mkdir(exist_ok=True)
        (sub / f"file_{i:05d}.txt").write_text(
            generate_text(length, seed + i), encoding="utf-8"
        )


def main() -> int:
    ap = argparse.ArgumentParser(description="batch processing throughput benchmark")
    ap.add_argument("--n", type=int, default=10000, help="number of files (default 10000)")
    ap.add_argument("--length", type=int, default=100, help="words per file (default 100)")
    ap.add_argument("--mode", type=str, default="detect",
                    choices=["detect", "clean", "dilute", "pipeline"],
                    help="batch mode (default detect)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--output", type=str, default=None, help="JSON output path")
    ap.add_argument("--workdir", type=str, default=None,
                    help="working directory (default: system temp)")
    args = ap.parse_args()

    workdir = Path(args.workdir) if args.workdir else Path(tempfile.mkdtemp(prefix="tws_bench_batch_"))
    input_dir = workdir / "input"
    output_dir = workdir / "output"

    print(f"[{args.benchmark if hasattr(args, 'benchmark') else 'batch'}] Creating {args.n} files in {input_dir} ...")
    t_create = time.perf_counter()
    create_files(input_dir, args.n, args.length, args.seed)
    create_elapsed = time.perf_counter() - t_create

    # Warmup (small batch)
    warmup_dir = workdir / "warmup_in"
    warmup_out = workdir / "warmup_out"
    warmup_dir.mkdir(exist_ok=True)
    (warmup_dir / "warmup.txt").write_text(generate_text(50, 999), encoding="utf-8")
    process_batch(str(warmup_dir), str(warmup_out), mode=args.mode)

    # Benchmark
    print(f"[batch] Running process_batch(mode={args.mode}) on {args.n} files ...")
    tracemalloc.start()
    t0 = time.perf_counter()

    result = process_batch(str(input_dir), str(output_dir), mode=args.mode)

    elapsed = time.perf_counter() - t0
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # Compute stats
    total_chars = sum(len(generate_text(args.length, args.seed + i)) for i in range(args.n))
    throughput = args.n / elapsed if elapsed > 0 else float("inf")

    report = {
        "benchmark": "batch",
        "mode": args.mode,
        "n": args.n,
        "words_per_text": args.length,
        "files_created": result.get("count", 0),
        "create_elapsed_sec": round(create_elapsed, 3),
        "process_elapsed_sec": round(elapsed, 4),
        "throughput_files_per_sec": round(throughput, 2),
        "avg_ms_per_file": round(elapsed / args.n * 1000, 3),
        "peak_memory_mb": round(peak / 1024 / 1024, 3),
        "current_memory_mb": round(current / 1024 / 1024, 3),
        "workdir": str(workdir),
    }

    print(json.dumps(report, indent=2))

    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2))

    # Cleanup
    if not args.workdir:
        shutil.rmtree(workdir, ignore_errors=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
