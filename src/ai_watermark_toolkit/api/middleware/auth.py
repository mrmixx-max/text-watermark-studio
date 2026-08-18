from __future__ import annotations

import hmac

from fastapi import Header, HTTPException

from ...core.config import settings


def require_api_key(x_api_key: str | None = Header(default=None)):
    """API-key gate — fail-closed outside development (P0-1).

    - ``AI_WM_API_KEY`` configured: the header must match exactly
      (``invalid_api_key`` otherwise). Comparison uses hmac.compare_digest
      to prevent timing side-channel attacks.
    - No key configured AND ``AI_WM_ENV`` is not ``development``: the API is
      fail-CLOSED — every request is rejected until the operator sets
      ``AI_WM_API_KEY``. An open-by-default API on a non-dev deployment is
      how forensic endpoints (embed/report-sign/finding) get abused.
    - No key configured AND ``AI_WM_ENV == development``: open (local studio
      convenience, documented; the dev server binds 127.0.0.1 by default).
    """
    if settings.api_key:
        if not hmac.compare_digest(x_api_key or '', settings.api_key):
            raise HTTPException(status_code=401, detail='invalid_api_key')
        return
    env = getattr(settings, 'app_env', 'development')
    if env != 'development':
        raise HTTPException(
            status_code=401,
            detail=('api_key_not_configured: set AI_WM_API_KEY '
                    '(API is fail-closed outside development)'),
        )
