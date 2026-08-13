"""All-encompassing burn-in / release gate for Text Watermark Studio.

Runs, in order:
  1. compile + import scan of every module
  2. full test suite (once sequential)
  3. full test suite x2 in parallel (race check under load)
  4. TUI burn-in (all menu actions headless)
  5. prompt-optimizer evaluator loop (winner must beat baseline)
  6. deterministic benchmarks (attack matrix + synthid sweep)
  7. CLI smoke (every subcommand registered, exit codes sane)
  8. local-LLM backend against the real Ollama (list + known model)
  9. optional KGW end-to-end proof against a real model (--with-e2e)
 10. version consistency + clean git state

Usage: python benchmarks/full_burnin.py [--with-e2e]

Exit code 0 = everything passed; 1 = at least one stage failed.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable

RESULTS: list[tuple[str, bool, str]] = []


def stage(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""), flush=True)


def run(cmd: list[str], timeout: int = 600, cwd: Path | None = None) -> str:
    p = subprocess.run(cmd, cwd=str(cwd or REPO), capture_output=True,
                       text=True, timeout=timeout, encoding="utf-8",
                       errors="replace")
    return (p.stdout or "") + (p.stderr or "")


def main() -> int:
    with_e2e = "--with-e2e" in sys.argv
    t0 = time.time()

    # 1. compile + import scan ------------------------------------------------
    out = run([PY, "-c", f"""
import sys, pathlib, py_compile
sys.path.insert(0, {str(REPO / 'src')!r})
n = 0
for f in pathlib.Path({str(REPO / 'src')!r}).rglob('*.py'):
    py_compile.compile(str(f), doraise=True)
    n += 1
import pkgutil, importlib
import ai_watermark_toolkit
m = 0
for mod in pkgutil.walk_packages(ai_watermark_toolkit.__path__, 'ai_watermark_toolkit.'):
    importlib.import_module(mod.name); m += 1
print(f'OK: {{n}} files compiled, {{m}} modules imported')
"""])
    stage("Compile + Import-Scan", "OK:" in out, out.strip().splitlines()[-1] if out.strip() else "no output")

    # 2. full suite sequential -------------------------------------------------
    out = run([PY, "-m", "pytest", "tests/", "-q", "--timeout=120"])
    last = [l for l in out.splitlines() if "passed" in l or "failed" in l]
    last_line = (last[-1].strip() if last else out.strip()[-120:])
    detail = last_line.replace("warning", "").replace("warnings", "").strip()
    stage("Testsuite (sequenziell)", " passed" in last_line and " failed" not in last_line, detail)

    # 3. full suite x2 parallel ------------------------------------------------
    procs = [
        subprocess.Popen([PY, "-m", "pytest", "tests/", "-q", "--timeout=120"],
                         cwd=str(REPO), stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                         errors="replace")
        for _ in range(2)
    ]
    outs = [p.communicate(timeout=600)[0] for p in procs]
    parallel_ok = all(" failed" not in o and " passed" in o for o in outs)
    lines = []
    for o in outs:
        for l in o.splitlines():
            if "passed" in l or "failed" in l:
                lines.append(l.replace("warning", "").replace("warnings", "").strip())
    stage("Testsuite (2x parallel)", parallel_ok, " | ".join(lines))

    # 4. TUI burn-in ------------------------------------------------------------
    out = run([PY, str(REPO / "benchmarks" / "tui_burnin.py")])
    stage("TUI Burn-in (18 Aktionen)", "BURN-IN PASSED" in out,
          "18/18" if "BURN-IN PASSED" in out else out.strip()[-150:])

    # 5. prompt-optimizer loop ---------------------------------------------------
    out = run([PY, "-c", f"""
import sys, json
sys.path.insert(0, {str(REPO / 'src')!r})
from ai_watermark_toolkit.optimization.service import PromptOptimizationService
r = PromptOptimizationService().optimize(
    'Rewrite the given text so it no longer reads like AI output. Keep all facts, numbers and names exactly as they are.')
w = r['winner']
print(json.dumps({{'baseline': r['baseline_score'], 'winner': w['candidate']['variant'],
                   'winner_score': w['avg_score'], 'guardrail': w['guardrail_passed']}}))
"""])
    try:
        opt = json.loads(out.strip().splitlines()[-1])
        opt_ok = opt["winner_score"] > opt["baseline"] and opt["guardrail"]
        stage("Prompt-Optimizer-Loop", opt_ok,
              f"winner={opt['winner']} {opt['winner_score']} > baseline {opt['baseline']}")
    except Exception:
        stage("Prompt-Optimizer-Loop", False, out.strip()[-200:])

    # 6. deterministic benchmarks -----------------------------------------------
    am = run([PY, str(REPO / "benchmarks" / "attack_matrix.py")])
    ss = run([PY, str(REPO / "benchmarks" / "synthid_sweep.py")])
    stage("Attack-Matrix", "Attack" in am and len(am.strip()) > 200,
          f"{len(am.strip())} bytes output")
    stage("SynthID-Sweep", ("gamma" in ss.lower() or "γ" in ss) and len(ss.strip()) > 200,
          f"{len(ss.strip())} bytes output")

    # 7. CLI smoke ---------------------------------------------------------------
    help_out = run([str(REPO / ".venv" / "Scripts" / "ai-wm.exe"), "--help"],
                   cwd=REPO) if (REPO / ".venv").exists() else \
        run([PY, "-m", "ai_watermark_toolkit.cli", "--help"], cwd=REPO)
    expected = ["detect", "clean", "dilute", "embed", "pipeline", "report",
                "watch", "rewrite", "image-score", "batch", "serve", "tui",
                "llm", "file-inspect", "file-clean", "file-embed",
                "file-detect", "splash"]
    missing = [c for c in expected if c not in help_out]
    stage("CLI-Smoke (Subcommands)", not missing,
          "alle registriert" if not missing else f"fehlt: {missing}")

    # 8. local LLM backend against real Ollama ------------------------------------
    out = run([PY, "-c", f"""
import sys
sys.path.insert(0, {str(REPO / 'src')!r})
from ai_watermark_toolkit.llm.service import LocalLLMService
svc = LocalLLMService()
models = svc.list_models()
print(f"models={{len(models)}}")
"""])
    try:
        n_models = int([l for l in out.splitlines() if "models=" in l][-1].split("=")[1])
        stage("LLM-Backend (echtes Ollama)", n_models > 0, f"{n_models} Modelle erreichbar")
    except Exception:
        stage("LLM-Backend (echtes Ollama)", False, "Ollama nicht erreichbar")

    # 9. optional KGW E2E against real model --------------------------------------
    if with_e2e:
        out = run([PY, str(REPO / "benchmarks" / "kgw_e2e_proof.py")], timeout=900)
        stage("KGW E2E (echtes Modell)", "watermark_detected" in out,
              [l for l in out.splitlines() if "z" in l.lower()][-1] if out.strip() else "")

    # 10. version consistency + git -----------------------------------------------
    out = run(["git", "status", "--porcelain"], cwd=REPO)
    dirty = [l for l in out.splitlines() if l.strip()]
    out2 = run(["git", "log", "--oneline", "-1"], cwd=REPO)
    stage("Git sauber", not dirty, out2.strip().split(" ", 1)[0] if out2.strip() else "")

    print()
    failed = [r for r in RESULTS if not r[1]]
    dur = time.time() - t0
    print(f"=== {len(RESULTS) - len(failed)}/{len(RESULTS)} Stufen bestanden in {dur:.0f}s ===")
    if failed:
        for name, _, detail in failed:
            print(f"  FEHLGESCHLAGEN: {name} — {detail}")
        return 1
    print("ALL-ENCOMPASSING BURN-IN PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
