from fastapi import APIRouter, Request
from pydantic import BaseModel, model_validator
from ...rewrite.service import RewriteService
from ..response_utils import respond, checkbox_to_bool

router = APIRouter(prefix='/api/rewrite', tags=['rewrite'])
svc = RewriteService()

class RewriteRequest(BaseModel):
    text: str
    mode: str = 'clarity'
    preserve: bool = True

    @model_validator(mode='before')
    @classmethod
    def normalize(cls, data):
        if isinstance(data, dict):
            data['preserve'] = checkbox_to_bool(data.get('preserve', False))
        return data

@router.post('/run')
def run_rewrite(req: RewriteRequest, request: Request):
    return respond(request, svc.rewrite(req.text, req.mode, req.preserve))
