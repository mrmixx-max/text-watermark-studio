from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass

from redis.asyncio import Redis

from ..core.config import settings

JOB_PREFIX = "tws:job:"
QUEUE_KEY = f"tws:queue:{settings.queue_name}"
DEPTH_KEY = "tws:queue:depth"
BACKPRESSURE_KEY = "tws:queue:backpressure"


@dataclass
class QueueJob:
    job_id: str
    task: str
    payload: dict
    status: str = "queued"

    def to_dict(self) -> dict:
        return asdict(self)


class RedisQueueService:
    def __init__(self, redis: Redis):
        self.redis = redis

    async def enqueue(self, task: str, payload: dict) -> dict:
        depth = await self.redis.llen(QUEUE_KEY)
        if depth >= settings.queue_max_depth:
            await self.redis.set(BACKPRESSURE_KEY, "1", ex=60)
            return {"error": "backpressure", "queue_depth": depth}
        job = QueueJob(str(uuid.uuid4()), task, payload)
        await self.redis.set(f"{JOB_PREFIX}{job.job_id}", json.dumps(job.to_dict()), ex=settings.job_ttl_sec)
        await self.redis.rpush(QUEUE_KEY, job.job_id)
        await self.redis.set(DEPTH_KEY, await self.redis.llen(QUEUE_KEY), ex=settings.job_ttl_sec)
        return job.to_dict()

    async def next_job(self) -> dict | None:
        job_id = await self.redis.lpop(QUEUE_KEY)
        if not job_id:
            return None
        raw = await self.redis.get(f"{JOB_PREFIX}{job_id}")
        return json.loads(raw) if raw else {"job_id": job_id, "task": "unknown", "payload": {}}

    async def update_status(self, job_id: str, status: str, result: dict | None = None):
        raw = await self.redis.get(f"{JOB_PREFIX}{job_id}")
        job = json.loads(raw) if raw else {"job_id": job_id}
        job["status"] = status
        if result is not None:
            job["result"] = result
        await self.redis.set(f"{JOB_PREFIX}{job_id}", json.dumps(job), ex=settings.job_ttl_sec)
        return job

    async def get_job(self, job_id: str) -> dict | None:
        raw = await self.redis.get(f"{JOB_PREFIX}{job_id}")
        return json.loads(raw) if raw else None

    async def queue_depth(self) -> int:
        return await self.redis.llen(QUEUE_KEY)
