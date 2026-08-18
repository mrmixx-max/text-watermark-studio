import json
from pathlib import Path


def test_local_llm_files_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / 'src/ai_watermark_toolkit/llm/service.py').exists()
    assert (root / 'src/ai_watermark_toolkit/api/routes/llm.py').exists()
    assert (root / 'data/local_llm.json').exists()
    tools = json.loads((root / 'mcp/tools.json').read_text(encoding='utf-8'))['tools']
    names = {t['name'] for t in tools}
    assert 'llm_status' in names and 'llm_configure' in names
