from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, asdict

INVISIBLE_CPS = {
    0x00AD, 0x034F, 0x061C, 0x180E,
    0x200B, 0x200C, 0x200D, 0x200E, 0x200F,
    0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
    0x2060, 0x2061, 0x2062, 0x2063, 0x2064,
    0x2066, 0x2067, 0x2068, 0x2069,
    0x206A, 0x206B, 0x206C, 0x206D, 0x206E, 0x206F,  # deprecated format chars
    0xFEFF, 0xFFF9, 0xFFFA, 0xFFFB,
}

# Aggressive-only fillers: script-specific, invisible in most fonts, and
# legitimate in real text (Braille blank, Hangul fillers). Removing them
# can damage genuine content, so they are opt-in via aggressive=True.
AGGRESSIVE_CPS = {
    0x115F, 0x1160,          # Hangul Choseong/Jungseong Filler
    0x180B, 0x180C, 0x180D, 0x180F,  # Mongolian variation selectors / FVS1-4
    0x2800,                  # Braille pattern blank
    0x3164,                  # Hangul Filler
    0xFFA0,                  # Halfwidth Hangul Filler
    0xFFFC,                  # Object Replacement Character
}

CONFUSABLES = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x",
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O",
    "Р": "P", "С": "C", "Т": "T", "Х": "X",
    "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K",
    "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X",
    "α": "a", "ο": "o", "ν": "v", "ι": "i", "κ": "k",
})


@dataclass
class Finding:
    index: int
    cp: str
    name: str
    category: str


@dataclass
class SanitizeResult:
    text: str
    findings: list[Finding] = field(default_factory=list)
    confusable_folds: int = 0

    @property
    def risk_score(self) -> float:
        if not self.findings and not self.confusable_folds:
            return 0.0
        return min(1.0, 0.15 * len(self.findings) + 0.05 * self.confusable_folds)

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "findings": [asdict(f) for f in self.findings],
            "confusable_folds": self.confusable_folds,
            "risk_score": self.risk_score,
        }


def _cp_name(cp: int) -> str:
    try:
        return unicodedata.name(chr(cp))
    except ValueError:
        return f"U+{cp:04X}"


def analyze(text: str, *, aggressive: bool = False) -> list[Finding]:
    out: list[Finding] = []
    for i, ch in enumerate(text):
        o = ord(ch)
        cat = unicodedata.category(ch)
        if o in INVISIBLE_CPS or (cat in {"Cf", "Cc"} and ch not in "\t\n\r"):
            out.append(Finding(i, f"U+{o:04X}", _cp_name(o), "invisible"))
        elif aggressive and o in AGGRESSIVE_CPS:
            out.append(Finding(i, f"U+{o:04X}", _cp_name(o), "aggressive_filler"))
        elif 0xE0001 <= o <= 0xE007F or 0xE0100 <= o <= 0xE01EF:
            out.append(Finding(i, f"U+{o:04X}", _cp_name(o), "tag_or_vs"))
    return out


def sanitize(text: str, *, nfkc: bool = False, fold_confusables: bool = False,
             aggressive: bool = False) -> SanitizeResult:
    findings = analyze(text, aggressive=aggressive)
    drop = {f.index for f in findings}
    s = "".join(ch for i, ch in enumerate(text) if i not in drop)
    folds = 0
    if fold_confusables:
        before = s
        s = s.translate(CONFUSABLES)
        folds = sum(1 for a, b in zip(before, s) if a != b) + abs(len(before) - len(s))
    if nfkc:
        s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[^\S\n]+", " ", s)
    s = re.sub(r" ?\n ?", "\n", s)
    return SanitizeResult(text=s, findings=findings, confusable_folds=folds)
