"""Real KGW-style statistical watermark detection.

Implements the Kirchenbauer et al. greenlist scheme in a text-only setting:
for each token, a pseudorandom hash over (key, previous_token, token)
decides whether the token belongs to the greenlist. A watermarked text
shows a green-ratio significantly above the expected gamma; a normal text
does not. Multi-key: test every registered KGW key, report per-key Z-scores
with a Bonferroni-style note.

Honest limits (documented, not hidden):
- This detects texts generated WITH this exact scheme and key. It is not
  a universal detector for unknown sampling schemes (e.g. whatever a
  vendor ships) — key and hash scheme must match.
- Word-level tokens approximate model tokenizers. Real BPE tokenizers
  shift the statistics slightly; the Z-test still separates cleanly when
  n is large enough.
"""

from __future__ import annotations

import hashlib
import math
import re

# Default greenlist fraction (KGW gamma). Keep in sync with the generator.
DEFAULT_GAMMA = 0.25

_TOKEN_RE = re.compile(r"[A-Za-z0-9\u00C0-\u024F]+(?:['-][A-Za-z0-9\u00C0-\u024F]+)*")


def tokenize(text: str) -> list[str]:
    """Word-level tokenization approximating a model tokenizer.

    Lowercased, because most KGW-style deployments greenlist on the
    tokenizer surface form, and mixed case doubles the effective vocab.
    """
    return [m.group(0).lower() for m in _TOKEN_RE.finditer(text)]


def _unit_interval(h: str) -> float:
    """Map a hex digest to [0, 1)."""
    return int(h[:8], 16) / 0xFFFFFFFF


def green_token(token: str, prev_token: str, key: str, gamma: float = DEFAULT_GAMMA) -> bool:
    """KGW greenlist membership: PRF(key, prev, token) < gamma."""
    digest = hashlib.sha256(f"{key}:{prev_token}:{token}".encode("utf-8")).hexdigest()
    return _unit_interval(digest) < gamma


def detect_kgw(text: str, key: str, gamma: float = DEFAULT_GAMMA) -> dict:
    """Z-score test for one key. Returns None-ish fields if text too short."""
    tokens = tokenize(text)
    n = len(tokens) - 1  # number of scored tokens (each scored against its predecessor)
    if n < 10:
        return {
            "z_score": None, "p_value": None, "green_count": 0,
            "n_tokens": n, "green_rate": None, "verdict": "too_short",
        }
    green = sum(
        1 for i in range(1, len(tokens))
        if green_token(tokens[i], tokens[i - 1], key, gamma)
    )
    mu = gamma * n
    sigma = math.sqrt(n * gamma * (1 - gamma))
    z = (green - mu) / sigma
    p_value = 0.5 * math.erfc(z / math.sqrt(2))  # one-sided upper tail
    rate = green / n
    if z >= 4.0:
        verdict = "watermark_detected"
    elif z >= 2.0:
        verdict = "weak_signal"
    else:
        verdict = "no_signal"
    return {
        "z_score": round(z, 4), "p_value": round(p_value, 10),
        "green_count": green, "n_tokens": n, "green_rate": round(rate, 4),
        "verdict": verdict,
    }


def detect_multi_key(text: str, keys: list[dict], gamma: float = DEFAULT_GAMMA) -> dict:
    """Test all KGW-family keys. Best Z-score wins; report all.

    keys: list of dicts with at least {'key_id': str, 'secret': str}.
    Only keys with family 'kgw' (or carrying a 'secret') are tested.
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
    best = max(results, key=lambda r: r["z_score"] if r["z_score"] is not None else -1)
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
