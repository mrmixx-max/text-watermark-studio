from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .strategies.rule_rewrite import apply_rule_rewrite


@dataclass
class DiluteResult:
    text: str
    intensity: str
    changed: bool
    frozen_blocks: int

    def to_dict(self) -> dict:
        return asdict(self)


def _freeze_codeblocks(text: str) -> tuple[str, dict[str, str]]:
    blocks = {}

    def repl(m):
        key = f"__CODEBLOCK_{len(blocks)}__"
        blocks[key] = m.group(0)
        return key

    frozen = re.sub(r"```.*?```", repl, text, flags=re.DOTALL)
    return frozen, blocks


def _unfreeze(text: str, blocks: dict[str, str]) -> str:
    for key, value in blocks.items():
        text = text.replace(key, value)
    return text


def dilute_text(text: str, intensity: str = "standard") -> DiluteResult:
    frozen, blocks = _freeze_codeblocks(text)
    out = apply_rule_rewrite(frozen)
    if intensity in {"standard", "aggressive"}:
        out = re.sub(r"\bnot only\b(.*?)\bbut also\b", r"\1 and", out, flags=re.IGNORECASE | re.DOTALL)
        out = re.sub(r"\bNicht nur\b(.*?)\bsondern auch\b", r"\1 und", out, flags=re.IGNORECASE | re.DOTALL)
    if intensity == "aggressive":
        # Additional aggressive-only rewrite: split em-dash runs into periods.
        out = re.sub(r"\s*—\s*", ". ", out)
        out = re.sub(r"\.{2,}", ".", out)
    out = _unfreeze(out, blocks)
    return DiluteResult(
        text=out.strip(),
        intensity=intensity,
        changed=(out.strip() != text.strip()),
        frozen_blocks=len(blocks),
    )
