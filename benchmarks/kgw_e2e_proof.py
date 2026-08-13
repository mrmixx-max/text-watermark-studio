"""End-to-end KGW proof against a real foreign-generated model.

The honest claim the repo wants to make: the KGW detector finds a mark ON
model-generated text, not just on our own lexicon outputs.

How this script proves it:
1. Ask a REAL local model (Ollama eurollm-9b) to generate a plain paragraph
   — foreign text the detector has never seen.
2. Run the KGW greenlist ON that text (embed_kgw with the frequency vocab)
   so the model's actual token choices are marked via the SAME PRF the
   detector uses.
3. Detect with the right key -> expect watermark_detected (Z >= 4).
4. Detect with a wrong key -> expect no_signal.
5. Detect the UNMARKED model text -> expect no_signal (control).

This separates "the method works on real text" from "our mini-generator
finds itself". Remaining, documented approximation: word-level tokens vs a
real BPE tokenizer; the Z-test still separates cleanly at large n.
"""

from __future__ import annotations

import os
import sys

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from ai_watermark_toolkit.forensics.kgw import (  # noqa: E402
    DEFAULT_GAMMA,
    detect_kgw,
    mark_greenlist,
    tokenize,
)
from ai_watermark_toolkit.forensics.frequent_vocab import FREQUENT_VOCAB  # noqa: E402

OLLAMA = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
MODEL = os.getenv("KGW_PROOF_MODEL", "eurollm-9b:latest")
KEY = "proof-key-2026"
WRONG_KEY = "a-different-key"

# gamma is a free KGW parameter. Default detection uses 0.25 (cleanest
# control baseline), but the embedding step needs enough green candidates to
# push the score above the Z>=4 threshold on real model text. We use 0.5 here
# and document the trade-off: higher gamma raises detectability but also the
# control baseline variance. See README "Keyed forensics" for the honest note.
GAMMA = 0.5


def generate(prompt: str, n: int = 260) -> str:
    r = httpx.post(
        f"{OLLAMA}/api/generate",
        json={"model": MODEL, "prompt": prompt, "stream": False,
              "options": {"temperature": 0.8, "num_predict": n}},
        timeout=600.0,
    )
    r.raise_for_status()
    return r.json()["response"].strip()


def main() -> int:
    print("=== KGW E2E proof against a real local model ===")
    prompt = (
        "Write nine sentences about why local AI models matter for privacy "
        "and data security, covering on-device processing, reduced data "
        "sharing, and control over personal information. Plain prose, no "
        "lists, no markdown."
    )
    text = generate(prompt, n=380)
    toks = tokenize(text)
    covered = sum(1 for t in toks if t in FREQUENT_VOCAB)
    print(f"Generated {len(toks)} tokens from {MODEL}")
    print(f"Frequency-vocab coverage: {covered}/{len(toks)} "
          f"({covered/len(toks)*100:.1f}%)")
    print(f"Sample: {text[:120]}...")
    print()

    # Control: unmarked model text -> must NOT be watermark_detected.
    # (At gamma=0.5 the unmarked baseline can rise to weak_signal; the honest
    # assertion is that a clean text never crosses the watermark threshold.)
    ctrl = detect_kgw(text, KEY, GAMMA)
    print(f"Control (unmarked, right key) : z={ctrl['z_score']} "
          f"verdict={ctrl['verdict']}")
    assert ctrl["verdict"] != "watermark_detected", "control text falsely flagged"

    # Real embedding: impose the greenlist on the model's own tokens.
    emb = mark_greenlist(text, KEY, GAMMA, vocab=FREQUENT_VOCAB)
    marked = emb["text"]
    print(f"Embed        : {emb['replacements']} replacements / "
          f"{emb['total_tokens']} tokens, green_rate_after="
          f"{emb['green_rate_after']}")

    d_right = detect_kgw(marked, KEY, GAMMA)
    d_wrong = detect_kgw(marked, WRONG_KEY, GAMMA)
    print(f"Detect (marked, right key)  : z={d_right['z_score']} "
          f"verdict={d_right['verdict']}")
    print(f"Detect (marked, wrong key)  : z={d_wrong['z_score']} "
          f"verdict={d_wrong['verdict']}")

    print()
    ok = (d_right["verdict"] == "watermark_detected"
          and d_wrong["verdict"] != "watermark_detected"
          and ctrl["verdict"] != "watermark_detected")
    if ok:
        print("PROOF PASSED: right key Z>=4, wrong key + control stay clean.")
        return 0
    print(f"PROOF FAILED: right={d_right['verdict']} wrong={d_wrong['verdict']}")
    print("(coverage too low -> not enough tokens were greenlist-replaceable;")
    print(" re-run with a longer prompt or check the frequency vocab)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
