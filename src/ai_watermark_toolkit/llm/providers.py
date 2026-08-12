from __future__ import annotations

from typing import Dict, Any

PROMPTS: Dict[str, str] = {
    "clarity": (
        "Rewrite the user's text in a clear, direct style. Remove filler words, "
        "flatten complex clauses, keep every fact. Return plain text only."
    ),
    "concise": (
        "Rewrite the user's text to be substantially more concise. Cut redundancy "
        "and fluff, keep every fact and number. Return plain text only."
    ),
    "plain": (
        "Rewrite the user's text in plain, simple language. Replace jargon with "
        "everyday words. Keep the meaning. Return plain text only."
    ),
    "formal": (
        "Rewrite the user's text in a formal register. No contractions, no slang. "
        "Keep the meaning. Return plain text only."
    ),
    "structural": (
        "Restructure the user's text without changing its meaning: reorder paragraphs "
        "and sentences, change clause order, vary sentence openings. Do not paraphrase "
        "every word; keep the facts, numbers and names identical. Return plain text only."
    ),
    "backtranslate": (
        "Paraphrase the user's text: first translate it into English, then translate "
        "the English version back into the original language. Keep every fact, number "
        "and name. Return only the final text in the original language."
    ),
    "backtranslate_phase1": (
        "Translate the user's text into English. Keep every fact, number and name. "
        "Return only the English translation."
    ),
    "backtranslate_phase2": (
        "Translate the user's English text back into its original language. Keep every "
        "fact, number and name. Return only the final text in the original language."
    ),
}


def build_rewrite_prompt(text: str, style: str = 'clarity', instruction: str | None = None) -> Dict[str, Any]:
    base = PROMPTS.get(style, PROMPTS['clarity'])
    prompt = (
        f"{base} "
        f"Additional instruction: {instruction or 'none'}.\n\n"
        f"TEXT:\n{text}"
    )
    return {'style': style, 'instruction': instruction, 'prompt': prompt}
