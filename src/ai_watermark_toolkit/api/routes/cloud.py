from fastapi import APIRouter, Request
from pydantic import BaseModel

from ...cloud.service import CloudUploadService
from ..response_utils import respond

router = APIRouter(prefix='/api/cloud', tags=['cloud'])
svc = CloudUploadService()

class UploadRequest(BaseModel):
    filename: str
    content_type: str
    size_bytes: int
    provider: str = 's3'
    purpose: str = 'general'

class ConfirmRequest(BaseModel):
    upload_id: str
    etag: str | None = None

@router.post('/request-upload')
def request_upload(req: UploadRequest, request: Request):
    return respond(request, svc.request_upload(req.filename, req.content_type, req.size_bytes, req.provider, req.purpose))

@router.post('/confirm-upload')
def confirm_upload(req: ConfirmRequest, request: Request):
    return respond(request, svc.confirm_upload(req.upload_id, req.etag))

@router.get('/uploads')
def list_uploads(request: Request):
    return respond(request, svc.list_uploads())
