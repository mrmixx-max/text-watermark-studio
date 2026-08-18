from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from ...core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Template / static paths
# ---------------------------------------------------------------------------
WEB_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = WEB_DIR / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
router = APIRouter(tags=["dashboard"])

# In-memory counters (module-level so SSE + pages share them)
_stats = {
    "detections_total": 0,
    "detections_last_minute": 0,
    "embeds_total": 0,
    "cleans_total": 0,
    "reports_total": 0,
    "last_detection_ts": 0.0,
    "last_embed_ts": 0.0,
    "last_clean_ts": 0.0,
    "last_report_ts": 0.0,
    "start_ts": time.time(),
    "recent_detections": [],  # list of {ts, verdict, signal, text_preview}
}


def bump_stat(name: str, **ctx) -> None:
    """Update a dashboard statistic (called from API routes)."""
    _stats[f"{name}_total"] = _stats.get(f"{name}_total", 0) + 1
    _stats[f"last_{name}_ts"] = time.time()
    if name == "detections":
        det = {
            "ts": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
            "verdict": ctx.get("verdict", "unknown"),
            "signal": ctx.get("signal", ""),
            "text_preview": (ctx.get("text", "") or "")[:80],
        }
        _stats["recent_detections"].insert(0, det)
        _stats["recent_detections"] = _stats["recent_detections"][:20]


def get_stats() -> dict:
    """Return a snapshot of current dashboard statistics."""
    now = time.time()
    uptime = now - _stats["start_ts"]
    # detections in last 60s
    recent = [
        d for d in _stats["recent_detections"]
        if now - _iso_to_ts(d["ts"]) < 60
    ]
    _stats["detections_last_minute"] = len(recent)
    return {
        "detections_total": _stats["detections_total"],
        "detections_last_minute": _stats["detections_last_minute"],
        "embeds_total": _stats["embeds_total"],
        "cleans_total": _stats["cleans_total"],
        "reports_total": _stats["reports_total"],
        "recent_detections": _stats["recent_detections"][:10],
        "uptime_seconds": int(uptime),
        "version": "2.4.1",
        "env": settings.app_env,
    }


def _iso_to_ts(iso: str) -> float:
    try:
        return datetime.fromisoformat(iso).timestamp()
    except (ValueError, TypeError):
        return 0.0


# ---------------------------------------------------------------------------
# SSE: real-time stats stream
# ---------------------------------------------------------------------------
async def stats_event_generator():
    """Yield SSE events with current stats every 2 seconds."""
    while True:
        try:
            data = json.dumps(get_stats(), default=str)
            yield f"event: stats\ndata: {data}\n\n"
            await asyncio.sleep(2)
        except asyncio.CancelledError:
            break
        except (ValueError, RuntimeError) as exc:
            logger.debug("SSE generator error: %s", exc)
            await asyncio.sleep(2)


@router.get("/events/stats", summary="Real-time stats via SSE")
async def sse_stats():
    """Server-Sent Events stream of dashboard statistics."""
    return StreamingResponse(
        stats_event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Page routes (Jinja2 SSR)
# ---------------------------------------------------------------------------
@router.get("/", response_class=HTMLResponse)
async def page_overview(request: Request):
    return templates.TemplateResponse(
        request, "overview.html", {"stats": get_stats(), "page": "overview"}
    )


@router.get("/watermark", response_class=HTMLResponse)
async def page_watermark(request: Request):
    return templates.TemplateResponse(
        request, "watermark.html", {"stats": get_stats(), "page": "watermark"}
    )


@router.get("/files", response_class=HTMLResponse)
async def page_files(request: Request):
    return templates.TemplateResponse(
        request, "files.html", {"stats": get_stats(), "page": "files"}
    )


@router.get("/reports", response_class=HTMLResponse)
async def page_reports(request: Request):
    return templates.TemplateResponse(
        request, "reports.html", {"stats": get_stats(), "page": "reports"}
    )


@router.get("/settings", response_class=HTMLResponse)
async def page_settings(request: Request):
    return templates.TemplateResponse(
        request, "settings.html", {"stats": get_stats(), "page": "settings"}
    )


# ---------------------------------------------------------------------------
# Mount helper — call from fastapi_app.py to wire in the dashboard
# ---------------------------------------------------------------------------
def mount_web_dashboard(app):
    """Include the dashboard router and serve static files."""
    # Form-data adapter endpoints for HTMX (mounted first so /dashboard/api/* works)
    from .forms import router as forms_router
    app.include_router(forms_router)
    # Page routes at /dashboard/
    app.include_router(router, prefix="/dashboard")
