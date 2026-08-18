from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ...services.job_service import JobService

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
service = JobService()


class BatchJobRequest(BaseModel):
    input_dir: str
    output_dir: str
    mode: str = "pipeline"
    intensity: str = "standard"
    lang: str = "auto"


@router.post("")
def create_job(req: BatchJobRequest):
    job = service.create_batch_job(req.input_dir, req.output_dir, req.mode, req.intensity, req.lang)
    return service.run_batch_job(job["job_id"])


@router.get("/{job_id}")
def get_job(job_id: str):
    return service.get_job(job_id)
