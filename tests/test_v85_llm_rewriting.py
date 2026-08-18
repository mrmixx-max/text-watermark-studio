import json
from pathlib import Path


def test_llm_route_and_mcp_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / 'src/ai_watermark_toolkit/api/routes/llm.py').exists()
    assert (root / 'src/ai_watermark_toolkit/llm/providers.py').exists()
    data = json.loads((root / 'mcp/tools.json').read_text(encoding='utf-8'))
    names = {tool['name'] for tool in data['tools']}
    assert 'llm_status' in names
    assert 'llm_configure' in names
    assert 'llm_rewrite' in names
