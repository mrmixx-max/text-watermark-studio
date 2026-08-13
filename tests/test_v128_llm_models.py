"""Tests for multi-model support in the local LLM backend (2026-08-13).

Contract: the studio can list, install (pull) and switch between ANY model a
local Ollama instance knows — not just EuroLLM. A mock Ollama HTTP server
backed by http.server keeps these tests offline and deterministic.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from ai_watermark_toolkit.llm.service import LocalLLMService

# mock Ollama state
KNOWN_MODELS = [{"name": "eurollm-9b:latest", "size": 9_000_000_000},
                {"name": "llama3.2:3b", "size": 3_200_000_000}]


class MockOllamaHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/tags":
            self._json(200, {"models": KNOWN_MODELS})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/api/pull":
            name = body.get("name", "")
            if name == "nope:99b":
                self._json(200, b'{"error":"model not found"}')
                return
            # stream NDJSON: status line first, then the pull stream
            # (no Content-Length, no chunked framing -> client reads to EOF)
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            self._ndjson(b'{"status":"pulling manifest"}')
            self._ndjson(b'{"status":"downloading","completed":50,"total":100}')
            self._ndjson(b'{"status":"success"}')
            KNOWN_MODELS.append({"name": name, "size": 5_000_000_000})
        else:
            self._json(404, {"error": "not found"})

    def _json(self, code, payload):
        data = payload if isinstance(payload, bytes) else \
            json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _ndjson(self, payload):
        self.wfile.write(payload + b"\n")

    def log_message(self, *args):  # silence
        pass


@pytest.fixture(scope="module")
def mock_ollama():
    server = HTTPServer(("127.0.0.1", 0), MockOllamaHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.fixture()
def svc(tmp_path, mock_ollama, monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", mock_ollama)
    cfg = tmp_path / "local_llm.json"
    cfg.write_text(json.dumps({
        "provider": "llama.cpp-openai-compatible",
        "model_family": "mradermacher/EuroLLM-9B-Instruct-2512-GGUF",
        "model_variant": "eurollm-9b",
        "server_base_url": "http://127.0.0.1:8080/v1",
        "installed": False, "updated_at": None,
    }), encoding="utf-8")
    return LocalLLMService(path=cfg)


class TestList:
    def test_lists_all_known_models(self, svc):
        models = svc.list_models()
        names = {m["name"] for m in models}
        assert "eurollm-9b:latest" in names
        assert "llama3.2:3b" in names

    def test_model_installed_accepts_latest_suffix(self, svc):
        assert svc.model_installed("eurollm-9b") is True
        assert svc.model_installed("eurollm-9b:latest") is True
        assert svc.model_installed("qwen99") is False


class TestInstall:
    def test_install_pulls_and_selects_any_model(self, svc):
        statuses = []
        result = svc.install_model("llama3.2:3b", progress=statuses.append)
        assert result["installed"] is True
        assert svc.load()["model_variant"] == "llama3.2:3b"
        assert any("downloading" in s for s in statuses)

    def test_install_fails_on_unknown_model(self, svc):
        with pytest.raises(RuntimeError, match="model not found"):
            svc.install_model("nope:99b")

    def test_install_unreachable_raises(self, svc, monkeypatch):
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:9")
        with pytest.raises(RuntimeError, match="unreachable"):
            svc.install_model("llama3.2:3b")


class TestUse:
    def test_use_switches_to_installed_model(self, svc):
        cfg = svc.use_model("llama3.2:3b")
        assert cfg["model_variant"] == "llama3.2:3b"
        assert cfg["installed"] is True

    def test_use_rejects_unknown_model(self, svc):
        with pytest.raises(ValueError, match="model_not_installed"):
            svc.use_model("does-not-exist")
