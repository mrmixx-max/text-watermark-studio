from __future__ import annotations

from typing import Dict, Any
from .service import SamplingConfig


def build_rewrite_prompt(text: str, style: str = "clarity", instruction: str | None = None) -> Dict[str, Any]:
    """Build a rewrite prompt for the given style.

    Styles:
    - backtranslate_phase1: Translate to German
    - backtranslate_phase2: Translate back to original language
    - structural: Restructure sentences
    - clarity (default): Rewrite in clear, direct style
    """
    if style == "backtranslate_phase1":
        prompt = (
            f"Translate the user's text into German. "
            f"Preserve meaning, keep it concise, and return plain text only. "
            f"Additional instruction: {instruction or 'none'}.\n\n"
            f"TEXT:\n{text}"
        )
    elif style == "backtranslate_phase2":
        prompt = (
            f"Translate the user's text back into its original language. "
            f"Preserve meaning, keep it concise, and return plain text only. "
            f"Additional instruction: {instruction or 'none'}.\n\n"
            f"TEXT:\n{text}"
        )
    elif style == "structural":
        prompt = (
            f"Restructure the user's text. Reorder sentences for better flow "
            f"while preserving meaning. Return plain text only. "
            f"Additional instruction: {instruction or 'none'}.\n\n"
            f"TEXT:\n{text}"
        )
    else:  # clarity + unknown styles
        prompt = (
            f"Rewrite the user's text in a clear, direct style. "
            f"Preserve meaning, keep it concise, and return plain text only. "
            f"Additional instruction: {instruction or 'none'}.\n\n"
            f"TEXT:\n{text}"
        )
    return {"style": style, "instruction": instruction, "prompt": prompt}


def build_sampling_params(sampling: SamplingConfig | None = None, backend_type: str = "openai") -> dict[str, Any]:
    """Build sampling parameters dict for the target backend.

    Parameters
    ----------
    sampling:
        Sampling configuration. Uses defaults if None.
    backend_type:
        'openai' for /chat/completions APIs, 'llama.cpp' for /completion API.
    """
    if sampling is None:
        sampling = SamplingConfig()

    if backend_type == "llama.cpp":
        return sampling.to_llama_cpp_dict()
    return sampling.to_openai_dict()
