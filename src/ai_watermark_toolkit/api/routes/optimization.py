from fastapi import APIRouter
from pydantic import BaseModel
from ...optimization.service import PromptOptimizationService

router = APIRouter(prefix='/api/optimization', tags=['optimization'])
svc = PromptOptimizationService()


class OptimizeRequest(BaseModel):
    system: str


@router.get('/baselines', summary='List baseline variants (demo)')
def baselines(system: str):
    return {'baselines': svc.variants(system)}


@router.post('/candidates', summary='Generate candidate variants')
def candidates(req: OptimizeRequest):
    return {'candidates': svc.variants(req.system)}


@router.post('/score', summary='Score a candidate (demo heuristic)')
def score(req: dict):
    candidate = req.get('candidate', '')
    return {
        'candidate': candidate,
        'score': 0.5 + min(0.5, len(candidate) / 2000),
        'note': 'Demo heuristic: length-based placeholder.'
    }


@router.post('/optimize', summary='Optimize a system prompt (demo)')
def optimize(req: OptimizeRequest):
    return {'variants': svc.variants(req.system)}


@router.post('/promote', summary='Promote a variant (demo no-op)')
def promote(req: OptimizeRequest):
    variants = svc.variants(req.system)
    return {'promoted': variants[0] if variants else None}
