from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv('AI_WM_APP_NAME', 'Text Watermark Studio v8')
    app_env: str = os.getenv('AI_WM_ENV', 'development')
    host: str = os.getenv('AI_WM_HOST', '127.0.0.1')
    port: int = int(os.getenv('AI_WM_PORT', '8080'))
    cors_origins: str = os.getenv('AI_WM_CORS_ORIGINS', '*')
    log_level: str = os.getenv('AI_WM_LOG_LEVEL', 'INFO')
    api_key: str = os.getenv('AI_WM_API_KEY', '')
    rate_limit_requests: int = int(os.getenv('AI_WM_RATE_LIMIT_REQUESTS', '60'))
    rate_limit_window_sec: int = int(os.getenv('AI_WM_RATE_LIMIT_WINDOW_SEC', '60'))
    redis_url: str = os.getenv('AI_WM_REDIS_URL', 'redis://localhost:6379/0')
    stream_key: str = os.getenv('AI_WM_STREAM_KEY', 'tws:stream:jobs')
    queue_name: str = os.getenv('AI_WM_QUEUE_NAME', 'tws:queue:jobs')
    dlq_stream_key: str = os.getenv('AI_WM_DLQ_STREAM_KEY', 'tws:stream:jobs:dlq')
    stream_group: str = os.getenv('AI_WM_STREAM_GROUP', 'tws-workers')
    consumer_name: str = os.getenv('AI_WM_CONSUMER_NAME', 'studio-consumer-1')
    min_idle_ms: int = int(os.getenv('AI_WM_MIN_IDLE_MS', '60000'))
    max_retries: int = int(os.getenv('AI_WM_MAX_RETRIES', '3'))
    retry_backoff_ms: int = int(os.getenv('AI_WM_RETRY_BACKOFF_MS', '5000'))
    stream_maxlen: int = int(os.getenv('AI_WM_STREAM_MAXLEN', '10000'))


settings = Settings()
