from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...graph_memory.service import GraphMemoryService

router = APIRouter(prefix="/api/graph", tags=["graph"])
svc = GraphMemoryService()


class NodeRequest(BaseModel):
    node: dict


class EdgeRequest(BaseModel):
    edge: dict


class FactRequest(BaseModel):
    subject: str
    relation: str
    object_: str
    subject_type: str = "Entity"
    object_type: str = "Entity"
    evidence: list | None = None


@router.get("/schema")
def schema():
    return svc.schema()


@router.get("/all")
def all_graph():
    return svc.graph()


@router.post("/node")
def add_node(req: NodeRequest):
    try:
        return svc.add_node(req.node)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/edge")
def add_edge(req: EdgeRequest):
    try:
        return svc.add_edge(req.edge)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/fact")
def fact(req: FactRequest):
    return svc.ingest_fact(req.subject, req.relation, req.object_, req.subject_type, req.object_type, req.evidence)


@router.get("/query")
def query(label: str):
    return svc.query(label)


@router.get("/neighbors")
def neighbors(node_id: str):
    return svc.neighbors(node_id)


@router.get("/subgraph")
def subgraph(seed: str, depth: int = 1):
    return svc.subgraph(seed, depth)
