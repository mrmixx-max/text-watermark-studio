"""Run all performance benchmarks and collect results into a single JSON report.

Usage:
    python benchmarks/run_all_benchmarks.py [--output benchmarks/benchmark_results.json]
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent
ROOT = BENCH_DIR.parent

BENCHMARKS = [
    ("embed", "benchmark_embed.py", {"--n": "1000", "--length": "200"}),
    ("detect", "benchmark_detect.py", {"--n": "1000", "--length": "200"}),
    ("batch", "benchmark_batch.py", {"--n": "10000", "--length": "100", "--mode": "detect"}),
    ("watch", "benchmark_watch.py", {"--n": "1000", "--length": "100"}),
]


def run_benchmark(name: str, script: str, args: dict) -> dict:
    cmd = [sys.executable, str(BENCH_DIR / script)]
    for k, v in args.items():
        cmd.extend([k, v])
    output_file = BENCH_DIR / f"_result_{name}.json"
    cmd.extend(["--output", str(output_file)])

    print(f"\n{'='*60}")
    print(f"Running benchmark: {name}")
    print(f"  Command: {' '.join(cmd)}")
    print(f"{'='*60}")

    t0 = time.perf_counter()
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    elapsed = time.perf_counter() - t0

    if result.returncode != 0:
        print(f"  FAILED (exit {result.returncode})")
        print(f"  stderr: {result.stderr[:500]}")
        return {"benchmark": name, "error": f"exit {result.returncode}", "stderr": result.stderr[:500]}

    data = json.loads(output_file.read_text())
    data["wall_time_sec"] = round(elapsed, 3)
    output_file.unlink(missing_ok=True)
    return data


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=str, default=str(BENCH_DIR / "benchmark_results.json"))
    args = ap.parse_args()

    results = {}
    for name, script, script_args in BENCHMARKS:
        results[name] = run_benchmark(name, script, script_args)

    report = {
        "meta": {
            "project": "Text Watermark Studio v108",
            "python": sys.version,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        },
        "results": results,
    }

    Path(args.output).write_text(json.dumps(report, indent=2))
    print(f"\n{'='*60}")
    print(f"All benchmarks complete. Results written to: {args.output}")
    print(f"{'='*60}")

    # Print summary table
    print(f"\n{'Benchmark':<12} {'N':>8} {'Time (s)':>10} {'Files/s':>10} {'ms/file':>10} {'Peak MB':>10}")
    print("-" * 62)
    for name, data in results.items():
        if "error" in data:
            print(f"{name:<12} {'ERROR':>8}")
            continue
        print(f"{name:<12} {data.get('n', data.get('files_created', data.get('files_reported', 0))):>8} "
              f"{data.get('elapsed_sec', data.get('process_elapsed_sec', data.get('scan_elapsed_sec', 0))):>10.3f} "
              f"{data.get('throughput_files_per_sec', 0):>10.1f} "
              f"{data.get('avg_ms_per_file', 0):>10.3f} "
              f"{data.get('peak_memory_mb', 0):>10.3f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
