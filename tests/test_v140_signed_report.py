"""Signed forensic findings as a product (C3, 2026-08-13).

Contract under test:
- sign_report/verify_report (HMAC-SHA256 over canonical JSON, signature block
  excluded from the hash; key_id + signature_date; best-effort tamper report).
- CLI report-sign / report-verify / report-keygen with the 0/1/2 exit-code
  contract and --secret-file.
- API POST /api/forensics/report-sign + report-verify: secret resolved
  server-side from the KeyRegistry, never in the request body; auth enforced.
- ML-DSA-44 optional path: skipped when cryptography.mldsa is unavailable.

No data/ writes: the API tests use a tmp-path registry via monkeypatch.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ai_watermark_toolkit.forensics.signed_report import (
    canonical_json,
    generate_mldsa_keypair,
    mldsa_available,
    mldsa_status,
    sign_report,
    verify_report,
)

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"
SECRET = "c3-test-secret-0001"

PAYLOAD = {
    "report_id": "r-2026-08-13-001",
    "verdict": "watermark_detected",
    "z_score": 5.31,
    "green_rate": 0.58,
    "key_label": "demo-kgw-1",
    "findings": [{"char": "\u200b", "codepoint": "200B"}],
}


def run_cli(args, stdin=None, cwd=None):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC)
    base = [sys.executable, "-m", "ai_watermark_toolkit.cli"]
    return subprocess.run(base + args, capture_output=True, text=True,
                          input=stdin, env=env, cwd=cwd or REPO)


# ---------------------------------------------------------------- HMAC core
class TestHmacCore:
    def test_sign_verify_roundtrip(self):
        signed = sign_report(PAYLOAD, SECRET, key_id="demo-kgw-1")
        assert signed["signature"]["algorithm"] == "hmac-sha256"
        assert signed["signature"]["key_id"] == "demo-kgw-1"
        assert signed["signature"]["signature_date"]
        assert len(signed["signature"]["digest"]) == 64  # sha256 hex
        res = verify_report(signed, SECRET)
        assert res["valid"] is True
        assert res["reason"] == "ok"
        assert res["key_id"] == "demo-kgw-1"
        assert res["recomputed_digest"] == signed["signature"]["digest"]

    def test_canonical_json_deterministic_key_order(self):
        a = canonical_json({"b": 1, "a": {"y": 2, "x": 1}})
        b = canonical_json({"a": {"x": 1, "y": 2}, "b": 1})
        assert a == b
        assert '"a":{"x":1,"y":2},"b":1' in a.decode()

    def test_same_payload_same_digest(self):
        s1 = sign_report({"verdict": "x", "n": 1}, SECRET)
        s2 = sign_report({"n": 1, "verdict": "x"}, SECRET)
        assert s1["signature"]["digest"] == s2["signature"]["digest"]

    def test_tamper_payload_invalid_with_field_names(self):
        signed = sign_report(PAYLOAD, SECRET)
        tampered = dict(signed)
        tampered["z_score"] = 99.9
        res = verify_report(tampered, SECRET)
        assert res["valid"] is False
        assert res["reason"] == "payload_tampered"
        assert "z_score" in res["tampered_fields"]

    def test_tamper_added_field_invalid(self):
        signed = sign_report(PAYLOAD, SECRET)
        tampered = dict(signed)
        tampered["injected"] = "attacker"
        res = verify_report(tampered, SECRET)
        assert res["valid"] is False
        assert any("injected" in f for f in res["tampered_fields"])

    def test_wrong_secret_invalid(self):
        signed = sign_report(PAYLOAD, SECRET)
        res = verify_report(signed, "wrong-secret")
        assert res["valid"] is False
        assert res["reason"] == "digest_mismatch"  # fields intact -> key mismatch
        assert res["tampered_fields"] == []

    def test_signature_block_not_hashed(self):
        # the signature covers the payload WITHOUT the signature field:
        # signature METADATA (key_id, extra fields) is not part of the hash,
        # so touching it does not invalidate the document. The digest itself
        # is the comparison target and must stay untouched (replacing it with
        # garbage is correctly detected as digest_mismatch).
        signed = sign_report(PAYLOAD, SECRET)
        forged = json.loads(json.dumps(signed))
        forged["signature"]["key_id"] = "spoofed"
        forged["signature"]["extra"] = "attacker-noise"
        forged["signature"]["note"] = {"nested": [1, 2]}
        res = verify_report(forged, SECRET)
        assert res["valid"] is True
        # digest is the stored comparison value: replacing it invalidates
        broken = json.loads(json.dumps(signed))
        broken["signature"]["digest"] = "0" * 64
        res = verify_report(broken, SECRET)
        assert res["valid"] is False
        assert res["reason"] == "digest_mismatch"

    def test_missing_secret_verify(self):
        signed = sign_report(PAYLOAD, SECRET)
        res = verify_report(signed, None)
        assert res["valid"] is False
        assert res["reason"] == "missing_secret"

    def test_malformed_inputs(self):
        assert verify_report("not-a-dict", SECRET)["reason"] == "malformed"
        assert verify_report({"payload": 1}, SECRET)["reason"] == "missing_signature"
        assert verify_report({"signature": {"algorithm": "nope"}}, SECRET)[
            "reason"] == "unsupported_algorithm"

    def test_sign_requires_dict_and_secret(self):
        with pytest.raises(ValueError):
            sign_report("nope", SECRET)
        with pytest.raises(ValueError):
            sign_report(PAYLOAD, "")
        with pytest.raises(ValueError):
            sign_report(PAYLOAD, SECRET, algorithm="hmac-md5")

    def test_default_key_id(self):
        signed = sign_report(PAYLOAD, SECRET)
        assert signed["signature"]["key_id"] == "default"

    def test_mldsa_feature_probe(self):
        assert isinstance(mldsa_available(), bool)
        status = mldsa_status()
        assert status["available"] == mldsa_available()
        assert status["algorithm"] == "mldsa-44"


# ---------------------------------------------------------------- CLI
class TestCliSignedReport:
    def _payload_file(self, tmp_path):
        f = tmp_path / "payload.json"
        f.write_text(json.dumps(PAYLOAD), encoding="utf-8")
        return f

    def _secret_file(self, tmp_path, secret=SECRET):
        f = tmp_path / "secret.txt"
        f.write_text(secret, encoding="utf-8")
        return f

    def test_cli_sign_verify_roundtrip_secret_file(self, tmp_path):
        payload = self._payload_file(tmp_path)
        secret_f = self._secret_file(tmp_path)
        r = run_cli(["report-sign", str(payload), "--secret-file", str(secret_f),
                     "--key-id", "demo-kgw-1"], cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        out = tmp_path / "report-signed.json"
        assert out.exists()
        signed = json.loads(out.read_text(encoding="utf-8"))
        assert signed["signature"]["algorithm"] == "hmac-sha256"
        r = run_cli(["report-verify", str(out), "--secret-file", str(secret_f)],
                    cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        assert json.loads(r.stdout)["valid"] is True

    def test_cli_sign_from_stdin(self, tmp_path):
        r = run_cli(["report-sign", "-", "--secret", SECRET], stdin=json.dumps(PAYLOAD),
                    cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        assert (tmp_path / "report-signed.json").exists()

    def test_cli_verify_wrong_secret_exit_1(self, tmp_path):
        payload = self._payload_file(tmp_path)
        secret_f = self._secret_file(tmp_path)
        assert run_cli(["report-sign", str(payload), "--secret-file", str(secret_f)],
                       cwd=tmp_path).returncode == 0
        out = tmp_path / "report-signed.json"
        wrong = tmp_path / "wrong.txt"
        wrong.write_text("totally-wrong", encoding="utf-8")
        r = run_cli(["report-verify", str(out), "--secret-file", str(wrong)],
                    cwd=tmp_path)
        assert r.returncode == 1
        assert json.loads(r.stdout)["valid"] is False

    def test_cli_sign_missing_secret_exit_2(self, tmp_path):
        payload = self._payload_file(tmp_path)
        r = run_cli(["report-sign", str(payload)], cwd=tmp_path)
        assert r.returncode == 2
        assert "secret" in r.stderr.lower()

    def test_cli_verify_missing_secret_exit_2(self, tmp_path):
        payload = self._payload_file(tmp_path)
        secret_f = self._secret_file(tmp_path)
        assert run_cli(["report-sign", str(payload), "--secret-file", str(secret_f)],
                       cwd=tmp_path).returncode == 0
        r = run_cli(["report-verify", str(tmp_path / "report-signed.json")], cwd=tmp_path)
        assert r.returncode == 2

    def test_cli_verify_tampered_exit_1(self, tmp_path):
        payload = self._payload_file(tmp_path)
        secret_f = self._secret_file(tmp_path)
        assert run_cli(["report-sign", str(payload), "--secret-file", str(secret_f)],
                       cwd=tmp_path).returncode == 0
        out = tmp_path / "report-signed.json"
        signed = json.loads(out.read_text(encoding="utf-8"))
        signed["green_rate"] = 0.99
        out.write_text(json.dumps(signed), encoding="utf-8")
        r = run_cli(["report-verify", str(out), "--secret-file", str(secret_f)],
                    cwd=tmp_path)
        assert r.returncode == 1
        res = json.loads(r.stdout)
        assert res["valid"] is False
        assert "green_rate" in res["tampered_fields"]

    def test_cli_invalid_json_exit_2(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        r = run_cli(["report-sign", str(bad), "--secret", SECRET], cwd=tmp_path)
        assert r.returncode == 2

    def test_cli_mldsa_unavailable_error_path(self, tmp_path):
        if mldsa_available():
            pytest.skip("mldsa present — error path not exercised")
        r = run_cli(["report-sign", "-", "--algorithm", "mldsa-44", "--secret", SECRET],
                    stdin=json.dumps(PAYLOAD), cwd=tmp_path)
        assert r.returncode == 1
        assert "mldsa-44" in r.stderr.lower()
        r = run_cli(["report-keygen"], cwd=tmp_path)
        assert r.returncode == 1


# ---------------------------------------------------------------- API
class TestApiSignedReport:
    def _client(self, tmp_path, monkeypatch):
        from fastapi.testclient import TestClient

        from ai_watermark_toolkit.api import fastapi_app
        from ai_watermark_toolkit.api.routes import forensics as forensics_route
        from ai_watermark_toolkit.forensics.key_registry import KeyRegistry

        reg = KeyRegistry(str(tmp_path / "keys.json"))
        monkeypatch.setattr(forensics_route, "keys", reg)
        return TestClient(fastapi_app.app)

    def _register_key(self, client, key_id="sig-key-1", secret=SECRET):
        client.post("/api/forensics/keys",
                    json={"key_id": key_id, "family": "kgw", "secret": secret})

    def test_api_sign_verify_roundtrip(self, tmp_path, monkeypatch):
        c = self._client(tmp_path, monkeypatch)
        self._register_key(c)
        r = c.post("/api/forensics/report-sign",
                   json={"payload": PAYLOAD, "key_id": "sig-key-1"})
        assert r.status_code == 200, r.text
        signed = r.json()
        assert signed["signature"]["algorithm"] == "hmac-sha256"
        assert signed["signature"]["key_id"] == "sig-key-1"
        assert "secret" not in json.dumps(signed).replace("shared_secret", "")
        assert SECRET not in json.dumps(signed)  # echtes Secret nie im Report
        r = c.post("/api/forensics/report-verify",
                   json={"signed": signed, "key_id": "sig-key-1"})
        assert r.status_code == 200
        assert r.json()["valid"] is True

    def test_api_verify_key_id_from_document(self, tmp_path, monkeypatch):
        c = self._client(tmp_path, monkeypatch)
        self._register_key(c)
        signed = c.post("/api/forensics/report-sign",
                        json={"payload": PAYLOAD, "key_id": "sig-key-1"}).json()
        r = c.post("/api/forensics/report-verify", json={"signed": signed})
        assert r.status_code == 200
        assert r.json()["valid"] is True

    def test_api_verify_tampered_invalid(self, tmp_path, monkeypatch):
        c = self._client(tmp_path, monkeypatch)
        self._register_key(c)
        signed = c.post("/api/forensics/report-sign",
                        json={"payload": PAYLOAD, "key_id": "sig-key-1"}).json()
        signed["z_score"] = -1.0
        r = c.post("/api/forensics/report-verify",
                   json={"signed": signed, "key_id": "sig-key-1"})
        assert r.status_code == 200
        res = r.json()
        assert res["valid"] is False
        assert "z_score" in res["tampered_fields"]

    def test_api_sign_unknown_key_404(self, tmp_path, monkeypatch):
        c = self._client(tmp_path, monkeypatch)
        r = c.post("/api/forensics/report-sign",
                   json={"payload": PAYLOAD, "key_id": "nope"})
        assert r.status_code == 404

    def test_api_sign_key_without_secret_400(self, tmp_path, monkeypatch):
        c = self._client(tmp_path, monkeypatch)
        c.post("/api/forensics/keys", json={"key_id": "nosecret"})
        r = c.post("/api/forensics/report-sign",
                   json={"payload": PAYLOAD, "key_id": "nosecret"})
        assert r.status_code == 400
        assert "secret" in r.json()["detail"]

    def test_api_sign_mldsa_rejected_400(self, tmp_path, monkeypatch):
        c = self._client(tmp_path, monkeypatch)
        self._register_key(c)
        r = c.post("/api/forensics/report-sign",
                   json={"payload": PAYLOAD, "key_id": "sig-key-1",
                         "algorithm": "mldsa-44"})
        assert r.status_code == 400

    def test_api_requires_auth_when_configured(self, tmp_path, monkeypatch):
        from types import SimpleNamespace

        from ai_watermark_toolkit.api.middleware import auth as auth_mod
        c = self._client(tmp_path, monkeypatch)
        self._register_key(c)  # register while auth is still off
        monkeypatch.setattr(auth_mod, "settings", SimpleNamespace(api_key="test-secret"))
        r = c.post("/api/forensics/report-sign",
                   json={"payload": PAYLOAD, "key_id": "sig-key-1"})
        assert r.status_code == 401
        r = c.post("/api/forensics/report-verify",
                   json={"signed": {"signature": {"key_id": "sig-key-1"}}})
        assert r.status_code == 401
        r = c.post("/api/forensics/report-sign",
                   json={"payload": PAYLOAD, "key_id": "sig-key-1"},
                   headers={"X-API-Key": "test-secret"})
        assert r.status_code == 200


# ---------------------------------------------------------------- ML-DSA-44 (optional)
@pytest.mark.skipif(not mldsa_available(), reason="cryptography mldsa module not installed")
class TestMldsa44:
    def test_keypair_generation(self):
        pair = generate_mldsa_keypair()
        assert "BEGIN PRIVATE KEY" in pair["private_key_pem"]
        assert "BEGIN PUBLIC KEY" in pair["public_key_pem"]
        assert pair["algorithm"] == "mldsa-44"

    def test_sign_verify_roundtrip(self):
        pair = generate_mldsa_keypair()
        signed = sign_report(PAYLOAD, SECRET, algorithm="mldsa-44",
                             private_key_pem=pair["private_key_pem"],
                             key_id="mldsa-key-1")
        sig = signed["signature"]
        assert sig["algorithm"] == "mldsa-44"
        assert sig["signature_b64"]
        assert sig["public_key_pem"] == pair["public_key_pem"]
        # embedded public key suffices
        assert verify_report(signed)["valid"] is True
        # explicit public key also works
        res = verify_report(signed, public_key_pem=pair["public_key_pem"])
        assert res["valid"] is True
        assert res["algorithm"] == "mldsa-44"

    def test_tamper_invalid(self):
        pair = generate_mldsa_keypair()
        signed = sign_report(PAYLOAD, SECRET, algorithm="mldsa-44",
                             private_key_pem=pair["private_key_pem"])
        signed["findings"] = []
        res = verify_report(signed)
        assert res["valid"] is False
        assert res["reason"] == "payload_tampered"
        assert "findings" in res["tampered_fields"]

    def test_wrong_public_key_invalid(self):
        pair = generate_mldsa_keypair()
        other = generate_mldsa_keypair()
        signed = sign_report(PAYLOAD, SECRET, algorithm="mldsa-44",
                             private_key_pem=pair["private_key_pem"])
        res = verify_report(signed, public_key_pem=other["public_key_pem"])
        assert res["valid"] is False
        # P0-2: fremder externer Key wird als Trust-Anker behandelt — die
        # Identität ist nicht verankert (ehrlicher als nur 'signature_invalid').
        assert res["reason"] == "key_not_pinned"

    def test_sign_without_private_key_raises(self):
        with pytest.raises(ValueError):
            sign_report(PAYLOAD, SECRET, algorithm="mldsa-44")

    def test_cli_keygen_sign_verify_roundtrip(self, tmp_path):
        r = run_cli(["report-keygen", "--output-dir", str(tmp_path)], cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        priv = tmp_path / "mldsa_private.pem"
        pub = tmp_path / "mldsa_public.pem"
        assert priv.exists() and pub.exists()
        payload = tmp_path / "payload.json"
        payload.write_text(json.dumps(PAYLOAD), encoding="utf-8")
        r = run_cli(["report-sign", str(payload), "--algorithm", "mldsa-44",
                     "--private-key", str(priv), "--key-id", "mldsa-key-1"], cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        r = run_cli(["report-verify", str(tmp_path / "report-signed.json"),
                     "--public-key", str(pub)], cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        assert json.loads(r.stdout)["valid"] is True
