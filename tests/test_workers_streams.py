"""Tests for workers/streams_worker.py"""
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_watermark_toolkit.workers import streams_worker


@pytest.mark.anyio
async def test_handle_message_no_job_id():
    redis = AsyncMock()
    svc = MagicMock()
    svc.get_job = AsyncMock()
    fields = {"no_job_id": "x"}
    await streams_worker.handle_message(redis, svc, "msg1", fields)
    redis.xack.assert_awaited_once_with(
        streams_worker.settings.stream_key,
        streams_worker.settings.stream_group,
        "msg1",
    )
    svc.get_job.assert_not_awaited()


@pytest.mark.anyio
async def test_handle_message_job_not_found():
    redis = AsyncMock()
    svc = MagicMock()
    svc.get_job = AsyncMock(return_value=None)
    fields = {"job_id": "abc"}
    await streams_worker.handle_message(redis, svc, "msg1", fields)
    redis.xack.assert_awaited_once()


@pytest.mark.anyio
async def test_handle_message_retry_not_due():
    redis = AsyncMock()
    svc = MagicMock()
    job = {"job_id": "abc", "payload": {"text": "hi"}, "attempts": 0}
    svc.get_job = AsyncMock(return_value=job)
    future_ms = str(int((time.time() + 60) * 1000))
    fields = {"job_id": "abc", "retry_at_ms": future_ms}
    await streams_worker.handle_message(redis, svc, "msg1", fields)
    svc.set_status.assert_not_called()


@pytest.mark.anyio
async def test_handle_message_success():
    redis = AsyncMock()
    svc = MagicMock()
    job = {"job_id": "abc", "payload": {"text": "hi"}, "attempts": 0}
    svc.get_job = AsyncMock(return_value=job)
    svc.set_status = AsyncMock()
    fields = {"job_id": "abc"}
    with patch("ai_watermark_toolkit.workers.streams_worker.run_pipeline") as mock_pipe:
        mock_pipe.return_value = ("cleaned", {"verdict": "clean"})
        await streams_worker.handle_message(redis, svc, "msg1", fields)
    svc.set_status.assert_any_await("abc", "processing")
    svc.set_status.assert_any_await("abc", "done", result={"text": "cleaned", "report": {"verdict": "clean"}})
    redis.xack.assert_awaited_once()


@pytest.mark.anyio
async def test_handle_message_failure_retries():
    redis = AsyncMock()
    svc = MagicMock()
    job = {"job_id": "abc", "payload": {"text": "hi"}, "attempts": 0}
    svc.get_job = AsyncMock(return_value=job)
    svc.set_status = AsyncMock()
    svc.mark_retry = AsyncMock()
    fields = {"job_id": "abc"}
    with patch("ai_watermark_toolkit.workers.streams_worker.run_pipeline", side_effect=RuntimeError("boom")):
        await streams_worker.handle_message(redis, svc, "msg1", fields)
    svc.mark_retry.assert_awaited_once()
    redis.xack.assert_awaited_once()
