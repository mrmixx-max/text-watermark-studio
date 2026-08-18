"""D1 "E-Prozess-Detektion": e-process (anytime-valid likelihood-ratio)
detection tests (v1.4.1, 2026-08-13).

Literature: 2602.17608 (e-values for statistical watermarking),
2607.21958. The e-process multiplies per-token likelihood ratios
e_t = p1(x_t)/p0(x_t) over the SAME green_token PRF and the SAME scored
token stream that detect_kgw uses; E_n >= 1/alpha is an anytime-valid
(Ville's inequality) rejection that permits early stopping and needs no
minimum sample size.

All numbers below are DETERMINISTIC (fixed VOCAB, fixed generators, fixed
seeds). Empirically verified seed documentation:

  strong signal    generate_watermarked("start", KEY_A, 200, seed=7)
                   -> z=24.49 (watermark_detected), log_e=56.81
  sample efficiency (the core D1 claim: z<4 but e detected)
                   generate_partial("start", KEY_A, 60, green_prob=0.45, seed=12)
                   -> z=3.578 (< 4, weak_signal), log_e=3.842 > log(20)=2.996
                   Robust, not a single lucky seed: 38 of seeds 0..79 at
                   green_prob=0.45 (and 22 of 80 at 0.5) satisfy z<4 AND
                   e detected; verified additional seeds: (0.45,5) z=3.876
                   log_e=4.242, (0.5,0) z=3.28 log_e=3.442, (0.5,14)
                   z=3.876 log_e=4.242.
  Bonferroni bite  same generator, seed=5: single-key log_e=4.242 sits
                   between log(3/0.05)=4.094 and log(3/0.001)=8.006 ->
                   detected at alpha=0.05 with K=3, NOT at alpha=0.001.
  unmarked control rng(123), 400 random vocab words -> log_e=-13.07
  wrong key        watermarked with KEY_A, tested with KEY_B -> log_e=-11.59
"""

import json
import math
import random
import subprocess
import sys
from pathlib import Path
from typing import ClassVar

from ai_watermark_toolkit.forensics.e_value import (
    e_detect,
    e_detect_multi,
    e_process,
)
from ai_watermark_toolkit.forensics.kgw import (
    DEFAULT_GAMMA,
    detect_kgw,
    green_token,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

KEY_A = "test-secret-alpha-001"
KEY_B = "test-secret-beta-002"
KEY_C = "test-secret-gamma-003"

# Syllable-built vocabulary (same construction as test_v113_kgw_detector):
# enough DISTINCT (prev, token) pairs that green rates stay well-behaved.
_SIL1 = ["ba", "be", "bi", "bo", "bu", "ca", "ce", "ci", "co", "cu", "da", "de", "di", "do", "du", "fa", "fe", "fi", "fo", "fu", "ga", "ge", "gi", "go", "gu", "ka", "ke", "ki", "ko", "ku", "la", "le", "li", "lo", "lu", "ma", "me", "mi", "mo", "mu", "na", "ne", "ni", "no", "nu", "pa", "pe", "pi", "po", "pu", "ra", "re", "ri", "ro", "ru", "sa", "se", "si", "so", "su", "ta", "te", "ti", "to", "tu", "va", "ve", "vi", "vo", "vu", "wa", "we", "wi", "wo", "wu", "za", "ze", "zi", "zo", "zu"]
_SIL2 = ["an", "en", "in", "on", "un", "ar", "er", "ir", "or", "ur", "al", "el", "il", "ol", "ul", "at", "et", "it", "ot", "ut", "as", "es", "is", "os", "us"]
VOCAB = [s1 + s2 for s1 in _SIL1 for s2 in _SIL2]

_POOL_CACHE = {}


def _pools(key: str, prev: str) -> tuple[list[str], list[str]]:
    """Cached (green, red) candidate lists for (key, prev)."""
    ck = (key, prev)
    if ck not in _POOL_CACHE:
        g = [c for c in VOCAB if green_token(c, prev, key, DEFAULT_GAMMA)]
        r = [c for c in VOCAB if not green_token(c, prev, key, DEFAULT_GAMMA)]
        _POOL_CACHE[ck] = (g, r)
    return _POOL_CACHE[ck]


def generate_watermarked(seed_token: str, key: str, n: int, seed: int = 7) -> str:
    """KGW generator: a green token at every position (~100% green rate)."""
    rng = random.Random(seed)
    out = [seed_token]
    prev = seed_token
    for _ in range(n):
        green_cands, _ = _pools(key, prev)
        chosen = rng.choice(green_cands) if green_cands else rng.choice(VOCAB)
        out.append(chosen)
        prev = chosen
    return " ".join(out)


def generate_partial(seed_token: str, key: str, n: int,
                     green_prob: float, seed: int) -> str:
    """KGW generator with a controlled green probability (weak signal)."""
    rng = random.Random(seed)
    out = [seed_token]
    prev = seed_token
    for _ in range(n):
        green_cands, red_cands = _pools(key, prev)
        pool = green_cands if rng.random() < green_prob else red_cands
        chosen = rng.choice(pool) if pool else rng.choice(VOCAB)
        out.append(chosen)
        prev = chosen
    return " ".join(out)


KEYS_3 = [
    {"key_id": "a", "family": "kgw", "secret": KEY_A},
    {"key_id": "b", "family": "kgw", "secret": KEY_B},
    {"key_id": "c", "family": "kgw", "secret": KEY_C},
]

ALPHA = 0.05
LOG_THRESHOLD_1K = math.log(1.0 / ALPHA)  # log(20)


class TestEDeterminism:
    def test_marked_text_is_e_detected(self):
        text = generate_watermarked("start", KEY_A, 200)  # seed=7
        r = e_detect(text, KEY_A, alpha=ALPHA)
        assert r["detected"] is True, r
        assert r["verdict"] == "e_value_detected", r
        assert r["log_e"] > LOG_THRESHOLD_1K
        assert r["e_value"] > 1.0 / ALPHA
        assert r["n_tokens"] == 200
        assert r["green_rate"] > 0.9  # greedy generator is ~100% green

    def test_unmarked_text_not_detected(self):
        rng = random.Random(123)
        text = " ".join(rng.choice(VOCAB) for _ in range(400))
        r = e_detect(text, KEY_A, alpha=ALPHA)
        assert r["detected"] is False, r
        assert r["verdict"] == "no_e_value", r
        assert r["e_value"] < 1.0 / ALPHA
        # Z-score agrees (no_signal)
        assert detect_kgw(text, KEY_A)["z_score"] < 2.0

    def test_wrong_key_not_detected(self):
        text = generate_watermarked("start", KEY_A, 300)
        r = e_detect(text, KEY_B, alpha=ALPHA)
        assert r["detected"] is False, r
        assert r["log_e"] < 0.0

    def test_parity_strong_signal_z_and_e_agree(self):
        """Strong signal: the Z-score AND the e-process both detect."""
        text = generate_watermarked("start", KEY_A, 200)
        z = detect_kgw(text, KEY_A)
        e = e_detect(text, KEY_A)
        assert z["verdict"] == "watermark_detected", z
        assert z["z_score"] >= 4.0
        assert e["detected"] is True and e["verdict"] == "e_value_detected", e

    def test_too_short_single_token(self):
        r = e_detect("hello", KEY_A)
        assert r["verdict"] == "too_short"
        assert r["n_tokens"] == 0
        assert r["detected"] is False

    def test_short_text_no_minimum_sample_size(self):
        """Anytime-valid: no n<10 gate (unlike detect_kgw); still valid."""
        r = e_detect("one two three", KEY_A)
        assert r["n_tokens"] == 2
        assert r["verdict"] == "no_e_value"


class TestSampleEfficiency:
    """The core D1 claim: short marked text where z<4 but E detects."""

    # (green_prob, seed) pairs, all empirically verified (see module doc).
    CASES: ClassVar = [(0.45, 12), (0.45, 5), (0.5, 0), (0.5, 14)]

    def test_short_marked_text_z_below_4_e_detected(self):
        for green_prob, seed in self.CASES:
            text = generate_partial("start", KEY_A, 60, green_prob, seed)
            z = detect_kgw(text, KEY_A)
            e = e_detect(text, KEY_A)
            assert z["z_score"] < 4.0, f"seed={seed}: {z}"
            assert z["verdict"] != "watermark_detected", f"seed={seed}: {z}"
            assert e["detected"] is True, f"seed={seed}: {e}"
            assert e["verdict"] == "e_value_detected", f"seed={seed}: {e}"
            assert e["log_e"] > LOG_THRESHOLD_1K, f"seed={seed}: {e}"


class TestBonferroni:
    def test_multi_key_finds_correct_key(self):
        text = generate_watermarked("start", KEY_B, 200)
        r = e_detect_multi(text, KEYS_3, alpha=ALPHA)
        assert r["tested_keys"] == 3
        assert r["best"]["key_id"] == "b", r
        assert r["detected"] is True, r
        assert r["best"]["verdict"] == "e_value_detected", r
        assert "bonferroni_corrected_over_3_keys" in r["note"]
        # per-key threshold is K/alpha
        assert r["best"]["threshold"] == 3.0 / ALPHA

    def test_bonferroni_small_alpha_not_detected(self):
        """Weak signal, K=3: E_max=4.242 sits between log(3/0.05) and
        log(3/0.001), so alpha=0.05 detects but alpha=0.001 does not."""
        text = generate_partial("start", KEY_A, 60, 0.45, seed=5)
        # sanity: single-key e detection at alpha=0.05, z below 4
        assert e_detect(text, KEY_A, alpha=ALPHA)["detected"] is True
        assert detect_kgw(text, KEY_A)["z_score"] < 4.0
        m05 = e_detect_multi(text, KEYS_3, alpha=0.05)
        m001 = e_detect_multi(text, KEYS_3, alpha=0.001)
        assert m05["detected"] is True, m05
        assert m05["best"]["key_id"] == "a", m05
        assert m001["detected"] is False, m001
        # tight threshold (Bonferroni) is the reason, not the text
        assert m05["best"]["log_e"] > math.log(3.0 / 0.05)
        assert m001["best"]["log_e"] < math.log(3.0 / 0.001)

    def test_multi_key_no_keys_registered(self):
        r = e_detect_multi("any text here", [{"key_id": "x", "family": "greenlist_bias"}])
        assert r["tested_keys"] == 0
        assert "no_kgw_keys_registered" in r["note"]
        assert r["best"] is None


class TestNumerics:
    def test_long_text_no_overflow(self):
        text = generate_watermarked("start", KEY_A, 2000)
        r = e_detect(text, KEY_A)
        assert r["detected"] is True, r
        assert math.isfinite(r["log_e"]) and r["log_e"] > 100.0
        assert math.isfinite(r["e_value"]) and r["e_value"] > 1.0 / ALPHA
        assert math.isfinite(e_process(text, KEY_A))  # no OverflowError

    def test_very_long_text_e_value_capped_not_crashing(self):
        """log_e beyond float64 range: verdict still exact, e_value capped
        at the largest finite float instead of raising OverflowError."""
        text = generate_watermarked("start", KEY_A, 5000)
        r = e_detect(text, KEY_A)
        assert r["log_e"] > 700.0  # beyond exp() range
        assert r["detected"] is True, r
        assert math.isfinite(r["e_value"])
        assert r["e_value"] >= 1e300  # saturated near float max

    def test_e_process_matches_e_detect(self):
        text = generate_watermarked("start", KEY_A, 200)
        assert math.isclose(e_process(text, KEY_A),
                            e_detect(text, KEY_A)["e_value"], rel_tol=1e-9)


class TestEarlyStop:
    def test_early_stop_stops_early(self):
        text = generate_watermarked("start", KEY_A, 200)
        r = e_detect(text, KEY_A, early_stop=True)
        assert r["detected"] is True, r
        assert r["stopped_at"] is not None
        assert r["stopped_at"] < r["n_tokens"], r  # 11 of 200 empirically
        assert r["tokens_processed"] == r["stopped_at"]
        full = e_detect(text, KEY_A, early_stop=False)
        assert full["tokens_processed"] == full["n_tokens"] == 200
        assert full["stopped_at"] is None

    def test_early_stop_anytime_valid_consistency(self):
        """Ville: a stopping-time detection implies the full-run detection
        (log_e is monotone, the martingale never decreases in log space)."""
        for green_prob, seed in [(0.45, 12), (0.45, 5)]:
            text = generate_partial("start", KEY_A, 60, green_prob, seed)
            stopped = e_detect(text, KEY_A, early_stop=True)
            full = e_detect(text, KEY_A, early_stop=False)
            assert stopped["detected"] == full["detected"]
            if stopped["detected"]:
                assert full["log_e"] >= stopped["log_e"]


class TestTokenizationConsistency:
    def test_word_level_matches_detect_kgw(self):
        text = generate_watermarked("Start", KEY_A, 120)
        e = e_detect(text, KEY_A, level="word")
        z = detect_kgw(text, KEY_A, level="word")
        assert e["n_tokens"] == z["n_tokens"]
        assert e["green_count"] == z["green_count"]

    def test_context_window_matches_detect_kgw(self):
        text = generate_watermarked("start", KEY_A, 150)
        for context in (2, 3):
            e = e_detect(text, KEY_A, context=context)
            z = detect_kgw(text, KEY_A, context=context)
            assert e["n_tokens"] == z["n_tokens"]
            assert e["green_count"] == z["green_count"]

    def test_bpe_level_matches_detect_kgw(self):
        text = generate_watermarked("start", KEY_A, 100)
        e = e_detect(text, KEY_A, level="bpe")
        z = detect_kgw(text, KEY_A, level="bpe")
        assert e["n_tokens"] == z["n_tokens"]
        assert e["green_count"] == z["green_count"]

    def test_prose_text_matches_detect_kgw(self):
        text = ("Hello, world! It's a test-case for the e-process. "
                "Several analysts reviewed the data and compared it with "
                "earlier results; nothing was watermarked here.") * 4
        e = e_detect(text, KEY_A)
        z = detect_kgw(text, KEY_A)
        assert e["n_tokens"] == z["n_tokens"]
        assert e["green_count"] == z["green_count"]
        assert e["n_tokens"] > 10  # not too_short on either path


class TestCliEFlag:
    def _run(self, args, text):
        cmd = [sys.executable, "-m", "ai_watermark_toolkit.cli", "detect", *args]
        return subprocess.run(cmd, input=text, capture_output=True, text=True,
                              cwd=str(REPO_ROOT), timeout=180)

    def test_cli_e_value_detected_exit1(self):
        text = generate_watermarked("start", KEY_A, 200)
        proc = self._run(["--stdin", "--key", KEY_A, "--e-value"], text)
        assert proc.returncode == 1, proc.stderr
        out = json.loads(proc.stdout)
        assert out["z_score"] >= 4.0  # Z path unchanged
        assert "e_value" in out, out.keys()
        assert out["e_value"]["detected"] is True
        assert out["e_value"]["verdict"] == "e_value_detected"
        assert out["e_value"]["log_e"] > math.log(20.0)

    def test_cli_e_value_unmarked_exit0(self):
        rng = random.Random(123)
        text = " ".join(rng.choice(VOCAB) for _ in range(200))
        proc = self._run(["--stdin", "--key", KEY_A, "--e-value"], text)
        assert proc.returncode == 0, proc.stdout
        out = json.loads(proc.stdout)
        assert out["e_value"]["detected"] is False
        assert out["e_value"]["verdict"] == "no_e_value"

    def test_cli_without_flag_has_no_e_value_key(self):
        text = generate_watermarked("start", KEY_A, 100)
        proc = self._run(["--stdin", "--key", KEY_A], text)
        assert proc.returncode == 1
        out = json.loads(proc.stdout)
        assert "e_value" not in out  # flag stays opt-in

    def test_cli_e_value_requires_key(self):
        proc = self._run(["--stdin", "--e-value"], "plain text here")
        assert proc.returncode == 2
        assert "requires --key" in (proc.stderr or "")
