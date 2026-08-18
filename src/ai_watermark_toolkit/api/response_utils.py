from __future__ import annotations

import json

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse


def wants_hx_html(request: Request) -> bool:
    return request.headers.get("HX-Request", "").lower() == "true"


def render_payload(payload):
    safe = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    return (
        '<pre class="overflow-x-auto whitespace-pre-wrap rounded-xl border border-white/10 bg-black/30 p-4 text-xs text-emerald-200">'
        + safe
        + "</pre>"
    )


def respond(request: Request, payload):
    if wants_hx_html(request):
        return HTMLResponse(render_payload(payload))
    # JSONResponse has no default= kwarg; pre-serialize non-JSON-safe values
    # (dataclasses, UUIDs, Path, sets) via json.dumps with default=str.
    if isinstance(payload, (str, int, float, bool, type(None))):
        return JSONResponse(payload)
    return JSONResponse(json.loads(json.dumps(payload, ensure_ascii=False, default=str)))


def parse_metadata_field(metadata):
    if metadata in (None, "", {}):
        return {}
    if isinstance(metadata, dict):
        return metadata
    try:
        return json.loads(metadata)
    except Exception:
        return {"raw_metadata": str(metadata)}


def get_redis(request: Request):
    """Return app.state.redis or raise a clean 503 when Redis is unavailable.

    The API uses an async Redis client for queues/streams/ops. Without a
    configured Redis service these endpoints have no backend; a bare
    AttributeError would surface as a 500, which is misleading.
    """
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="Redis backend unavailable")
    return redis


def checkbox_to_bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).lower() in {"true", "1", "yes", "on"}
