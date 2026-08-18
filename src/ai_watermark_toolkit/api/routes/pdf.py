from __future__ import annotations

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel

from ...pdf.service import PDFService

router = APIRouter(prefix='/api/pdf', tags=['pdf'])
svc = PDFService()


class ExtractRequest(BaseModel):
    text: str


@router.get('/strategy', summary='PDF processing strategy info')
def strategy(filename: str = 'document.pdf', size_bytes: int | None = None):
    return {
        'engine': 'demo-pdf-service',
        'filename': filename,
        'size_bytes': size_bytes,
        'note': 'Demo stub: returns text summaries; PyMuPDF path is planned.'
    }


@router.post('/extract', summary='Extract text summary from PDF text layer')
def extract(req: ExtractRequest):
    return svc.extract_text(req.text)


@router.post('/extract-window', summary='Extract a page window (demo: text-only)')
async def extract_window(
    file: UploadFile = File(...),  # noqa: B008
    start_page: int = Form(0),
    end_page: int | None = Form(None),
):
    blob = await file.read()
    text = blob.decode('utf-8', errors='replace')
    result = svc.extract_text(text)
    result['window'] = {'start_page': start_page, 'end_page': end_page}
    return result
