from __future__ import annotations

from typing import Dict, Any
from .service import SamplingConfig


def build_rewrite_prompt(text: str, style: str = "clarity", instruction: str | None = None) -> Dict[str, Any]:
    prompt = (
        f"Rewrite the user's text in style='{style}'. "
        "Preserve meaning, keep it concise, and return plain text only. "
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
