from __future__ import annotations

from fastapi import APIRouter

from ...schemas.text import TextRequest
from ...services.text_service import TextService

router = APIRouter(prefix="/api", tags=["text"])
service = TextService()


@router.post("/detect")
def detect(req: TextRequest):
    return service.detect(req.text, lang=req.lang)


@router.post("/clean")
def clean(req: TextRequest):
    return service.clean(req.text, nfkc=req.nfkc, fold_confusables=req.fold_confusables)


@router.post("/dilute")
def dilute(req: TextRequest):
    return service.dilute(req.text, intensity=req.intensity)


@router.post("/pipeline")
def pipeline(req: TextRequest):
    return service.pipeline(
        req.text,
        lang=req.lang,
        intensity=req.intensity,
        nfkc=req.nfkc,
        fold_confusables=req.fold_confusables,
        rewrite_mode=req.rewrite_mode,
        aggressive=req.aggressive,
    )
