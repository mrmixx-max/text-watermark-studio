from __future__ import annotations

import re

REPLACEMENTS = [
    # German stock openers / fillers / closers (both word orders)
    (r"\bIn der heutigen (?:digitalen )?(?:Zeit|Welt)\b", "Heute"),
    (r"\bEs ist wichtig (?:zu betonen|festzuhalten|zu beachten),? dass\b", ""),
    (r"\bist es wichtig (?:zu betonen|festzuhalten|zu beachten),? dass\b", ""),
    (r"\bist es wichtig (?:zu betonen|festzuhalten|zu beachten)\b", "ist wichtig"),
    (r"\bZusammenfassend l[aä]sst sich sagen,? dass\b", "Kurz gesagt:"),
    (r"\bDarüber hinaus\b", "Außerdem"),
    # German buzzwords with inflection endings
    (r"\bnahtlose\b", "reibungslose"),
    (r"\bnahtloser\b", "reibungsloser"),
    (r"\bnahtlosen\b", "reibungslosen"),
    (r"\bnahtloses\b", "reibungsloses"),
    (r"\bnahtlos\b", "reibungslos"),
    (r"\bganzheitliche\b", "umfassende"),
    (r"\bganzheitlicher\b", "umfassender"),
    (r"\bganzheitlichen\b", "umfassenden"),
    (r"\bganzheitliches\b", "umfassendes"),
    (r"\bganzheitlich\b", "umfassend"),
    (r"\bSynergien\b", "Zusammenspiel"),
    (r"\bSynergie\b", "Zusammenspiel"),
    # English markers
    (r"\bFurthermore\b", "Also"),
    (r"\bMoreover\b", "Also"),
    (r"\bIt is important to (?:note|remember|understand) that\b", ""),
    (r"\bIn conclusion,? it is clear that\b", "In short,"),
    (r"\bleveraging\b", "using"),
    (r"\bleverage\b", "use"),
    (r"\bleveragen\b", "nutzen"),
    (r"\bdelve into\b", "examine"),
    (r"\bseamlessly\b", "smoothly"),
    (r"\bseamless\b", "smooth"),
]


def apply_rule_rewrite(text: str) -> str:
    out = text
    for pattern, repl in REPLACEMENTS:
        out = re.sub(pattern, repl, out, flags=re.IGNORECASE)
    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"\s+([,.;:!?])", r"\1", out)
    return out.strip()
