from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class FamilySpec:
    slug: str
    title: str
    category: str
    visibility: str
    robustness: str
    detectability: str
    requirements: list[str]
    notes: str

    def to_dict(self):
        return asdict(self)
