from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

AUDIT_LOG = Path(__file__).resolve().parents[3] / "data" / "audit.log"


def append_audit(event: str, payload: dict[str, Any]) -> dict[str, Any]:
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "event": event,
        "payload": payload,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def read_audit(limit: int = 100):
    if not AUDIT_LOG.exists():
        return []
    lines = AUDIT_LOG.read_text(encoding="utf-8").splitlines()[-limit:]
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except Exception:
            out.append({"event": "corrupt_line", "raw": line})
    return out


class AuditLogger:
    """Klassen-API um die Funktions-API (append_audit/read_audit).

    Kompatibilitäts-Wrapper: routes/forensics.py erwartet eine Instanz mit
    .write(...) und .read(...). Pfad wird als Ziel für append_audit genutzt
    (Standard bleibt data/audit.log, wenn Pfad None ist).
    """

    def __init__(self, path: str | None = None):
        self.path = path

    def write(self, payload: dict) -> dict:
        event = str(payload.get("event", "unknown"))
        return append_audit(event, payload)

    def read(self, limit: int = 100):
        return read_audit(limit)
