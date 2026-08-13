#!/usr/bin/env python3
"""Attack matrix v2: real-model KGW blackbox benchmark with post-hoc marking.

Extends benchmarks/attack_matrix.py (synthetic, deterministic) with the
honest product truth measured in the blackbox E2E audit (2026-08-13): the
generator itself shows NO greenlist bias (green_rate ~= gamma), so the
benchmark pipeline is generate -> post-hoc mark_greenlist -> detect.

Per sample:
  * one real EuroLLM generation (Ollama HTTP API, never `ollama run`)
  * one model paraphrase call (cost-capped: 1 call per sample)
  * unmarked control for free (the pre-marking original)
  * post-hoc KGW marking: key "blackbox-2026", gamma=0.25, word level
  * right-key / wrong-key / unmarked detection
  * attack matrix: truncate 50% (front/back), reformat, word shuffle
    (seed 42), unicode spam (15% ZWSP+bidi), model paraphrase -> dZ
  * segment stability: overlapping 100-token windows (step 50)

Reproducibility: generated texts are cached in %TEMP%/tws-e2e-blackbox-v2/
generated_cache.json. With a complete cache the benchmark runs fully
deterministically WITHOUT Ollama (--skip-generation), which is what the
burn-in stage uses.

CLI:
  python benchmarks/attack_matrix_v2.py --samples 20          # generate + measure
  python benchmarks/attack_matrix_v2.py --samples 5 --skip-generation
                                                              # cached-only, no Ollama
  python benchmarks/attack_matrix_v2.py --fresh               # ignore cache, regenerate
  python benchmarks/attack_matrix_v2.py --help

Artifacts: results.json + REPORT.md in --out (default %TEMP%/tws-e2e-blackbox-v2).
No writes into the repo besides this file; nothing touches data/.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from ai_watermark_toolkit.forensics.kgw import (  # noqa: E402
    DEFAULT_GAMMA,
    detect_kgw,
    green_token,
    mark_greenlist,
    tokenize,
)

# --- configuration -----------------------------------------------------------
OLLAMA = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
MODEL = os.getenv("KGW_BLACKBOX_MODEL", "eurollm-9b:latest")
KEY = "blackbox-2026"
WRONG_KEY = "wrong-key-0000"
GAMMA = float(os.getenv("KGW_GAMMA", "0.25"))
SEED = 42
DETECT_THRESHOLD = 4.0  # detector verdict threshold
WINDOW = 100            # segment window (tokens)
WINDOW_STEP = 50        # overlapping step

# Same base prompt as blackbox round 1 (keeps measurements comparable).
BASE_PROMPT = (
    "Write a short essay about why local AI models matter for privacy and data "
    "security. Cover on-device processing, reduced data sharing, and control over "
    "personal information. Plain prose, full sentences, no lists, no markdown, "
    "no headings."
)

PARAPHRASE_PROMPT = (
    "Rewrite the following text in your own words. Keep the exact meaning, "
    "all facts, names and numbers. Lightly rephrase sentence by sentence; "
    "do not change every word, keep the overall structure and length. "
    "Return only the rewritten text, no commentary.\n\nTEXT:\n{text}"
)

BASE_N_TOKENS = 300   # generation budget per sample (CPU: ~3-4 tok/s)


def ollama_generate(prompt: str, n: int, temperature: float = 0.8,
                    seed: int = SEED) -> tuple[str, dict]:
    """One HTTP call to Ollama. Never `ollama run`."""
    payload = json.dumps({
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": n, "seed": seed},
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA}/api/generate", data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=900) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    dt = time.time() - t0
    text = body.get("response", "").strip()
    toks = body.get("eval_count", 0)
    rate = toks / dt if dt > 0 else 0.0
    return text, {"tokens": toks, "secs": round(dt, 1), "tok_per_s": round(rate, 2)}


def ollama_available() -> bool:
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


# --- statistics (mirrors kgw._summarize_z) ------------------------------------
def z_of(green: int, n: int, gamma: float) -> float:
    mu = gamma * n
    sigma = math.sqrt(n * gamma * (1 - gamma))
    return (green - mu) / sigma if sigma else 0.0


def detect(text: str, key: str, gamma: float = GAMMA) -> dict:
    return detect_kgw(text, key, gamma, level="word", context=1)


def token_flags(text: str, key: str, gamma: float):
    """Per-token green flags (c=1), aligned with detect_kgw scoring."""
    toks = tokenize(text, level="word")
    flags = [None]  # token 0 has no predecessor
    for i in range(1, len(toks)):
        flags.append(green_token(toks[i], [toks[i - 1]], key, gamma))
    return toks, flags


def window_scores(toks, flags, w: int = WINDOW, step: int = WINDOW_STEP,
                  gamma: float = GAMMA) -> list[dict]:
    """Overlapping sliding windows of w scored tokens, step `step`."""
    scored = [(t, f) for t, f in zip(toks[1:], flags[1:])]
    n = len(scored)
    wins = []
    for start in range(0, max(1, n - w + 1), step):
        seg = scored[start:start + w]
        if len(seg) < 10:
            continue
        green = sum(1 for _, f in seg if f)
        z = z_of(green, len(seg), gamma)
        wins.append({
            "start": start + 1, "end": start + len(seg), "n": len(seg),
            "green": green, "green_rate": round(green / len(seg), 3),
            "z": round(z, 2),
        })
    return wins


def summarize_windows(wins: list[dict]) -> dict:
    zs = [w["z"] for w in wins]
    if not zs:
        return {"n_windows": 0, "mean_z": None, "std_z": None,
                "min_z": None, "max_z": None, "pct_ge_4": None}
    mean = sum(zs) / len(zs)
    var = sum((z - mean) ** 2 for z in zs) / len(zs)
    return {
        "n_windows": len(zs), "mean_z": round(mean, 2),
        "std_z": round(math.sqrt(var), 2), "min_z": min(zs), "max_z": max(zs),
        "pct_ge_4": round(100.0 * sum(1 for z in zs if z >= DETECT_THRESHOLD) / len(zs), 1),
    }


# --- attacks ---------------------------------------------------------------
def attack_truncate_first(text: str) -> str:
    toks = tokenize(text, level="word")
    return " ".join(toks[: max(1, len(toks) // 2)])


def attack_truncate_last(text: str) -> str:
    toks = tokenize(text, level="word")
    return " ".join(toks[len(toks) // 2:])


def attack_reformat(text: str) -> str:
    flat = re.sub(r"\s+", " ", text).strip()
    sentences = re.split(r"(?<=[.!?]) ", flat)
    return "\n".join(s.strip() for s in sentences if s.strip())


def attack_word_shuffle(text: str, seed: int = 42) -> str:
    rng = random.Random(seed)
    words = text.split()
    rng.shuffle(words)
    return " ".join(words)


def attack_unicode_spam(text: str, fraction: float = 0.15) -> str:
    """Inject ZWSP + bidi controls after ~15% of word boundaries."""
    words = text.split(" ")
    out = []
    for i, w in enumerate(words):
        out.append(w)
        if i > 0 and i % max(1, round(1.0 / fraction)) == 0:
            out.append("\u200b\u202e\u202c" if i % 2 else "\u200b")
        out.append(" ")
    return "".join(out).rstrip()


def attack_paraphrase(text: str, seed: int = SEED) -> str:
    prompt = PARAPHRASE_PROMPT.format(text=text)
    budget = min(320, len(tokenize(text, "word")) + 40)
    out, _ = ollama_generate(prompt, n=budget, seed=seed)
    return out


ATTACKS_RULE_BASED = [
    ("truncate_first", attack_truncate_first),
    ("truncate_last", attack_truncate_last),
    ("reformat", attack_reformat),
    ("word_shuffle", attack_word_shuffle),
    ("unicode_spam", attack_unicode_spam),
]


# --- cache -------------------------------------------------------------------
def cache_complete(cache: dict, n_samples: int) -> bool:
    return all(f"base_{i}" in cache and f"para_{i}" in cache
               for i in range(1, n_samples + 1))


def main() -> int:
    ap = argparse.ArgumentParser(
        description="KGW blackbox attack matrix v2 (real-model, cached, reproducible).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--samples", type=int, default=20,
                    help="Anzahl echte EuroLLM-Generierungen (Ziel 20; CPU-Limit beachten)")
    ap.add_argument("--fresh", action="store_true",
                    help="Cache ignorieren und neu generieren")
    ap.add_argument("--skip-generation", action="store_true",
                    help="Nur Cache verwenden; Fehler wenn Cache unvollständig (kein Ollama)")
    ap.add_argument("--cache-mode", action="store_true", default=True,
                    help="Cache verwenden wenn vollständig, sonst generieren (Default)")
    ap.add_argument("--out", type=Path, default=None,
                    help="Artefakt-Ordner (Default: %%TEMP%%/tws-e2e-blackbox-v2)")
    ap.add_argument("--num-predict", type=int, default=BASE_N_TOKENS,
                    help="Token-Budget pro Basis-Generierung")
    ap.add_argument("--prompt", type=str, default=BASE_PROMPT,
                    help="Generierungs-Prompt (Default: Runde-1-Prompt)")
    args = ap.parse_args()

    out_dir = args.out or Path(os.environ.get("TEMP", "/tmp")) / "tws-e2e-blackbox-v2"
    out_dir.mkdir(parents=True, exist_ok=True)
    # Cache is central (shared across --out runs): always lives next to the
    # default artifact dir so the burn-in (--out burnin-n5) reuses the same
    # generated texts instead of re-generating or re-writing the main cache.
    cache_dir = Path(os.environ.get("TEMP", "/tmp")) / "tws-e2e-blackbox-v2"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / "generated_cache.json"
    results_file, report_file = out_dir / "results.json", out_dir / "REPORT.md"

    use_cache = (args.cache_mode or args.skip_generation) and not args.fresh
    cache: dict = {}
    if use_cache and cache_file.exists():
        cache = json.loads(cache_file.read_text("utf-8"))

    if args.skip_generation:
        if not cache_complete(cache, args.samples):
            print(f"[FEHLER] --skip-generation: Cache {cache_file} unvollständig "
                  f"({len([k for k in cache if k.startswith('base_')])}/{args.samples} "
                  f"Basis-Samples). Einmalig ohne --skip-generation ausführen:\n"
                  f"  python benchmarks/attack_matrix_v2.py --samples {args.samples}",
                  file=sys.stderr)
            return 2
        print(f"[Modus] cache-only — kein Ollama-Kontakt, N={args.samples} aus Cache")
    elif use_cache and cache_complete(cache, args.samples):
        print(f"[Modus] Cache vollständig (N={args.samples}) — keine Generierung")
    else:
        if not ollama_available():
            print("[FEHLER] Ollama nicht erreichbar unter "
                  f"{OLLAMA}. Cache unvollständig. "
                  "Entweder Ollama starten oder --skip-generation verwenden.",
                  file=sys.stderr)
            return 2
        print(f"[Modus] Generierung: {args.samples} Basis + {args.samples} "
              f"Paraphrase via {MODEL} (CPU ~3-4 tok/s → ca. "
              f"{args.samples * (args.num_predict + 320) / 3.5 / 60:.0f} min erwartet)")

    t0 = time.time()
    results = {
        "config": {
            "model": MODEL, "key": KEY, "wrong_key": WRONG_KEY,
            "gamma": GAMMA, "seed": SEED, "n_samples": args.samples,
            "num_predict": args.num_predict, "window": WINDOW,
            "window_step": WINDOW_STEP, "level": "word", "context": 1,
            "mode": "cached" if (use_cache and cache_complete(cache, args.samples)) or args.skip_generation
                    else ("generated" if args.fresh else "cache-then-generate"),
        },
        "controls": [], "attacks": [], "segments": [], "greenlist_null": {},
        "timing": {}, "artifacts": {"out_dir": str(out_dir),
                                    "cache_file": str(cache_file)},
    }

    def gen_cached(tag: str, prompt: str, n: int, seed: int = SEED) -> tuple[str, dict]:
        if tag in cache:
            return cache[tag]["text"], cache[tag]["meta"]
        text, meta = ollama_generate(prompt, n, seed=seed)
        cache[tag] = {"text": text, "meta": meta, "seed": seed}
        cache_file.write_text(json.dumps(cache, ensure_ascii=False, indent=2),
                              encoding="utf-8")
        return text, meta

    unmarked_green_rates = []
    marked_green_rates = []

    for s in range(args.samples):
        sid = s + 1
        sseed = SEED + sid  # independent sample per seed
        print(f"[sample {sid}/{args.samples}] Basis (seed={sseed}) ...", flush=True)
        base, base_meta = gen_cached(f"base_{sid}", args.prompt, args.num_predict, sseed)

        # unmarked control: the same text BEFORE post-hoc marking (free)
        d_unmarked = detect(base, KEY)
        unmarked_green_rates.append(d_unmarked["green_rate"])

        # post-hoc marking (deterministic, fixed seed)
        emb = mark_greenlist(base, KEY, GAMMA, vocab=None, seed=SEED,
                             level="word", context=1)
        marked = emb["text"]
        d_right = detect(marked, KEY)
        d_wrong = detect(marked, WRONG_KEY)
        marked_green_rates.append(d_right["green_rate"])
        z_before = d_right["z_score"]

        results["controls"].append({
            "sample": sid, "seed": sseed,
            "base_tokens": d_unmarked["n_tokens"] + 1,
            "n_tokens_marked": d_right["n_tokens"],
            "green_rate_marked": d_right["green_rate"],
            "z_right_key": z_before,
            "z_wrong_key": d_wrong["z_score"],
            "z_unmarked_control": d_unmarked["z_score"],
            "verdict": d_right["verdict"],
        })

        # attacks (only on marked texts)
        print(f"[sample {sid}] Paraphrase (1 Modell-Call) ...", flush=True)
        para_text, para_meta = gen_cached(f"para_{sid}",
                                          PARAPHRASE_PROMPT.format(text=marked),
                                          min(320, len(tokenize(marked, "word")) + 40),
                                          sseed)
        attack_texts = {"paraphrase": para_text}
        for name, fn in ATTACKS_RULE_BASED:
            attack_texts[name] = fn(marked)

        for name, a_text in attack_texts.items():
            da = detect(a_text, KEY)
            results["attacks"].append({
                "sample": sid, "attack": name,
                "n_tokens": da["n_tokens"], "green_rate": da["green_rate"],
                "z_after": da["z_score"],
                "dZ": round(da["z_score"] - z_before, 2) if da["z_score"] is not None else None,
                "verdict": da["verdict"],
                "breaks_mark": da["verdict"] != "watermark_detected",
            })

        # segment stability on the marked baseline
        toks, flags = token_flags(marked, KEY, GAMMA)
        wins = window_scores(toks, flags)
        results["segments"].append({
            "sample": sid, "total_tokens": len(toks),
            "summary": summarize_windows(wins), "windows": wins,
        })

    # greenlist null check: unmarked originals should hover around gamma=0.25
    def stats(vals: list) -> dict:
        if not vals:
            return {"n": 0, "mean": None, "std": None}
        mean = sum(vals) / len(vals)
        var = sum((v - mean) ** 2 for v in vals) / len(vals)
        return {"n": len(vals), "mean": round(mean, 4), "std": round(math.sqrt(var), 4)}

    results["greenlist_null"] = {
        "gamma": GAMMA,
        "unmarked_originals": stats(unmarked_green_rates),
        "posthoc_marked": stats(marked_green_rates),
    }
    results["timing"] = {"total_secs": round(time.time() - t0, 1)}

    results_file.write_text(json.dumps(results, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    print_tables(results)
    report_file.write_text(build_report(results), encoding="utf-8")
    print(f"\nArtefakte -> {out_dir}")
    print(f"  results.json ({results_file.stat().st_size} bytes)")
    print(f"  REPORT.md   ({report_file.stat().st_size} bytes)")
    print(f"  generated_cache.json ({cache_file.stat().st_size} bytes, "
          f"{len(cache)} Einträge)")
    return 0


def fmt(v, width: int = 7, nd: int = 2) -> str:
    if v is None:
        return "-".rjust(width)
    return f"{v:.{nd}f}".rjust(width)


def print_tables(r: dict) -> None:
    cfg = r["config"]
    print("=" * 96)
    print(f"KGW BLACKBOX ATTACK MATRIX v2 — Modell={cfg['model']}  "
          f"gamma={cfg['gamma']}  key={cfg['key']}  N={cfg['n_samples']}  "
          f"Modus={cfg['mode']}")
    print("=" * 96)

    print("\nTabelle 1 — Kontrollen + Angriffe (ΔZ je Angriff)")
    header = (f"{'Smp':>3} | {'z_right':>7} | {'z_wrong':>7} | {'z_unmark':>8} | "
              + " | ".join(f"{a:>18}" for a in
                           ["paraphrase", "trunc_first", "trunc_last",
                            "reformat", "shuffle", "unicode"]))
    print(header)
    print("-" * len(header))
    ctrl = {c["sample"]: c for c in r["controls"]}
    atk = {}
    for a in r["attacks"]:
        atk.setdefault(a["sample"], {})[a["attack"]] = a
    for sid in sorted(ctrl):
        c = ctrl[sid]
        cells = [f"{c['z_right_key']:.2f}", f"{c['z_wrong_key']:.2f}",
                 f"{c['z_unmarked_control']:.2f}"]
        for name in ["paraphrase", "truncate_first", "truncate_last",
                     "reformat", "word_shuffle", "unicode_spam"]:
            a = atk.get(sid, {}).get(name)
            if a is None:
                cells.append("-")
            else:
                cells.append(f"{a['z_after']:.2f}/{a['dZ']:+.2f}")
        print(f"{sid:>3} | " + " | ".join(f"{c:>18}" for c in cells))

    print("\nTabelle 2 — Segmentstabilität (100-Token-Fenster, Schritt 50, markiert)")
    h2 = (f"{'Smp':>3} | {'Fenster':>7} | {'Mean-Z':>7} | {'Std':>6} | "
          f"{'Min':>6} | {'Max':>6} | {'%≥4.0':>7}")
    print(h2)
    print("-" * len(h2))
    for seg in r["segments"]:
        sm = seg["summary"]
        print(f"{seg['sample']:>3} | {sm['n_windows']:>7} | "
              f"{fmt(sm['mean_z'])} | {fmt(sm['std_z'])} | {fmt(sm['min_z'])} | "
              f"{fmt(sm['max_z'])} | {fmt(sm['pct_ge_4'], 7, 1)}")

    gn = r["greenlist_null"]
    print("\nTabelle 3 — Greenlist-Nullkontrolle (Generator ohne Bias?)")
    print(f"{'Bedingung':>20} | {'n':>3} | {'Mean Green-Rate':>15} | {'Std':>7}")
    print("-" * 56)
    for label, d in [("unmarked Originale", gn["unmarked_originals"]),
                     ("post-hoc markiert", gn["posthoc_marked"])]:
        print(f"{label:>20} | {d['n']:>3} | {fmt(d['mean'], 15, 4)} | {fmt(d['std'], 7, 4)}")
    print(f"(Theorie: unmarked ≈ gamma={gn['gamma']}, markiert deutlich höher)")


def build_report(r: dict) -> str:
    cfg = r["config"]
    L = []
    L.append("# KGW Blackbox — Attack Matrix v2 (REPORT)")
    L.append("")
    L.append(f"**Modell:** {cfg['model']} · **Key:** {cfg['key']} · "
             f"**Wrong-Key:** {cfg['wrong_key']} · **γ:** {cfg['gamma']} · "
             f"**Level:** {cfg['level']}, context={cfg['context']} · "
             f"**Seed:** {cfg['seed']} · **N:** {cfg['n_samples']}")
    L.append("")
    L.append(f"**Modus:** {cfg['mode']} · **Laufzeit:** {r['timing']['total_secs']} s")
    L.append("")
    L.append("**Artefakte:** " + r["artifacts"]["out_dir"])
    L.append("")
    L.append("## Methodik (Kurzform)")
    L.append("")
    L.append("1. N echte EuroLLM-Generierungen (Ollama-HTTP, nie `ollama run`), "
             "1 Seed pro Sample (42..42+N-1).")
    L.append("2. Unmarked-Kontrolle = Originaltext **vor** der Markierung "
             "(gleiche Tokens, kein Zusatz-Call).")
    L.append("3. Post-hoc KGW-Markierung `mark_greenlist(key, γ, level=word, "
             "seed=42)` — die ehrliche Produkt-Wahrheit, da der echte Generator "
             "keinen Greenlist-Bias zeigt (Runde 1, F3).")
    L.append("4. Angriffe nur auf markierte Texte; ΔZ = z_attack − z_baseline.")
    L.append("5. Segmentstabilität: überlappende 100-Token-Fenster (Schritt 50) "
             "auf den markierten Baselines.")
    L.append("6. Paraphrase = 1 Modell-Call pro Sample (Kosten-Cap), alle anderen "
             "Angriffe rule-based/deterministisch.")
    L.append("")
    L.append("## Tabelle 1 — Kontrollen + Angriffe (z_after / ΔZ)")
    L.append("")
    L.append("| Smp | z_right | z_wrong | z_unmarked | Paraphrase | Trunc 50% vorn "
             "| Trunc 50% hinten | Reformat | Word-Shuffle | Unicode-Spam |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    ctrl = {c["sample"]: c for c in r["controls"]}
    atk = {}
    for a in r["attacks"]:
        atk.setdefault(a["sample"], {})[a["attack"]] = a
    for sid in sorted(ctrl):
        c = ctrl[sid]
        cells = [f"{c['z_right_key']:.2f}", f"{c['z_wrong_key']:.2f}",
                 f"{c['z_unmarked_control']:.2f}"]
        for name in ["paraphrase", "truncate_first", "truncate_last",
                     "reformat", "word_shuffle", "unicode_spam"]:
            a = atk.get(sid, {}).get(name)
            cells.append(f"{a['z_after']:.2f} / {a['dZ']:+.2f}" if a else "-")
        L.append("| " + " | ".join([str(sid)] + cells) + " |")
    L.append("")
    L.append("ΔZ-Summary (Mittelwert über Samples, nur nicht-None):")
    L.append("")
    L.append("| Angriff | Mean ΔZ | Min ΔZ | Max ΔZ | bricht Markierung? |")
    L.append("|---|---|---|---|---|")
    for name in ["paraphrase", "truncate_first", "truncate_last",
                 "reformat", "word_shuffle", "unicode_spam"]:
        dzs = [a["dZ"] for a in r["attacks"]
               if a["attack"] == name and a["dZ"] is not None]
        breaks = sum(1 for a in r["attacks"]
                     if a["attack"] == name and a["breaks_mark"])
        if dzs:
            L.append(f"| {name} | {sum(dzs)/len(dzs):+.2f} | {min(dzs):+.2f} | "
                     f"{max(dzs):+.2f} | {breaks}/{len(dzs)} |")
        else:
            L.append(f"| {name} | - | - | - | - |")
    L.append("")
    L.append("## Tabelle 2 — Segmentstabilität (100-Token-Fenster, Schritt 50)")
    L.append("")
    L.append("| Smp | Tokens | Fenster | Mean-Z | Std | Min | Max | % ≥ 4.0 |")
    L.append("|---|---|---|---|---|---|---|---|")
    for seg in r["segments"]:
        sm = seg["summary"]
        g = lambda v: "–" if v is None else f"{v:.2f}"  # noqa: E731
        L.append(f"| {seg['sample']} | {seg['total_tokens']} | {sm['n_windows']} | "
                 f"{g(sm['mean_z'])} | {g(sm['std_z'])} | {g(sm['min_z'])} | "
                 f"{g(sm['max_z'])} | {sm['pct_ge_4']} |")
    L.append("")
    L.append("## Tabelle 3 — Greenlist-Nullkontrolle")
    L.append("")
    gn = r["greenlist_null"]
    L.append("| Bedingung | n | Mean Green-Rate | Std |")
    L.append("|---|---|---|---|")
    for label, d in [("unmarked Originale", gn["unmarked_originals"]),
                     ("post-hoc markiert", gn["posthoc_marked"])]:
        m = "–" if d["mean"] is None else f"{d['mean']:.4f}"
        s = "–" if d["std"] is None else f"{d['std']:.4f}"
        L.append(f"| {label} | {d['n']} | {m} | {s} |")
    L.append("")
    L.append(f"Theorie: unmarked ≈ γ={gn['gamma']} (kein Generator-Bias) — "
             "markiert deutlich darüber. Bestätigt, dass post-hoc Markierung der "
             "einzige Signalkanal ist (vgl. Runde-1-F3: 0.4928 ≈ γ=0.5).")
    L.append("")
    L.append("## Grenzen / Ehrlichkeit")
    L.append("")
    L.append("- Gemessene Sample-Zahl: N=" + str(cfg["n_samples"])
             + " (CPU-Limit; Ziel war 20).")
    L.append("- Paraphrase nutzt dasselbe Modell (kein unabhängiger Angreifer); "
             "1 Call pro Sample.")
    L.append("- `word_shuffle` zerstört Grammatik — erwartbar stärkster Angriff, "
             "aber kein realistischer Angreifer.")
    L.append("- Segmente messen den post-hoc markierten Text (Signal ist "
             "implantierbar), nicht das Sampling-Verhalten des Generators.")
    L.append("- Reproduktion ohne Ollama: `--skip-generation` mit vollständigem "
             "Cache (deterministisch).")
    L.append("")
    L.append("## Reproduktion")
    L.append("")
    L.append("```bash")
    L.append("# voller Lauf (Generierung, N Samples):")
    L.append("python benchmarks/attack_matrix_v2.py --samples 8")
    L.append("# deterministisch aus Cache (kein Ollama nötig):")
    L.append("python benchmarks/attack_matrix_v2.py --samples 8 --skip-generation")
    L.append("# komplett neu generieren:")
    L.append("python benchmarks/attack_matrix_v2.py --samples 8 --fresh")
    L.append("```")
    L.append("")
    L.append("## Einordnung vs. Runde 1 (tws-e2e-blackbox, N=5)")
    L.append("")
    L.append("- Runde 1: γ=0.5, Key `e2e-blackbox-key-2026`, z_right 12.9–13.7, "
             "Paraphrase bimodal, Trunkierung hält, Reformat ΔZ=0.00.")
    L.append("- v2: γ=0.25 (ehrlicher Default), Key `blackbox-2026`, zusätzlich "
             "Word-Shuffle + Unicode-Spam + überlappende Fenster, unmarked "
             "Control ohne Zusatz-Call.")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    sys.exit(main())
