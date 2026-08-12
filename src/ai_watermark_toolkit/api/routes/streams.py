from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel
from ...streams.redis_streams import RedisStreamsService

router = APIRouter(prefix='/api/streams', tags=['streams'])


class StreamJobRequest(BaseModel):
    text: str
    lang: str = 'auto'
    intensity: str = 'standard'
    nfkc: bool = False
    fold_confusables: bool = False


@router.post('/enqueue', summary='Enqueue a Redis Streams job')
async def enqueue(req: StreamJobRequest, request: Request):
    svc = RedisStreamsService(request.app.state.redis)
    await svc.ensure_group()
    return await svc.enqueue(req.model_dump())


@router.get('/{job_id}', summary='Get job status')
async def get_job(job_id: str, request: Request):
    svc = RedisStreamsService(request.app.state.redis)
    return await svc.get_job(job_id) or {'error': 'not_found'}


@router.get('/metrics', summary='Get stream metrics')
async def metrics(request: Request):
    svc = RedisStreamsService(request.app.state.redis)
    await svc.ensure_group()
    return await svc.stream_info()
