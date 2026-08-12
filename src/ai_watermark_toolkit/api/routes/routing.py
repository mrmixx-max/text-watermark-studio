from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, model_validator
from typing import Any, Dict
from ...routing.service import ModelRoutingService
from ..response_utils import respond, checkbox_to_bool

router = APIRouter(prefix='/api/routing', tags=['routing'])
svc = ModelRoutingService()

class DecideRequest(BaseModel):
    task: str = 'general'
    profile: str = 'default'
    need_large_context: bool = False
    privacy_mode: bool = False

    @model_validator(mode='before')
    @classmethod
    def normalize(cls, data):
        if isinstance(data, dict):
            data['need_large_context'] = checkbox_to_bool(data.get('need_large_context'))
            data['privacy_mode'] = checkbox_to_bool(data.get('privacy_mode'))
        return data

class ConfigureRequest(BaseModel):
    profile: str = 'default'
    config: Dict[str, Any] = Field(default_factory=dict)

@router.get('/status')
def status(request: Request):
    return respond(request, svc.status())

@router.post('/decide')
def decide(req: DecideRequest, request: Request):
    return respond(request, svc.decide(req.task, req.profile, req.need_large_context, req.privacy_mode))

@router.post('/configure')
def configure(req: ConfigureRequest, request: Request):
    return respond(request, svc.configure(req.model_dump()))
