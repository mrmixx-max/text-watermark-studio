from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

UPLOADS = Path(__file__).resolve().parents[3] / "data" / "uploads.json"


class CloudUploadService:
    def _load(self):
        if not UPLOADS.exists():
            return []
        return json.loads(UPLOADS.read_text(encoding="utf-8"))

    def _save(self, items):
        UPLOADS.parent.mkdir(parents=True, exist_ok=True)
        UPLOADS.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    def request_upload(
        self,
        filename: str,
        content_type: str,
        size_bytes: int,
        provider: str = "s3",
        purpose: str = "general",
    ) -> dict[str, Any]:
        safe_name = filename.replace("..", "").replace("/", "_").replace("\\", "_")
        item = {
            "upload_id": str(uuid4()),
            "filename": safe_name,
            "content_type": content_type,
            "size_bytes": int(size_bytes),
            "provider": provider,
            "purpose": purpose,
            "status": "requested",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        items = self._load()
        items.append(item)
        self._save(items)
        return item

    def confirm_upload(self, upload_id: str, etag: str | None = None) -> dict[str, Any]:
        items = self._load()
        for item in items:
            if item["upload_id"] == upload_id:
                item["status"] = "confirmed"
                item["etag"] = etag
                item["confirmed_at"] = datetime.now(timezone.utc).isoformat()
                self._save(items)
                return item
        return {"error": "upload_not_found", "upload_id": upload_id}

    def list_uploads(self):
        return self._load()
