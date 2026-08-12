from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass
class DocumentPayload:
    format: str
    text: str
    metadata: dict

    def to_dict(self):
        return asdict(self)
