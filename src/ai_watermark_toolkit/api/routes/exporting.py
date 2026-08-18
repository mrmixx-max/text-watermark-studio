from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, model_validator

from ...exporting.service import ExportService
from ..response_utils import parse_metadata_field, respond

router = APIRouter(prefix='/api/export', tags=['export'])
svc = ExportService()

class ExportRequest(BaseModel):
    title: str = 'Export'
    text: str
    format: str = Field(default='md')
    style: str = Field(default='clean')
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode='before')
    @classmethod
    def normalize(cls, data):
        if isinstance(data, dict):
            data['metadata'] = parse_metadata_field(data.get('metadata'))
        return data

@router.post('/run')
def run_export(req: ExportRequest, request: Request):
    return respond(request, svc.export(req.title, req.text, req.format, req.style, req.metadata))
