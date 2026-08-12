from fastapi import APIRouter
from pydantic import BaseModel
from ...multi_agent.service import MultiAgentService

router = APIRouter(prefix='/api/multi-agent', tags=['multi-agent'])
svc = MultiAgentService()


class RunRequest(BaseModel):
    text: str


@router.get('/spec', summary='Multi-agent loop spec (demo)')
def spec():
    return {
        'agents': ['generator', 'critic', 'refiner'],
        'loop': 'generator -> critic -> refiner (demo)',
        'note': 'Demo stub: single-pass run with two drafts.'
    }


@router.post('/run', summary='Run the multi-agent feedback loop')
def run(req: RunRequest):
    return svc.run(req.text)


@router.post('/promote', summary='Promote a draft (demo no-op)')
def promote(req: RunRequest):
    result = svc.run(req.text)
    result['promoted'] = True
    return result
