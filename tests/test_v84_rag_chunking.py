import json
from pathlib import Path


def test_rag_chunking_route_and_mcp_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / 'src/ai_watermark_toolkit/api/routes/rag.py').exists()
    assert (root / 'src/ai_watermark_toolkit/rag/chunking.py').exists()
    data = json.loads((root / 'mcp/tools.json').read_text(encoding='utf-8'))
    names = {tool['name'] for tool in data['tools']}
    assert 'rag_strategies' in names
    assert 'rag_chunk' in names
