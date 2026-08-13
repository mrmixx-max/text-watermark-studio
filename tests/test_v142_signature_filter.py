"""D3 "Signature Filtering" (v1.4.2, 2026-08-13) — FPR control via
signature-token pre-filtering (arXiv 2606.18430v2, Hong/Chen/Yu 2026).

Problem class: when ONE token type dominates a text (e.g. 85% of the
tokens), that type's greenlist color alone can flip the whole Z-test —
an UNMARKED text then fires a false alarm (or a marked one is masked).
The paper calls these "signature tokens" and removes them BEFORE the
green/red count. The paper's 78-99% TPR gains need a MILP-learned
signature set; our implementation is honestly scoped: a frequency
heuristic (share >= min_share AND |z_contribution| >= 3) for FPR CONTROL
only — no TPR promise (see signature_filter's docstring).

All numbers below are DETERMINISTIC (fixed VOCAB, fixed generators, fixed
seeds). Empirically verified seed documentation:

  FPR proof (THE core claim), dominant token "baban" 85/100, KEY_A:
      without filter: 29 of 30 seeds (0..29) give |z| >= 4.0
                     (paper-class high FPR; (baban,baban) hashes RED for
                     KEY_A -> redlist_detected, seed 0: z=-4.8161)
      with    filter: 0 of 30 seeds give |z| >= 4.0
      seed 0 healed : z=-4.8161 (redlist_detected) -> z=+0.1491
                     (no_signal); removed baban count=84 share=0.8485
                     z_contribution=-5.2915; n_before=99 n_after=15
  parity anchor    : generate_watermarked("start", KEY_A) -> z=34.641
                     (byte-identical to pre-v142), result keys unchanged
                     (no signature_filtered key when filter is off)
  marked prose     : mark_greenlist(prose, KEY_A, seed=42) -> 156
                     replacements, z=24.3597 watermark_detected with AND
                     without filter (nothing removed, n_after=241)
  blocks           : baban*40 + boban*30 + cocun*30 + 19 fillers -> all
                     three hash RED, |z_contribution| in {3.6056, 3.1623};
                     max_filter=2 removes [baban, boban] (n_removed=69);
                     min_share=0.35 removes nothing (baban share 0.3305)
  small stats      : ["alpha","beta","alpha","gamma","alpha"] (context=1)
                     -> n=4, total_green=0, alpha count=2 share=0.5,
                     z_contribution=-0.8165, beta/gamma count=1
                     share=0.25 z_contribution=-0.5774
"""

import json
import random
import subprocess
import sys
from pathlib import Path

from ai_watermark_toolkit.forensics.kgw import (
    DEFAULT_GAMMA,
    detect_kgw,
    detect_multi_key,
    green_token,
    mark_greenlist,
    signature_filter,
    signature_token_stats,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

KEY_A = "test-secret-alpha-001"
KEY_B = "test-secret-beta-002"

# Syllable-built vocabulary (same construction as test_v113_kgw_detector):
# enough DISTINCT (prev, token) pairs that green rates stay well-behaved.
_SIL1 = ("ba be bi bo bu ca ce ci co cu da de di do du fa fe fi fo fu "
         "ga ge gi go gu ka ke ki ko ku la le li lo lu ma me mi mo mu "
         "na ne ni no nu pa pe pi po pu ra re ri ro ru sa se si so su "
         "ta te ti to tu va ve vi vo vu wa we wi wo wu za ze zi zo zu").split()
_SIL2 = ("an en in on un ar er ir or ur al el il ol ul at et it ot ut "
         "as es is os us").split()
VOCAB = [s1 + s2 for s1 in _SIL1 for s2 in _SIL2]

# "baban" dominates the FPR texts; (baban, baban) hashes RED for KEY_A.
DOMINANT = "baban"


def generate_watermarked(seed_token: str, key: str, n: int = 400,
                         gamma: float = DEFAULT_GAMMA, seed: int = 7) -> str:
    """KGW generator (test_v113): random token from the greenlist at every
    position -> ~100% green rate -> huge positive Z-score."""
    rng = random.Random(seed)
    out = [seed_token]
    prev = seed_token
    for _ in range(n):
        green_cands = [c for c in VOCAB if green_token(c, prev, key, gamma)]
        chosen = rng.choice(green_cands) if green_cands else rng.choice(VOCAB)
        out.append(chosen)
        prev = chosen
    return " ".join(out)


def dominated_text(seed: int, d_count: int = 85, n_total: int = 100) -> str:
    """UNMARKED text where one token type dominates (d_count of n_total).

    Fillers are random VOCAB words seeded by `seed`; the dominant block is
    `d_count` repetitions of DOMINANT. No watermarking anywhere in it.
    """
    rng = random.Random(seed)
    fillers = [rng.choice(VOCAB) for _ in range(n_total - d_count)]
    return " ".join([DOMINANT] * d_count + fillers)


def blocks_text() -> str:
    """Three red-hashing dominant blocks + fillers (see module docstring)."""
    rng = random.Random(3)
    fillers = [rng.choice(VOCAB) for _ in range(19)]
    return " ".join([DOMINANT] * 40 + ["boban"] * 30 + ["cocun"] * 30 + fillers)


def marked_prose() -> str:
    """Deterministically greenlist-marked prose (seed=42, see docstring)."""
    prose = (
        "This report is an important review of our work. "
        "We need to find a better way to show the results. "
        "The team can make a good case and help people understand the change. "
        "It is a big problem with a small fix, a new idea that gives real value. "
        "We can take the time to build the right approach and reduce the risk. "
        "Leaders say we must improve how we use the data, start early and stop guessing. "
    ) * 3
    return mark_greenlist(prose, KEY_A, seed=42)["text"]


class TestSignatureTokenStats:
    def test_stats_known_small_text(self):
        """Hand-verifiable stats for a tiny known stream (context=1)."""
        tokens = ["alpha", "beta", "alpha", "gamma", "alpha"]
        st = signature_token_stats(tokens, 1, KEY_A)
        assert st["n_tokens"] == 4
        assert st["total_green"] == 0  # all four pairs hash red for KEY_A
        by_token = {t["token"]: t for t in st["types"]}
        assert by_token["alpha"]["count"] == 2
        assert by_token["alpha"]["share"] == 0.5
        assert by_token["alpha"]["green_count"] == 0
        assert by_token["alpha"]["green_rate"] == 0.0
        assert by_token["alpha"]["z_contribution"] == -0.8165
        for tok in ("beta", "gamma"):
            assert by_token[tok]["count"] == 1
            assert by_token[tok]["share"] == 0.25
            assert by_token[tok]["z_contribution"] == -0.5774
        # sorted by count descending (deterministic order)
        counts = [t["count"] for t in st["types"]]
        assert counts == sorted(counts, reverse=True)

    def test_stats_consistent_with_detect_kgw(self):
        """Per-type counts/green sum to exactly what detect_kgw scores."""
        tokens = ["alpha", "beta", "alpha", "gamma", "alpha", "beta", "delta"]
        text = " ".join(tokens)
        st = signature_token_stats(tokens, 1, KEY_A)
        det = detect_kgw(text, KEY_A)
        assert st["n_tokens"] == det["n_tokens"] == 6
        assert st["total_green"] == det["green_count"]
        assert sum(t["count"] for t in st["types"]) == st["n_tokens"]
        # share sums to 1.0 over the scored stream
        assert abs(sum(t["share"] for t in st["types"]) - 1.0) < 1e-9
        # green_rate == green_count / count
        for t in st["types"]:
            assert t["green_rate"] == round(t["green_count"] / t["count"], 4)

    def test_stats_short_stream_no_crash(self):
        st = signature_token_stats(["only"], 1, KEY_A)
        assert st["n_tokens"] == 0
        assert st["types"] == []

    def test_stats_matches_manual_green_token(self):
        """z_contribution matches the direct per-type Z formula."""
        tokens = ["alpha", "beta", "alpha", "gamma", "alpha"]
        ctx_pairs = [(tokens[i], tokens[max(0, i - 1):i]) for i in range(1, len(tokens))]
        green_a = sum(1 for tok, ctx in ctx_pairs if tok == "alpha" and green_token(tok, ctx, KEY_A))
        count_a = sum(1 for tok, _ in ctx_pairs if tok == "alpha")
        expected = (green_a - count_a * DEFAULT_GAMMA) / (
            (count_a * DEFAULT_GAMMA * (1 - DEFAULT_GAMMA)) ** 0.5)
        st = signature_token_stats(tokens, 1, KEY_A)
        by_token = {t["token"]: t for t in st["types"]}
        assert abs(by_token["alpha"]["z_contribution"] - round(expected, 4)) < 1e-9


class TestSignatureFilterLimits:
    def test_max_filter_caps_removed_types(self):
        toks = blocks_text().split()
        f2 = signature_filter(toks, 1, KEY_A, max_filter=2)
        removed = [t["token"] for t in f2["removed"]]
        assert removed == [DOMINANT, "boban"], removed  # top |z| first (stable tie)
        assert f2["n_removed"] == 69
        assert f2["n_after"] == 49
        assert f2["n_before"] == 118
        assert "cocun" not in removed  # third candidate exceeds the cap
        f1 = signature_filter(toks, 1, KEY_A, max_filter=1)
        assert [t["token"] for t in f1["removed"]] == [DOMINANT]
        f0 = signature_filter(toks, 1, KEY_A, max_filter=0)
        assert f0["removed"] == [] and f0["n_removed"] == 0

    def test_min_share_threshold_respected(self):
        toks = blocks_text().split()
        # baban share 0.3305: >= 0.25 (removed by default), < 0.35 (kept)
        removed_default = signature_filter(toks, 1, KEY_A)
        assert [t["token"] for t in removed_default["removed"]] == [DOMINANT, "boban", "cocun"]
        strict = signature_filter(toks, 1, KEY_A, min_share=0.35)
        assert strict["removed"] == []
        assert strict["n_removed"] == 0 and strict["n_after"] == strict["n_before"]

    def test_filtered_tokens_drop_only_removed_types(self):
        toks = blocks_text().split()
        f = signature_filter(toks, 1, KEY_A, max_filter=1)
        assert f["filtered_tokens"] == [t for t in toks if t != DOMINANT]


class TestDetectKgwSignatureFilter:
    def test_fpr_control_dominant_token_heals(self):
        """THE core proof: unmarked dominant-token text alarms WITHOUT the
        filter and is healed WITH it (documented seed 0, see docstring)."""
        text = dominated_text(seed=0)
        off = detect_kgw(text, KEY_A)
        assert off["verdict"] == "redlist_detected", off  # false alarm
        assert off["z_score"] == -4.8161, off
        on = detect_kgw(text, KEY_A, signature_filter=True)
        assert on["verdict"] == "no_signal", on  # healed
        assert on["z_score"] == 0.1491, on
        assert on["n_tokens"] == 15
        sf = on["signature_filtered"]
        assert sf["n_before"] == 99 and sf["n_after"] == 15 and sf["n_removed"] == 84
        assert sf["removed"] == [{
            "token": DOMINANT, "count": 84, "share": 0.8485,
            "z_contribution": -5.2915,
        }], sf["removed"]

    def test_fpr_control_seed_loop(self):
        """Paper-style FPR class: ~all seeds alarm without the filter, none
        with it. 29/30 vs 0/30 empirically (seeds 0..29, documented)."""
        alarms_off = 0
        for seed in range(30):
            text = dominated_text(seed=seed)
            off = detect_kgw(text, KEY_A)
            on = detect_kgw(text, KEY_A, signature_filter=True)
            if abs(off["z_score"]) >= 4.0:
                alarms_off += 1
            assert abs(on["z_score"]) < 4.0, (seed, on)  # healed everywhere
            assert on["signature_filtered"]["n_after"] == 15
        assert alarms_off >= 25, alarms_off  # the high-FPR class exists

    def test_normal_marked_text_detected_both_ways(self):
        """A genuinely marked text stays detected with AND without filter
        (filter removes nothing relevant: removed == [])."""
        text = marked_prose()
        off = detect_kgw(text, KEY_A)
        on = detect_kgw(text, KEY_A, signature_filter=True)
        assert off["verdict"] == on["verdict"] == "watermark_detected"
        assert off["z_score"] == on["z_score"] == 24.3597, (off, on)
        assert on["signature_filtered"]["removed"] == []
        assert on["signature_filtered"]["n_after"] == on["signature_filtered"]["n_before"] == 241

    def test_filtered_too_short_is_honest(self):
        """Filtering can shrink the stream below the n>=10 gate: report
        too_short on the FILTERED count instead of a phantom Z."""
        rng = random.Random(5)
        fillers = [rng.choice(VOCAB) for _ in range(5)]
        text = " ".join([DOMINANT] * 85 + fillers)  # n_before=89, n_after=5
        on = detect_kgw(text, KEY_A, signature_filter=True)
        assert on["verdict"] == "too_short"
        assert on["z_score"] is None
        assert on["n_tokens"] == 5
        assert on["signature_filtered"]["n_after"] == 5
        assert on["signature_filtered"]["n_before"] == 89

    def test_bpe_level_filter_parity(self):
        """BPE boundary scoring: distinct words -> nothing removed, identical
        Z with and without the filter."""
        text = " ".join(VOCAB[:40])
        off = detect_kgw(text, KEY_A, level="bpe")
        on = detect_kgw(text, KEY_A, level="bpe", signature_filter=True)
        assert off["z_score"] == on["z_score"] == 0.8321, (off, on)
        assert on["signature_filtered"]["removed"] == []


class TestParity:
    def test_default_result_unchanged(self):
        """signature_filter=False is byte-identical to the pre-v142 shape:
        exact Z anchor (34.641, measured before the change) and no new key."""
        text = generate_watermarked("start", KEY_A)
        r = detect_kgw(text, KEY_A)
        assert r["z_score"] == 34.641, r
        assert r["verdict"] == "watermark_detected"
        assert r["green_rate"] == 1.0
        assert set(r.keys()) == {
            "z_score", "p_value", "green_count", "n_tokens",
            "green_rate", "verdict", "signal",
        }, r.keys()  # no signature_filtered when the flag is off

    def test_default_prose_parity(self):
        """Plain prose stays quiet; Z anchor 0.0199 from the v113 class."""
        text = (
            "The report summarizes current findings across several domains. "
            "Analysts reviewed the data and compared it with earlier results. "
            "Nothing in this document was produced with a watermarking scheme."
        ) * 30
        r = detect_kgw(text, KEY_A)
        assert r["z_score"] == 0.0199, r
        assert r["verdict"] == "no_signal"
        assert "signature_filtered" not in r

    def test_multi_key_forwards_flag_opt_in(self):
        """detect_multi_key forwards the flag; default keeps parity."""
        text = marked_prose()
        keys = [{"key_id": "a", "family": "kgw", "secret": KEY_A}]
        off = detect_multi_key(text, keys)
        assert "signature_filtered" not in off["best"]
        on = detect_multi_key(text, keys, signature_filter=True)
        assert on["best"]["signature_filtered"]["removed"] == []
        assert on["best"]["z_score"] == off["best"]["z_score"] == 24.3597

    def test_too_short_default_has_no_new_key(self):
        r = detect_kgw("one two three", KEY_A)
        assert r["verdict"] == "too_short"
        assert "signature_filtered" not in r
        rs = detect_kgw("one two three", KEY_A, signature_filter=True)
        assert rs["verdict"] == "too_short"
        assert rs["signature_filtered"] == {
            "removed": [], "n_removed": 0, "n_after": 2, "n_before": 2,
        }


class TestCliSignatureFilter:
    def _run(self, args, text):
        cmd = [sys.executable, "-m", "ai_watermark_toolkit.cli", "detect"] + args
        return subprocess.run(cmd, input=text, capture_output=True, text=True,
                              cwd=str(REPO_ROOT), timeout=180)

    def test_cli_flag_is_opt_in(self):
        """Without --signature-filter the output has no such field."""
        proc = self._run(["--stdin", "--key", KEY_A], marked_prose())
        assert proc.returncode == 1, proc.stderr  # detected
        out = json.loads(proc.stdout)
        assert out["z_score"] >= 4.0
        assert "signature_filtered" not in out  # flag stays opt-in

    def test_cli_flag_marked_text_detected(self):
        proc = self._run(["--stdin", "--key", KEY_A, "--signature-filter"], marked_prose())
        assert proc.returncode == 1, proc.stderr
        out = json.loads(proc.stdout)
        assert out["z_score"] == 24.3597
        assert out["signature_filtered"]["removed"] == []
        assert out["signature_filtered"]["n_after"] == 241

    def test_cli_flag_heals_fpr_alarm(self):
        """CLI proof of the failure class: exit 1 (false alarm) without the
        flag, exit 0 (healed) with it; dominant token documented in output."""
        text = dominated_text(seed=0)
        off = self._run(["--stdin", "--key", KEY_A], text)
        assert off.returncode == 1, off.stdout  # FPR alarm
        out_off = json.loads(off.stdout)
        assert out_off["verdict"] == "redlist_detected"
        assert out_off["z_score"] == -4.8161
        assert "signature_filtered" not in out_off
        on = self._run(["--stdin", "--key", KEY_A, "--signature-filter"], text)
        assert on.returncode == 0, on.stdout  # healed
        out_on = json.loads(on.stdout)
        assert abs(out_on["z_score"]) < 4.0
        assert out_on["verdict"] == "no_signal"
        assert out_on["signature_filtered"]["removed"][0]["token"] == DOMINANT
        assert out_on["signature_filtered"]["n_after"] == 15

    def test_cli_flag_requires_key(self):
        proc = self._run(["--stdin", "--signature-filter"], "plain text here")
        assert proc.returncode == 2
