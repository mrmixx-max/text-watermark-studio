from __future__ import annotations

import re
from dataclasses import dataclass, asdict

DEFAULT_PATTERNS: list[tuple[str, int, str, str]] = [
    ("en", 3, r"\bdelve(?:s|d)? into\b", "delve into"),
    ("en", 3, r"\bleverage(?:s|d)?\b", "leverage"),
    ("en", 3, r"\bin today'?s (?:digital |fast-paced )?world\b", "stock opener"),
    ("en", 3, r"\bit is important to (?:note|remember|understand)\b", "filler"),
    ("en", 3, r"\bin conclusion,?\s+it is clear\b", "template closer"),
    ("en", 2, r"\bfurthermore,?\b", "furthermore"),
    ("en", 2, r"\bmoreover,?\b", "moreover"),
    ("de", 3, r"\b[Ii]n der heutigen (?:digitalen )?(?:Zeit|Welt)\b", "Stock-Opener"),
    ("de", 3, r"\b[Ee]s ist wichtig (?:zu betonen|festzuhalten|zu beachten)\b", "Füllsatz"),
    ("de", 3, r"\b[Zz]usammenfassend l[aä]sst sich sagen\b", "Schlussformel"),
    ("de", 2, r"\b[Dd]ar[uü]ber hinaus\b", "Übergang inflationär"),
    ("de", 2, r"\bNicht nur\b.+\bsondern auch\b", "nicht nur/sondern auch"),
]


@dataclass
class Hit:
    lang: str
    severity: int
    note: str
    start: int
    end: int
    snippet: str

    def to_dict(self) -> dict:
        return asdict(self)


def scan_markers(text: str, lang: str = "auto") -> list[Hit]:
    hits: list[Hit] = []
    for lg, sev, pat, note in DEFAULT_PATTERNS:
        if lang not in ("auto", lg):
            continue
        for m in re.finditer(pat, text, flags=re.IGNORECASE | re.DOTALL):
            sn = m.group(0).replace("\n", " ")
            if len(sn) > 100:
                sn = sn[:97] + "..."
            hits.append(Hit(lg, sev, note, m.start(), m.end(), sn))
    hits.sort(key=lambda h: (-h.severity, h.start))
    return hits
