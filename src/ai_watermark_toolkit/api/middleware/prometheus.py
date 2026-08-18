from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware

from ...observability.metrics import HTTP_REQUEST_DURATION_SECONDS, HTTP_REQUESTS_TOTAL


class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        route = request.url.path
        method = request.method
        start = time.perf_counter()
        response = await call_next(request)
        status = str(response.status_code)
        HTTP_REQUESTS_TOTAL.labels(method=method, route=route, status=status).inc()
        HTTP_REQUEST_DURATION_SECONDS.labels(method=method, route=route).observe(time.perf_counter() - start)
        return response
