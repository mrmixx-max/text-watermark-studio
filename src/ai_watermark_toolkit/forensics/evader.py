"""Adversarial evaluation: minimize a KGW watermark signal with minimal edits.

This is a STRESS TEST for the studio's own KGW implementation, not a tool
for laundering third-party texts. It answers the research question every
watermark scheme must answer: *how many word changes does an attacker need
to push the Z-score below a detection threshold while preserving the text?*

Method (greedy, deterministic by default):

1. Tokenize at word level and score every token against its greenlist
   context (the exact ``(token, context)`` pairs ``detect_kgw`` uses).
2. A marked text has green_rate >> gamma, so a large fraction of scored
   tokens are green. Each green token contributes +1 to the green count.
3. The evader replaces green tokens with NON-green alternatives, one at a
   time, preferring positions whose replacement costs the least semantic
   similarity. After each batch it recomputes the Z-score (statistics are
   cheap at word level) and stops as soon as the Z-score is below the
   target threshold.
4. Output is a MEASUREMENT: Z before/after, words changed, semantic
   similarity (difflib ratio + word overlap), iterations, per-attempt
   trajectory.

Candidate alternatives come from the studio's own frequency vocabulary and
synonym banks first (same-class words, cheap); an optional Ollama backend
can supply natural infill candidates per position. Everything degrades to
the deterministic path when no LLM is configured.

Honest limits: this attacks the exact ``detect_kgw`` scheme with the known
key (white-box). Real-world attackers do not know the key. The evader
therefore measures the SCHEME'S robustness floor, not its field resistance.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from .frequent_vocab import FREQUENT_VOCAB
from .kgw import (
    DEFAULT_GAMMA,
    detect_kgw,
    green_token,
    tokenize,
)

# ---------------------------------------------------------------------------
# Candidate pools (non-green alternatives)
# ---------------------------------------------------------------------------


def _candidate_pool(word: str) -> list[str]:
    """Return replacement candidates for a word.

    Priority: the frequency-vocabulary pool the word ITSELF belongs to
    (same-class synonyms), then a small set of generic high-frequency
    content words. We deliberately do NOT dump every vocabulary value into
    the pool — that produces semantically broken swaps ('takes' ->
    'persons'). The pool stays class-aware; the evader's similarity metric
    (word_overlap) depends on it.
    """
    low = word.lower()
    cands: list[str] = []
    # Same-class first: only the pool containing the original word.
    for pool in FREQUENT_VOCAB.values():
        if low in pool:
            cands.extend(pool)
    # Generic content-word fallbacks (neutral, same frequency band).
    cands += [
        "major",
        "general",
        "current",
        "specific",
        "certain",
        "various",
        "significant",
        "substantial",
        "notable",
        "considerable",
        "overall",
        "primary",
        "essential",
        "overall",
        "core",
        "main",
    ]
    # Dedupe, case-normalized, exclude the word itself.
    seen: set = set()
    out: list[str] = []
    for c in cands:
        if c.lower() != low and c.lower() not in seen:
            seen.add(c.lower())
            out.append(c)
    return out


def _first_non_green(
    candidates: Sequence[str],
    ctx: Sequence[str],
    key: str,
    gamma: float,
) -> str | None:
    """Return the first candidate that is NOT green for (key, ctx)."""
    for c in candidates:
        if not green_token(c, list(ctx), key, gamma):
            return c
    return None


# ---------------------------------------------------------------------------
# Core evader
# ---------------------------------------------------------------------------


def evade(
    text: str,
    key: str,
    gamma: float = DEFAULT_GAMMA,
    level: str = "word",
    context: int = 1,
    target_z: float = 3.9,
    max_changes: int | None = None,
    ollama_model: str | None = None,
    seed: int = 0,
) -> dict[str, Any]:
    """Push the KGW Z-score of ``text`` below ``target_z`` with minimal edits.

    Greedy loop: score every token, collect green positions, replace the
    greenest ones with non-green alternatives, recompute Z, stop below
    target. Returns the evaded text plus the full measurement.

    ``ollama_model`` (optional): use a local Ollama model to propose natural
    candidates per position (falls back to the deterministic pool on any
    failure). ``max_changes`` caps the edit budget (default: no cap, but the
    loop stops at target_z).
    """
    import random

    rng = random.Random(seed)
    tokens = tokenize(text, level=level)
    n = len(tokens)
    if n < 11:
        return _result(text, text, tokens, tokens, [], [], target_z, 0, 0, 1.0, "too_short")

    before = detect_kgw(text, key, gamma=gamma, level=level, context=context)
    before_z = before.get("z_score") or 0.0
    if before_z < target_z:
        # Already below target — nothing to do.
        return _result(
            text,
            text,
            tokens,
            tokens,
            [],
            [],
            target_z,
            before_z,
            0,
            1.0,
            "already_below",
        )

    # Score every token position against its greenlist context.
    scored: list[tuple[int, str, list[str], bool]] = []
    for i in range(1, n):
        ctx = tokens[max(0, i - context) : i]
        is_green = green_token(tokens[i], ctx, key, gamma)
        scored.append((i, tokens[i], ctx, is_green))

    green_positions = [p for p, _, _, g in scored if g]
    max_changes = max_changes or len(green_positions)

    work = list(tokens)
    changed: list[dict[str, Any]] = []
    trajectory: list[dict[str, Any]] = []
    z_now = before_z

    # Iterate: each round, try replacing green positions. To keep edits
    # minimal we shuffle the green positions (seeded) so a partial budget
    # does not always hit the same prefix of the text.
    green_order = list(green_positions)
    rng.shuffle(green_order)
    used = 0
    for pos in green_order:
        if used >= max_changes:
            break
        ctx = work[max(0, pos - context) : pos]
        if not green_token(work[pos], ctx, key, gamma):
            # Already flipped by a previous edit (context changed) — skip.
            continue
        orig = work[pos]
        candidates = _candidate_pool(orig)
        if ollama_model:
            llm_cands = _ollama_candidates(" ".join(work), pos, ollama_model)
            if llm_cands:
                candidates = llm_cands + candidates
        replacement = _first_non_green(candidates, ctx, key, gamma)
        if replacement is None:
            continue
        work[pos] = replacement
        used += 1
        changed.append({"position": pos, "original": orig, "replacement": replacement})
        # Recompute after each change (cheap at word level) to stop early.
        evaded_text = " ".join(work)
        r = detect_kgw(evaded_text, key, gamma=gamma, level=level, context=context)
        z_now = r.get("z_score") or 0.0
        trajectory.append({"changes": used, "z_score": round(z_now, 4), "verdict": r.get("verdict")})
        if z_now < target_z:
            break

    evaded = " ".join(work)
    similarity = _similarity(text, evaded)
    word_overlap = _word_overlap(text, evaded)
    after = detect_kgw(evaded, key, gamma=gamma, level=level, context=context)
    return _result(
        text,
        evaded,
        tokens,
        work,
        changed,
        trajectory,
        target_z,
        before_z,
        after.get("z_score") or 0.0,
        similarity,
        "evaded" if (after.get("z_score") or 0.0) < target_z else "budget_exhausted",
        word_overlap=word_overlap,
        verdict_after=after.get("verdict"),
    )


def _result(
    original: str,
    evaded: str,
    tokens_before: list[str],
    tokens_after: list[str],
    changes: list[dict[str, Any]],
    trajectory: list[dict[str, Any]],
    target_z: float,
    z_before: float,
    z_after: float,
    similarity: float,
    status: str,
    word_overlap: float | None = None,
    verdict_after: str | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "target_z": target_z,
        "z_before": round(z_before, 4),
        "z_after": round(z_after, 4),
        "z_delta": round(z_after - z_before, 4),
        "verdict_after": verdict_after,
        "words_before": len(tokens_before),
        "words_after": len(tokens_after),
        "changes": len(changes),
        "change_ratio": round(len(changes) / max(1, len(tokens_before)), 4),
        "similarity": round(similarity, 4),
        "word_overlap": round(word_overlap, 4) if word_overlap is not None else None,
        "trajectory": trajectory,
        "changes_detail": changes,
        "text": evaded,
    }


def _similarity(a: str, b: str) -> float:
    """difflib ratio — character-level similarity (stdlib, deterministic)."""
    from difflib import SequenceMatcher

    return SequenceMatcher(None, a, b).ratio()


def _word_overlap(a: str, b: str) -> float:
    """Fraction of original words that survived unchanged (position-insensitive)."""
    from collections import Counter

    ca, cb = Counter(a.split()), Counter(b.split())
    overlap = sum((ca & cb).values())
    return overlap / max(1, sum(ca.values()))


def _ollama_candidates(sentence: str, mask_index: int, model: str, top_k: int = 3, timeout: float = 20.0) -> list[str]:
    """Ask a local Ollama model for natural alternatives at one position.

    Best effort: any failure returns [] and the deterministic pool takes
    over. Guards against chatty/meta responses the same way the invariant
    infill does (comma-separated answer expected, reject rambling).
    """
    import re
    import urllib.request

    tokens = sentence.split()
    prompt_sentence = " ".join(w if i != mask_index else "[MASK]" for i, w in enumerate(tokens))
    payload = json.dumps(
        {
            "model": model,
            "prompt": (
                "List 3 natural words that fit the [MASK] in this sentence, "
                "plain and neutral. Reply with ONLY the words, comma-separated, "
                f"no explanation.\nText: {prompt_sentence}\nWords:"
            ),
            "stream": False,
            "options": {"num_predict": 20, "temperature": 0.0},
        }
    ).encode("utf-8")
    try:
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []
    out = (data.get("response") or "").strip()
    if "," not in out:
        return []
    words = [w for part in out.split(",") for w in re.findall(r"[A-Za-z'\-]+", part)]
    return [w for w in words if len(w) > 1][:top_k]


def format_evade_report(result: dict[str, Any]) -> str:
    """Human-readable report for CLI output."""
    lines = [
        "KGW adversarial evaluation (white-box, own scheme)",
        f"  status:    {result['status']}",
        f"  Z before:  {result['z_before']:+.2f}   Z after: {result['z_after']:+.2f}   (target < {result['target_z']})",
        f"  verdict:   {result.get('verdict_after')}",
        f"  changes:   {result['changes']} of {result['words_before']} words   ({result['change_ratio'] * 100:.1f}%)",
        f"  similarity: {result['similarity'] * 100:.1f}%"
        f"   word overlap: {(result.get('word_overlap') or 0) * 100:.1f}%",
    ]
    if result["trajectory"]:
        lines.append("  trajectory (changes -> z):")
        for t in result["trajectory"]:
            lines.append(f"    {t['changes']:>3} -> {t['z_score']:+.2f} ({t['verdict']})")
    return "\n".join(lines)
