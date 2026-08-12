from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class MarkupStripResult:
    text: str
    removed_comments: int
    removed_hidden_spans: int


def strip_markup(text: str) -> MarkupStripResult:
    comments = re.findall(r"<!--.*?-->", text, flags=re.DOTALL)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    hidden_spans = re.findall(
        r"<span[^>]*(?:display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0)[^>]*>.*?</span>",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(
        r"<span[^>]*(?:display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0)[^>]*>.*?</span>",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return MarkupStripResult(text=text, removed_comments=len(comments), removed_hidden_spans=len(hidden_spans))
