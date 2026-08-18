"""Tests for the multi-model LLM router with fallback, health checks, and load balancing.

Uses a mock Ollama HTTP server (http.server-based) to stay offline and
deterministic.  Mirrors the pattern from test_v128_llm_models.py.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from ai_watermark_toolkit.llm.router import (
    ModelHealth,
    ModelRouter,
    RouterExhaustedError,
    RouterStats,
)
from ai_watermark_toolkit.llm.service import LocalLLMService

# ---- mock Ollama server ------------------------------------------------

KNOWN_MODELS = [
    {"name": "llama3.2:3b", "size": 3_200_000_000},
    {"name": "qwen2.5:7b", "size": 7_500_000_000},
    {"name": "phi3:mini", "size": 2_300_000_000},
]

# Models that should fail health checks (simulating OOM / not loaded).
UNHEALTHY_MODELS: set[str] = set()

# Models that should fail at request time (simulating inference failure).
FAILING_MODELS: set[str] = set()


class MockOllamaHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/tags":
            self._json(200, {"models": KNOWN_MODELS})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/api/show":
            name = body.get("name", "")
            if name in UNHEALTHY_MODELS:
                self._json(404, {"error": "model not found"})
            else:
                self._json(200, {"modelfile": "# mock", "details": {"family": "llama"}})
        elif self.path == "/v1/chat/completions":
            name = body.get("model", "")
            if name in FAILING_MODELS:
                self._json(500, {"error": "out of memory"})
            else:
                self._json(200, {
                    "id": "chatcmpl-mock",
                    "object": "chat.completion",
                    "model": name,
                    "choices": [{"message": {"role": "assistant", "content": f"response from {name}"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
                })
        elif self.path == "/api/pull":
            name = body.get("name", "")
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            self.wfile.write(b'{"status":"pulling manifest"}\n')
            self.wfile.write(b'{"status":"success"}\n')
        else:
            self._json(404, {"error": "not found"})

    def _json(self, code, payload):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

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


@pytest.fixture(autouse=True)
def _reset_ollama_state():
    UNHEALTHY_MODELS.clear()
    FAILING_MODELS.clear()
    yield
    UNHEALTHY_MODELS.clear()
    FAILING_MODELS.clear()


@pytest.fixture()
def svc(tmp_path, mock_ollama, monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", mock_ollama)
    cfg = tmp_path / "local_llm.json"
    cfg.write_text(json.dumps({
        "provider": "ollama",
        "model_family": "llama3.2:3b",
        "model_variant": "llama3.2:3b",
        "server_base_url": f"{mock_ollama}/v1",
        "installed": True,
        "updated_at": None,
    }), encoding="utf-8")
    return LocalLLMService(path=cfg)


@pytest.fixture()
def router(svc):
    return ModelRouter(
        service=svc,
        models=["llama3.2:3b", "qwen2.5:7b", "phi3:mini"],
        health_check_timeout=5,
        health_cache_ttl_seconds=10,
    )


# ---- ModelHealth dataclass ---------------------------------------------

class TestModelHealth:
    def test_to_dict_roundtrip(self):
        h = ModelHealth(model_name="llama3.2:3b", is_healthy=True,
                        last_checked="2026-01-01T00:00:00+00:00",
                        response_time_ms=12.3, consecutive_failures=0)
        d = h.to_dict()
        assert d["model"] == "llama3.2:3b"
        assert d["healthy"] is True
        assert d["response_time_ms"] == 12.3

    def test_default_values(self):
        h = ModelHealth(model_name="x")
        assert h.is_healthy is False
        assert h.last_checked is None
        assert h.consecutive_failures == 0


# ---- RouterStats dataclass ---------------------------------------------

class TestRouterStats:
    def test_record_and_to_dict(self):
        s = RouterStats()
        s.record_request("a")
        s.record_request("a")
        s.record_request("b")
        s.record_success()
        s.record_failure("b")
        s.record_fallback()
        d = s.to_dict()
        assert d["total_requests"] == 3
        assert d["successful_requests"] == 1
        assert d["failed_requests"] == 1
        assert d["fallback_count"] == 1
        assert d["per_model_requests"] == {"a": 2, "b": 1}
        assert d["per_model_failures"] == {"b": 1}


# ---- ModelRouter construction ------------------------------------------

class TestModelRouterConstruction:
    def test_empty_models(self, svc):
        r = ModelRouter(service=svc)
        assert r.models == []

    def test_models_list_preserved(self, router):
        assert router.models == ["llama3.2:3b", "qwen2.5:7b", "phi3:mini"]

    def test_models_setter_replaces(self, router):
        router.models = ["a", "b"]
        assert router.models == ["a", "b"]

    def test_add_model_append(self, router):
        router.add_model("newmodel:1b")
        assert "newmodel:1b" in router.models

    def test_add_model_at_priority(self, router):
        router.add_model("priority:1b", priority=0)
        assert router.models[0] == "priority:1b"

    def test_add_duplicate_ignored(self, router):
        n = len(router.models)
        router.add_model("llama3.2:3b")
        assert len(router.models) == n

    def test_remove_model(self, router):
        router.remove_model("qwen2.5:7b")
        assert "qwen2.5:7b" not in router.models


# ---- health checking ---------------------------------------------------

class TestHealthCheck:
    def test_check_health_marks_healthy(self, router):
        h = router.check_health("llama3.2:3b")
        assert h.is_healthy is True
        assert h.last_checked is not None
        assert h.response_time_ms is not None
        assert h.consecutive_failures == 0

    def test_check_health_marks_unhealthy(self, router):
        UNHEALTHY_MODELS.add("phi3:mini")
        h = router.check_health("phi3:mini")
        assert h.is_healthy is False
        assert h.last_error is not None
        assert h.consecutive_failures == 1

    def test_refresh_health_checks_all(self, router):
        results = router.refresh_health()
        assert len(results) == 3
        assert all(h.is_healthy for h in results)

    def test_refresh_health_with_unhealthy(self, router):
        UNHEALTHY_MODELS.add("qwen2.5:7b")
        results = router.refresh_health()
        statuses = {h.model_name: h.is_healthy for h in results}
        assert statuses["llama3.2:3b"] is True
        assert statuses["qwen2.5:7b"] is False
        assert statuses["phi3:mini"] is True

    def test_unknown_model_gets_health_entry(self, router):
        UNHEALTHY_MODELS.add("unknown-model")
        h = router.check_health("unknown-model")
        # unknown-model is in UNHEALTHY_MODELS so /api/show returns 404
        assert h.is_healthy is False
        assert h.model_name == "unknown-model"


# ---- routing / round-robin ---------------------------------------------

class TestRouting:
    def test_get_next_model_returns_healthy(self, router):
        router.refresh_health()
        m = router.get_next_model()
        assert m in router.models

    def test_get_next_model_prefers(self, router):
        router.refresh_health()
        m = router.get_next_model(prefer="phi3:mini")
        assert m == "phi3:mini"

    def test_get_next_model_empty_when_all_unhealthy(self, router):
        UNHEALTHY_MODELS.update(router.models)
        router.refresh_health()
        assert router.get_next_model() == ""

    def test_round_robin_cycles(self, router):
        router.refresh_health()
        seen = [router.get_next_model() for _ in range(6)]
        # Should cycle through all 3 models twice.
        assert set(seen) == set(router.models)
        assert seen[0] == seen[3]
        assert seen[1] == seen[4]
        assert seen[2] == seen[5]

    def test_round_robin_skips_unhealthy(self, router):
        UNHEALTHY_MODELS.add("qwen2.5:7b")
        router.refresh_health()
        for _ in range(6):
            m = router.get_next_model()
            assert m != "qwen2.5:7b"


# ---- execute with fallback ---------------------------------------------

class TestExecute:
    def test_execute_succeeds_first_model(self, router):
        router.refresh_health()
        resp = router.execute({"messages": [{"role": "user", "content": "hi"}]})
        assert "choices" in resp
        assert "_router_meta" in resp
        assert resp["_router_meta"]["fallback_count"] == 0

    def test_execute_fallback_on_failure(self, router):
        router.refresh_health()
        # Make the first model in priority order fail.
        FAILING_MODELS.add("llama3.2:3b")
        resp = router.execute({"messages": [{"role": "user", "content": "hi"}]})
        assert "choices" in resp
        meta = resp["_router_meta"]
        assert meta["model"] != "llama3.2:3b"
        assert meta["fallback_count"] >= 1
        assert "llama3.2:3b" in meta["attempted"]

    def test_execute_all_fail_raises(self, router):
        router.refresh_health()
        FAILING_MODELS.update(router.models)
        with pytest.raises(RouterExhaustedError, match="all .* model"):
            router.execute({"messages": [{"role": "user", "content": "hi"}]})

    def test_execute_no_healthy_models_raises(self, router):
        UNHEALTHY_MODELS.update(router.models)
        router.refresh_health()
        with pytest.raises(RouterExhaustedError, match="no healthy"):
            router.execute({"messages": [{"role": "user", "content": "hi"}]})

    def test_execute_fallback_callback(self, router):
        router.refresh_health()
        FAILING_MODELS.add("llama3.2:3b")
        events = []

        def on_fail(failed, next_m, err):
            events.append((failed, next_m, str(err)))

        resp = router.execute(
            {"messages": [{"role": "user", "content": "hi"}]},
            on_fallback=on_fail,
        )
        assert len(events) >= 1
        assert events[0][0] == "llama3.2:3b"
        assert resp["_router_meta"]["model"] != "llama3.2:3b"

    def test_execute_prefer_model(self, router):
        router.refresh_health()
        resp = router.execute(
            {"messages": [{"role": "user", "content": "hi"}]},
            prefer="phi3:mini",
        )
        assert resp["_router_meta"]["model"] == "phi3:mini"

    def test_execute_tracks_stats(self, router):
        router.refresh_health()
        router.reset_stats()
        router.execute({"messages": [{"role": "user", "content": "hi"}]})
        s = router.router_status()["stats"]
        assert s["total_requests"] >= 1
        assert s["successful_requests"] >= 1


# ---- router_status -----------------------------------------------------

class TestRouterStatus:
    def test_status_shape(self, router):
        st = router.router_status()
        assert "models" in st
        assert "model_count" in st
        assert "healthy_count" in st
        assert "unhealthy_count" in st
        assert "stats" in st
        assert st["model_count"] == 3

    def test_status_after_health_check(self, router):
        router.refresh_health()
        st = router.router_status()
        assert st["healthy_count"] == 3
        assert st["unhealthy_count"] == 0

    def test_status_with_unhealthy(self, router):
        UNHEALTHY_MODELS.add("phi3:mini")
        router.refresh_health()
        st = router.router_status()
        assert st["healthy_count"] == 2
        assert st["unhealthy_count"] == 1
        phi_status = next(m for m in st["models"] if m["model"] == "phi3:mini")
        assert phi_status["healthy"] is False
        assert phi_status["last_error"] is not None

    def test_reset_stats(self, router):
        router.refresh_health()
        router.execute({"messages": [{"role": "user", "content": "hi"}]})
        router.reset_stats()
        st = router.router_status()
        assert st["stats"]["total_requests"] == 0


# ---- edge cases --------------------------------------------------------

class TestEdgeCases:
    def test_single_model_router(self, svc):
        r = ModelRouter(service=svc, models=["llama3.2:3b"])
        r.refresh_health()
        assert r.get_next_model() == "llama3.2:3b"
        resp = r.execute({"messages": [{"role": "user", "content": "hi"}]})
        assert resp["_router_meta"]["model"] == "llama3.2:3b"

    def test_health_staleness(self, router):
        router.refresh_health()
        h = router._health["llama3.2:3b"]
        assert h.is_healthy is True
        # Simulate the model hitting the consecutive-failures threshold.
        # At this point the router permanently excludes it from the healthy
        # list (health is NOT re-checked until failures are below threshold).
        h.is_healthy = False
        h.consecutive_failures = 3  # == max_consecutive_failures default
        # Set last_checked to now so the TTL-based re-check doesn't fire
        # (with failures >= max the "retry quickly" path is also skipped).
        h.last_checked = router._now_iso()
        # With consecutive_failures >= max, the router excludes the model
        # regardless of last_checked age.
        healthy = router._get_healthy_models()
        assert "llama3.2:3b" not in healthy

    def test_consecutive_failures_threshold(self, svc):
        r = ModelRouter(
            service=svc,
            models=["llama3.2:3b"],
            max_consecutive_failures=2,
        )
        r.refresh_health()
        h = r._health["llama3.2:3b"]
        h.consecutive_failures = 2
        h.is_healthy = False
        # At threshold, model is excluded from healthy list.
        healthy = r._get_healthy_models()
        assert "llama3.2:3b" not in healthy

    def test_models_setter_preserves_health(self, router):
        router.refresh_health()
        assert router._health["llama3.2:3b"].is_healthy is True
        router.models = ["llama3.2:3b", "newmodel"]
        # Health for llama3.2:3b should be preserved.
        assert "llama3.2:3b" in router._health
        assert "newmodel" in router._health
