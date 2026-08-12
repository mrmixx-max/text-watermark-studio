from __future__ import annotations

from typing import Dict, Any


def build_rewrite_prompt(text: str, style: str = 'clarity', instruction: str | None = None) -> Dict[str, Any]:
    prompt = (
        f"Rewrite the user's text in style='{style}'. "
        "Preserve meaning, keep it concise, and return plain text only. "
        f"Additional instruction: {instruction or 'none'}.\n\n"
        f"TEXT:\n{text}"
    )
    return {'style': style, 'instruction': instruction, 'prompt': prompt}
