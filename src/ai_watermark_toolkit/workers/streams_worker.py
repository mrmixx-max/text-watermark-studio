from __future__ import annotations

import asyncio
import time
from redis.asyncio import Redis
from ..core.config import settings
from ..pipeline import run_pipeline
from ..streams.redis_streams import RedisStreamsService


async def process_loop():
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    svc = RedisStreamsService(redis)
    await svc.ensure_group()
    while True:
        try:
            reclaimed = await redis.xautoclaim(
                settings.stream_key,
                settings.stream_group,
                settings.consumer_name,
                settings.min_idle_ms,
                '0-0',
                count=10,
            )
            if reclaimed and len(reclaimed) >= 2:
                _, msgs, *_ = reclaimed
                for msg_id, fields in msgs:
                    await handle_message(redis, svc, msg_id, fields)
            rows = await redis.xreadgroup(
                settings.stream_group,
                settings.consumer_name,
                {settings.stream_key: '>'},
                count=10,
                block=2000,
            )
            for _, messages in rows or []:
                for msg_id, fields in messages:
                    await handle_message(redis, svc, msg_id, fields)
        except Exception:
            await asyncio.sleep(1)


async def handle_message(redis: Redis, svc: RedisStreamsService, msg_id: str, fields: dict):
    job_id = fields.get('job_id')
    if not job_id:
        await redis.xack(settings.stream_key, settings.stream_group, msg_id)
        return
    job = await svc.get_job(job_id)
    if not job:
        await redis.xack(settings.stream_key, settings.stream_group, msg_id)
        return
    retry_at_ms = fields.get('retry_at_ms')
    if retry_at_ms and int(retry_at_ms) > int(time.time() * 1000):
        return
    try:
        await svc.set_status(job_id, 'processing')
        payload = job['payload']
        out, report = run_pipeline(
            payload['text'],
            lang=payload.get('lang', 'auto'),
            intensity=payload.get('intensity', 'standard'),
            nfkc=payload.get('nfkc', False),
            fold_confusables=payload.get('fold_confusables', False),
        )
        await svc.set_status(job_id, 'done', result={'text': out, 'report': report})
        await redis.xack(settings.stream_key, settings.stream_group, msg_id)
    except Exception as exc:
        attempts = int(job.get('attempts', 0))
        if attempts + 1 >= settings.max_retries:
            await svc.move_to_dlq(job_id, str(exc))
        else:
            await svc.mark_retry(job_id, str(exc))
        await redis.xack(settings.stream_key, settings.stream_group, msg_id)


if __name__ == '__main__':
    asyncio.run(process_loop())
