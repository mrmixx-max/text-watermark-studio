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
  The paraphrase/rewrite path is now a first-class transform (`rewrite`,
  via RewriteService — rule-based structural, or the local Ollama backend
  with `--use-llm`), measured like any other transform: ΔZ is the evidence,
  and regeneration is called regeneration in the report.
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

from .key_registry import KeyRegistry, mask_secret_key_id
from .kgw import DEFAULT_GAMMA, detect_multi_key

# ------------------------------------------------------------------ transforms
# The transformations lifted from benchmarks/attack_matrix_v2.py
# (ATTACKS_RULE_BASED): clean (unicode/metadata hygiene), truncate, word-shuffle
# and reformat are stdlib-deterministic. `rewrite` is the paraphrase path via
# RewriteService (rule-based structural when no LLM backend, or the local
# Ollama backend when --use-llm) — it measures what an actual paraphrase
# attack does to the KGW signal instead of leaving it undocumented.
TRANSFORM_METHODS = ("clean", "truncate", "shuffle", "reformat", "rewrite")

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
    "rewrite": "paraphrase via RewriteService. Rule-based 'structural' mode "
    "rotates sentences and varies openings without an LLM; with "
    "--use-llm the local Ollama backend rewrites through a model "
    "(or backtranslates DE->EN->DE). Paraphrase changes the token "
    "surface -> the greenlist hash changes, so ΔZ measures the "
    "real-world attack. Honest boundary: a strong rewrite can "
    "collapse z (removed:true), but that is REGENERATION, not "
    "'cleaning' — ΔZ proves signal change, never cleaner honesty. "
    "Light structural edits typically keep removed:false.",
}

_TRANSFORM_META = {
    "clean": "unicode/metadata hygiene (sanitize_unicode, ZWSP/bidi/control removal)",
    "truncate": "first N word tokens (fraction)",
    "shuffle": "word shuffle, fixed seed",
    "reformat": "whitespace normalization, sentence-per-line",
    "rewrite": "paraphrase (RewriteService: structural rule-based, or local LLM backend)",
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
    rng = random.Random(seed)  # nosec B311 — deterministic seeded RNG for attack matrix, not crypto
    words = text.split()
    rng.shuffle(words)
    return " ".join(words)


def _transform_reformat(text: str) -> str:
    """Whitespace normalization + one sentence per line (attack_matrix reformat)."""
    flat = re.sub(r"\s+", " ", text).strip()
    sentences = re.split(r"(?<=[.!?]) ", flat)
    return "\n".join(s.strip() for s in sentences if s.strip())


def _transform_rewrite(text: str, mode: str = "structural", use_llm: bool = False) -> tuple[str, dict]:
    """Paraphrase via RewriteService (lazy import — keeps the core stdlib-light).

    ``mode`` is one of RewriteService's modes (clarity/concise/plain/formal/
    structural/backtranslate). ``use_llm=False`` (default) runs the rule-based
    structural path with no external call; ``use_llm=True`` calls the local
    Ollama backend (OpenAI-compatible, LOCAL_LLM_BASE_URL / LOCAL_LLM_MODEL).

    Returns (rewritten_text, meta) where meta records mode/backend so a
    measured result is reproducible. The service protects numbers, URLs,
    quotes and proper nouns across the rewrite (preserve=True).

    Raises ValueError for an unknown mode (RewriteService itself silently
    ignores unknown modes on the rule-based path — the ΔZ core must not).
    """
    _VALID_MODES = {"clarity", "concise", "plain", "formal", "structural", "backtranslate"}
    if mode not in _VALID_MODES:
        raise ValueError(f"unknown rewrite mode: {mode} (supported: {sorted(_VALID_MODES)})")
    from ..rewrite.service import RewriteService

    svc = RewriteService(llm_backend=use_llm)
    res = svc.rewrite(text, mode=mode, preserve=True, use_llm=use_llm)
    metrics = res.get("metrics", {})
    meta = {
        "method": "rewrite",
        "mode": mode,
        "backend": res.get("backend", "local-llm" if use_llm else "rule-based"),
        "similarity_ratio": metrics.get("similarity_ratio"),
        "note": _TRANSFORM_META["rewrite"],
    }
    return res["rewritten"], meta


def _apply_transform(
    text: str,
    method: str,
    *,
    seed: int = 42,
    truncate_fraction: float = 0.6,
    rewrite_mode: str = "structural",
    use_llm: bool = False,
) -> tuple[str, dict]:
    """Apply a transform; returns (transformed_text, transform_meta).

    ``method`` must be one of TRANSFORM_METHODS. The meta dict records the
    parameters used so a measured result is reproducible. ``rewrite`` is the
    paraphrase path (RewriteService); it is the only method that may perform
    an external LLM call — only when ``use_llm=True`` (default: rule-based).
    """
    if method == "clean":
        before = len(text)
        out = _transform_clean(text)
        return out, {"method": method, "removed_chars": before - len(out), "note": _TRANSFORM_META[method]}
    if method == "truncate":
        from .kgw import tokenize

        toks = tokenize(text, level="word")
        out = _transform_truncate(text, truncate_fraction)
        return out, {
            "method": method,
            "fraction": truncate_fraction,
            "n_tokens_before": len(toks),
            "n_tokens_after": len(tokenize(out, level="word")),
            "note": _TRANSFORM_META[method],
        }
    if method == "shuffle":
        out = _transform_shuffle(text, seed)
        return out, {"method": method, "seed": seed, "note": _TRANSFORM_META[method]}
    if method == "reformat":
        out = _transform_reformat(text)
        return out, {"method": method, "note": _TRANSFORM_META[method]}
    if method == "rewrite":
        out, meta = _transform_rewrite(text, mode=rewrite_mode, use_llm=use_llm)
        return out, meta
    raise ValueError(f"unknown transform method: {method} (supported: {sorted(TRANSFORM_METHODS)})")


# ------------------------------------------------------------------ key handling
def _resolve_key(registry: KeyRegistry, key_arg: str) -> dict:
    """Resolve a key argument (key_id OR raw secret) to a key dict.

    Mirrors the CLI detect convention: a key_id matching a registry entry
    resolves to that entry (with its secret and gamma); anything else is
    treated as a raw secret. The reported key_id of a raw secret is MASKED
    (``secret:<sha256-prefix>``, see key_registry.mask_secret_key_id) so the
    secret never leaks into ΔZ results or signed reports — the measurement
    still uses the real secret (parity: raw-secret workflow keeps working).
    Raises ValueError when the resolved key carries no secret.
    """
    key = next((k for k in registry.list_keys() if k.get("key_id") == key_arg), None)
    if key is None:
        key = {
            "key_id": mask_secret_key_id(key_arg),
            "family": "kgw",
            "secret": key_arg,
            "gamma": None,
            "key_source": "raw_secret",
        }
    else:
        key = dict(key)
        key.setdefault("key_source", "registry")
    if not key.get("secret"):
        raise ValueError(f"key {key_arg} has no secret")
    return key


def _measure(text: str, key: dict, level: str, context: int) -> dict:
    """Single-key KGW detection via detect_multi_key (Registry resolution path)."""
    result = detect_multi_key(
        text,
        [key],
        gamma=key.get("gamma") or DEFAULT_GAMMA,
        level=level,
        context=context,
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
def delta_z(
    text_before: str,
    text_after: str,
    key_id_or_secret: str,
    *,
    level: str = "word",
    context: int = 1,
    registry: KeyRegistry | None = None,
) -> dict:
    """Measure KGW mark strength before vs after (ΔZ check).

    Resolves ``key_id_or_secret`` through the registry (key_id -> registered
    secret; anything else -> raw secret), then detects both texts with that
    single key via ``detect_multi_key`` (the CLI's registry-resolution path).

    Returns::

        {
          "key_id": str,               # resolved key identity (masked for raw secrets)
          "key_source": str,           # 'registry' | 'raw_secret'
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
        raise TypeError("text_before and text_after must be strings")
    reg = registry if registry is not None else KeyRegistry("data/key_registry.json")
    key = _resolve_key(reg, key_id_or_secret)
    gamma = key.get("gamma") or DEFAULT_GAMMA

    before = _measure(text_before, key, level, context)
    after = _measure(text_after, key, level, context)

    z_before = before["z_score"]
    z_after = after["z_score"]
    delta = round(z_before - z_after, 4) if z_before is not None and z_after is not None else None
    removed = bool(before["verdict"] == "watermark_detected" and after["verdict"] != "watermark_detected")
    return {
        "key_id": key.get("key_id", "unknown"),
        "key_source": key.get("key_source", "registry"),
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


def delta_z_transform(
    text: str,
    key_id_or_secret: str,
    method: str = "clean",
    *,
    level: str = "word",
    context: int = 1,
    registry: KeyRegistry | None = None,
    seed: int = 42,
    truncate_fraction: float = 0.6,
    rewrite_mode: str = "structural",
    use_llm: bool = False,
    max_transformed_chars: int = 1000,
) -> dict:
    """Apply a transform, then measure the ΔZ it causes.

    ``method`` in TRANSFORM_METHODS (clean/truncate/shuffle/reformat/rewrite —
    the repo-available attacks lifted from benchmarks/attack_matrix_v2.py, plus
    the paraphrase path via RewriteService). ``rewrite_mode`` selects the
    RewriteService mode (structural default — rule-based, no LLM; other modes
    with ``use_llm=True`` call the local Ollama backend). The transform is
    applied to ``text`` and :func:`delta_z` measures text vs transformed.

    Returns the delta_z result plus::

        "method": str,              # transform used
        "transform_meta": dict,     # reproducible parameters (seed, fraction, mode, ...)
        "transformed_text": str,    # only when short (<= max_transformed_chars)
        "transformed_text_omitted": bool,  # True when the text was too long

    Honest boundaries: same as :func:`delta_z` — ΔZ proves signal change, not
    cleaner honesty. ``removed:false`` for clean/reformat is EXPECTED (mark
    strength survives hygiene); shuffle is the provable removal path; rewrite
    measures the paraphrase attack (a strong LLM rewrite can collapse z, but
    that is regeneration, not 'cleaning').
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    transformed, meta = _apply_transform(
        text,
        method,
        seed=seed,
        truncate_fraction=truncate_fraction,
        rewrite_mode=rewrite_mode,
        use_llm=use_llm,
    )
    result = delta_z(text, transformed, key_id_or_secret, level=level, context=context, registry=registry)
    result["method"] = method
    result["transform_meta"] = meta
    if len(transformed) <= max_transformed_chars:
        result["transformed_text"] = transformed
        result["transformed_text_omitted"] = False
    else:
        result["transformed_text_omitted"] = True
    return result


def delta_z_report(delta_result: dict, sign_secret: str | None = None, *, key_id: str | None = None) -> dict:
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
        dict(delta_result),
        sign_secret,
        key_id=key_id or delta_result.get("key_id") or "default",
        algorithm="hmac-sha256",
    )
