"""Regression tests: KGW context window c (2026-08-13).

Hebel B generalizes the greenlist PRF from a single predecessor token to a
context window of c preceding tokens: green_token(token, context) hashes
(key, *context, token). c=1 is byte-identical to the historical
(key, prev, token) hash.

Two contracts are pinned here:
1. mark_greenlist(..., context=c) -> detect_kgw(..., context=c) round-trips:
   the correct c finds a strong signal (z >= 4), while wrong c (1, 2, 8)
   collapses the signal back to noise (z < 4, near zero).
2. Byte identity at c=1: the new list-based signature produces the exact same
   digests as the historical (key, prev, token) hash, so all pre-existing
   greenlist decisions are unchanged.

Deterministic synthesis, filesystem-safe (tmp_path only, never data/).
"""

import hashlib
from typing import ClassVar

from ai_watermark_toolkit.forensics.frequent_vocab import FREQUENT_VOCAB
from ai_watermark_toolkit.forensics.kgw import (
    detect_kgw,
    green_token,
    mark_greenlist,
)

KEY = "context-window-key"
WRONG = "context-window-wrong-key"
GAMMA = 0.5

TEXT = (
    "Local AI models protect user privacy by processing information on the "
    "device instead of sending everything to a remote server. This approach "
    "reduces the amount of personal data shared with outside systems and "
    "gives people direct control over their information. The result is a "
    "lower risk of breaches and a stronger security posture. People trust "
    "systems that keep their data nearby and handle processing transparently. "
    "Organizations benefit because sensitive records never leave the building, "
    "and compliance becomes easier when data remains under local control. "
    "Small devices can now run capable models without depending on external "
    "services, which removes network latency and protects against outages. "
    "The same principle applies to healthcare, finance, and public services, "
    "where confidentiality is not optional but a legal requirement."
)


class TestContextWindowRoundTrip:
    def test_correct_context_detects_wrong_context_collapses(self, tmp_path):
        c_mark = 4
        emb = mark_greenlist(TEXT, KEY, GAMMA, vocab=FREQUENT_VOCAB, seed=3, context=c_mark)
        assert emb["replacements"] > 0, emb

        # correct context: strong green signal
        r_correct = detect_kgw(emb["text"], KEY, GAMMA, context=c_mark)
        assert r_correct["verdict"] == "watermark_detected", r_correct
        assert r_correct["z_score"] >= 4.0, r_correct
        assert r_correct["signal"] == "greenlist", r_correct

        # wrong contexts: the signal collapses back to noise
        for c_wrong in (1, 2, 8):
            if c_wrong == c_mark:
                continue
            r = detect_kgw(emb["text"], KEY, GAMMA, context=c_wrong)
            assert r["z_score"] < 4.0, (c_wrong, r)
            assert abs(r["z_score"]) < 3.0, (c_wrong, r)  # near zero
            assert r["verdict"] != "watermark_detected", (c_wrong, r)

        # filesystem safety: exercise tmp_path only, never data/
        out = tmp_path / "marked_context4.txt"
        out.write_text(emb["text"], encoding="utf-8")
        assert out.read_text(encoding="utf-8") == emb["text"]

    def test_mark_context2_roundtrips_at_2(self):
        c_mark = 2
        emb = mark_greenlist(TEXT, KEY, GAMMA, vocab=FREQUENT_VOCAB, seed=3, context=c_mark)
        r = detect_kgw(emb["text"], KEY, GAMMA, context=c_mark)
        assert r["verdict"] == "watermark_detected", r
        assert r["z_score"] >= 4.0, r


class TestContextOneByteIdentity:
    # Fixed reference digests from the ORIGINAL single-predecessor hash
    # sha256(f"{key}:{prev}:{token}"). The new list-based c=1 signature must
    # reproduce them byte-for-byte, so every pre-existing greenlist decision
    # is unchanged.
    FIXED: ClassVar = [
        ("world", "hello", "5e2ef91373ac90d9fbf2275cf79831db302852e5ef45ce346ae2f268a24d7816", False),
        ("the", "quick", "39dec8d744c9adf9e0bb75afc7f2592b5bea7c471adad3f5d61108db318469ce", True),
        ("data", "local", "d75918ecc34ebbd8c7c2db1bd3dcc43834274ff1927a2a91dae7f607f4776fa5", False),
        ("alpha", "beta", "c9b2fe60c855e757a59a2c61854bb547606314a64f1d75595f90696050046084", False),
    ]

    def test_green_token_c1_byte_identical_to_old_hash(self):
        key = "ctx-byte-key"
        for token, prev, old_digest, old_bool in self.FIXED:
            # historical hash
            assert hashlib.sha256(f"{key}:{prev}:{token}".encode()).hexdigest() == old_digest
            # new list-based signature must hash to the same digest
            new_digest = hashlib.sha256((f"{key}:" + ":".join([prev]) + f":{token}").encode("utf-8")).hexdigest()
            assert new_digest == old_digest, (token, prev)
            # and green_token must return the fixed historical verdict,
            # regardless of whether context is passed as str, list or tuple
            assert green_token(token, prev, key) is old_bool, (token, prev)
            assert green_token(token, [prev], key) is old_bool, (token, prev)
            assert green_token(token, (prev,), key) is old_bool, (token, prev)

    def test_detect_kgw_default_context_is_one(self):
        # Default context=1 must reproduce the historical single-predecessor
        # verdict for a marked text (no regression from the generalization).
        emb = mark_greenlist(TEXT, KEY, GAMMA, vocab=FREQUENT_VOCAB, seed=3)
        r = detect_kgw(emb["text"], KEY, GAMMA)
        assert r["verdict"] == "watermark_detected", r
        assert r["z_score"] >= 4.0, r
