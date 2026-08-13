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


def _bpe_encoding():
    """Lazily load the tiktoken cl100k_base encoding (cached per process)."""
    global _BPE_ENC
    if _BPE_ENC is None:
        try:
            import tiktoken
        except ImportError as e:  # pragma: no cover - dependency hint path
            raise ImportError(
                "BPE-level detection needs tiktoken: pip install text-watermark-studio[bpe]"
            ) from e
        _BPE_ENC = tiktoken.get_encoding("cl100k_base")
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
    digest = hashlib.sha256(
        (f"{key}:" + ":".join(ctx) + f":{token}").encode("utf-8")
    ).hexdigest()
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
        "z_score": round(z, 4), "p_value": round(p_value, 10),
        "green_count": green, "n_tokens": n, "green_rate": round(rate, 4),
        "verdict": verdict, "signal": signal,
    }


def detect_kgw(text: str, key: str, gamma: float = DEFAULT_GAMMA,
               level: str = "word", context: int = 1) -> dict:
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
    """
    if level == "bpe":
        return _detect_bpe_boundaries(text, key, gamma)
    tokens = tokenize(text, level=level)
    n = len(tokens) - 1  # number of scored tokens (each scored against its predecessors)
    if n < 10:
        return {
            "z_score": None, "p_value": None, "green_count": 0,
            "n_tokens": n, "green_rate": None, "verdict": "too_short",
            "signal": None,
        }
    green = sum(
        1 for i in range(1, len(tokens))
        if green_token(tokens[i], tokens[max(0, i - context):i], key, gamma)
    )
    return _summarize_z(green, n, gamma)


def _bpe_word_subwords(text: str) -> list[list[str]]:
    """Per-word BPE subword lists; mark and detect share this exact surface."""
    words = [m.group(0) for m in _TOKEN_RE.finditer(text)]
    return [s for s in (bpe_tokenize(w) for w in words) if s]


def _score_bpe_boundaries(subs: list[list[str]], key: str, gamma: float) -> tuple[int, int]:
    """Count green word-boundary pairs: (last subword of prev, first of curr).

    Returns (green, n) where n is the number of scored boundary pairs.
    This is the single source of truth for the BPE green rate so that
    mark_greenlist and detect_kgw can never drift apart.
    """
    n = len(subs) - 1
    if n <= 0:
        return 0, 0
    green = sum(
        1 for i in range(1, len(subs))
        if green_token(subs[i][0], subs[i - 1][-1], key, gamma)
    )
    return green, n


def _detect_bpe_boundaries(text: str, key: str, gamma: float) -> dict:
    """BPE-level detection scored at word boundaries (see detect_kgw)."""
    subs = _bpe_word_subwords(text)
    green, n = _score_bpe_boundaries(subs, key, gamma)
    if n < 10:
        return {
            "z_score": None, "p_value": None, "green_count": 0,
            "n_tokens": n, "green_rate": None, "verdict": "too_short",
            "signal": None,
        }
    return _summarize_z(green, n, gamma)


def detect_multi_key(text: str, keys: list[dict], gamma: float = DEFAULT_GAMMA) -> dict:
    """Test all KGW-family keys. Best |Z|-score wins; report all.

    keys: list of dicts with at least {'key_id': str, 'secret': str}.
    Only keys with family 'kgw' (or carrying a 'secret') are tested.

    Selection is by Z MAGNITUDE with sign preserved: a redlist watermark shows
    a strongly NEGATIVE z (greenlist under-represented) that must still win
    over near-zero wrong keys, while a greenlist watermark shows a strongly
    POSITIVE z. Raw `max(z_score)` would wrongly skip the redlist key.
    """
    results = []
    for k in keys:
        secret = k.get("secret")
        family = k.get("family", "")
        if not secret or (family and family != "kgw"):
            continue
        r = detect_kgw(text, secret, gamma)
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


def mark_greenlist(text: str, key: str, gamma: float = DEFAULT_GAMMA,
                   vocab: dict[str, list[str]] | None = None,
                   seed: int | None = None, level: str = "word",
                   context: int = 1) -> dict:
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
    rng = random.Random(seed)
    # flat list of green candidates across the pool for fallback substitution
    fallback = [w for ws in pool.values() for w in ws]

    def _first_bpe(word: str) -> str:
        return bpe_tokenize(word)[0]

    def _last_bpe(word: str) -> str:
        return bpe_tokenize(word)[-1]

    def _is_green(cand: str, ctx: list[str]) -> bool:
        if level == "bpe":
            return green_token(_first_bpe(cand), _last_bpe(ctx[-1]), key, gamma)
        # word level: hash over the (up to c) preceding lowercased words
        return green_token(cand.lower(), [w.lower() for w in ctx], key, gamma)

    parts = _SPLIT_RE.split(text)
    replaced = 0
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
            win.append(green_pick.lower())
        else:
            win.append(lower)
    new_text = "".join(parts)
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
        green_now = sum(
            1 for i in range(1, len(tokens_after))
            if green_token(tokens_after[i], tokens_after[max(0, i - context):i], key, gamma)
        ) if n else 0
        total_tokens = len(tokens_after)
    return {
        "text": new_text,
        "replacements": replaced,
        "total_tokens": total_tokens,
        "green_rate_after": round(green_now / n, 4) if n else None,
    }


def embed_kgw(text: str, key: str, gamma: float = DEFAULT_GAMMA,
              lexicon: dict[str, list[str]] | None = None, seed: int | None = None) -> dict:
    """KGW-embed a text via lexicon rewrite: replace content words with
    synonyms that land in the greenlist of (key, previous_token).

    Returns {'text': ..., 'replacements': n, 'total_tokens': n,
             'replaceable': k, 'green_rate_estimate': ...}.
    The first token is never replaced (no predecessor to score against).
    """
    lex = lexicon if lexicon is not None else EMBED_LEXICON
    rng = random.Random(seed)
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
    green_now = sum(
        1 for i in range(1, len(tokens_after))
        if green_token(tokens_after[i], tokens_after[i - 1], key, gamma)
    ) if n else 0
    return {
        "text": new_text,
        "replacements": replaced,
        "replaceable": replaceable,
        "total_tokens": len(tokens_after),
        "green_rate_after": round(green_now / n, 4) if n else None,
    }
