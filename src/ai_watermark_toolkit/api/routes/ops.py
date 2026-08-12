from __future__ import annotations

import json
from fastapi import APIRouter, Request, Response
from ...core.config import settings
from ...observability.metrics import render_metrics, STREAM_PENDING_GAUGE, STREAM_DEAD_LETTER_GAUGE, DLQ_REPLAYS_TOTAL
from ...streams.redis_streams import RedisStreamsService

router = APIRouter(prefix='/api/ops', tags=['ops'])


@router.get('/metrics', summary='Prometheus metrics endpoint')
async def metrics(request: Request):
    svc = RedisStreamsService(request.app.state.redis)
    info = await svc.stream_info()
    pending = info.get('pending', {}).get('pending', 0) if isinstance(info.get('pending'), dict) else 0
    STREAM_PENDING_GAUGE.set(pending)
    STREAM_DEAD_LETTER_GAUGE.set(info.get('dead_letter', 0))
    payload, content_type = render_metrics()
    return Response(content=payload, media_type=content_type)


@router.get('/status', summary='JSON operations status')
async def status(request: Request):
    svc = RedisStreamsService(request.app.state.redis)
    info = await svc.stream_info()
    return {
        'service': settings.app_name,
        'env': settings.app_env,
        'redis': settings.redis_url,
        'stream': settings.stream_key,
        'dlq_stream': settings.dlq_stream_key,
        'metrics': info,
    }


@router.post('/dlq/replay/{job_id}', summary='Replay a DLQ job back into the main stream')
async def replay_dlq(job_id: str, request: Request):
    svc = RedisStreamsService(request.app.state.redis)
    job = await svc.get_job(job_id)
    if not job:
        return {'error': 'not_found'}
    payload = job.get('payload', {})
    replayed = await svc.enqueue(payload)
    await svc.set_status(job_id, 'replayed')
    DLQ_REPLAYS_TOTAL.inc()
    return {'replayed_from': job_id, 'new_job': replayed}
