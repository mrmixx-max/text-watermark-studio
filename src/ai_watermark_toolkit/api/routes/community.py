from fastapi import APIRouter, Request
from pydantic import BaseModel
from ...community.service import CommunityService
from ..response_utils import respond
router = APIRouter(prefix='/api/community', tags=['community'])
svc = CommunityService()
class DetectRequest(BaseModel): min_size: int = 2
@router.post('/detect')
def detect(req: DetectRequest, request: Request): return respond(request, svc.detect(req.min_size))
@router.post('/summarize')
def summarize(request: Request): return respond(request, svc.summarize())
@router.get('/list')
def list_communities(request: Request): return respond(request, svc.list())
@router.get('/get')
def get_community(community_id: str, request: Request): return respond(request, svc.get(community_id))
