from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...optimization.service import PromptOptimizationService

router = APIRouter(prefix="/api/optimization", tags=["optimization"])
svc = PromptOptimizationService()


class OptimizeRequest(BaseModel):
    system: str


class PromoteRequest(BaseModel):
    system: str
    template_id: str
    candidate_variant: str | None = None
    version: str | None = None


class RollbackRequest(BaseModel):
    template_id: str
    version: str


@router.get("/evals", summary="List the locked evaluation set")
def evals():
    return {"evals": svc.eval_cases()}


@router.post("/candidates", summary="Generate base + one-variable candidates")
def candidates(req: OptimizeRequest):
    return {"candidates": svc.variants(req.system)}


@router.post("/optimize", summary="Run the evaluator loop (no promotion)")
def optimize(req: OptimizeRequest):
    return svc.optimize(req.system)


@router.post("/promote", summary="Promote winner into the prompt registry")
def promote(req: PromoteRequest):
    try:
        record = svc.promote(req.system, req.template_id, candidate_variant=req.candidate_variant, version=req.version)
        return {"promoted": record}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.get("/history/{template_id}", summary="All versions of a template")
def history(template_id: str):
    return {"history": svc.history(template_id)}


@router.post("/rollback", summary="Restore a previous version as new stable")
def rollback(req: RollbackRequest):
    try:
        record = svc.rollback(req.template_id, req.version)
        return {"restored": record}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
