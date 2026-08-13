"""Regression tests: two-sided redlist detection (2026-08-13).

KGW has two mirror-image watermark families:
  - greenlist: generation FAVOURS the hash-derived token set (green rate
    climbs above gamma -> positive z).
  - redlist: generation AVOIDS the hash-derived token set (green rate drops
    below gamma -> negative z).

Hebel A adds two-sided scoring so the SIGN of z is reported explicitly:
z > 0 -> "greenlist" signal, z < 0 -> "redlist" signal, plus the additive
verdicts `redlist_detected` and `weak_redlist_signal`. The redlist generator
below mirrors test_v113's greenlist generator but picks from the COMPLEMENT of
the greenlist, so the green rate collapses to ~0 under the right key and z
goes strongly negative.

Deterministic synthesis, filesystem-safe (tmp_path only, never data/).
"""

import random

from ai_watermark_toolkit.forensics.kgw import (
    DEFAULT_GAMMA,
    detect_kgw,
    green_token,
)

_SIL1 = ("ba be bi bo bu ca ce ci co cu da de di do du fa fe fi fo fu "
         "ga ge gi go gu ka ke ki ko ku la le li lo lu ma me mi mo mu "
         "na ne ni no nu pa pe pi po pu ra re ri ro ru sa se si so su "
         "ta te ti to tu va ve vi vo vu wa we wi wo wu za ze zi zo zu").split()
_SIL2 = ("an en in on un ar er ir or ur al el il ol ul at et it ot ut "
         "as es is os us").split()
VOCAB = [s1 + s2 for s1 in _SIL1 for s2 in _SIL2]

KEY_A = "test-secret-alpha-001"
KEY_B = "test-secret-beta-002"


def generate_redlist(seed_token: str, key: str, n: int = 400,
                     gamma: float = DEFAULT_GAMMA, seed: int = 7) -> str:
    """KGW redlist generator: pick from the COMPLEMENT of the greenlist."""
    rng = random.Random(seed)
    out = [seed_token]
    prev = seed_token
    for _ in range(n):
        red_cands = [c for c in VOCAB if not green_token(c, prev, key, gamma)]
        chosen = rng.choice(red_cands) if red_cands else rng.choice(VOCAB)
        out.append(chosen)
        prev = chosen
    return " ".join(out)


def generate_greenlist(seed_token: str, key: str, n: int = 400,
                       gamma: float = DEFAULT_GAMMA, seed: int = 7) -> str:
    """KGW greenlist generator (mirror of test_v113): greedy green pick."""
    rng = random.Random(seed)
    out = [seed_token]
    prev = seed_token
    for _ in range(n):
        green_cands = [c for c in VOCAB if green_token(c, prev, key, gamma)]
        chosen = rng.choice(green_cands) if green_cands else rng.choice(VOCAB)
        out.append(chosen)
        prev = chosen
    return " ".join(out)


def generate_unmarked(seed_token: str, n: int = 400, seed: int = 1) -> str:
    """Uniform random text: no greenlist or redlist bias at all."""
    rng = random.Random(seed)
    out = [seed_token]
    for _ in range(n):
        out.append(rng.choice(VOCAB))
    return " ".join(out)


class TestRedlistSignal:
    def test_redlist_text_detected_negative_z(self):
        text = generate_redlist("start", KEY_A)
        r = detect_kgw(text, KEY_A)
        assert r["verdict"] == "redlist_detected", r
        assert r["signal"] == "redlist", r
        assert r["z_score"] < -4.0, r
        assert r["green_rate"] < 0.1, r  # redlist collapses the green rate
        # two-sided p-value: |z| > 4 -> p < 0.001
        assert r["p_value"] < 0.001, r

    def test_weak_redlist_signal(self):
        # short redlist text -> z in [-4, -2): weak (sub-threshold) redlist
        text = generate_redlist("start", KEY_A, n=25)
        r = detect_kgw(text, KEY_A)
        assert r["verdict"] == "weak_redlist_signal", r
        assert r["signal"] == "redlist", r
        assert -4.0 <= r["z_score"] < -2.0, r

    def test_greenlist_text_keeps_greenlist_signal(self):
        text = generate_greenlist("start", KEY_A)
        r = detect_kgw(text, KEY_A)
        assert r["verdict"] == "watermark_detected", r
        assert r["signal"] == "greenlist", r
        assert r["z_score"] >= 4.0, r
        assert r["p_value"] < 0.001, r

    def test_unmarked_text_has_no_signal(self, tmp_path):
        text = generate_unmarked("start", seed=1)
        r = detect_kgw(text, KEY_A)
        assert r["verdict"] == "no_signal", r
        assert r["signal"] is None, r
        assert abs(r["z_score"]) < 2.0, r
        # filesystem safety: exercise tmp_path only, never data/
        out = tmp_path / "unmarked.txt"
        out.write_text(text, encoding="utf-8")
        assert out.read_text(encoding="utf-8") == text

    def test_wrong_key_redlist_text_is_no_signal(self):
        text = generate_redlist("start", KEY_A)
        r = detect_kgw(text, KEY_B)
        assert r["verdict"] == "no_signal", r
        assert r["signal"] is None, r
        assert abs(r["z_score"]) < 2.0, r
