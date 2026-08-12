from __future__ import annotations

from fastapi import Header, HTTPException
from ...core.config import settings


def require_api_key(x_api_key: str | None = Header(default=None)):
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail='invalid_api_key')
