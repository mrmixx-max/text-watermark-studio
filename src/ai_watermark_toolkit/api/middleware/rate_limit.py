from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, limit: int = 60, window_sec: int = 60, exempt_paths: set[str] | None = None):
        super().__init__(app)
        self.limit = limit
        self.window_sec = window_sec
        self.exempt_paths = exempt_paths or {'/health', '/ready', '/docs', '/openapi.json'}
        self.store: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.exempt_paths or request.url.path.startswith('/static'):
            return await call_next(request)
        client = request.client.host if request.client else 'unknown'
        key = f'{client}:{request.url.path}'
        now = time.time()
        q = self.store[key]
        while q and now - q[0] > self.window_sec:
            q.popleft()
        if len(q) >= self.limit:
            retry_after = max(1, int(self.window_sec - (now - q[0])))
            resp = JSONResponse({'error': 'rate_limit_exceeded', 'retry_after': retry_after}, status_code=429)
            resp.headers['X-RateLimit-Limit'] = str(self.limit)
            resp.headers['X-RateLimit-Remaining'] = '0'
            resp.headers['Retry-After'] = str(retry_after)
            return resp
        q.append(now)
        response = await call_next(request)
        response.headers['X-RateLimit-Limit'] = str(self.limit)
        response.headers['X-RateLimit-Remaining'] = str(max(0, self.limit - len(q)))
        return response
