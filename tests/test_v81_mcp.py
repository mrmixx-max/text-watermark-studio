from pathlib import Path
import json


def test_mcp_manifest_exists():
    root = Path(__file__).resolve().parents[1]
    assert (root / 'mcp/tools.json').exists()
    assert (root / 'mcp/mcp.json').exists()
    assert (root / 'hermes/plugins/plugin.json').exists()
    assert (root / 'hermes/skills/text-watermark-studio-lab/SKILL.md').exists()


def test_mcp_manifest_has_tools():
    root = Path(__file__).resolve().parents[1]
    data = json.loads((root / 'mcp/tools.json').read_text(encoding='utf-8'))
    assert len(data['tools']) >= 10
