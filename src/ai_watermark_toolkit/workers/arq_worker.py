from __future__ import annotations

import json
from typing import ClassVar

from arq import create_pool
from arq.connections import RedisSettings

from ..core.config import settings
from ..pipeline import run_pipeline


async def startup(ctx):
    ctx['redis'] = await create_pool(RedisSettings.from_dsn(settings.redis_url))


async def shutdown(ctx):
    await ctx['redis'].close()


async def process_text_job(ctx, job_json: str):
    job = json.loads(job_json)
    text = job['payload']['text']
    lang = job['payload'].get('lang', 'auto')
    intensity = job['payload'].get('intensity', 'standard')
    nfkc = job['payload'].get('nfkc', False)
    fold_confusables = job['payload'].get('fold_confusables', False)
    out, report = run_pipeline(text, lang=lang, intensity=intensity, nfkc=nfkc, fold_confusables=fold_confusables)
    return {'job_id': job['job_id'], 'text': out, 'report': report}


class WorkerSettings:
    functions: ClassVar = [process_text_job]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
