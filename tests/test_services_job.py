"""Tests for services/job_service.py"""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from ai_watermark_toolkit.services.job_service import JobService


@pytest.fixture
def svc(tmp_path):
    return JobService(state_dir=str(tmp_path))


def test_create_batch_job(svc):
    job = svc.create_batch_job("/in", "/out", "clean", "standard", "en")
    assert "job_id" in job
    assert job["input_dir"] == "/in"
    assert job["output_dir"] == "/out"
    assert job["mode"] == "clean"
    assert job["status"] == "queued"


def test_get_job(svc):
    job = svc.create_batch_job("/in", "/out", "clean", "standard", "en")
    fetched = svc.get_job(job["job_id"])
    assert fetched["job_id"] == job["job_id"]


def test_get_job_missing(svc):
    with pytest.raises(HTTPException) as exc:
        svc.get_job("nonexistent")
    assert exc.value.status_code == 404


def test_run_batch_job(svc):
    job = svc.create_batch_job("/in", "/out", "clean", "standard", "en")
    with patch("ai_watermark_toolkit.services.job_service.process_batch") as mock_batch:
        mock_batch.return_value = {"files_processed": 5}
        result = svc.run_batch_job(job["job_id"])
    assert result["status"] == "done"
    assert result["result"]["files_processed"] == 5
