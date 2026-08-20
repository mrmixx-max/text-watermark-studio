from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from fastapi import HTTPException

from ..batch import process_batch


@dataclass
class BatchJob:
    job_id: str
    input_dir: str
    output_dir: str
    mode: str
    intensity: str
    lang: str
    status: str = "queued"

    def to_dict(self) -> dict:
        return asdict(self)


class JobService:
    def __init__(self, state_dir: str = ".ai_wm_jobs"):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def create_batch_job(self, input_dir: str, output_dir: str, mode: str, intensity: str, lang: str) -> dict:
        job = BatchJob(str(uuid.uuid4()), input_dir, output_dir, mode, intensity, lang)
        job_path = self.state_dir / f"{job.job_id}.json"
        job_path.write_text(json.dumps(job.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return job.to_dict()

    def run_batch_job(self, job_id: str) -> dict:
        job_path = self.state_dir / f"{job_id}.json"
        job = json.loads(job_path.read_text(encoding="utf-8"))
        job["status"] = "running"
        job_path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
        result = process_batch(
            job["input_dir"],
            job["output_dir"],
            mode=job["mode"],
            intensity=job["intensity"],
            lang=job["lang"],
        )
        job["status"] = "done"
        job["result"] = result
        job_path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
        return job

    def get_job(self, job_id: str) -> dict:
        job_path = self.state_dir / f"{job_id}.json"
        if not job_path.exists():
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        return json.loads(job_path.read_text(encoding="utf-8"))
