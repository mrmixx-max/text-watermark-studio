"""Attack matrix: which paraphrase/stego attack breaks the KGW mark first?

Runs a battery of attacks against a greenlist-marked text and reports how
far the Z-score falls. This is the benchmark table defenders and researchers
cite: mark strength vs. structural rewrite, dilute intensities, unicode spam,
and word shuffling.

Deterministic by default (synthetic seed text, no LLM); optionally generates
from a local Ollama model when OLLAMA_BASE_URL+KGW_PROOF_MODEL are set.

Output: table to stdout + attack_matrix.json in the working directory.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from ai_watermark_toolkit.forensics.kgw import (  # noqa: E402
    DEFAULT_GAMMA,
    detect_kgw,
    mark_greenlist,
)
from ai_watermark_toolkit.forensics.frequent_vocab import FREQUENT_VOCAB  # noqa: E402
from ai_watermark_toolkit.transform.dilute import dilute_text  # noqa: E402
from ai_watermark_toolkit.rewrite.service import RewriteService  # noqa: E402

KEY = os.getenv("KGW_KEY", "attack-matrix-key")
GAMMA = float(os.getenv("KGW_GAMMA", "0.5"))

SEED_TEXT = (
    "Local AI models protect user privacy by processing information on the "
    "device instead of sending everything to a remote server. This approach "
    "reduces the amount of personal data shared with outside systems and "
    "gives people direct control over their information. The result is a "
    "lower risk of breaches and a stronger security posture. People trust "
    "systems that keep their data nearby and handle processing transparently. "
    "Organizations benefit because sensitive records never leave the building, "
    "and compliance becomes easier when data remains under local control. "
    "Small devices can now run capable models without depending on external "
    "services, which removes network latency and protects against outages. "
    "The same principle applies to healthcare, finance, and public services, "
    "where confidentiality is not optional but a legal requirement. Every "
    "layer of the system can be inspected, and the user decides what leaves "
    "the machine and what stays private. Over time this changes the default "
    "from constant sharing toward careful retention and measured disclosure."
)


def _unicode_spam(text: str, n: int = 12) -> str:
    """Inject zero-width characters — the cheapest stego attack."""
    out = []
    step = max(1, len(text) // n)
    for i, ch in enumerate(text):
        out.append(ch)
        if i % step == 0 and ch == " ":
            out.append("\u200b")
    return "".join(out)


def _shuffle_words(text: str, seed: int = 1) -> str:
    """Randomly permute content words — destroys local token statistics."""
    import random
    rng = random.Random(seed)
    words = text.split()
    rng.shuffle(words)
    return " ".join(words)


def attack(name: str, fn) -> dict:
    marked = mark_greenlist(SEED_TEXT, KEY, GAMMA, vocab=FREQUENT_VOCAB, seed=42)
    baseline = detect_kgw(marked["text"], KEY, GAMMA)
    try:
        attacked = fn(marked["text"])
        after = detect_kgw(attacked, KEY, GAMMA)
    except Exception as e:  # pragma: no cover
        after = {"z_score": None, "verdict": f"error: {type(e).__name__}"}
    drop = (baseline["z_score"] or 0) - (after["z_score"] or 0)
    return {
        "attack": name,
        "baseline_z": baseline["z_score"],
        "after_z": after["z_score"],
        "z_drop": round(drop, 2),
        "verdict": after["verdict"],
        "breaks_mark": after["verdict"] != "watermark_detected",
    }


def main() -> int:
    svc = RewriteService()
    attacks = [
        ("structural (rule-based)", lambda t: svc.rewrite(t, mode="structural")["rewritten"]),
        ("dilute light", lambda t: dilute_text(t, intensity="light").text),
        ("dilute standard", lambda t: dilute_text(t, intensity="standard").text),
        ("dilute aggressive", lambda t: dilute_text(t, intensity="aggressive").text),
        ("unicode spam (ZWSP)", _unicode_spam),
        ("word shuffle", _shuffle_words),
    ]
    results = [attack(n, f) for n, f in attacks]
    print(f"{'Attack':30} {'base-Z':>7} {'nach-Z':>7} {'ΔZ':>6} {'Urteil':>20} {'bricht?':>8}")
    print("-" * 88)
    for r in results:
        bz = f"{r['baseline_z']:.2f}" if r["baseline_z"] is not None else "  -"
        az = f"{r['after_z']:.2f}" if r["after_z"] is not None else "  -"
        print(f"{r['attack']:30} {bz:>7} {az:>7} {r['z_drop']:>6.2f} "
              f"{str(r['verdict']):>20} {'JA' if r['breaks_mark'] else 'nein':>8}")
    with open("attack_matrix.json", "w", encoding="utf-8") as f:
        json.dump({"key": KEY, "gamma": GAMMA, "results": results}, f, indent=2)
    print("\nattack_matrix.json geschrieben.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
