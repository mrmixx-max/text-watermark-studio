from __future__ import annotations

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

HTTP_REQUESTS_TOTAL = Counter('tws_http_requests_total', 'Total HTTP requests', ['method', 'route', 'status'])
HTTP_REQUEST_DURATION_SECONDS = Histogram('tws_http_request_duration_seconds', 'HTTP request duration', ['method', 'route'])
STREAM_JOBS_TOTAL = Counter('tws_stream_jobs_total', 'Total stream jobs enqueued')
DLQ_REPLAYS_TOTAL = Counter('tws_dlq_replays_total', 'Total DLQ replays')
STREAM_PENDING_GAUGE = Gauge('tws_stream_pending', 'Pending stream messages')
STREAM_DEAD_LETTER_GAUGE = Gauge('tws_stream_dead_letter', 'Dead letter jobs')


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
