"""Generation-time watermarking primitives (sampling-bias demo).

This package holds the EXPERIMENTAL generation-time half of the KGW
watermark. The standard, production path for text watermarking in this
project remains the post-hoc text rewrite in ``forensics/kgw.py``
(``mark_greenlist`` / ``embed_kgw``).
"""

from .kgw_sampler import (  # noqa: F401
    SAMPLER_GAMMA,
    bias_logits,
    default_vocab,
    generate_marked_text,
    sample_with_kgw_bias,
)

__all__ = [
    "SAMPLER_GAMMA",
    "bias_logits",
    "default_vocab",
    "generate_marked_text",
    "sample_with_kgw_bias",
]
