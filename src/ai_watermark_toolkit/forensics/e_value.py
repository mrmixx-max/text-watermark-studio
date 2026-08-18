"""E-process (anytime-valid likelihood-ratio) watermark detection.

D1 from the build list: detect a KGW greenlist watermark with an e-process
instead of (or after) the Z-score. Literature: 2602.17608 (e-values for
statistical watermarking), 2607.21958.

Theory (per-token likelihood ratio)
-----------------------------------
Null H0 (human/uniform):  P(token green) = gamma, P(red) = 1 - gamma.
Alternative H1 (watermarked, logit bias delta > 0 on green tokens):

    p1(green) = gamma*e^delta / (gamma*e^delta + 1 - gamma)
    p1(red)   = (1 - gamma) / (gamma*e^delta + 1 - gamma)

with the same denominator for both, so the per-token likelihood ratio is

    e_t = e^delta / denom   if x_t is green, else  1 / denom
    denom = gamma*e^delta + (1 - gamma)

E_n = prod_{t=1..n} e_t is a nonnegative martingale under H0 with E[E_n] = 1
(e-process). Ville's inequality makes any stopping time valid:

    P( sup_n E_n >= 1/alpha ) <= alpha      (anytime validity)

so we may stop as soon as E_n crosses 1/alpha (early_stop) and still control
the false positive rate. The validity is independent of delta: ANY delta > 0
yields a valid martingale, so delta is fixed (default 0.4).

Multi-key: Bonferroni over K keys -> each key must reach E >= K/alpha.

Numerical stability
-------------------
E_n grows super-exponentially on marked text and can exceed float64 range
(exp(709) ~ 1.8e308) for long texts; on clean text it decays toward 0. All
decisions therefore happen in LOG space (log_e = sum log(e_t), compared
against log(1/alpha)); e_value is exp(log_e) capped at the largest finite
float, so no OverflowError can ever escape the API.

Tokenization
------------
The scored token stream is EXACTLY the stream detect_kgw scores: word level
scores tokens[1:] against the preceding context window, bpe level scores
word-boundary pairs (first subword of word i against last subword of word
i-1). Both paths call the SAME green_token PRF with the same arguments, so
e_detect and detect_kgw can never drift apart (verified by tests).
"""

from __future__ import annotations

import math
import sys

from .kgw import DEFAULT_GAMMA, _bpe_word_subwords, green_token, tokenize

# Default logit bias on greenlist tokens under the alternative. Any delta > 0
# gives a valid e-process (validity is delta-independent); 0.4 is the
# reference value from the literature and the demo implementation.
DEFAULT_DELTA = 0.4

# Largest finite float64 exponent; log-space accumulation is capped only for
# the exp() conversion, never for the verdict comparison.
_LOG_MAX = math.log(sys.float_info.max)  # ~709.78


def _iter_scored(text: str, key: str, gamma: float, level: str, context: int):
    """Yield the (token, context) pairs exactly as detect_kgw scores them.

    Word level: token tokens[i] against context window
    tokens[max(0, i-context):i] (list context). BPE level: first subword of
    word i against the last subword of word i-1 (single-token context),
    mirroring _score_bpe_boundaries. This is the single source of truth for
    the e-process token stream, so mark/detect consistency with detect_kgw is
    structural, not incidental.
    """
    if level == "bpe":
        subs = _bpe_word_subwords(text)
        for i in range(1, len(subs)):
            yield subs[i][0], subs[i - 1][-1]
    else:
        tokens = tokenize(text, level=level)
        for i in range(1, len(tokens)):
            yield tokens[i], tokens[max(0, i - context) : i]


def _log_process(text: str, key: str, gamma: float, delta: float, level: str, context: int) -> tuple[list[bool], float]:
    """Green flags + per-token log-ratio contributions for the whole text.

    Returns (flags, log_denom) where log_denom = log(gamma*e^delta + 1-gamma)
    is shared by every token; e_detect uses this to iterate with early stop
    without re-tokenizing.
    """
    denom = gamma * math.exp(delta) + (1.0 - gamma)
    log_denom = math.log(denom)
    flags = [green_token(tok, ctx, key, gamma) for tok, ctx in _iter_scored(text, key, gamma, level, context)]
    return flags, log_denom


def e_process(
    text: str,
    key: str,
    gamma: float = DEFAULT_GAMMA,
    delta: float = DEFAULT_DELTA,
    level: str = "word",
    context: int = 1,
) -> float:
    """Run the e-process over the whole text; return E_n (the product).

    Computed in log space and capped at the largest finite float: for long
    marked texts E_n legitimately exceeds float64 range, so the returned
    value saturates at ~1.8e308 (use e_detect()["log_e"] for the exact value).
    """
    flags, log_denom = _log_process(text, key, gamma, delta, level, context)
    log_e = 0.0
    for g in flags:
        log_e += (delta - log_denom) if g else -log_denom
    return math.exp(min(log_e, _LOG_MAX))


def e_detect(
    text: str,
    key: str,
    gamma: float = DEFAULT_GAMMA,
    delta: float = DEFAULT_DELTA,
    alpha: float = 0.05,
    level: str = "word",
    context: int = 1,
    early_stop: bool = False,
) -> dict:
    """E-process detection for one key: E_n >= 1/alpha (anytime-valid).

    `early_stop=True` stops as soon as log_e >= log(1/alpha) — Ville's
    inequality makes the stopping time valid, so the verdict is exact while
    only a prefix of the text is processed (reported via tokens_processed /
    stopped_at). Without early_stop the whole text is scored and n_tokens is
    identical to detect_kgw's n_tokens for the same input.

    Returns: e_value, log_e, threshold (1/alpha), detected, n_tokens,
    tokens_processed, stopped_at, green_count, green_rate, delta, alpha,
    verdict ('e_value_detected' | 'no_e_value' | 'too_short').
    """
    flags, log_denom = _log_process(text, key, gamma, delta, level, context)
    n_total = len(flags)
    if n_total == 0:
        return {
            "e_value": 1.0,
            "log_e": 0.0,
            "threshold": round(1.0 / alpha, 6),
            "detected": False,
            "n_tokens": 0,
            "tokens_processed": 0,
            "stopped_at": None,
            "green_count": 0,
            "green_rate": None,
            "delta": delta,
            "alpha": alpha,
            "verdict": "too_short",
            "signal": None,
        }
    log_threshold = math.log(1.0 / alpha)
    log_e = 0.0
    green = 0
    stopped_at = None
    processed = 0
    for i, g in enumerate(flags, start=1):
        if g:
            green += 1
            log_e += delta - log_denom
        else:
            log_e -= log_denom
        processed = i
        if early_stop and log_e >= log_threshold:
            stopped_at = i
            break
    detected = log_e >= log_threshold
    return {
        "e_value": math.exp(min(log_e, _LOG_MAX)),
        # Full precision: e_detect_multi re-uses log_e for the Bonferroni
        # comparison, and rounding here could flip a borderline verdict.
        "log_e": log_e,
        "threshold": round(1.0 / alpha, 6),
        "detected": detected,
        "n_tokens": n_total,
        "tokens_processed": processed,
        "stopped_at": stopped_at,
        "green_count": green,
        "green_rate": round(green / processed, 4),
        "delta": delta,
        "alpha": alpha,
        "verdict": "e_value_detected" if detected else "no_e_value",
        "signal": "greenlist" if detected else None,
    }


def e_detect_multi(
    text: str,
    keys: list[dict],
    gamma: float = DEFAULT_GAMMA,
    delta: float = DEFAULT_DELTA,
    alpha: float = 0.05,
    level: str = "word",
    context: int = 1,
    early_stop: bool = False,
) -> dict:
    """Test K keys with Bonferroni correction: E_max >= K/alpha.

    keys: list of dicts with at least {'key_id': str, 'secret': str}; keys
    with a non-kgw family (or no secret) are skipped, mirroring
    detect_multi_key. Each key is scored with the corrected per-key threshold
    K/alpha (in log space: log(K) - log(alpha)); the best key is the one with
    the largest log_e (ties resolved by input order, deterministic).

    Returns: tested_keys, alpha, best (dict, Bonferroni-corrected), detected,
    note, results (per-key dicts).
    """
    results = []
    for k in keys:
        secret = k.get("secret")
        family = k.get("family", "")
        if not secret or (family and family != "kgw"):
            continue
        r = e_detect(text, secret, gamma, delta, alpha, level=level, context=context, early_stop=early_stop)
        r["key_id"] = k.get("key_id", "unknown")
        results.append(r)
    if not results:
        return {
            "tested_keys": 0,
            "alpha": alpha,
            "best": None,
            "detected": False,
            "note": "no_kgw_keys_registered",
            "results": [],
        }
    k_count = len(results)
    log_threshold_bonf = math.log(k_count) - math.log(alpha)
    for r in results:
        r["threshold"] = round(k_count / alpha, 6)
        r["detected"] = r["log_e"] >= log_threshold_bonf
        r["verdict"] = "e_value_detected" if r["detected"] else "no_e_value"
    best = max(results, key=lambda r: r["log_e"])
    return {
        "tested_keys": k_count,
        "alpha": alpha,
        "best": best,
        "detected": best["detected"],
        "note": f"bonferroni_corrected_over_{k_count}_keys",
        "results": results,
    }
