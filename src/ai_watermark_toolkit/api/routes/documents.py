from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ...documents.service import DocumentService

router = APIRouter(prefix="/api/documents", tags=["documents"])
svc = DocumentService()


class DocumentLoadRequest(BaseModel):
    filename: str
    content: str


class DocumentExportRequest(BaseModel):
    text: str
    target_format: str


@router.get("/formats", summary="List supported document formats")
def formats():
    return svc.supported()


@router.post("/load", summary="Normalize an incoming document payload to lab text")
def load(req: DocumentLoadRequest):
    return svc.load_text(req.filename, req.content).to_dict()


@router.post("/export", summary="Export normalized text to a target document format")
def export(req: DocumentExportRequest):
    return svc.export_text(req.text, req.target_format)
