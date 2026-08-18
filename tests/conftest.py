"""Shared pytest fixtures for the TWS test suite.

Environment independence (2026-08-16):
- The repo ships a .env with AI_WM_API_KEY set (fail-closed API). Many API
  test suites were written for the documented dev convention (empty key ->
  fail-open in development) and would otherwise 401 on every request.
- This autouse fixture patches the auth middleware's settings object to the
  empty-key dev default for EVERY test. Tests that explicitly exercise auth
  (e.g. TestApiDeltaZ.test_api_requires_auth,
  TestKeySecretProtection.test_post_key_requires_api_key_when_configured)
  patch auth_mod.settings themselves AFTER this fixture, so their
  test-secret wins (monkeypatch applies later patches over earlier ones).
"""

from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def _fail_open_dev_auth(monkeypatch):
    """Default all API requests to fail-open (dev) regardless of .env.

    The API is fail-closed outside development when AI_WM_API_KEY is set in
    the environment (see api/middleware/auth.py). A local .env with a real
    key would break every API test that expects the documented dev behavior.
    Patch the settings object the middleware reads — frozen dataclass, so
    patch the module attribute, not the instance.
    """
    from ai_watermark_toolkit.api.middleware import auth as auth_mod

    monkeypatch.setattr(
        auth_mod,
        "settings",
        SimpleNamespace(api_key="", app_env="development"),
    )


@pytest.fixture(autouse=True)
def _ensure_demo_kgw_key(monkeypatch):
    """Ensure the demo-kgw-1 key exists in the registry with a secret.

    Many API/CLI tests reference 'demo-kgw-1' as a valid KGW key with a
    secret. Some tests (v147/v149) rely on this key being present at
    runtime. The registry file is gitignored and may be missing after
    a fresh checkout or after another test cleaned it up."""
    import json as _json
    from pathlib import Path as _Path

    reg_path = _Path("data/key_registry.json")
    try:
        data = _json.loads(reg_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        data = {"keys": []}

    keys = data.get("keys", [])
    has_kgw_secret = any(k.get("key_id") == "demo-kgw-1" and k.get("secret") for k in keys)
    if not has_kgw_secret:
        keys.append(
            {
                "key_id": "demo-kgw-1",
                "family": "kgw",
                "status": "active",
                "owner": "local",
                "secret": "demo-kgw-secret-0001",
                "gamma": 0.5,
            }
        )
        data["keys"] = keys
        reg_path.write_text(
            _json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
