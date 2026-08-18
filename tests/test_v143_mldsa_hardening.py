"""ML-DSA (FIPS 204) hardening for signed forensic findings (D2, 2026-08-13).

Extends the C3 contract (test_v140_signed_report.py) with the pitfalls that
matter when ML-DSA signatures become the audit anchor for findings:

- PEM round-trip stability: the private key is a short random seed; the
  public key is deterministically derived at load time, so save → reload →
  sign → verify must be stable, and the reloaded public key must be
  byte-identical to the stored one.
- Non-determinism: two signatures of the same payload MUST differ, and BOTH
  must verify (FIPS 204 signing is randomized — a deterministic signature
  would indicate a broken RNG path).
- verify-order regression: cryptography's ML-DSA API is
  ``public_key.verify(signature, data)`` — signature FIRST. A swapped call
  must NOT verify; this pins the documented API trap so a future refactor
  cannot silently break it.
- context=b"" pure mode: signing with the default context and with an
  explicit empty context are interchangeable (FIPS 204 pure mode, no
  pre-hash).
- mldsa-65 / mldsa-87 parameter sets: supported by cryptography >= 50
  (verified against 50.0.0); round-trips + measured signature sizes.
- algorithm label vs. actual key type: a document whose signature block
  claims a different parameter set than the embedded key/signature must not
  verify as-is (label trust: the label advertises the security level).

No data/ writes — all key material lives in tmp_path.
"""

import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ai_watermark_toolkit.forensics.signed_report import (
    MLDSA_ALGORITHMS,
    SUPPORTED_ALGORITHMS,
    _mldsa_verify,
    canonical_json,
    generate_mldsa_keypair,
    mldsa_available,
    sign_report,
    verify_report,
)

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"
SECRET = "d2-test-secret-0001"

PAYLOAD = {
    "report_id": "r-2026-08-13-d2-001",
    "verdict": "watermark_detected",
    "z_score": 5.31,
    "green_rate": 0.58,
    "key_label": "demo-kgw-1",
    "findings": [{"char": "\u200b", "codepoint": "200B"}],
}

# Measured on cryptography 50.0.0 (Windows, 2026-08-13): signature bytes
# for the three FIPS 204 parameter sets. Ranges are generous (crypto
# implementations may pad/round); the strict relation 44 < 65 < 87 holds.
SIG_SIZE_RANGES = {
    "mldsa-44": (2300, 2600),
    "mldsa-65": (3100, 3500),
    "mldsa-87": (4400, 4800),
}

ALL_ALGS = tuple(MLDSA_ALGORITHMS)


def _supports(algorithm: str) -> bool:
    """True when cryptography exposes the *PrivateKey class for algorithm."""
    if not mldsa_available():
        return False
    from cryptography.hazmat.primitives.asymmetric import mldsa as _m

    return getattr(_m, MLDSA_ALGORITHMS[algorithm] + "PrivateKey", None) is not None


def _find_cli_python():
    """Find the Python executable that can import cryptography."""

    try:
        import cryptography  # noqa: F401

        return [sys.executable, "-m", "ai_watermark_toolkit.cli"]
    except ImportError:
        pass
    venv = os.environ.get("VIRTUAL_ENV")
    if venv:
        candidates = [
            Path(venv) / "Scripts" / "python.exe",
            Path(venv) / "bin" / "python",
        ]
        for py in candidates:
            if py.exists():
                try:
                    result = subprocess.run(
                        [str(py), "-c", "import cryptography; print(cryptography.__version__)"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if result.returncode == 0:
                        return [str(py), "-m", "ai_watermark_toolkit.cli"]
                except Exception:
                    pass
    return [sys.executable, "-m", "ai_watermark_toolkit.cli"]


def _find_cli_python():
    """Find the Python executable that can import cryptography."""

    try:
        import cryptography  # noqa: F401

        return [sys.executable, "-m", "ai_watermark_toolkit.cli"]
    except ImportError:
        pass
    # Look for project venv (even if VIRTUAL_ENV is not set in this shell)
    candidates = [
        Path(REPO) / ".venv" / "Scripts" / "python.exe",
        Path(REPO) / ".venv" / "bin" / "python",
        Path(REPO) / "venv" / "Scripts" / "python.exe",
        Path(REPO) / "venv" / "bin" / "python",
    ]
    env_venv = os.environ.get("VIRTUAL_ENV")
    if env_venv:
        candidates.insert(0, Path(env_venv) / "Scripts" / "python.exe")
        candidates.insert(1, Path(env_venv) / "bin" / "python")
    for py in candidates:
        if py.exists():
            try:
                result = subprocess.run(
                    [str(py), "-c", "import cryptography; print(cryptography.__version__)"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    env={**os.environ, "PYTHONPATH": str(SRC)},
                )
                if result.returncode == 0:
                    return [str(py), "-m", "ai_watermark_toolkit.cli"]
            except Exception:
                pass
    return [sys.executable, "-m", "ai_watermark_toolkit.cli"]


def run_cli(args, stdin=None, cwd=None):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC)
    venv = os.environ.get("VIRTUAL_ENV")
    if venv:
        env["VIRTUAL_ENV"] = venv
        env["PATH"] = str(Path(venv) / "Scripts") + os.pathsep + env.get("PATH", "")
    base = _find_cli_python()
    return subprocess.run(base + args, capture_output=True, text=True, input=stdin, env=env, cwd=cwd or REPO)


def _sig_bytes(signed: dict) -> int:
    return len(base64.b64decode(signed["signature"]["signature_b64"]))


# ---------------------------------------------------------------- PEM round-trip
@pytest.mark.skipif(not mldsa_available(), reason="cryptography mldsa module not installed")
class TestPemRoundTrip:
    def test_reload_derives_identical_public_key(self):
        pair = generate_mldsa_keypair()
        from cryptography.hazmat.primitives import serialization

        loaded = serialization.load_pem_private_key(pair["private_key_pem"].encode("utf-8"), password=None)
        reloaded_pub = (
            loaded.public_key()
            .public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode("utf-8")
        )
        # The private PEM is a seed; the public key is derived at load time.
        assert reloaded_pub == pair["public_key_pem"]

    def test_sign_with_reloaded_key_verifies_against_stored_public(self):
        from cryptography.hazmat.primitives import serialization

        pair = generate_mldsa_keypair()
        loaded = serialization.load_pem_private_key(pair["private_key_pem"].encode("utf-8"), password=None)
        data = canonical_json(PAYLOAD)
        sig = loaded.sign(data)
        # no exception = valid against the ORIGINAL public key PEM
        serialization.load_pem_public_key(pair["public_key_pem"].encode("utf-8")).verify(sig, data)

    def test_sign_report_with_private_pem_string_verifies(self):
        # sign_report takes the PEM as a string — the same reload path the
        # CLI uses after report-keygen wrote the file.
        pair = generate_mldsa_keypair()
        signed = sign_report(PAYLOAD, SECRET, algorithm="mldsa-44", private_key_pem=pair["private_key_pem"])
        assert verify_report(signed)["valid"] is True

    def test_private_pem_is_seed_sized(self):
        # FIPS 204 private keys are a 32-byte seed: PKCS#8 PEM stays tiny
        # (~130 bytes) while the public key carries the derived material.
        pair = generate_mldsa_keypair()
        assert "BEGIN PRIVATE KEY" in pair["private_key_pem"]
        assert len(pair["private_key_pem"]) < 400
        assert len(pair["public_key_pem"]) > 800  # SPKI holds the derived key

    def test_two_generations_produce_different_keys(self):
        a = generate_mldsa_keypair()
        b = generate_mldsa_keypair()
        assert a["private_key_pem"] != b["private_key_pem"]
        assert a["public_key_pem"] != b["public_key_pem"]


# ---------------------------------------------------------------- non-determinism
@pytest.mark.skipif(not mldsa_available(), reason="cryptography mldsa module not installed")
@pytest.mark.parametrize("algorithm", ALL_ALGS)
class TestNonDeterminism:
    def test_two_signatures_differ_and_both_verify(self, algorithm):
        if not _supports(algorithm):
            pytest.skip(f"{algorithm} not supported by installed cryptography")
        pair = generate_mldsa_keypair(algorithm)
        s1 = sign_report(PAYLOAD, SECRET, algorithm=algorithm, private_key_pem=pair["private_key_pem"])
        s2 = sign_report(PAYLOAD, SECRET, algorithm=algorithm, private_key_pem=pair["private_key_pem"])
        # FIPS 204 signing is randomized: same payload, different signature
        assert s1["signature"]["signature_b64"] != s2["signature"]["signature_b64"]
        # ...and BOTH must verify (same public key, same payload)
        assert verify_report(s1)["valid"] is True
        assert verify_report(s2)["valid"] is True


# ---------------------------------------------------------------- verify-order trap
@pytest.mark.skipif(not mldsa_available(), reason="cryptography mldsa module not installed")
class TestVerifyOrderRegression:
    def test_correct_order_verifies(self):
        pair = generate_mldsa_keypair()
        data = canonical_json(PAYLOAD)
        from cryptography.hazmat.primitives import serialization

        private_key = serialization.load_pem_private_key(pair["private_key_pem"].encode("utf-8"), password=None)
        public_key = serialization.load_pem_public_key(pair["public_key_pem"].encode("utf-8"))
        signature = private_key.sign(data)
        # signature FIRST — no exception expected
        _mldsa_verify(public_key, signature, data)

    def test_swapped_order_rejected(self):
        pair = generate_mldsa_keypair()
        data = canonical_json(PAYLOAD)
        from cryptography.hazmat.primitives import serialization

        private_key = serialization.load_pem_private_key(pair["private_key_pem"].encode("utf-8"), password=None)
        public_key = serialization.load_pem_public_key(pair["public_key_pem"].encode("utf-8"))
        signature = private_key.sign(data)
        # the classic API trap: (data, signature) instead of (signature, data)
        # must NOT verify — otherwise the trap would be harmless and the
        # module's careful ordering would be pointless.
        with pytest.raises((ValueError, TypeError, Exception)):
            _mldsa_verify(public_key, data, signature)
        with pytest.raises((ValueError, TypeError, Exception)):
            public_key.verify(data, signature)


# ---------------------------------------------------------------- context = b""
@pytest.mark.skipif(not mldsa_available(), reason="cryptography mldsa module not installed")
class TestContextPureMode:
    def test_default_context_equals_empty_context(self):
        pair = generate_mldsa_keypair()
        data = canonical_json(PAYLOAD)
        from cryptography.hazmat.primitives import serialization

        private_key = serialization.load_pem_private_key(pair["private_key_pem"].encode("utf-8"), password=None)
        public_key = serialization.load_pem_public_key(pair["public_key_pem"].encode("utf-8"))
        # default (context=None) and explicit pure mode (context=b"") are
        # interchangeable — FIPS 204 pure mode, no pre-hash
        sig_default = private_key.sign(data)
        sig_explicit = private_key.sign(data, context=b"")
        public_key.verify(sig_default, data, context=b"")  # default == b""
        public_key.verify(sig_explicit, data)  # b"" == default
        assert sig_default != sig_explicit  # still non-deterministic

    def test_signed_report_uses_pure_mode(self):
        # sign_report does not expose a context parameter; the round-trip
        # through verify_report proves the pure-mode default works end to end.
        pair = generate_mldsa_keypair()
        signed = sign_report(PAYLOAD, SECRET, algorithm="mldsa-44", private_key_pem=pair["private_key_pem"])
        assert verify_report(signed)["valid"] is True


# ---------------------------------------------------------------- mldsa-65 / mldsa-87
@pytest.mark.skipif(not mldsa_available(), reason="cryptography mldsa module not installed")
@pytest.mark.parametrize("algorithm", ("mldsa-65", "mldsa-87"))
class TestMldsa65_87:
    def test_keygen_sign_verify_roundtrip(self, algorithm):
        if not _supports(algorithm):
            pytest.skip(f"{algorithm} not supported by installed cryptography")
        pair = generate_mldsa_keypair(algorithm)
        assert pair["algorithm"] == algorithm
        signed = sign_report(
            PAYLOAD,
            SECRET,
            algorithm=algorithm,
            private_key_pem=pair["private_key_pem"],
            key_id="mldsa-" + algorithm[-2:],
        )
        assert signed["signature"]["algorithm"] == algorithm
        res = verify_report(signed)
        assert res["valid"] is True
        assert res["algorithm"] == algorithm
        # embedded public key == generated public key
        assert signed["signature"]["public_key_pem"] == pair["public_key_pem"]

    def test_signature_size_measured(self, algorithm):
        if not _supports(algorithm):
            pytest.skip(f"{algorithm} not supported by installed cryptography")
        pair = generate_mldsa_keypair(algorithm)
        signed = sign_report(PAYLOAD, SECRET, algorithm=algorithm, private_key_pem=pair["private_key_pem"])
        size = _sig_bytes(signed)
        lo, hi = SIG_SIZE_RANGES[algorithm]
        assert lo <= size <= hi

    def test_tamper_invalid(self, algorithm):
        if not _supports(algorithm):
            pytest.skip(f"{algorithm} not supported by installed cryptography")
        pair = generate_mldsa_keypair(algorithm)
        signed = sign_report(PAYLOAD, SECRET, algorithm=algorithm, private_key_pem=pair["private_key_pem"])
        signed["z_score"] = -7.0
        res = verify_report(signed)
        assert res["valid"] is False
        assert "z_score" in res["tampered_fields"]

    def test_wrong_public_key_invalid(self, algorithm):
        if not _supports(algorithm):
            pytest.skip(f"{algorithm} not supported by installed cryptography")
        pair = generate_mldsa_keypair(algorithm)
        other = generate_mldsa_keypair(algorithm)
        signed = sign_report(PAYLOAD, SECRET, algorithm=algorithm, private_key_pem=pair["private_key_pem"])
        res = verify_report(signed, public_key_pem=other["public_key_pem"])
        assert res["valid"] is False
        # P0-2: fremder externer Key = Trust-Anker, Identität nicht verankert
        assert res["reason"] == "key_not_pinned"


# ---------------------------------------------------------------- label trust
@pytest.mark.skipif(not mldsa_available(), reason="cryptography mldsa module not installed")
class TestAlgorithmLabelTrust:
    def test_sizes_are_strictly_ordered(self):
        sizes = {}
        for algorithm in ALL_ALGS:
            if not _supports(algorithm):
                pytest.skip(f"{algorithm} not supported by installed cryptography")
            pair = generate_mldsa_keypair(algorithm)
            signed = sign_report(PAYLOAD, SECRET, algorithm=algorithm, private_key_pem=pair["private_key_pem"])
            sizes[algorithm] = _sig_bytes(signed)
        assert sizes["mldsa-44"] < sizes["mldsa-65"] < sizes["mldsa-87"]

    def test_label_mismatch_does_not_verify(self):
        # A document whose signature block CLAIMS mldsa-87 but carries a
        # mldsa-44 key + signature must not pass as-is: the label advertises
        # the security level, so label and actual key type have to agree.
        pair44 = generate_mldsa_keypair("mldsa-44")
        signed = sign_report(PAYLOAD, SECRET, algorithm="mldsa-44", private_key_pem=pair44["private_key_pem"])
        relabeled = json.loads(json.dumps(signed))
        relabeled["signature"]["algorithm"] = "mldsa-87"
        res = verify_report(relabeled)
        assert res["valid"] is False
        assert res["reason"] == "algorithm_mismatch"


# ---------------------------------------------------------------- API surface
class TestAlgorithmSurface:
    def test_supported_algorithms_cover_all_parameter_sets(self):
        for algorithm in ALL_ALGS:
            assert algorithm in SUPPORTED_ALGORITHMS
        assert SUPPORTED_ALGORITHMS[0] == "hmac-sha256"

    @pytest.mark.skipif(not mldsa_available(), reason="cryptography mldsa module not installed")
    def test_keypair_invalid_parameter_set_raises(self):
        with pytest.raises(ValueError):
            generate_mldsa_keypair("mldsa-128")


# ---------------------------------------------------------------- CLI mldsa-65
@pytest.mark.skipif(not _supports("mldsa-65"), reason="cryptography < 50: no mldsa-65")
class TestCliMldsa65:
    @pytest.mark.skipif(not mldsa_available(), reason="cryptography mldsa module not installed")
    def test_cli_keygen_sign_verify_roundtrip(self, tmp_path):
        r = run_cli(["report-keygen", "--algorithm", "mldsa-65", "--output-dir", str(tmp_path)], cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        priv = tmp_path / "mldsa_private.pem"
        pub = tmp_path / "mldsa_public.pem"
        assert priv.exists() and pub.exists()
        payload = tmp_path / "payload.json"
        payload.write_text(json.dumps(PAYLOAD), encoding="utf-8")
        r = run_cli(
            [
                "report-sign",
                str(payload),
                "--algorithm",
                "mldsa-65",
                "--private-key",
                str(priv),
                "--key-id",
                "mldsa65-1",
            ],
            cwd=tmp_path,
        )
        assert r.returncode == 0, r.stderr
        signed = json.loads((tmp_path / "report-signed.json").read_text(encoding="utf-8"))
        assert signed["signature"]["algorithm"] == "mldsa-65"
        r = run_cli(["report-verify", str(tmp_path / "report-signed.json"), "--public-key", str(pub)], cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        assert json.loads(r.stdout)["valid"] is True
