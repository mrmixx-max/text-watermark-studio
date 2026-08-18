import json
from pathlib import Path


def test_multi_agent_routes_and_tools_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / 'src/ai_watermark_toolkit/multi_agent/service.py').exists()
    assert (root / 'src/ai_watermark_toolkit/api/routes/multi_agent.py').exists()
    data = json.loads((root / 'mcp/tools.json').read_text(encoding='utf-8'))
    names = {tool['name'] for tool in data['tools']}
    assert 'ma_run' in names and 'ma_promote' in names and 'ma_spec' in names
