"""Tests for workers/arq_worker.py"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from ai_watermark_toolkit.workers import arq_worker


def test_worker_settings():
    assert arq_worker.process_text_job in arq_worker.WorkerSettings.functions
    assert arq_worker.WorkerSettings.on_startup is arq_worker.startup
    assert arq_worker.WorkerSettings.on_shutdown is arq_worker.shutdown


@pytest.mark.anyio
async def test_process_text_job():
    job = {
        "job_id": "abc",
        "payload": {
            "text": "hello",
            "lang": "en",
            "intensity": "standard",
            "nfkc": False,
            "fold_confusables": False,
        },
    }
    ctx = {}
    with patch("ai_watermark_toolkit.workers.arq_worker.run_pipeline") as mock_pipe:
        mock_pipe.return_value = ("cleaned", {"verdict": "clean"})
        result = await arq_worker.process_text_job(ctx, json.dumps(job))
    assert result["job_id"] == "abc"
    assert result["text"] == "cleaned"
    assert result["report"]["verdict"] == "clean"


@pytest.mark.anyio
async def test_startup_shutdown():
    ctx = {}
    with patch("ai_watermark_toolkit.workers.arq_worker.create_pool") as mock_pool:
        mock_redis = AsyncMock()
        mock_pool.return_value = mock_redis
        await arq_worker.startup(ctx)
        assert "redis" in ctx
        await arq_worker.shutdown(ctx)
        mock_redis.close.assert_awaited_once()
