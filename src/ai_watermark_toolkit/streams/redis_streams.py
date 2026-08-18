from __future__ import annotations

import json
import logging
import time
import uuid

from redis.asyncio import Redis

from ..core.config import settings

logger = logging.getLogger(__name__)

JOB_PREFIX = 'tws:v6:job:'
STATUS_INDEX_PREFIX = 'tws:v6:status:'


class RedisStreamsService:
    def __init__(self, redis: Redis):
        self.redis = redis

    async def ensure_group(self):
        try:
            await self.redis.xgroup_create(settings.stream_key, settings.stream_group, id='0', mkstream=True)
        except Exception:
            logger.debug("stream group already exists or unavailable (continuing)", exc_info=True)

    async def enqueue(self, payload: dict) -> dict:
        job_id = str(uuid.uuid4())
        job = {
            'job_id': job_id,
            'status': 'queued',
            'attempts': 0,
            'max_attempts': settings.max_retries,
            'created_at': int(time.time()),
            'payload': payload,
            'last_error': ''
        }
        await self.redis.set(f'{JOB_PREFIX}{job_id}', json.dumps(job), ex=86400)
        await self.redis.sadd(f'{STATUS_INDEX_PREFIX}queued', job_id)
        await self.redis.xadd(settings.stream_key, {'job_id': job_id}, maxlen=settings.stream_maxlen, approximate=True)
        return job

    async def get_job(self, job_id: str):
        raw = await self.redis.get(f'{JOB_PREFIX}{job_id}')
        return json.loads(raw) if raw else None

    async def _move_status(self, job_id: str, new_status: str):
        raw = await self.redis.get(f'{JOB_PREFIX}{job_id}')
        job = json.loads(raw) if raw else {'job_id': job_id}
        old = job.get('status')
        if old:
            await self.redis.srem(f'{STATUS_INDEX_PREFIX}{old}', job_id)
        await self.redis.sadd(f'{STATUS_INDEX_PREFIX}{new_status}', job_id)
        return job

    async def set_status(self, job_id: str, status: str, result: dict | None = None, error: str = ''):
        job = await self._move_status(job_id, status)
        job['status'] = status
        if result is not None:
            job['result'] = result
        if error:
            job['last_error'] = error
        await self.redis.set(f'{JOB_PREFIX}{job_id}', json.dumps(job), ex=86400)
        return job

    async def mark_retry(self, job_id: str, error: str):
        job = await self._move_status(job_id, 'retrying')
        job['attempts'] = int(job.get('attempts', 0)) + 1
        job['status'] = 'retrying'
        job['last_error'] = error
        await self.redis.set(f'{JOB_PREFIX}{job_id}', json.dumps(job), ex=86400)
        await self.redis.xadd(
            settings.stream_key,
            {'job_id': job_id, 'retry_at_ms': str(int(time.time() * 1000) + settings.retry_backoff_ms)},
            maxlen=settings.stream_maxlen,
            approximate=True,
        )
        return job

    async def move_to_dlq(self, job_id: str, reason: str):
        job = await self._move_status(job_id, 'dead_letter')
        job['status'] = 'dead_letter'
        job['last_error'] = reason
        await self.redis.set(f'{JOB_PREFIX}{job_id}', json.dumps(job), ex=86400)
        await self.redis.xadd(
            settings.dlq_stream_key,
            {'job_id': job_id, 'reason': reason, 'payload': json.dumps(job.get('payload', {}))},
            maxlen=settings.stream_maxlen,
            approximate=True,
        )
        return job

    async def stream_info(self):
        queued = await self.redis.scard(f'{STATUS_INDEX_PREFIX}queued')
        retrying = await self.redis.scard(f'{STATUS_INDEX_PREFIX}retrying')
        done = await self.redis.scard(f'{STATUS_INDEX_PREFIX}done')
        dead = await self.redis.scard(f'{STATUS_INDEX_PREFIX}dead_letter')
        pending = {'pending': 0, 'min': None, 'max': None, 'consumers': []}
        try:
            xp = await self.redis.xpending(settings.stream_key, settings.stream_group)
            if isinstance(xp, dict):
                pending = xp
            elif isinstance(xp, (list, tuple)) and len(xp) >= 4:
                pending = {'pending': xp[0], 'min': xp[1], 'max': xp[2], 'consumers': xp[3]}
        except Exception:
            logger.debug("xpending unavailable (continuing with defaults)", exc_info=True)
        return {'queued': queued, 'retrying': retrying, 'done': done, 'dead_letter': dead, 'pending': pending}
