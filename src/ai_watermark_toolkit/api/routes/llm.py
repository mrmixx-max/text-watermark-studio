from fastapi import APIRouter, Request
from pydantic import BaseModel, model_validator
from ...llm.service import LocalLLMService
from ..response_utils import respond, checkbox_to_bool

router = APIRouter(prefix='/api/llm', tags=['llm'])
svc = LocalLLMService()

class ConfigureRequest(BaseModel):
    server_base_url: str | None = None
    model_variant: str | None = None
    installed: bool | None = None

    @model_validator(mode='before')
    @classmethod
    def normalize(cls, data):
        if isinstance(data, dict):
            if 'installed' in data:
                data['installed'] = checkbox_to_bool(data.get('installed'))
        return data

@router.get('/status')
def status(request: Request):
    return respond(request, svc.status())

@router.post('/configure')
def configure(req: ConfigureRequest, request: Request):
    return respond(request, svc.configure(req.server_base_url, req.model_variant, req.installed))
