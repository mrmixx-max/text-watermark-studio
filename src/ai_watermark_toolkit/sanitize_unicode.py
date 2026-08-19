from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field

INVISIBLE_CPS = {
    0x00AD,  # soft hyphen
    0x034F,  # combining grapheme joiner
    0x061C,  # arabic letter mark
    0x180E,  # mongolian vowel separator
    0x200B,  # zero width space
    0x200C,  # zero width non-joiner
    0x200D,  # zero width joiner
    0x200E,  # left-to-right mark
    0x200F,  # right-to-left mark
    0x202A,  # left-to-right embedding
    0x202B,  # right-to-left embedding
    0x202C,  # pop directional formatting
    0x202D,  # left-to-right override
    0x202E,  # right-to-left override
    0x2060,  # word joiner
    0x2061,  # function application
    0x2062,  # invisible times
    0x2063,  # invisible separator
    0x2064,  # invisible plus
    0x2066,  # left-to-right isolate
    0x2067,  # right-to-left isolate
    0x2068,  # first strong isolate
    0x2069,  # pop directional isolate
    0x206A,  # inhibit symmetric swapping
    0x206B,  # activate symmetric swapping
    0x206C,  # inhibit arabic form shaping
    0x206D,  # activate arabic form shaping
    0x206E,  # national digit shapes
    0x206F,  # nominal digit shapes
    0xFEFF,  # zero width no-break space (BOM)
    0xFFF9,  # interlinear annotation anchor
    0xFFFA,  # interlinear annotation separator
    0xFFFB,  # interlinear annotation terminator
}

# Exotic spaces: fancy separators that should be normalized to ASCII space.
# From markscrub's unicode.ts — keep space semantics instead of stripping.
EXOTIC_SPACE_CPS = {
    0x00A0,  # no-break space
    0x1680,  # ogham space mark
    0x2000,  # en quad
    0x2001,  # em quad
    0x2002,  # en space
    0x2003,  # em space
    0x2004,  # three-per-em space
    0x2005,  # four-per-em space
    0x2006,  # six-per-em space
    0x2007,  # figure space
    0x2008,  # punctuation space
    0x2009,  # thin space
    0x200A,  # hair space
    0x202F,  # narrow no-break space
    0x205F,  # medium mathematical space
    0x3000,  # ideographic space
}

# Line/paragraph separators (distinct from newline/carriage return).
LINE_SEP_CPS = {
    0x2028,  # line separator
    0x2029,  # paragraph separator
}

# Aggressive-only fillers: script-specific, invisible in most fonts, and
# legitimate in real text (Braille blank, Hangul fillers). Removing them
# can damage genuine content, so they are opt-in via aggressive=True.
AGGRESSIVE_CPS = {
    0x115F,
    0x1160,  # Hangul Choseong/Jungseong Filler
    0x180B,
    0x180C,
    0x180D,
    0x180F,  # Mongolian variation selectors / FVS1-4
    0x2800,  # Braille pattern blank
    0x3164,  # Hangul Filler
    0xFFA0,  # Halfwidth Hangul Filler
    0xFFFC,  # Object Replacement Character
}

CONFUSABLES = str.maketrans(
    {
        "а": "a",
        "е": "e",
        "о": "o",
        "р": "p",
        "с": "c",
        "у": "y",
        "х": "x",
        "А": "A",
        "В": "B",
        "Е": "E",
        "К": "K",
        "М": "M",
        "Н": "H",
        "О": "O",
        "Р": "P",
        "С": "C",
        "Т": "T",
        "Х": "X",
        "Α": "A",
        "Β": "B",
        "Ε": "E",
        "Ζ": "Z",
        "Η": "H",
        "Ι": "I",
        "Κ": "K",
        "Μ": "M",
        "Ν": "N",
        "Ο": "O",
        "Ρ": "P",
        "Τ": "T",
        "Υ": "Y",
        "Χ": "X",
        "α": "a",
        "ο": "o",
        "ν": "v",
        "ι": "i",
        "κ": "k",
    },
)


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
        elif o in EXOTIC_SPACE_CPS:
            out.append(Finding(i, f"U+{o:04X}", _cp_name(o), "exotic_space"))
        elif o in LINE_SEP_CPS:
            out.append(Finding(i, f"U+{o:04X}", _cp_name(o), "line_sep"))
    return out


def sanitize(
    text: str, *, nfkc: bool = False, fold_confusables: bool = False, aggressive: bool = False,
) -> SanitizeResult:
    findings = analyze(text, aggressive=aggressive)
    drop = {f.index for f in findings if f.category in {"invisible", "aggressive_filler", "tag_or_vs"}}
    space_replace = {f.index for f in findings if f.category == "exotic_space"}
    newline_replace = {f.index for f in findings if f.category == "line_sep"}
    s = "".join(
        " " if i in space_replace else "\n" if i in newline_replace else ch
        for i, ch in enumerate(text)
        if i not in drop
    )
    folds = 0
    if fold_confusables:
        before = s
        s = s.translate(CONFUSABLES)
        folds = sum(1 for a, b in zip(before, s, strict=False) if a != b) + abs(len(before) - len(s))
    if nfkc:
        s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[^\S\n]+", " ", s)
    s = re.sub(r" ?\n ?", "\n", s)
    return SanitizeResult(text=s, findings=findings, confusable_folds=folds)
