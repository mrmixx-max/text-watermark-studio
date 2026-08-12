from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from redis.asyncio import Redis
from ..core.config import settings
from ..core.logging import setup_logging
from .middleware.rate_limit import RateLimitMiddleware
from .middleware.request_id import RequestIDMiddleware
from .middleware.prometheus import PrometheusMiddleware
from .routes.text import router as text_router
from .routes.jobs import router as jobs_router
from .routes.studio import router as studio_router
from .routes.queue import router as queue_router
from .routes.streams import router as streams_router
from .routes.ops import router as ops_router
from .routes.forensics import router as forensics_router
from .routes.lab import router as lab_router
from .routes.documents import router as documents_router
from .routes.pdf import router as pdf_router
from .routes.rag import router as rag_router
from .routes.llm import router as llm_router
from .routes.routing import router as routing_router
from .routes.prompts import router as prompts_router
from .routes.optimization import router as optimization_router
from .routes.multi_agent import router as multi_agent_router
from .routes.graph import router as graph_router
from .routes.community import router as community_router
from .routes.rewrite import router as rewrite_router
from .routes.exporting import router as exporting_router
from .routes.cloud import router as cloud_router
from .routes.llm import router as llm_router
from .routes.routing import router as routing_router

setup_logging(settings.log_level)
WEB_ROOT = Path(__file__).resolve().parents[1] / 'web'


@asynccontextmanager
async def lifespan(app: FastAPI):
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        # Probe connectivity so Redis-dependent routes fail with a clean 503
        # (state.redis = None -> get_redis() raises HTTPException) instead of
        # a raw 500 from a connection error on first use.
        await redis.ping()
        app.state.redis = redis
    except Exception:
        app.state.redis = None
        await redis.aclose()
    try:
        yield
    finally:
        if app.state.redis is not None:
            await app.state.redis.close()


app = FastAPI(
    title=settings.app_name,
    version='1.0.2',
    summary='Text Watermark Studio v1.0.2 Watermarking Lab Edition',
    description='Adds a modular watermarking lab with taxonomy-driven family plugins, capabilities, demo embed/detect routines, and a lab UI.',
    lifespan=lifespan,
)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(PrometheusMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(',')] if settings.cors_origins else ['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)
app.add_middleware(RateLimitMiddleware, limit=settings.rate_limit_requests, window_sec=settings.rate_limit_window_sec)
app.include_router(text_router)
app.include_router(jobs_router)
app.include_router(studio_router)
app.include_router(queue_router)
app.include_router(streams_router)
app.include_router(ops_router)
app.include_router(forensics_router)
app.include_router(lab_router)
app.include_router(documents_router)
app.include_router(pdf_router)
app.include_router(rag_router)
app.include_router(llm_router)
app.include_router(routing_router)
app.include_router(prompts_router)
app.include_router(optimization_router)
app.include_router(multi_agent_router)
app.include_router(graph_router)
app.include_router(community_router)
app.include_router(rewrite_router)
app.include_router(exporting_router)
app.include_router(cloud_router)


@app.get('/health', tags=['system'])
async def health():
    return {'ok': True, 'env': settings.app_env, 'redis': settings.redis_url, 'version': '0.8.0', 'mode': 'watermark_lab'}


@app.get('/ready', tags=['system'])
async def ready(request: Request):
    try:
        await request.app.state.redis.ping()
        return {'ready': True}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get('/', include_in_schema=False)
async def root():
    return FileResponse(WEB_ROOT / 'index.html')
