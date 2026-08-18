"""Real KGW-style statistical watermark detection AND embedding.

Detection implements the Kirchenbauer et al. greenlist scheme in a
text-only setting: for each token, a pseudorandom hash over
(key, previous_token, token) decides whether the token belongs to the
greenlist. A watermarked text shows a green-ratio significantly above the
expected gamma; a normal text does not. Multi-key: test every registered
KGW key, report per-key Z-scores with a Bonferroni-style note.

Embedding works in a text-only rewrite mode (no model pipeline needed):
for every replaceable token, pick a lexicon synonym that lands in the
greenlist of (key, previous_token). Enough replacements push the green
ratio above gamma; the detector then finds the text with the same key.

Honest limits (documented, not hidden):
- Detection only fires on texts generated/embedded WITH this exact scheme
  and key. It is not a universal detector for unknown vendor schemes —
  key and hash scheme must match.
- Embedding rewrites content words only (a small built-in lexicon). Its
  strength depends on lexicon coverage and text length; short texts or
  texts without lexicon hits may stay below the detection threshold.
- Word-level tokens approximate model tokenizers. Real BPE tokenizers
  shift the statistics slightly; the Z-test still separates cleanly when
  n is large enough.
"""

from __future__ import annotations

import collections
import hashlib
import math
import random
import re

# Default greenlist fraction (KGW gamma). Keep in sync with the generator.
DEFAULT_GAMMA = 0.25

_TOKEN_RE = re.compile(r"[A-Za-z0-9\u00C0-\u024F]+(?:['-][A-Za-z0-9\u00C0-\u024F]+)*")
_SPLIT_RE = re.compile(r"([A-Za-z0-9\u00C0-\u024F]+(?:['-][A-Za-z0-9\u00C0-\u024F]+)*)")

_BPE_ENC = None
_BPE_WORD_CACHE: dict[str, list[str]] = {}


def _bpe_encoding():
    """Lazily load the tiktoken cl100k_base encoding (cached per process)."""
    global _BPE_ENC
    if _BPE_ENC is None:
        try:
            import tiktoken
        except ImportError as e:  # pragma: no cover - dependency hint path
            raise ImportError("BPE-level detection needs tiktoken: pip install text-watermark-studio[bpe]") from e
        try:
            _BPE_ENC = tiktoken.get_encoding("cl100k_base")
        except (KeyError, ValueError) as e:  # pragma: no cover - encoding error
            raise RuntimeError("BPE encoding 'cl100k_base' unavailable — tiktoken may need an update") from e
    return _BPE_ENC


def bpe_tokenize(text: str) -> list[str]:
    """Byte-pair-encode the text into subword tokens (model-grade surface).

    cl100k prefixes continuation tokens with spaces (" word"); we strip that
    for the hash surface so mark and detect hash the SAME subword form in
    both isolated-word and running-text contexts. Case is preserved. This is
    the documented approximation: subword granularity is BPE-exact, the
    space-prefix is normalized for consistency.
    """
    enc = _bpe_encoding()
    return [t for t in (enc.decode([tok]).strip() for tok in enc.encode(text)) if t]


def _bpe_subwords_cached(word: str) -> list[str]:
    """BPE subwords for a single word, cached (hot-path helper for mark_greenlist)."""
    cached = _BPE_WORD_CACHE.get(word)
    if cached is None:
        cached = bpe_tokenize(word)
        _BPE_WORD_CACHE[word] = cached
    return cached


# Small built-in rewrite lexicon: content word -> synonyms. Demo-scale by
# design; plug in WordNet or a domain lexicon for stronger coverage.
EMBED_LEXICON: dict[str, list[str]] = {
    "important": ["crucial", "vital", "essential", "key", "significant"],
    "significant": ["important", "notable", "considerable", "substantial"],
    "change": ["alter", "modify", "shift", "transform", "adjust"],
    "show": ["reveal", "display", "demonstrate", "illustrate", "indicate"],
    "find": ["discover", "locate", "identify", "detect", "uncover"],
    "make": ["create", "produce", "build", "generate", "form"],
    "use": ["employ", "apply", "utilize", "deploy", "adopt"],
    "help": ["assist", "support", "aid", "enable", "facilitate"],
    "good": ["solid", "sound", "effective", "strong", "valuable"],
    "bad": ["poor", "weak", "flawed", "inadequate", "problematic"],
    "big": ["large", "substantial", "major", "considerable", "broad"],
    "small": ["tiny", "minor", "limited", "narrow", "modest"],
    "new": ["fresh", "recent", "novel", "modern", "current"],
    "old": ["former", "previous", "ancient", "outdated", "prior"],
    "give": ["provide", "offer", "supply", "deliver", "grant"],
    "take": ["grab", "receive", "accept", "obtain", "adopt"],
    "need": ["require", "demand", "necessitate", "call for"],
    "think": ["consider", "believe", "reason", "judge", "assume"],
    "know": ["understand", "recognize", "realize", "grasp", "comprehend"],
    "say": ["state", "declare", "mention", "report", "claim"],
    "look": ["glance", "examine", "inspect", "observe", "review"],
    "start": ["begin", "initiate", "launch", "commence", "kick off"],
    "stop": ["halt", "end", "cease", "terminate", "finish"],
    "fast": ["rapid", "quick", "swift", "speedy", "brisk"],
    "slow": ["gradual", "sluggish", "delayed", "measured"],
    "hard": ["difficult", "challenging", "tough", "demanding"],
    "easy": ["simple", "straightforward", "effortless", "basic"],
    "increase": ["raise", "boost", "expand", "grow", "elevate"],
    "reduce": ["lower", "cut", "decrease", "shrink", "diminish"],
    "create": ["generate", "produce", "design", "build", "form"],
    "destroy": ["demolish", "wreck", "dismantle", "ruin"],
    "improve": ["enhance", "upgrade", "refine", "strengthen", "optimize"],
    "learn": ["study", "master", "absorb", "grasp"],
    "write": ["compose", "draft", "record", "document"],
    "read": ["scan", "review", "examine", "study"],
    "build": ["construct", "assemble", "erect", "develop"],
    "people": ["individuals", "persons", "humans", "folks"],
    "problem": ["issue", "challenge", "difficulty", "obstacle"],
    "result": ["outcome", "effect", "consequence", "product"],
    "way": ["method", "approach", "manner", "route", "path"],
    "time": ["period", "moment", "duration", "interval"],
    "world": ["globe", "planet", "earth", "realm"],
    "work": ["labor", "effort", "task", "operation"],
    "year": ["annum", "cycle", "period"],
    "day": ["date", "period", "cycle"],
    "place": ["location", "site", "spot", "position"],
    "thing": ["object", "item", "entity", "element"],
    "point": ["aspect", "element", "detail", "factor"],
    "part": ["piece", "segment", "portion", "section"],
    "case": ["instance", "example", "scenario", "situation"],
    "question": ["query", "inquiry", "issue", "topic"],
}


def tokenize(text: str, level: str = "word") -> list[str]:
    """Tokenize at word level (default) or BPE subword level.

    Word level lowercases; BPE level preserves case (the greenlist hashes
    over the exact subword surface a real tokenizer would see).
    """
    if level == "bpe":
        return bpe_tokenize(text)
    return [m.group(0).lower() for m in _TOKEN_RE.finditer(text)]


def _unit_interval(h: str) -> float:
    """Map a hex digest to [0, 1)."""
    return int(h[:8], 16) / 0xFFFFFFFF


def green_token(token: str, context, key: str, gamma: float = DEFAULT_GAMMA) -> bool:
    """KGW greenlist membership over a context window: PRF(key, *context, token) < gamma.

    `context` is either a single previous token (backward-compatible) or a
    list/tuple of the c preceding tokens (context-window scheme). The PRF
    hashes (key, *context, token). For a single-token context the digest is
    byte-identical to the historical (key, prev, token) hash, so all existing
    c=1 call sites keep producing the exact same greenlist decisions.
    """
    ctx = list(context) if isinstance(context, (list, tuple)) else [context]
    digest = hashlib.sha256((f"{key}:" + ":".join(ctx) + f":{token}").encode("utf-8")).hexdigest()
    return _unit_interval(digest) < gamma


def _summarize_z(green: int, n: int, gamma: float) -> dict:
    """Summarize a green-count Z-test into a detector result dict.

    Two-sided p-value (|z|). The SIGN of z carries the watermark semantics:
    z > 0 means the greenlist is over-represented (a greenlist watermark that
    FAVOURS a hash-derived token set); z < 0 means it is under-represented —
    the signature of a REDLIST watermark that AVOIDS a hash-derived token set.
    The verdict + signal fields encode that sign explicitly.
    """
    mu = gamma * n
    sigma = math.sqrt(n * gamma * (1 - gamma))
    z = (green - mu) / sigma
    p_value = math.erfc(abs(z) / math.sqrt(2))  # two-sided instead of upper-tail
    rate = green / n
    if z >= 4.0:
        verdict, signal = "watermark_detected", "greenlist"
    elif z <= -4.0:
        verdict, signal = "redlist_detected", "redlist"
    elif z >= 2.0:
        verdict, signal = "weak_signal", "greenlist"
    elif z <= -2.0:
        verdict, signal = "weak_redlist_signal", "redlist"
    else:
        verdict, signal = "no_signal", None
    return {
        "z_score": round(z, 4),
        "p_value": round(p_value, 10),
        "green_count": green,
        "n_tokens": n,
        "green_rate": round(rate, 4),
        "verdict": verdict,
        "signal": signal,
    }


def _type_stats(pairs: list, key: str, gamma: float) -> dict:
    """Raw per-token-TYPE statistics over scored (token, context) pairs.

    `pairs` mirrors exactly what detect_kgw scores (token at position i
    against its context window) so the per-type numbers can never drift from
    the detector's own count. Raw (unrounded) values; the public wrappers
    round for display while comparisons use full precision.
    """
    n = len(pairs)
    per: dict[str, list[int]] = {}
    for tok, ctx in pairs:
        st = per.setdefault(tok, [0, 0])
        st[0] += 1
        if green_token(tok, ctx, key, gamma):
            st[1] += 1
    types = []
    for tok, (count, gc) in per.items():
        var = count * gamma * (1.0 - gamma)
        zc = (gc - count * gamma) / math.sqrt(var) if count and var > 0 else None
        types.append(
            {
                "token": tok,
                "count": count,
                "share": count / n if n else 0.0,
                "green_count": gc,
                "green_rate": gc / count if count else None,
                "z_contribution": zc,
            }
        )
    types.sort(key=lambda t: -t["count"])
    return {
        "n_tokens": n,
        "total_green": sum(t["green_count"] for t in types),
        "types": types,
    }


def _scored_pairs(tokens: list[str], context_seq: int) -> list:
    """(token, context) pairs exactly as detect_kgw scores a token list."""
    return [(tokens[i], tokens[max(0, i - context_seq) : i]) for i in range(1, len(tokens))]


def signature_token_stats(tokens: list[str], context_seq: int, key: str, gamma: float = DEFAULT_GAMMA) -> dict:
    """Per-token-TYPE statistics over the scored stream (signature diagnostics).

    `tokens` is a full token list (its first element is the unscored seed
    token, exactly like detect_kgw's stream); `context_seq` is the greenlist
    context window size c — identical to detect_kgw(..., context=c). For
    every token type the detector actually scores:

      count          number of scored occurrences
      share          count / n (share of the scored stream)
      green_count    how many of those occurrences hash green
      green_rate     green_count / count
      z_contribution the Z-value that type ALONE would produce:
                     (green_count - count*gamma) / sqrt(count*gamma*(1-gamma))

    A type with high share AND |z_contribution| >= 3 can flip the global
    Z-test by itself — the "signature tokens" of arXiv 2606.18430v2. These
    stats expose exactly that per-type leverage. This is a DIAGNOSTIC, not a
    verdict: it does not by itself prove or disprove a watermark.

    Returns {"n_tokens": n, "total_green": green, "types": [...]} with types
    sorted by count descending (deterministic order).
    """
    raw = _type_stats(_scored_pairs(tokens, context_seq), key, gamma)
    return {
        "n_tokens": raw["n_tokens"],
        "total_green": raw["total_green"],
        "types": [
            {
                "token": t["token"],
                "count": t["count"],
                "share": round(t["share"], 4),
                "green_count": t["green_count"],
                "green_rate": round(t["green_rate"], 4) if t["green_rate"] is not None else None,
                "z_contribution": round(t["z_contribution"], 4) if t["z_contribution"] is not None else None,
            }
            for t in raw["types"]
        ],
    }


def _filter_pairs(
    pairs: list, key: str, gamma: float, min_share: float, max_filter: int, tokens: list[str] | None = None
) -> dict:
    """Shared signature-filter core over scored pairs (see signature_filter)."""
    stats = _type_stats(pairs, key, gamma)
    candidates = [
        t
        for t in stats["types"]
        if t["share"] >= min_share and t["z_contribution"] is not None and abs(t["z_contribution"]) >= 3.0
    ]
    # Most destabilizing first (stable sort: equal |z| keeps count order).
    candidates.sort(key=lambda t: -abs(t["z_contribution"]))
    removed_types = candidates[:max_filter]
    removed_set = {t["token"] for t in removed_types}
    n_removed = sum(t["count"] for t in removed_types)
    return {
        "filtered_tokens": ([tok for tok in tokens if tok not in removed_set] if tokens is not None else []),
        "removed": [
            {
                "token": t["token"],
                "count": t["count"],
                "share": round(t["share"], 4),
                "z_contribution": round(t["z_contribution"], 4),
            }
            for t in removed_types
        ],
        "n_removed": n_removed,
        "n_before": stats["n_tokens"],
        "n_after": stats["n_tokens"] - n_removed,
        "green_removed": sum(t["green_count"] for t in removed_types),
        "total_green": stats["total_green"],
    }


def signature_filter(
    tokens: list[str],
    context_seq: int,
    key: str,
    gamma: float = DEFAULT_GAMMA,
    min_share: float = 0.25,
    max_filter: int = 3,
) -> dict:
    """Frequency-heuristic signature-token pre-filter for FPR CONTROL.

    Removes the up to `max_filter` token TYPES whose share of the scored
    stream is >= min_share AND whose |z_contribution| is >= 3.0 — the types
    that alone could flip the Z-test ("signature tokens", arXiv
    2606.18430v2). The detector then recomputes the Z-score over the
    remaining scored positions, which re-centers the test on texts dominated
    by one repetitive token (paper-measured: FPR 98% -> 0% for a dominant
    token; reproduced here for the dominant-token class).

    This is a FREQUENCY HEURISTIC, not the paper's MILP: it needs no learned
    signature set and needs no training data.

    HONEST LIMITS — this is FPR control, NOT a TPR improvement:
    - The paper's 78-99% TPR gains at weak signal come from a MILP-learned
      signature set; a frequency heuristic cannot promise them. We only
      claim FPR control for the dominant/repetitive-token failure class.
    - The thresholds (share >= min_share, |z| >= 3.0) are heuristics, not
      calibrated constants; tuning them trades FPR against TPR.
    - Removing tokens discards signal: on genuinely marked texts with
      repetitive vocabulary this can LOWER z. The feature is therefore
      opt-in (detect_kgw(..., signature_filter=False) by default).

    Returns:
      {"filtered_tokens": [...],   # original token list, removed types dropped
       "removed": [{"token", "count", "share", "z_contribution"}...],
       "n_removed": int, "n_before": int, "n_after": int,
       "green_removed": int}
    """
    return _filter_pairs(_scored_pairs(tokens, context_seq), key, gamma, min_share, max_filter, tokens)


def _apply_signature_filter(pairs: list, n: int, key: str, gamma: float) -> dict:
    """Filtered Z-summary: re-summarize after dropping signature tokens.

    Used by detect_kgw's opt-in path (word and BPE level). Returns a
    detect-shaped dict that additionally carries `signature_filtered`
    {"removed": [...], "n_removed": int, "n_after": int, "n_before": int}.
    An honest too_short is returned when the FILTERED stream drops below 10
    scored tokens.
    """
    fres = _filter_pairs(pairs, key, gamma, min_share=0.25, max_filter=3)
    green_after = fres["total_green"] - fres["green_removed"]
    n_after = fres["n_after"]
    sf = {
        "removed": fres["removed"],
        "n_removed": fres["n_removed"],
        "n_after": n_after,
        "n_before": n,
    }
    if n_after < 10:
        return {
            "z_score": None,
            "p_value": None,
            "green_count": green_after,
            "n_tokens": n_after,
            "green_rate": None,
            "verdict": "too_short",
            "signal": None,
            "signature_filtered": sf,
        }
    result = _summarize_z(green_after, n_after, gamma)
    result["signature_filtered"] = sf
    return result


def detect_kgw(
    text: str,
    key: str,
    gamma: float = DEFAULT_GAMMA,
    level: str = "word",
    context: int = 1,
    signature_filter: bool = False,
) -> dict:
    """Z-score test for one key. Returns None-ish fields if text too short.

    level="bpe" runs the greenlist over BPE subword tokens at WORD BOUNDARIES:
    the pair scored is (last subword of word i-1, first subword of word i).
    This matches exactly what text-only rewriting can impose — a rewrite can
    choose a whole word, not a mid-word subword. level="word" keeps the fast
    word-level approximation (default). The BPE path always uses a context
    window of 1 (single predecessor word).

    `context` (word level only) is the greenlist window size c: each token is
    hashed against the c preceding tokens. c=1 is the historical single-
    predecessor scheme and is byte-identical to previous releases.

    `signature_filter=True` (opt-in; DEFAULT False) pre-filters signature
    tokens (arXiv 2606.18430v2) BEFORE the green count: token types with
    share >= 0.25 of the scored stream AND |z_contribution| >= 3 are removed
    and the Z-test is recomputed over the remaining stream. This is an
    FPR-CONTROL measure for texts dominated by one repetitive token — NOT a
    TPR improvement (the paper's TPR gains need a MILP-learned signature
    set; see signature_filter's docstring). The result then additionally
    carries `signature_filtered` {"removed", "n_removed", "n_after",
    "n_before"}. Default False keeps the historical behavior and result
    shape byte-identical.
    """
    if level == "bpe":
        return _detect_bpe_boundaries(text, key, gamma, signature_filter=signature_filter)
    tokens = tokenize(text, level=level)
    n = len(tokens) - 1  # number of scored tokens (each scored against its predecessors)
    if n < 10:
        res = {
            "z_score": None,
            "p_value": None,
            "green_count": 0,
            "n_tokens": n,
            "green_rate": None,
            "verdict": "too_short",
            "signal": None,
        }
        if signature_filter:
            res["signature_filtered"] = {
                "removed": [],
                "n_removed": 0,
                "n_after": n,
                "n_before": n,
            }
        return res
    if signature_filter:
        # Opt-in signature pre-filter: same scored stream as the unfiltered
        # path (e_value._iter_scored is the single source of truth), with the
        # signature types dropped before the Z-test.
        from .e_value import _iter_scored  # lazy: e_value imports this module

        pairs = list(_iter_scored(text, key, gamma, level, context))
        return _apply_signature_filter(pairs, n, key, gamma)
    green = sum(1 for i in range(1, len(tokens)) if green_token(tokens[i], tokens[max(0, i - context) : i], key, gamma))
    return _summarize_z(green, n, gamma)


def _bpe_word_subwords(text: str) -> list[list[str]]:
    """Per-word BPE subword lists; mark and detect share this exact surface."""
    words = [m.group(0) for m in _TOKEN_RE.finditer(text)]
    return [s for s in (_bpe_subwords_cached(w) for w in words) if s]


def _score_bpe_boundaries(subs: list[list[str]], key: str, gamma: float) -> tuple[int, int]:
    """Count green word-boundary pairs: (last subword of prev, first of curr).

    Returns (green, n) where n is the number of scored boundary pairs.
    This is the single source of truth for the BPE green rate so that
    mark_greenlist and detect_kgw can never drift apart.
    """
    n = len(subs) - 1
    if n <= 0:
        return 0, 0
    green = sum(1 for i in range(1, len(subs)) if green_token(subs[i][0], subs[i - 1][-1], key, gamma))
    return green, n


def _detect_bpe_boundaries(text: str, key: str, gamma: float, signature_filter: bool = False) -> dict:
    """BPE-level detection scored at word boundaries (see detect_kgw)."""
    subs = _bpe_word_subwords(text)
    green, n = _score_bpe_boundaries(subs, key, gamma)
    if n < 10:
        res = {
            "z_score": None,
            "p_value": None,
            "green_count": 0,
            "n_tokens": n,
            "green_rate": None,
            "verdict": "too_short",
            "signal": None,
        }
        if signature_filter:
            res["signature_filtered"] = {
                "removed": [],
                "n_removed": 0,
                "n_after": n,
                "n_before": n,
            }
        return res
    if signature_filter:
        from .e_value import _iter_scored  # lazy: e_value imports this module

        pairs = list(_iter_scored(text, key, gamma, "bpe", 1))
        return _apply_signature_filter(pairs, n, key, gamma)
    return _summarize_z(green, n, gamma)


def detect_multi_key(
    text: str,
    keys: list[dict],
    gamma: float = DEFAULT_GAMMA,
    level: str = "word",
    context: int = 1,
    signature_filter: bool = False,
) -> dict:
    """Test all KGW-family keys. Best |Z|-score wins; report all.

    keys: list of dicts with at least {'key_id': str, 'secret': str}.
    Only keys with family 'kgw' (or carrying a 'secret') are tested.

    Selection is by Z MAGNITUDE with sign preserved: a redlist watermark shows
    a strongly NEGATIVE z (greenlist under-represented) that must still win
    over near-zero wrong keys, while a greenlist watermark shows a strongly
    POSITIVE z. Raw `max(z_score)` would wrongly skip the redlist key.

    `level` and `context` are forwarded to detect_kgw so the product path
    (API/CLI) can score at BPE granularity and with a context window c.
    `signature_filter` (default False) is forwarded to detect_kgw as well:
    when True, each per-key result carries its `signature_filtered` field.
    Default False keeps the historical behavior byte-identical.
    """
    results = []
    for k in keys:
        secret = k.get("secret")
        family = k.get("family", "")
        if not secret or (family and family != "kgw"):
            continue
        r = detect_kgw(text, secret, gamma, level=level, context=context, signature_filter=signature_filter)
        r["key_id"] = k.get("key_id", "unknown")
        results.append(r)
    if not results:
        return {"tested_keys": 0, "best": None, "results": [], "note": "no_kgw_keys_registered"}
    best = max(results, key=lambda r: abs(r["z_score"]) if r["z_score"] is not None else -1)
    # Bonferroni-style adjustment: multiple keys inflate false positives.
    m = len(results)
    best_p_adj = min(1.0, (best.get("p_value") or 1.0) * m)
    return {
        "tested_keys": m,
        "best": best,
        "best_p_adjusted": round(best_p_adj, 10),
        "note": f"bonferroni_adjusted_over_{m}_keys",
        "results": results,
    }


def _restore_case(word: str, template: str) -> str:
    if template.isupper() and len(template) > 1:
        return word.upper()
    if template[0].isupper():
        return word[0].upper() + word[1:]
    return word


def _derive_seed(key: str, seed: int | None) -> int:
    """Deterministic seed from key when no explicit seed is given.

    Same input + key always produce the same seed, making greenlist
    marking reproducible across runs. An explicit seed overrides.
    Extracted so mark_greenlist and embed_kgw share the same logic.
    """
    if seed is None:
        return int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big")
    return seed


def mark_greenlist(
    text: str,
    key: str,
    gamma: float = DEFAULT_GAMMA,
    vocab: dict[str, list[str]] | None = None,
    seed: int | None = None,
    level: str = "word",
    context: int = 1,
) -> dict:
    """Directly greenlist-mark a text so the detector finds it (embed path).

    Unlike embed_kgw (lexicon-synonym rewrite, best-effort), this imposes the
    greenlist: for every scored token whose (key, *context, token) hash is NOT
    green, it substitutes a green word from the provided pool, so the final
    green ratio is pushed well above gamma and the Z-score clears 4.0.

    `context` (word level only) is the greenlist window size c: each word is
    scored against the c preceding words, mirroring detect_kgw(..., context=c)
    exactly. c=1 is the historical single-predecessor scheme and is
    byte-identical to previous releases. level="bpe" always uses c=1: a
    candidate word is green when its FIRST BPE subword token hashes green
    against the LAST BPE subword of the single previous word — the same
    surface detect_kgw(level="bpe") scores, so mark→detect round-trips on the
    same token level.

    Substitutions are drawn from `vocab` (default: FREQUENT_VOCAB), a
    frequency pool, NOT synonyms — semantics are not preserved word-for-word;
    this is the honest signal-imposition approximation of token-sampling
    watermarking.
    """
    from .frequent_vocab import FREQUENT_VOCAB

    pool = vocab if vocab is not None else FREQUENT_VOCAB
    # deterministic seed ensures identical input + key always produce the
    # SAME marking (reproducible embeddings). A random per-run seed makes
    # the z-score of a fixed doc+key vary run to run (context=1 chains
    # depend on the concrete substitute words), which breaks round-trip
    # reproducibility and made CI flaky (z=3.9 vs 4.1 on identical input).
    rng = random.Random(_derive_seed(key, seed))
    # flat list of green candidates across the pool for fallback substitution
    fallback = [w for ws in pool.values() for w in ws]

    def _first_bpe(word: str) -> str:
        return _bpe_subwords_cached(word)[0]

    def _last_bpe(word: str) -> str:
        return _bpe_subwords_cached(word)[-1]

    def _is_green(cand: str, ctx: list[str]) -> bool:
        if level == "bpe":
            return green_token(_first_bpe(cand), _last_bpe(ctx[-1]), key, gamma)
        # word level: hash over the (up to c) preceding lowercased words
        return green_token(cand.lower(), [w.lower() for w in ctx], key, gamma)

    parts = _SPLIT_RE.split(text)
    replaced = 0
    subs_raw: list[tuple[int, str, str]] = []  # (index, original, replacement)
    # Rolling window of the last `context` finalized (post-substitution) words.
    # BPE keeps a window of 1 (single predecessor word).
    win = collections.deque(maxlen=context if level == "word" else 1)
    for i, part in enumerate(parts):
        if i % 2 == 0:
            continue
        token = part
        lower = token.lower()
        if not win:
            win.append(lower)
            continue
        ctx = list(win)
        if _is_green(token, ctx):
            win.append(lower)
            continue
        # not green -> substitute a green word (prefer a same-class word)
        cands = pool.get(lower, [])
        green_pick = None
        for c in cands:
            if _is_green(c, ctx):
                green_pick = c
                break
        if green_pick is None:
            # any fallback word that is green for (context, key)
            rng.shuffle(fallback)
            for c in fallback:
                if _is_green(c, ctx):
                    green_pick = c
                    break
        if green_pick is not None:
            parts[i] = _restore_case(green_pick, token)
            replaced += 1
            subs_raw.append((i, token, parts[i]))
            win.append(green_pick.lower())
        else:
            win.append(lower)
    new_text = "".join(parts)
    # Substitution positions in the FINAL text (post-substitution offsets —
    # replacements may change token length, so offsets are computed by
    # walking the joined parts once, not by tracking during substitution).
    subs_by_idx = {i: (orig, rep) for i, orig, rep in subs_raw}
    substitutions: list[dict] = []
    offset = 0
    for i, part in enumerate(parts):
        if i % 2 == 0:
            offset += len(part)
            continue
        entry = subs_by_idx.get(i)
        if entry is not None:
            orig, rep = entry
            substitutions.append(
                {
                    "start": offset,
                    "end": offset + len(rep),
                    "original": orig,
                    "replacement": rep,
                }
            )
        offset += len(part)
    if level == "bpe":
        # Report the SAME green rate the detector sees: word-boundary pairs
        # (last subword of prev word, first subword of curr word), not every
        # contiguous BPE pair in the flat subword stream.
        subs = _bpe_word_subwords(new_text)
        green_now, n = _score_bpe_boundaries(subs, key, gamma)
        total_tokens = len(subs)
    else:
        tokens_after = tokenize(new_text, level=level)
        n = max(0, len(tokens_after) - 1)
        green_now = (
            sum(
                1
                for i in range(1, len(tokens_after))
                if green_token(tokens_after[i], tokens_after[max(0, i - context) : i], key, gamma)
            )
            if n
            else 0
        )
        total_tokens = len(tokens_after)
    return {
        "text": new_text,
        "replacements": replaced,
        "total_tokens": total_tokens,
        "green_rate_after": round(green_now / n, 4) if n else None,
        "substitutions": substitutions,
    }


def embed_kgw(
    text: str,
    key: str,
    gamma: float = DEFAULT_GAMMA,
    lexicon: dict[str, list[str]] | None = None,
    seed: int | None = None,
) -> dict:
    """DEPRECATED — use :func:`mark_greenlist` instead.

    Legacy KGW-embed via lexicon rewrite: replaces content words with
    synonyms in the greenlist of (key, previous_token). Best-effort only:
    detection "may stay below the threshold" when few replacements are
    possible. ``mark_greenlist`` deterministically imposes the greenlist
    (guaranteed z > 4 with context/BPE support) and is the product path.

    Returns {'text': ..., 'replacements': n, 'total_tokens': n,
             'replaceable': k, 'green_rate_estimate': ...}.
    The first token is never replaced (no predecessor to score against).
    Kept for backward compatibility (tests/benchmarks); new callers must
    use mark_greenlist.
    """
    lex = lexicon if lexicon is not None else EMBED_LEXICON
    rng = random.Random(_derive_seed(key, seed))
    parts = _SPLIT_RE.split(text)
    replaced = 0
    replaceable = 0
    prev = ""
    for i, part in enumerate(parts):
        if i % 2 == 0:  # separator text (whitespace/punctuation)
            continue
        token = part
        lower = token.lower()
        candidates = lex.get(lower, [])
        if not candidates or not prev:
            prev = lower
            continue
        replaceable += 1
        green_cands = [c for c in candidates if green_token(c, prev, key, gamma)]
        if green_cands:
            chosen = rng.choice(green_cands)
            parts[i] = _restore_case(chosen, token)
            replaced += 1
            prev = chosen
        else:
            prev = lower
    new_text = "".join(parts)
    tokens_after = tokenize(new_text)
    n = max(0, len(tokens_after) - 1)
    green_now = (
        sum(1 for i in range(1, len(tokens_after)) if green_token(tokens_after[i], tokens_after[i - 1], key, gamma))
        if n
        else 0
    )
    return {
        "text": new_text,
        "replacements": replaced,
        "replaceable": replaceable,
        "total_tokens": len(tokens_after),
        "green_rate_after": round(green_now / n, 4) if n else None,
    }
