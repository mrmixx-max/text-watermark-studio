from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class IngestResult:
    text: str
    source: str


def read_text(path: str | None = None, stdin_text: str | None = None) -> IngestResult:
    if stdin_text is not None:
        return IngestResult(text=stdin_text, source="stdin")
    if not path:
        raise ValueError("path or stdin_text required")
    text = Path(path).read_text(encoding="utf-8")
    return IngestResult(text=text, source=str(path))
