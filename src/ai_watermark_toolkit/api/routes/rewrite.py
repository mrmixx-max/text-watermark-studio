from fastapi import APIRouter, Request
import os
from pydantic import BaseModel, model_validator
from ...rewrite.service import RewriteService
from ..response_utils import respond, checkbox_to_bool

router = APIRouter(prefix='/api/rewrite', tags=['rewrite'])
svc = RewriteService(llm_backend=bool(os.getenv('LOCAL_LLM_ENABLED', '0') == '1'))

class RewriteRequest(BaseModel):
    text: str
    mode: str = 'clarity'
    preserve: bool = True
    use_llm: bool | None = None

    @model_validator(mode='before')
    @classmethod
    def normalize(cls, data):
        if isinstance(data, dict):
            data['preserve'] = checkbox_to_bool(data.get('preserve', False))
        return data

@router.post('/run')
def run_rewrite(req: RewriteRequest, request: Request):
    return respond(request, svc.rewrite(req.text, req.mode, req.preserve, use_llm=req.use_llm))
