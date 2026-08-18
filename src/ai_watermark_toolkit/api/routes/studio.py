from __future__ import annotations

import io
import json
import zipfile

from fastapi import APIRouter, Response
from pydantic import BaseModel

from ...services.text_service import TextService

router = APIRouter(prefix="/api/studio", tags=["studio"])
service = TextService()


class DiffRequest(BaseModel):
    original: str
    modified: str


class ExportRequest(BaseModel):
    text: str
    lang: str = "auto"
    intensity: str = "standard"


@router.post("/diff", summary="Create a simple line diff", description="Returns a compact before/after diff preview.")
def diff(req: DiffRequest):
    a = req.original.splitlines()
    b = req.modified.splitlines()
    rows = []
    max_len = max(len(a), len(b))
    for i in range(max_len):
        left = a[i] if i < len(a) else ""
        right = b[i] if i < len(b) else ""
        rows.append({"line": i + 1, "original": left, "modified": right, "changed": left != right})
    return {"rows": rows}


@router.post(
    "/export/zip",
    summary="Export pipeline output as ZIP",
    description="Runs pipeline and returns a zip containing text and report.",
)
def export_zip(req: ExportRequest):
    result = service.pipeline(req.text, lang=req.lang, intensity=req.intensity)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("output.txt", result["text"])
        zf.writestr("report.json", json.dumps(result["report"], ensure_ascii=False, indent=2))
    return Response(
        buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="text-watermark-studio-export.zip"'},
    )
