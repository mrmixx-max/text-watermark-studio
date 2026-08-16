"""Regression tests for the 2026-08-13 agent audit findings.

B1: MCP manifest routes must match the real API (no dead interfaces).
B2: GET /keys must never leak the secret field.
B3: POST /keys requires the API key when one is configured.
B4: CORS must not combine wildcard origins with credentials.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest
from fastapi.testclient import TestClient

from ai_watermark_toolkit.api import fastapi_app
from ai_watermark_toolkit.api.routes import forensics as forensics_route
from ai_watermark_toolkit.core.config import settings
from ai_watermark_toolkit.forensics.key_registry import KeyRegistry

REPO = Path(__file__).resolve().parents[1]


def _client_with_registry(tmp_path, monkeypatch):
    """TestClient whose forensics routes use a tmp registry.

    Auth defaults to fail-open via the shared conftest autouse fixture
    (empty-key dev convention). Tests that exercise auth patch
    auth_mod.settings themselves AFTER this helper and win.
    """
    reg = KeyRegistry(str(tmp_path / "keys.json"))
    monkeypatch.setattr(forensics_route, "keys", reg)
    return TestClient(fastapi_app.app)


def _resolve_routes(app_or_router):
    """Flatten (method, path) pairs from a FastAPI app or router.

    fastapi >=0.137 wraps included routers as _IncludedRouter objects; the
    real router lives on their ``original_router`` attribute. Older versions
    expose routes flat. This resolves all representations.
    """
    result = set()
    for r in app_or_router.routes:
        if hasattr(r, "methods") and hasattr(r, "path"):
            for m in r.methods:
                result.add((m, r.path))
        orig = getattr(r, "original_router", None)
        if orig is not None and hasattr(orig, "routes"):
            result |= _resolve_routes(orig)
            continue
        nested = getattr(r, "router", None)
        if nested is not None and hasattr(nested, "routes"):
            result |= _resolve_routes(nested)
        elif hasattr(r, "routes"):
            result |= _resolve_routes(r)
    return result


class TestMCPManifestConsistency:
    def test_every_tool_path_exists_in_api(self):
        manifest = json.loads((REPO / "mcp" / "tools.json").read_text(encoding="utf-8"))
        app = fastapi_app.app
        real = _resolve_routes(app)
        # optional tools (e.g. ops_*) depend on plugins not present in a bare
        # install or CI; only non-optional tools must always resolve
        missing = [t["name"] for t in manifest["tools"]
                   if not t.get("optional")
                   and (t["method"], t["path"]) not in real]
        assert missing == []

    def test_manifest_still_has_usable_tool_count(self):
        manifest = json.loads((REPO / "mcp" / "tools.json").read_text(encoding="utf-8"))
        assert len(manifest["tools"]) >= 40  # was 56 before dead tools were removed


class TestKeySecretProtection:
    def test_get_keys_strips_secret(self, tmp_path, monkeypatch):
        c = _client_with_registry(tmp_path, monkeypatch)
        c.post("/api/forensics/keys",
               json={"key_id": "k1", "secret": "SUPER-SECRET-42"})
        body = c.get("/api/forensics/keys").json()
        assert "SUPER-SECRET-42" not in json.dumps(body)
        assert body["keys"][0]["key_id"] == "k1"

    def test_post_key_requires_api_key_when_configured(self, tmp_path, monkeypatch):
        # patch the settings OBJECT the auth middleware sees (frozen settings
        # cannot be mutated) and verify the API rejects unauthenticated writes
        from types import SimpleNamespace
        from ai_watermark_toolkit.api import middleware
        from ai_watermark_toolkit.api.middleware import auth as auth_mod

        monkeypatch.setattr(auth_mod, "settings", SimpleNamespace(api_key="test-secret"))
        c = _client_with_registry(tmp_path, monkeypatch)
        r = c.post("/api/forensics/keys", json={"key_id": "k2", "secret": "x"})
        assert r.status_code == 401
        r = c.post("/api/forensics/keys",
                   json={"key_id": "k2", "secret": "x"},
                   headers={"X-API-Key": "test-secret"})
        assert r.status_code == 200

    def test_get_keys_stays_open_but_safe(self, tmp_path, monkeypatch):
        # listing key names/metadata without secrets is fine without auth
        c = _client_with_registry(tmp_path, monkeypatch)
        assert c.get("/api/forensics/keys").status_code == 200


class TestCORS:
    def test_no_credentials_with_wildcard_origins(self):
        c = TestClient(fastapi_app.app)
        r = c.get("/health", headers={"Origin": "https://evil.example"})
        assert r.headers.get("access-control-allow-credentials") != "true"
