from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from statistics import mean, pstdev


@dataclass
class StyleFeatures:
    sentence_count: int
    avg_sentence_length: float
    sentence_length_stddev: float
    transition_density: float
    em_dash_count: int

    def to_dict(self) -> dict:
        return asdict(self)


def compute_style_features(text: str) -> StyleFeatures:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    lengths = [len(re.findall(r"\w+", s)) for s in sentences] or [0]
    transition_markers = re.findall(
        r"\b(?:furthermore|moreover|darüber hinaus|abschließend)\b", text, flags=re.IGNORECASE,
    )
    words = re.findall(r"\w+", text)
    density = len(transition_markers) / max(1, len(words))
    return StyleFeatures(
        sentence_count=len(sentences),
        avg_sentence_length=round(mean(lengths), 2),
        sentence_length_stddev=round(pstdev(lengths), 2) if len(lengths) > 1 else 0.0,
        transition_density=round(density, 4),
        em_dash_count=text.count("—"),
    )
