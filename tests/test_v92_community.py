from pathlib import Path
import json

def test_community_routes_and_tools_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / 'src/ai_watermark_toolkit/community/service.py').exists()
    assert (root / 'src/ai_watermark_toolkit/api/routes/community.py').exists()
    # data/graph/communities.json is a runtime artifact (gitignored); the
    # service creates it on first write. Assert the schema path instead.
    assert (root / 'data/graph/schema.json').exists()
    data = json.loads((root / 'mcp/tools.json').read_text(encoding='utf-8'))
    names = {tool['name'] for tool in data['tools']}
    assert 'community_detect' in names and 'community_summarize' in names
