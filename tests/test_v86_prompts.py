from pathlib import Path
import json


def test_prompt_registry_and_routes_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / 'data/prompts/registry.json').exists()
    assert (root / 'src/ai_watermark_toolkit/prompts/service.py').exists()
    assert (root / 'src/ai_watermark_toolkit/api/routes/prompts.py').exists()
    data = json.loads((root / 'mcp/tools.json').read_text(encoding='utf-8'))
    names = {tool['name'] for tool in data['tools']}
    assert 'prompt_templates' in names
    assert 'prompt_render' in names
    assert 'prompt_create_version' in names
    assert 'rewrite_run' in names
    assert 'opt_promote' in names
