from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from ...lab.service import WatermarkLabService

router = APIRouter(prefix='/api/lab', tags=['lab'])
svc = WatermarkLabService()


class LabTextRequest(BaseModel):
    text: str
    family: str | None = None
    options: dict | None = None


class LabDemoRequest(BaseModel):
    family: str
    secret: str | None = None
    gamma: float | None = None
    bias_strength: float | None = None
    context: int | None = None
    n_tokens: int | None = None
    seed: int | None = None
    prefix: str | None = None


@router.get('/families', summary='List watermarking families')
def families():
    return {'families': svc.families(), 'capabilities': svc.capabilities()}


@router.post('/detect-all', summary='Run demo detectors across all families')
def detect_all(req: LabTextRequest):
    return {'text_length': len(req.text), 'results': svc.detect_all(req.text, req.options)}


@router.post('/embed', summary='Run demo embed operation for one family')
def embed(req: LabTextRequest):
    return svc.embed_with(req.family or '', req.text, req.options)


@router.post('/demo', summary='Run the generation-time sampling-bias proof for one family')
def demo(req: LabDemoRequest):
    options = {k: v for k, v in {
        'secret': req.secret,
        'gamma': req.gamma,
        'bias_strength': req.bias_strength,
        'context': req.context,
        'n_tokens': req.n_tokens,
        'seed': req.seed,
        'prefix': req.prefix,
    }.items() if v is not None}
    return svc.demo_with(req.family, options)


@router.get('/mcp/tools', summary='Export MCP tool manifest')
def mcp_tools():
    from pathlib import Path
    import json
    path = Path(__file__).resolve().parents[4] / 'mcp' / 'tools.json'
    return json.loads(path.read_text(encoding='utf-8'))
