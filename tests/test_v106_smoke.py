from ai_watermark_toolkit.documents.service import DocumentService
from ai_watermark_toolkit.pdf.service import PDFService
from ai_watermark_toolkit.rag.chunking import TextChunker
from ai_watermark_toolkit.rewrite.service import RewriteService
from ai_watermark_toolkit.routing.service import ModelRoutingService


def test_rewrite_smoke():
    svc = RewriteService()
    result = svc.rewrite("this is really just a simple test.", mode="plain", preserve=False)
    assert "simple test" in result["rewritten"].lower()


def test_routing_smoke(tmp_path):
    svc = ModelRoutingService(path=tmp_path / "routing.json")
    decision = svc.decide(task="general")
    assert decision["selected"]["id"]


def test_chunker_smoke():
    chunker = TextChunker()
    chunks = chunker.split_with_metadata("Alpha. Beta. Gamma. Delta." * 100, chunk_size=120, overlap=20)
    assert len(chunks) >= 2
    assert chunks[0]["chunk_id"] == "chunk-1"


def test_pdf_smoke():
    svc = PDFService()
    result = svc.extract_text("Line 1\nLine 2\nLine 3")
    assert result["summary"]["line_count"] == 3


def test_documents_smoke():
    svc = DocumentService()
    result = svc.export("Titel", "Inhalt", fmt="md", metadata={"author": "demo"})
    assert "# Titel" in result["content"]
