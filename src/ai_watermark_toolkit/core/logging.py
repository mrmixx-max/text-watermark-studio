from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            'ts': datetime.now(timezone.utc).isoformat(),
            'level': record.levelname,
            'name': record.name,
            'message': record.getMessage(),
        }, ensure_ascii=False)


def setup_logging(level: str = 'INFO') -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
