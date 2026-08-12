from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from ...prompts.service import PromptRegistryService

router = APIRouter(prefix='/api/prompts', tags=['prompts'])
svc = PromptRegistryService()


class RenderRequest(BaseModel):
    template_id: str
    version: str | None = None
    variables: dict


class CreateTemplateRequest(BaseModel):
    payload: dict


@router.get('/templates', summary='List prompt templates and versions')
def templates():
    return {'templates': svc.list_templates()}


@router.post('/render', summary='Render a prompt template with variables')
def render(req: RenderRequest):
    return svc.render(req.template_id, req.variables, req.version)


@router.post('/create-version', summary='Create a new prompt template version')
def create_version(req: CreateTemplateRequest):
    return svc.create_version(req.payload)
