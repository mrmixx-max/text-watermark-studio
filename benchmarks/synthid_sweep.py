"""SynthID-style parameter sweep: at which paraphrase strength does the
greenlist mark stop being detectable?

Sweeps gamma x paraphrase-rate and reports the Z-score surface. This is the
"detection curve" — how much rewording a mark survives before the signal
drowns in noise. Deterministic, no LLM needed.

Output: table + synthid_sweep.json.
"""

from __future__ import annotations

import json
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from ai_watermark_toolkit.forensics.kgw import detect_kgw, mark_greenlist  # noqa: E402
from ai_watermark_toolkit.forensics.frequent_vocab import FREQUENT_VOCAB  # noqa: E402

KEY = os.getenv("KGW_KEY", "synthid-sweep-key")

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

GAMMAS = [0.1, 0.25, 0.4, 0.5, 0.6]
PARAPHRASE_RATES = [0.0, 0.15, 0.3, 0.45, 0.6, 0.75, 0.9]


def paraphrase(text: str, rate: float, seed: int = 7) -> str:
    """Approximate paraphrasing by replacing `rate` of ALL content words
    (len>=3, non-stopword-ish) with random pool words. Honest approximation
    of a rewrite attack's lexical churn across the whole text."""
    if rate == 0.0:
        return text
    rng = random.Random(seed)
    fallback = [w for ws in FREQUENT_VOCAB.values() for w in ws]
    words = text.split()
    for i, w in enumerate(words):
        clean = w.strip(".,;:!?")
        if len(clean) >= 3 and rng.random() < rate:
            suffix = w[len(clean):]
            words[i] = rng.choice(fallback) + suffix
    return " ".join(words)


def main() -> int:
    rows = []
    for g in GAMMAS:
        marked = mark_greenlist(SEED_TEXT, KEY, g, vocab=FREQUENT_VOCAB, seed=42)
        for pr in PARAPHRASE_RATES:
            attacked = paraphrase(marked["text"], pr)
            r = detect_kgw(attacked, KEY, g)
            rows.append({
                "gamma": g, "paraphrase_rate": pr,
                "z": r["z_score"], "verdict": r["verdict"],
            })

    print(f"{'γ':>4} | " + " ".join(f"p={pr:<4}" for pr in PARAPHRASE_RATES))
    print("-" * (6 + 9 * len(PARAPHRASE_RATES)))
    for g in GAMMAS:
        line = f"{g:>4} | "
        for pr in PARAPHRASE_RATES:
            row = next(x for x in rows if x["gamma"] == g and x["paraphrase_rate"] == pr)
            z = row["z"]
            cell = f"{'  -':>4}" if z is None else f"{z:>4.1f}"
            line += f"{cell:<6} "
        print(line)

    print("\nSchwellwert 4.0 = watermark_detected; Werte darunter = Mark gebrochen.")
    with open("synthid_sweep.json", "w", encoding="utf-8") as f:
        json.dump({"key": KEY, "gammas": GAMMAS,
                   "paraphrase_rates": PARAPHRASE_RATES, "rows": rows}, f, indent=2)
    print("synthid_sweep.json geschrieben.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
