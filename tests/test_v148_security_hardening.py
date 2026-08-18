"""P0-Security-Härtung (Runde 5): Auth fail-closed, CORS non-dev,
ML-DSA trust/Pinning, report-keygen chmod 0600, Secret-Maskierung.

Deckt die von Hand fertiggestellten P0-Fixes ab (P0-4/P0-5 hatte der
Security-Agent schon mit Tests geliefert).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"

from ai_watermark_toolkit.forensics.signed_report import (
    generate_mldsa_keypair,
    mldsa_status,
    sign_report,
    verify_report,
)


def _find_cli_python():
    """Find the Python executable that can import cryptography."""
    import sys
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
                        capture_output=True, text=True, timeout=10
                    )
                    if result.returncode == 0:
                        return [str(py), "-m", "ai_watermark_toolkit.cli"]
                except Exception:
                    pass
    return [sys.executable, "-m", "ai_watermark_toolkit.cli"]


def _find_cli_python():
    """Find the Python executable that can import cryptography."""
    import sys
    try:
        import cryptography  # noqa: F401
        return [sys.executable, "-m", "ai_watermark_toolkit.cli"]
    except ImportError:
        pass
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
                    capture_output=True, text=True, timeout=10,
                    env={**os.environ, "PYTHONPATH": str(SRC)}
                )
                if result.returncode == 0:
                    return [str(py), "-m", "ai_watermark_toolkit.cli"]
            except Exception:
                pass
    return [sys.executable, "-m", "ai_watermark_toolkit.cli"]


def run_cli(args, cwd=None):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC)
    venv = os.environ.get("VIRTUAL_ENV")
    if venv:
        env["VIRTUAL_ENV"] = venv
        env["PATH"] = str(Path(venv) / "Scripts") + os.pathsep + env.get("PATH", "")
        base = [str(Path(venv) / "Scripts" / "python.exe"), "-m", "ai_watermark_toolkit.cli"]
    else:
        base = [sys.executable, "-m", "ai_watermark_toolkit.cli"]
    return subprocess.run(
        base + list(args),
        capture_output=True, text=True, env=env, cwd=cwd or REPO)


# ------------------------------------------------------------ P0-1: Auth/CORS
class TestAuthFailClosed:
    def _client(self, api_key="", app_env="production"):
        from types import SimpleNamespace

        from fastapi.testclient import TestClient

        import ai_watermark_toolkit.api.fastapi_app as app_mod
        import ai_watermark_toolkit.api.middleware.auth as auth_mod
        import ai_watermark_toolkit.core.config as cfg_mod
        cfg_mod.settings = SimpleNamespace(
            api_key=api_key, app_env=app_env,
            cors_origins="*", app_name="t", log_level="INFO",
            rate_limit_requests=1000, rate_limit_window_sec=60,
            redis_url="redis://localhost:6379/0")
        auth_mod.settings = cfg_mod.settings
        app_mod.settings = cfg_mod.settings
        import importlib
        importlib.reload(app_mod)
        return TestClient(app_mod.app)

    def test_non_dev_without_key_is_fail_closed(self):
        client = self._client(api_key="", app_env="production")
        # /health ist bewusst öffentlich (Docker-HEALTHCHECK), alle
        # forensischen Endpoints sind fail-closed.
        r = client.get("/health")
        assert r.status_code == 200
        for path in ("/api/forensics/detect", "/api/forensics/report-sign",
                     "/api/forensics/finding"):
            r = client.post(path, json={"text": "x"}, headers={})
            assert r.status_code == 401, path

    def test_non_dev_with_key_requires_exact_match(self):
        client = self._client(api_key="secret123", app_env="production")
        r = client.post("/api/forensics/detect", json={"text": "x"},
                        headers={"X-API-Key": "wrong"})
        assert r.status_code == 401
        r = client.post("/api/forensics/detect", json={"text": "x"},
                        headers={"X-API-Key": "secret123"})
        assert r.status_code in (200, 400)  # auth ok; 400 = validierungsfehler

    def test_dev_without_key_is_open(self):
        client = self._client(api_key="", app_env="development")
        r = client.post("/api/forensics/detect", json={"text": "x"}, headers={})
        assert r.status_code in (200, 400)  # auth fail-open nur dev


# ---------------------------------------------------------- P0-2: trust/Pinning
class TestTrustAndPinning:
    @pytest.fixture(scope="class")
    def pair(self):
        if not mldsa_status()["available"]:
            pytest.skip("cryptography>=50 mit mldsa fehlt")
        return generate_mldsa_keypair("mldsa-44")

    def test_sign_records_embedded_key_unverified(self, pair):
        signed = sign_report({"t": "x"}, "s", key_id="k",
                             algorithm="mldsa-44",
                             private_key_pem=pair["private_key_pem"])
        assert signed["signature"]["trust"] == "embedded_key_unverified"

    def test_hmac_sign_records_shared_secret(self):
        signed = sign_report({"t": "x"}, "s", key_id="k")
        assert signed["signature"]["trust"] == "shared_secret"

    def test_verify_without_pinning_is_honest(self, pair):
        signed = sign_report({"t": "x"}, "s", key_id="k",
                             algorithm="mldsa-44",
                             private_key_pem=pair["private_key_pem"])
        v = verify_report(signed, "s")
        assert v["valid"] is True
        assert v["trust"] == "embedded_key_unverified"

    def test_verify_with_correct_pin_succeeds_pinned(self, pair):
        signed = sign_report({"t": "x"}, "s", key_id="k",
                             algorithm="mldsa-44",
                             private_key_pem=pair["private_key_pem"])
        v = verify_report(signed, "s",
                          trusted_public_keys=[pair["public_key_pem"]])
        assert v["valid"] is True
        assert v["trust"] == "pinned_key"

    def test_verify_with_wrong_pin_fails_key_not_pinned(self, pair):
        other = generate_mldsa_keypair("mldsa-44")
        signed = sign_report({"t": "x"}, "s", key_id="k",
                             algorithm="mldsa-44",
                             private_key_pem=pair["private_key_pem"])
        v = verify_report(signed, "s",
                          trusted_public_keys=[other["public_key_pem"]])
        assert v["valid"] is False
        assert v["reason"] == "key_not_pinned"
        assert v["trust"] == "pinned_key"

    @pytest.mark.skipif(not mldsa_status()["available"], reason="cryptography>=50 mit mldsa fehlt")
    def test_cli_public_key_acts_as_pinning(self, tmp_path, pair):
        if not mldsa_status()["available"]:
            pytest.skip("cryptography>=50 mit mldsa fehlt")
        payload = tmp_path / "p.json"
        payload.write_text(json.dumps({"t": "x"}), encoding="utf-8")
        signed = sign_report({"t": "x"}, "s", key_id="k",
                             algorithm="mldsa-44",
                             private_key_pem=pair["private_key_pem"])
        signed_path = tmp_path / "p.signed.json"
        signed_path.write_text(json.dumps(signed), encoding="utf-8")
        pub_path = tmp_path / "pub.pem"
        pub_path.write_text(pair["public_key_pem"], encoding="utf-8")
        r = run_cli(["report-verify", str(signed_path), "--public-key",
                     str(pub_path)])
        assert r.returncode == 0, r.stderr
        assert '"trust": "pinned_key"' in r.stdout


# ------------------------------------------------------------ P0-6: chmod 0600
class TestKeygenPermissions:
    @pytest.mark.skipif(os.name == "nt", reason="POSIX-Permissions")
    def test_private_key_is_0600(self, tmp_path):
        if not mldsa_status()["available"]:
            pytest.skip("cryptography>=50 mit mldsa fehlt")
        out = tmp_path / "keys"
        r = run_cli(["report-keygen", "--algorithm", "mldsa-44",
                     "--output-dir", str(out), "--prefix", "audit"])
        assert r.returncode == 0, r.stderr
        priv = out / "audit_private.pem"
        pub = out / "audit_public.pem"
        assert priv.exists() and pub.exists()
        assert (priv.stat().st_mode & 0o777) == 0o600
        assert (pub.stat().st_mode & 0o777) == 0o644


# -------------------------------------------------- P0-4: Secret-Maskierung (Rest)
class TestSecretMasking:
    def test_mask_secret_key_id_is_deterministic_and_reversible_never(self):
        from ai_watermark_toolkit.forensics.key_registry import is_masked_key_id, mask_secret_key_id
        m1 = mask_secret_key_id("geheim-123")
        m2 = mask_secret_key_id("geheim-123")
        assert m1 == m2
        assert m1.startswith("secret:")
        assert "geheim" not in m1
        assert len(m1) == len("secret:") + 16
        assert is_masked_key_id(m1) is True
        assert is_masked_key_id("demo-kgw-1") is False
