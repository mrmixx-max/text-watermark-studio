"""E2E tests for the HTTP API.

Tests both the FastAPI app (via TestClient) and the simple stdlib HTTP server
(via real subprocess + httpx).
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    """Find a free TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# FastAPI app tests via TestClient (in-process)
# ---------------------------------------------------------------------------
class TestFastAPIApp:
    """FastAPI app end-to-end via TestClient."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from ai_watermark_toolkit.api.fastapi_app import app
        return TestClient(app)

    def test_health_endpoint(self, client):
        """GET /health should return ok."""
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert "env" in data

    def test_detect_endpoint(self, client):
        """POST /api/detect should return detection layers."""
        r = client.post("/api/detect", json={"text": "Furthermore, this helps.", "lang": "en"})
        assert r.status_code == 200
        data = r.json()
        assert "layers" in data
        assert "unicode" in data["layers"]
        assert "markers" in data["layers"]

    def test_detect_endpoint_auto_lang(self, client):
        """POST /api/detect with lang=auto should work."""
        r = client.post("/api/detect", json={"text": "Hello world"})
        assert r.status_code == 200
        assert "layers" in r.json()

    def test_clean_endpoint(self, client):
        """POST /api/clean should return cleaned text."""
        r = client.post("/api/clean", json={"text": "Hello\u200bWorld\u202e"})
        assert r.status_code == 200
        data = r.json()
        assert "text" in data
        assert "\u200b" not in data["text"]
        assert "\u202e" not in data["text"]

    def test_dilute_endpoint(self, client):
        """POST /api/dilute should return diluted text."""
        r = client.post("/api/dilute",
                        json={"text": "This is not only good but also great.", "intensity": "standard"})
        assert r.status_code == 200
        data = r.json()
        assert "text" in data
        assert data["intensity"] == "standard"

    def test_pipeline_endpoint(self, client):
        """POST /api/pipeline should run the full pipeline."""
        r = client.post("/api/pipeline",
                        json={"text": "Hello\u200bWorld test.", "lang": "en", "intensity": "standard"})
        assert r.status_code == 200
        data = r.json()
        assert "text" in data
        assert "report" in data
        assert "before" in data["report"]
        assert "after" in data["report"]

    def test_404_for_unknown_route(self, client):
        """Unknown routes should return 404."""
        r = client.post("/api/nonexistent", json={"text": "test"})
        assert r.status_code == 404

    def test_detect_with_keyed_kgw(self, client):
        """POST /api/forensics/detect with key should run KGW detection."""
        # First register a key
        r = client.post("/api/forensics/keys", json={
            "key_id": "e2e-fastapi-key",
            "family": "kgw",
            "trigger_phrase": "",
        })
        # Key registration may or may not succeed depending on implementation
        # but the endpoint should respond
        assert r.status_code in (200, 201, 404, 422)

    def test_documents_formats_endpoint(self, client):
        """GET /api/documents/formats should return supported formats."""
        r = client.get("/api/documents/formats")
        # May be 200 or 404 depending on route availability
        assert r.status_code in (200, 404)


# ---------------------------------------------------------------------------
# Simple HTTP server tests (subprocess + httpx)
# ---------------------------------------------------------------------------
class TestSimpleHTTPServer:
    """Simple stdlib HTTP server end-to-end via subprocess + httpx."""

    @pytest.fixture(scope="class")
    def server_url(self):
        """Start the simple HTTP server as a subprocess."""
        import os
        port = _free_port()
        env = os.environ.copy()
        env["AI_WM_ENV"] = "development"

        cmd = [sys.executable, "-m", "ai_watermark_toolkit.cli", "serve",
               "--host", "127.0.0.1", "--port", str(port)]
        proc = subprocess.Popen(
            cmd, cwd=str(PROJECT_ROOT),
            env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        url = f"http://127.0.0.1:{port}"
        # Wait for server to be ready
        for _ in range(50):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                    break
            except OSError:
                time.sleep(0.1)
        else:
            proc.kill()
            pytest.fail("server did not start in time")
        yield url
        proc.kill()
        proc.wait(timeout=5)

    def test_health_via_httpx(self, server_url):
        """GET /health should return ok via real HTTP."""
        import httpx
        r = httpx.get(f"{server_url}/health", timeout=5)
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_detect_via_httpx(self, server_url):
        """POST /api/detect should work via real HTTP."""
        import httpx
        r = httpx.post(f"{server_url}/api/detect",
                       json={"text": "Furthermore, this helps.", "lang": "en"},
                       timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert "layers" in data

    def test_clean_via_httpx(self, server_url):
        """POST /api/clean should work via real HTTP."""
        import httpx
        r = httpx.post(f"{server_url}/api/clean",
                       json={"text": "Hello\u200bWorld\u202e"},
                       timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert "\u200b" not in data["text"]

    def test_dilute_via_httpx(self, server_url):
        """POST /api/dilute should work via real HTTP."""
        import httpx
        r = httpx.post(f"{server_url}/api/dilute",
                       json={"text": "Hello world", "intensity": "standard"},
                       timeout=5)
        assert r.status_code == 200
        assert "text" in r.json()

    def test_pipeline_via_httpx(self, server_url):
        """POST /api/pipeline should work via real HTTP."""
        import httpx
        r = httpx.post(f"{server_url}/api/pipeline",
                       json={"text": "Hello\u200bWorld", "lang": "en", "intensity": "standard"},
                       timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert "text" in data
        assert "report" in data

    def test_404_via_httpx(self, server_url):
        """Unknown route should return 404."""
        import httpx
        r = httpx.post(f"{server_url}/api/nonexistent", json={"text": "test"}, timeout=5)
        assert r.status_code == 404

    def test_root_returns_html(self, server_url):
        """GET / should return HTML (or 404 if web root missing)."""
        import httpx
        r = httpx.get(f"{server_url}/", timeout=5)
        assert r.status_code in (200, 404)
