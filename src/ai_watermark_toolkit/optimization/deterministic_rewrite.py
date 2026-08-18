"""Deterministic paraphrase rules for the optimizer's offline backend.

Interprets prompt constraints as concrete text transformations so that
candidate prompts produce measurably different output — reproducible, no
LLM. This is the honest offline path; the LLM backend replaces it with real
model rewrites when LOCAL_LLM_ENABLED is set.

Rules are deliberately shallow (dictionary + regex): the point is a
deterministic, comparable signal for prompt evaluation, not a full
rewrite engine (that lives in `rewrite/`).
"""

from __future__ import annotations

import re

# padded AI-phrasing -> concrete wording (one variable: style rule)
_PADDED: list[tuple[str, str]] = [
    ("comprehensive suite of solutions", "toolkit"),
    ("empowers teams to leverage", "lets teams use"),
    ("empowers", "helps"),
    ("robust security standards", "strict security"),
    ("In today's rapidly evolving digital landscape,", "Today,"),
    ("dive deep into the world of", "explore"),
    ("cutting-edge advancements", "new tools"),
    ("revolutionizing the way we think about", "changing"),
    ("In conclusion, it is important to note that", ""),
    ("stands as a testament to what is possible", "shows what happens"),
    ("groundbreaking", "new"),
    ("seamlessly integrate best-in-class workflows", "connect standard tools"),
    ("at every turn", ""),
    ("unlock unprecedented value", "create real value"),
    ("drive meaningful transformation", "make real change"),
    ("across their entire operational ecosystem", "everywhere"),
    ("in the modern era", "today"),
]

# passiv -> aktiv (one variable: active voice)
_PASSIVE = [
    (re.compile(r"\bis driven by ([A-Za-z0-9 ]+?)[.]", re.I), r"\1 drives it."),
    (re.compile(r"\bwas launched by ([A-Za-z0-9 ]+?)[.]", re.I), r"\1 launched it."),
    (re.compile(r"\bis powered by ([A-Za-z0-9 ]+?)[.]", re.I), r"\1 powers it."),
    (re.compile(r"\bis supported by ([A-Za-z0-9 ]+?)[.]", re.I), r"\1 supports it."),
]


def shorten_sentences(text: str) -> str:
    """Replace padded AI phrasing with concrete wording."""
    out = text
    for phrase, replacement in _PADDED:
        out = out.replace(phrase, replacement)
    # collapse double spaces/punctuation leftovers from empty replacements
    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"\s([,.;:])", r"\1", out)
    return out.strip()


def active_voice(text: str) -> str:
    """Convert a few deterministic passive constructions to active voice."""
    out = text
    for pattern, repl in _PASSIVE:
        out = pattern.sub(repl, out)
    return out


def apply_constraints(system_prompt: str, text: str) -> str:
    """Interpret the prompt's constraints as deterministic transformations.

    One variable per candidate: only the constraints actually present in the
    prompt are applied — a prompt without them returns the text unchanged
    (that is the baseline behaviour, and it is intentional).
    """
    out = text
    if "short, concrete sentences" in system_prompt or "Prefer active voice" in system_prompt:
        out = shorten_sentences(out)
        out = active_voice(out)
    if "Return only the rewritten text" in system_prompt:
        out = out.strip()
    # negative constraints ("Do not add new facts") and preserve-rules
    # change nothing deterministically — they are safety rails, not edits.
    return out
