"""ΔZ check as a service (C4, 2026-08-13) — watermark removal with receipt.

A cleaner claims "I remove watermarks". The ΔZ check *measures* that claim:
mark strength before (z_before), after (z_after), and the delta between them.
A sign-proven drop (z_before >= 4, z_after < 4) is `removed: true` — removal
with a receipt. This is the catalog position for IMATAG-style verification:
an evasion oracle ("mark present?") is useless against a cleaner, but a
before/after ΔZ measurement is the only load-bearing evidence of removal.

Honest boundaries (documented, not hidden):

- **ΔZ proves a change in mark strength, not cleaner honesty.** A cleaner
  could rewrite the text completely (paraphrase) — the signal disappears
  while the "cleaning" was actually regeneration. `removed: true` means:
  the watermark signal is no longer measurable with this key, nothing more.
  Paraphrase/regeneration is NOT covered by the stdlib transforms here
  (it needs an LLM); it is documented as open in TRANSFORM_NOTES.
- **Only your own KGW scheme and key are measured.** Detection fires only
  for texts embedded with this exact scheme (greenlist hash over
  key + context + token). An unknown vendor scheme needs its own key.
- **removed:true requires a provable before-state.** The verdict flips only
  from ``watermark_detected`` (z >= 4) to anything else. A weak or
  unmeasurable before-state can never produce a removal receipt — no
  "proof" of removal without a provable mark.
- **Delta sign convention:** ``delta_z = z_before - z_after`` (spec parity:
  delta_z == z_before - z_after exactly). A POSITIVE delta_z therefore
  means the mark got weaker/removed — the opposite sign of the attack
  matrix's ``dZ = z_after - z_before`` (benchmarks/attack_matrix_v2.py).
  The ``removed`` boolean is the primary product signal; delta_z is the
  magnitude.

Signing: :func:`delta_z_report` attaches a signed_report signature block
(HMAC-SHA256, stdlib) so a ΔZ finding becomes an auditable, court-ready
document. The secret is the operator's attestation key — symmetric, so
whoever holds it can forge (studio-internal trust model, same as
signed_report).
"""

from __future__ import annotations

import random
import re

from .key_registry import KeyRegistry
from .kgw import DEFAULT_GAMMA, detect_multi_key

# ------------------------------------------------------------------ transforms
# The stdlib-deterministic transformations lifted from
# benchmarks/attack_matrix_v2.py (ATTACKS_RULE_BASED): the repo-available
# attacks are clean (unicode/metadata hygiene), truncate, word-shuffle and
# reformat. Paraphrase needs an LLM call and is deliberately NOT part of the
# product path (see TRANSFORM_NOTES).
TRANSFORM_METHODS = ("clean", "truncate", "shuffle", "reformat")

TRANSFORM_NOTES = {
    "clean": "unicode/metadata hygiene (sanitize_unicode: strips ZWSP, bidi "
             "controls, format/control chars). Does NOT touch KGW greenlist "
             "tokens -> mark strength is preserved (removed:false).",
    "truncate": "keep the first truncate_fraction of word tokens. Weakens the "
                "mark (fewer scored tokens) but keeps the intact (prev, token) "
                "chain of the kept part -> at 60% the mark usually SURVIVES "
                "(removed:false). Honest finding, measured in test_v145.",
    "shuffle": "word-shuffle with a fixed seed (42, like the attack matrix). "
               "Breaks every (prev, token) greenlist pair -> z collapses to "
               "~0. The provable removal demonstration.",
    "reformat": "whitespace normalization + one sentence per line. Tokens are "
                "unchanged -> mark strength preserved (removed:false).",
}

_TRANSFORM_META = {
    "clean": "unicode/metadata hygiene (sanitize_unicode, ZWSP/bidi/control removal)",
    "truncate": "first N word tokens (fraction)",
    "shuffle": "word shuffle, fixed seed",
    "reformat": "whitespace normalization, sentence-per-line",
}


def _transform_clean(text: str) -> str:
    """Unicode/metadata hygiene: strip invisible/control characters (ZWSP, bidi)."""
    from ..sanitize_unicode import sanitize
    return sanitize(text).text


def _transform_truncate(text: str, fraction: float = 0.6) -> str:
    """First ``fraction`` of word tokens (attack_matrix truncate_first)."""
    from .kgw import tokenize
    toks = tokenize(text, level="word")
    return " ".join(toks[: max(1, int(len(toks) * fraction))])


def _transform_shuffle(text: str, seed: int = 42) -> str:
    """Word shuffle with a fixed seed (attack_matrix word_shuffle, seed 42)."""
    rng = random.Random(seed)
    words = text.split()
    rng.shuffle(words)
    return " ".join(words)


def _transform_reformat(text: str) -> str:
    """Whitespace normalization + one sentence per line (attack_matrix reformat)."""
    flat = re.sub(r"\s+", " ", text).strip()
    sentences = re.split(r"(?<=[.!?]) ", flat)
    return "\n".join(s.strip() for s in sentences if s.strip())


def _apply_transform(text: str, method: str, *, seed: int = 42,
                     truncate_fraction: float = 0.6) -> tuple[str, dict]:
    """Apply a stdlib transform; returns (transformed_text, transform_meta).

    ``method`` must be one of TRANSFORM_METHODS. The meta dict records the
    parameters used so a measured result is reproducible.
    """
    if method == "clean":
        before = len(text)
        out = _transform_clean(text)
        return out, {"method": method, "removed_chars": before - len(out),
                     "note": _TRANSFORM_META[method]}
    if method == "truncate":
        from .kgw import tokenize
        toks = tokenize(text, level="word")
        out = _transform_truncate(text, truncate_fraction)
        return out, {"method": method, "fraction": truncate_fraction,
                     "n_tokens_before": len(toks),
                     "n_tokens_after": len(tokenize(out, level="word")),
                     "note": _TRANSFORM_META[method]}
    if method == "shuffle":
        out = _transform_shuffle(text, seed)
        return out, {"method": method, "seed": seed,
                     "note": _TRANSFORM_META[method]}
    if method == "reformat":
        out = _transform_reformat(text)
        return out, {"method": method, "note": _TRANSFORM_META[method]}
    raise ValueError(
        f"unknown transform method: {method} (supported: {sorted(TRANSFORM_METHODS)})"
    )


# ------------------------------------------------------------------ key handling
def _resolve_key(registry: KeyRegistry, key_arg: str) -> dict:
    """Resolve a key argument (key_id OR raw secret) to a key dict.

    Mirrors the CLI detect convention: a key_id matching a registry entry
    resolves to that entry (with its secret and gamma); anything else is
    treated as a raw secret. Raises ValueError when the resolved key carries
    no secret.
    """
    key = next((k for k in registry.list_keys() if k.get("key_id") == key_arg), None)
    if key is None:
        key = {"key_id": key_arg, "family": "kgw", "secret": key_arg, "gamma": None}
    if not key.get("secret"):
        raise ValueError(f"key {key_arg} has no secret")
    return key


def _measure(text: str, key: dict, level: str, context: int) -> dict:
    """Single-key KGW detection via detect_multi_key (Registry resolution path)."""
    result = detect_multi_key(
        text, [key], gamma=key.get("gamma") or DEFAULT_GAMMA,
        level=level, context=context,
    )
    best = result.get("best") or {}
    return {
        "z_score": best.get("z_score"),
        "verdict": best.get("verdict", "no_signal"),
        "n_tokens": best.get("n_tokens"),
        "key_id": best.get("key_id"),
        "tested_keys": result.get("tested_keys"),
    }


# ------------------------------------------------------------------ core API
def delta_z(text_before: str, text_after: str, key_id_or_secret: str, *,
            level: str = "word", context: int = 1,
            registry: KeyRegistry | None = None) -> dict:
    """Measure KGW mark strength before vs after (ΔZ check).

    Resolves ``key_id_or_secret`` through the registry (key_id -> registered
    secret; anything else -> raw secret), then detects both texts with that
    single key via ``detect_multi_key`` (the CLI's registry-resolution path).

    Returns::

        {
          "key_id": str,               # resolved key identity
          "z_before": float|None,      # mark strength before (word/BPE level)
          "z_after": float|None,       # mark strength after
          "delta_z": float|None,       # z_before - z_after (None if either unmeasurable)
          "verdict_before": str,       # e.g. watermark_detected / no_signal / too_short
          "verdict_after": str,
          "removed": bool,             # before provable (z>=4) AND after not
          "n_before": int|None,        # scored tokens before
          "n_after": int|None,
          "gamma": float, "level": str, "context": int,
        }

    ``removed`` is True only when the before-state is PROVABLE
    (verdict_before == 'watermark_detected', i.e. z >= 4) and the after-state
    is not. delta_z positive = mark weakened/removed (sign convention
    documented in the module docstring).

    Honest boundary: ΔZ measures signal change — it never proves the cleaner
    was honest (a full rewrite removes the signal without "cleaning").
    """
    if not isinstance(text_before, str) or not isinstance(text_after, str):
        raise ValueError("text_before and text_after must be strings")
    reg = registry if registry is not None else KeyRegistry("data/key_registry.json")
    key = _resolve_key(reg, key_id_or_secret)
    gamma = key.get("gamma") or DEFAULT_GAMMA

    before = _measure(text_before, key, level, context)
    after = _measure(text_after, key, level, context)

    z_before = before["z_score"]
    z_after = after["z_score"]
    if z_before is not None and z_after is not None:
        delta = round(z_before - z_after, 4)
    else:
        delta = None
    removed = bool(
        before["verdict"] == "watermark_detected"
        and after["verdict"] != "watermark_detected"
    )
    return {
        "key_id": key.get("key_id", "unknown"),
        "z_before": z_before,
        "z_after": z_after,
        "delta_z": delta,
        "verdict_before": before["verdict"],
        "verdict_after": after["verdict"],
        "removed": removed,
        "n_before": before["n_tokens"],
        "n_after": after["n_tokens"],
        "gamma": gamma,
        "level": level,
        "context": context,
    }


def delta_z_transform(text: str, key_id_or_secret: str,
                      method: str = "clean", *,
                      level: str = "word", context: int = 1,
                      registry: KeyRegistry | None = None,
                      seed: int = 42,
                      truncate_fraction: float = 0.6,
                      max_transformed_chars: int = 1000) -> dict:
    """Apply a stdlib transform, then measure the ΔZ it causes.

    ``method`` in TRANSFORM_METHODS (clean/truncate/shuffle/reformat — the
    repo-available stdlib attacks lifted from benchmarks/attack_matrix_v2.py;
    paraphrase needs an LLM and is documented as open). The transform is
    applied to ``text`` and :func:`delta_z` measures text vs transformed.

    Returns the delta_z result plus::

        "method": str,              # transform used
        "transform_meta": dict,     # reproducible parameters (seed, fraction, ...)
        "transformed_text": str,    # only when short (<= max_transformed_chars)
        "transformed_text_omitted": bool,  # True when the text was too long

    Honest boundaries: same as :func:`delta_z` — ΔZ proves signal change, not
    cleaner honesty. ``removed:false`` for clean/reformat is EXPECTED (mark
    strength survives hygiene); shuffle is the provable removal path.
    """
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    transformed, meta = _apply_transform(
        text, method, seed=seed, truncate_fraction=truncate_fraction
    )
    result = delta_z(text, transformed, key_id_or_secret,
                     level=level, context=context, registry=registry)
    result["method"] = method
    result["transform_meta"] = meta
    if len(transformed) <= max_transformed_chars:
        result["transformed_text"] = transformed
        result["transformed_text_omitted"] = False
    else:
        result["transformed_text_omitted"] = True
    return result


def delta_z_report(delta_result: dict, sign_secret: str | None = None, *,
                   key_id: str | None = None) -> dict:
    """Attach a signed_report signature block to a ΔZ result (HMAC-SHA256).

    When ``sign_secret`` is None the result is returned unchanged (no
    signature block). When given, :func:`signed_report.sign_report` signs the
    canonical JSON of the result — the finding becomes an auditable document
    (verify with ``ai-wm report-verify --secret-file ...``). The default
    key_id is the result's own key_id. Returns a NEW dict; the input is not
    mutated.
    """
    if sign_secret is None:
        return dict(delta_result)
    from .signed_report import sign_report
    return sign_report(
        dict(delta_result), sign_secret,
        key_id=key_id or delta_result.get("key_id") or "default",
        algorithm="hmac-sha256",
    )
