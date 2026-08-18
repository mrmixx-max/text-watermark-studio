"""Benchmark: watch directory throughput (single pass).

Creates a directory with N synthetic files and runs watch_dir(once=True)
to measure how quickly a full directory sweep completes.

Usage:
    python benchmarks/benchmark_watch.py [--n 1000] [--length 100] [--seed 42]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ai_watermark_toolkit.forensics.watcher import watch_dir  # noqa: E402


def generate_text(length: int, seed: int) -> str:
    rng = __import__("random").Random(seed)
    words = [
        "the", "quick", "brown", "fox", "jumps", "over", "lazy", "dog",
        "furthermore", "moreover", "however", "therefore", "consequently",
        "significant", "results", "were", "observed", "experimental", "analysis",
        "confirmed", "hypothesis", "data", "shows", "clear", "pattern",
    ]
    return " ".join(rng.choices(words, k=length))


def create_files(directory: Path, n: int, length: int, seed: int) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    # Mix file types to exercise the scanner's format dispatch
    exts = [".txt", ".md", ".html", ".rst"]
    for i in range(n):
        sub = directory / f"watch_{i // 250:03d}"
        sub.mkdir(exist_ok=True)
        ext = exts[i % len(exts)]
        (sub / f"file_{i:05d}{ext}").write_text(
            generate_text(length, seed + i), encoding="utf-8"
        )


def main() -> int:
    ap = argparse.ArgumentParser(description="watch_dir throughput benchmark")
    ap.add_argument("--n", type=int, default=1000, help="number of files (default 1000)")
    ap.add_argument("--length", type=int, default=100, help="words per file (default 100)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--output", type=str, default=None, help="JSON output path")
    ap.add_argument("--workdir", type=str, default=None,
                    help="working directory (default: system temp)")
    args = ap.parse_args()

    workdir = Path(args.workdir) if args.workdir else Path(tempfile.mkdtemp(prefix="tws_bench_watch_"))
    watch_path = workdir / "watched"

    print(f"[watch] Creating {args.n} files in {watch_path} ...")
    t_create = time.perf_counter()
    create_files(watch_path, args.n, args.length, args.seed)
    create_elapsed = time.perf_counter() - t_create

    # Warmup
    warmup_dir = workdir / "warmup"
    warmup_dir.mkdir(exist_ok=True)
    (warmup_dir / "warmup.txt").write_text(generate_text(50, 999), encoding="utf-8")
    watch_dir(str(warmup_dir), once=True)

    # Benchmark
    print(f"[watch] Running watch_dir(once=True) on {args.n} files ...")
    tracemalloc.start()
    t0 = time.perf_counter()

    reported = watch_dir(str(watch_path), once=True)

    elapsed = time.perf_counter() - t0
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    throughput = reported / elapsed if elapsed > 0 else float("inf")

    report = {
        "benchmark": "watch",
        "n": args.n,
        "words_per_text": args.length,
        "files_reported": reported,
        "create_elapsed_sec": round(create_elapsed, 3),
        "scan_elapsed_sec": round(elapsed, 4),
        "throughput_files_per_sec": round(throughput, 2),
        "avg_ms_per_file": round(elapsed / reported * 1000, 3) if reported > 0 else 0,
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
