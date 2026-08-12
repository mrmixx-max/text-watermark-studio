from __future__ import annotations

import re

REPLACEMENTS = [
    (r"\bIn der heutigen (?:digitalen )?(?:Zeit|Welt)\b", "Heute"),
    (r"\bEs ist wichtig (?:zu betonen|festzuhalten|zu beachten),? dass\b", ""),
    (r"\bZusammenfassend l[aä]sst sich sagen,? dass\b", "Kurz gesagt:"),
    (r"\bDarüber hinaus\b", "Außerdem"),
    (r"\bFurthermore\b", "Also"),
    (r"\bMoreover\b", "Also"),
    (r"\bIt is important to (?:note|remember|understand) that\b", ""),
    (r"\bIn conclusion,? it is clear that\b", "In short,"),
    (r"\bleverage\b", "use"),
    (r"\bdelve into\b", "examine"),
]


def apply_rule_rewrite(text: str) -> str:
    out = text
    for pattern, repl in REPLACEMENTS:
        out = re.sub(pattern, repl, out, flags=re.IGNORECASE)
    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"\s+([,.;:!?])", r"\1", out)
    return out.strip()
