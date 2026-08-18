from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class DocumentPayload:
    format: str
    text: str
    metadata: dict

    def to_dict(self):
        return asdict(self)
