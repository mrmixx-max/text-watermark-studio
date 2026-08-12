from __future__ import annotations

from dataclasses import dataclass, asdict
from collections import Counter
import re


@dataclass
class NgramBiasResult:
    repeated_bigram_ratio: float
    top_bigram: str
    top_bigram_count: int
    note: str

    def to_dict(self) -> dict:
        return asdict(self)


def heuristic_ngram_bias(text: str) -> NgramBiasResult:
    tokens = re.findall(r"\w+", text.lower())
    bigrams = list(zip(tokens, tokens[1:]))
    if not bigrams:
        return NgramBiasResult(0.0, "", 0, "not enough tokens")
    counts = Counter(bigrams)
    top, count = counts.most_common(1)[0]
    ratio = count / max(1, len(bigrams))
    return NgramBiasResult(round(ratio, 4), " ".join(top), count, "heuristic anomaly score; not a keyed detector")
