from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ...rag.chunking import TextChunker

router = APIRouter(prefix="/api/rag", tags=["rag"])
chunker = TextChunker()


class ChunkRequest(BaseModel):
    text: str
    strategy: str = "recursive"
    chunk_size: int = 512
    overlap: int = 64


@router.get("/strategies", summary="List available RAG chunking strategies")
def strategies():
    return {
        "default": "recursive",
        "recommended_defaults": {
            "recursive": {"chunk_size": 512, "overlap": 64},
            "fixed": {"chunk_size": 512, "overlap": 64},
            "markdown": {"chunk_size": 700, "overlap": 80},
            "page": {"chunk_size": 700, "overlap": 80},
            "semantic_lite": {"chunk_size": 512, "overlap": 64},
        },
        "strategies": ["fixed", "recursive", "markdown", "page", "semantic_lite"],
    }


@router.post("/chunk", summary="Chunk text for RAG ingestion")
def chunk(req: ChunkRequest):
    chunks = chunker.split_with_metadata(req.text, chunk_size=req.chunk_size, overlap=req.overlap)
    return {
        "strategy": req.strategy,
        "chunk_size": req.chunk_size,
        "overlap": req.overlap,
        "chunks": chunks,
        "chunk_count": len(chunks),
    }
