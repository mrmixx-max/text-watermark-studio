from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ...queue.redis_queue import BACKPRESSURE_KEY, RedisQueueService
from ..response_utils import get_redis

router = APIRouter(prefix="/api/queue", tags=["queue"])


class QueuePayload(BaseModel):
    text: str
    lang: str = "auto"
    intensity: str = "standard"
    nfkc: bool = False
    fold_confusables: bool = False


def get_queue(request: Request) -> RedisQueueService:
    return RedisQueueService(get_redis(request))


@router.post("/enqueue")
async def enqueue(payload: QueuePayload, request: Request):
    queue = get_queue(request)
    return await queue.enqueue("process_text_job", payload.model_dump())


@router.get("/{job_id}")
async def get_job(job_id: str, request: Request):
    queue = get_queue(request)
    job = await queue.get_job(job_id)
    return job or {"error": "not_found"}


@router.get("/depth")
async def depth(request: Request):
    queue = get_queue(request)
    return {"depth": await queue.queue_depth(), "backpressure": bool(await get_redis(request).get(BACKPRESSURE_KEY))}
