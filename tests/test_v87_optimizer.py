import json
from pathlib import Path


def test_optimizer_routes_and_tools_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / 'src/ai_watermark_toolkit/optimization/service.py').exists()
    assert (root / 'src/ai_watermark_toolkit/api/routes/optimization.py').exists()
    data = json.loads((root / 'mcp/tools.json').read_text(encoding='utf-8'))
    names = {tool['name'] for tool in data['tools']}
    assert 'opt_optimize' in names and 'opt_promote' in names
