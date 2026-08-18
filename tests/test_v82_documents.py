import json
from pathlib import Path


def test_document_routes_and_manifest():
    root = Path(__file__).resolve().parents[1]
    assert (root / 'src/ai_watermark_toolkit/api/routes/documents.py').exists()
    data = json.loads((root / 'mcp/tools.json').read_text(encoding='utf-8'))
    names = {tool['name'] for tool in data['tools']}
    assert 'document_formats' in names
    assert 'document_load' in names
    assert 'document_export' in names
