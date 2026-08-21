from __future__ import annotations

import contextlib
import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from .service import LocalLLMService


@dataclass
class ModelHealth:
    """Health status for a single model in the router."""

    model_name: str
    is_healthy: bool = False
    last_checked: str | None = None
    last_error: str | None = None
    response_time_ms: float | None = None
    consecutive_failures: int = 0

    def to_dict(self) -> dict:
        return {
            "model": self.model_name,
            "healthy": self.is_healthy,
            "last_checked": self.last_checked,
            "last_error": self.last_error,
            "response_time_ms": self.response_time_ms,
            "consecutive_failures": self.consecutive_failures,
        }


@dataclass
class RouterStats:
    """Aggregate statistics for the router."""

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    fallback_count: int = 0
    per_model_requests: dict[str, int] = field(default_factory=dict)
    per_model_failures: dict[str, int] = field(default_factory=dict)

    def record_request(self, model: str) -> None:
        self.total_requests += 1
        self.per_model_requests[model] = self.per_model_requests.get(model, 0) + 1

    def record_success(self) -> None:
        self.successful_requests += 1

    def record_failure(self, model: str) -> None:
        self.failed_requests += 1
        self.per_model_failures[model] = self.per_model_failures.get(model, 0) + 1

    def record_fallback(self) -> None:
        self.fallback_count += 1

    def to_dict(self) -> dict:
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "fallback_count": self.fallback_count,
            "per_model_requests": dict(self.per_model_requests),
            "per_model_failures": dict(self.per_model_failures),
        }


class ModelRouter:
    """Multi-model LLM router with priority ordering, health checking,
    automatic fallback, and round-robin load balancing across healthy models.

    Models are kept in a priority-ordered list. When a request comes in:
      1. The router picks the next *healthy* model (round-robin).
      2. If that model fails (timeout, OOM, 5xx), it falls back to the next
         healthy model in priority order.
      3. If all models fail, a RouterExhaustedError is raised.

    Health is tracked per model and refreshed via ``refresh_health()`` or
    lazily on each request (stale entries trigger a re-ping).
    """

    def __init__(
        self,
        service: LocalLLMService,
        models: list[str] | None = None,
        health_check_timeout: int = 10,
        max_consecutive_failures: int = 3,
        health_cache_ttl_seconds: int = 60,
    ):
        self._svc = service
        self._health_check_timeout = health_check_timeout
        self._max_consecutive_failures = max_consecutive_failures
        self._health_cache_ttl = health_cache_ttl_seconds

        # Priority-ordered model list (first = highest priority).
        self._models: list[str] = list(models) if models else []

        # Health map keyed by model name.
        self._health: dict[str, ModelHealth] = {m: ModelHealth(model_name=m) for m in self._models}

        # Round-robin cursor -- index into the *healthy* model list.
        self._rr_index: int = 0

        # Aggregate stats.
        self._stats = RouterStats()

        # Thread safety for rr_index + health mutations.
        self._lock = threading.Lock()

    # ---- configuration ---------------------------------------------------

    @property
    def models(self) -> list[str]:
        """Priority-ordered list of model names."""
        return list(self._models)

    @models.setter
    def models(self, value: list[str]) -> None:
        with self._lock:
            new = list(value)
            # Preserve health entries for models that remain.
            new_health: dict[str, ModelHealth] = {}
            for m in new:
                new_health[m] = self._health.get(m, ModelHealth(model_name=m))
            self._models = new
            self._health = new_health
            self._rr_index = 0

    def add_model(self, model_name: str, priority: int | None = None) -> None:
        """Add a model to the router.

        Args:
            model_name: Ollama model name (e.g. ``"llama3.2:3b"``).
            priority: Insert position (0 = highest). ``None`` appends to end.
        """
        with self._lock:
            if model_name in self._health:
                return
            health = ModelHealth(model_name=model_name)
            if priority is not None:
                idx = max(0, min(priority, len(self._models)))
                self._models.insert(idx, model_name)
                self._health[model_name] = health
            else:
                self._models.append(model_name)
                self._health[model_name] = health

    def remove_model(self, model_name: str) -> None:
        with self._lock:
            if model_name in self._models:
                self._models.remove(model_name)
            self._health.pop(model_name, None)
            self._rr_index = 0

    # ---- health checking -------------------------------------------------

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _is_health_stale(self, h: ModelHealth) -> bool:
        if h.last_checked is None:
            return True
        if not h.is_healthy and h.consecutive_failures < self._max_consecutive_failures:
            return True
        try:
            last = datetime.fromisoformat(h.last_checked)
            age = (datetime.now(timezone.utc) - last).total_seconds()
            return age > self._health_cache_ttl
        except (ValueError, TypeError):
            return True

    def check_health(self, model_name: str) -> ModelHealth:
        """Ping a single model via Ollama's /api/show endpoint and update
        its health entry."""
        h = self._health.get(model_name)
        if h is None:
            h = ModelHealth(model_name=model_name)
            self._health[model_name] = h

        start = time.monotonic()
        try:
            self._svc._ollama(
                "/api/show",
                method="POST",
                payload={"name": model_name, "stream": False},
                timeout=self._health_check_timeout,
            )
            elapsed = (time.monotonic() - start) * 1000
            h.is_healthy = True
            h.last_checked = self._now_iso()
            h.last_error = None
            h.response_time_ms = round(elapsed, 1)
            h.consecutive_failures = 0
        except (ConnectionError, TimeoutError, OSError, ValueError, RuntimeError) as e:
            h.is_healthy = False
            h.last_checked = self._now_iso()
            h.last_error = str(e)
            h.response_time_ms = None
            h.consecutive_failures += 1

        return h

    def refresh_health(self) -> list[ModelHealth]:
        """Re-check health for every registered model. Returns the list."""
        results = []
        for m in self._models:
            results.append(self.check_health(m))
        return results

    def _ensure_health_checked(self, model_name: str) -> ModelHealth:
        """Return health for model_name, refreshing if stale."""
        h = self._health.get(model_name)
        if h is None:
            return self.check_health(model_name)
        if self._is_health_stale(h):
            return self.check_health(model_name)
        return h

    # ---- routing logic ---------------------------------------------------

    def _get_healthy_models(self) -> list[str]:
        """Return the subset of self._models that are currently healthy,
        preserving priority order. Lazily re-checks stale entries."""
        healthy = []
        for m in self._models:
            h = self._ensure_health_checked(m)
            if h.is_healthy and h.consecutive_failures < self._max_consecutive_failures:
                healthy.append(m)
        return healthy

    def _round_robin_pick(self, healthy: list[str]) -> str:
        """Pick the next model from *healthy* using round-robin. Thread-safe."""
        with self._lock:
            if not healthy:
                return ""
            idx = self._rr_index % len(healthy)
            self._rr_index = (self._rr_index + 1) % len(healthy)
            return healthy[idx]

    def get_next_model(self, prefer: str | None = None) -> str:
        """Pick the next model to serve a request.

        If *prefer* is given and healthy it is chosen. Otherwise the
        round-robin cursor advances across healthy models.

        Returns:
            A model name, or '' if no healthy model is available.
        """
        healthy = self._get_healthy_models()
        if not healthy:
            return ""
        if prefer and prefer in healthy:
            return prefer
        return self._round_robin_pick(healthy)

    def execute(
        self,
        payload: dict,
        prefer: str | None = None,
        on_fallback: Any = None,
    ) -> dict:
        """Execute a chat-completions request with automatic fallback.

        Tries each healthy model in priority order. On the first success the
        response dict is returned (with an added '_router_meta' key noting
        which model served the request). If a model raises, the next healthy
        model is tried.

        Args:
            payload: OpenAI-compatible /v1/chat/completions body
                ('model' will be overwritten per attempt).
            prefer: If given and healthy, use this model as the first attempt.
            on_fallback: Optional callback '(failed_model, next_model, error)'
                invoked each time the router falls back.

        Returns:
            The provider's JSON response dict augmented with '_router_meta'.

        Raises:
            RouterExhaustedError: All models failed.
        """
        healthy = self._get_healthy_models()
        if not healthy:
            # Last-ditch: try a full health refresh in case something changed.
            self.refresh_health()
            healthy = self._get_healthy_models()
            if not healthy:
                raise RouterExhaustedError("no healthy models available")

        # Build attempt order: prefer first, then round-robin from there.
        attempt_order: list[str] = []
        if prefer and prefer in healthy:
            attempt_order.append(prefer)
            for m in healthy:
                if m != prefer:
                    attempt_order.append(m)
        else:
            start = self._rr_index % len(healthy)
            attempt_order = healthy[start:] + healthy[:start]
            with self._lock:
                self._rr_index = (self._rr_index + 1) % len(healthy)

        last_error: Exception | None = None
        tried: list[str] = []

        for model in attempt_order:
            self._stats.record_request(model)
            tried.append(model)
            attempt_payload = dict(payload)
            attempt_payload["model"] = model
            try:
                resp = self._call_model(model, attempt_payload)
                resp["_router_meta"] = {
                    "model": model,
                    "attempted": tried,
                    "fallback_count": len(tried) - 1,
                    "timestamp": self._now_iso(),
                }
                self._stats.record_success()
                return resp
            except (ConnectionError, TimeoutError, OSError, ValueError, RuntimeError) as e:
                last_error = e
                self._stats.record_failure(model)
                h = self._health.get(model)
                if h:
                    h.is_healthy = False
                    h.consecutive_failures += 1
                    h.last_error = str(e)
                    h.last_checked = self._now_iso()
                if on_fallback:
                    model_idx = attempt_order.index(model)
                    next_m = attempt_order[model_idx + 1] if model_idx + 1 < len(attempt_order) else None
                    if next_m:
                        self._stats.record_fallback()
                        on_fallback(model, next_m, e)

        raise RouterExhaustedError(f"all {len(tried)} model(s) failed; last error: {last_error}") from last_error

    def _call_model(self, model: str, payload: dict) -> dict:
        """Make the actual HTTP call to a model via Ollama's OpenAI-compatible endpoint."""
        import urllib.error
        import urllib.request

        cfg = self._svc.load()
        base = cfg.get("server_base_url", "http://localhost:11434")
        # Remove trailing /v1 if present
        if base.endswith("/v1"):
            base = base[:-3]
        url = f"{base}/v1/chat/completions"
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"invalid scheme: {parsed.scheme}")

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            timeout = payload.get("timeout", 120)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = ""
            with contextlib.suppress(OSError, AttributeError):
                body = e.read().decode("utf-8", errors="replace")
            raise ModelRequestError(f"model {model} HTTP {e.code} {e.reason}: {body}") from e
        except urllib.error.URLError as e:
            raise ModelRequestError(f"model {model} unreachable: {e.reason}") from e

    # ---- status / introspection -----------------------------------------

    def router_status(self) -> dict:
        """Full router status for API/CLI consumption."""
        health_list = []
        for m in self._models:
            h = self._health.get(m, ModelHealth(model_name=m))
            health_list.append(h.to_dict())

        healthy_count = sum(1 for h in self._health.values() if h.is_healthy)
        return {
            "models": health_list,
            "model_count": len(self._models),
            "healthy_count": healthy_count,
            "unhealthy_count": len(self._models) - healthy_count,
            "round_robin_index": self._rr_index,
            "max_consecutive_failures": self._max_consecutive_failures,
            "health_cache_ttl": self._health_cache_ttl,
            "stats": self._stats.to_dict(),
        }

    def reset_stats(self) -> None:
        self._stats = RouterStats()


class RouterExhaustedError(Exception):
    """Raised when every model in the router fails."""


class ModelRequestError(RuntimeError):
    """Raised for a single model request failure (HTTP, timeout)."""
