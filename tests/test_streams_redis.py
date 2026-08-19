"""Tests for streams/redis_streams.py"""
import json
from unittest.mock import AsyncMock

import pytest

from ai_watermark_toolkit.streams import redis_streams


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.get = AsyncMock(side_effect=lambda k: {
        "tws:v6:job:abc": json.dumps({"job_id": "abc", "status": "queued", "attempts": 0, "payload": {"text": "hi"}})
    }.get(k))
    return redis


@pytest.fixture
def svc(mock_redis):
    return redis_streams.RedisStreamsService(mock_redis)


@pytest.mark.anyio
async def test_enqueue(mock_redis, svc):
    job = await svc.enqueue({"text": "hi"})
    assert "job_id" in job
    assert job["status"] == "queued"
    assert job["payload"]["text"] == "hi"
    mock_redis.set.assert_awaited()
    mock_redis.sadd.assert_awaited()
    mock_redis.xadd.assert_awaited()


@pytest.mark.anyio
async def test_get_job(mock_redis, svc):
    job = await svc.get_job("abc")
    assert job["job_id"] == "abc"


@pytest.mark.anyio
async def test_get_job_missing(mock_redis, svc):
    mock_redis.get = AsyncMock(return_value=None)
    job = await svc.get_job("xyz")
    assert job is None


@pytest.mark.anyio
async def test_set_status(mock_redis, svc):
    mock_redis.get = AsyncMock(return_value=json.dumps({"job_id": "abc", "status": "queued", "attempts": 0, "payload": {}}))
    await svc.set_status("abc", "done", result={"text": "clean"})
    mock_redis.set.assert_awaited()


@pytest.mark.anyio
async def test_mark_retry(mock_redis, svc):
    mock_redis.get = AsyncMock(return_value=json.dumps({"job_id": "abc", "status": "queued", "attempts": 0, "payload": {}}))
    await svc.mark_retry("abc", "boom")
    calls = mock_redis.set.await_args_list
    assert len(calls) >= 1


@pytest.mark.anyio
async def test_move_to_dlq(mock_redis, svc):
    mock_redis.get = AsyncMock(return_value=json.dumps({"job_id": "abc", "status": "queued", "attempts": 0, "payload": {}}))
    await svc.move_to_dlq("abc", "too many retries")
    mock_redis.xadd.assert_awaited()


@pytest.mark.anyio
async def test_stream_info(mock_redis, svc):
    mock_redis.scard = AsyncMock(return_value=0)
    mock_redis.xpending = AsyncMock(return_value={"pending": 0, "min": None, "max": None, "consumers": []})
    info = await svc.stream_info()
    assert info["queued"] == 0
    assert info["dead_letter"] == 0


@pytest.mark.anyio
async def test_ensure_group(mock_redis, svc):
    await svc.ensure_group()
    mock_redis.xgroup_create.assert_awaited_once()
