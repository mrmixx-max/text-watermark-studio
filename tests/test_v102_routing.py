import json
from pathlib import Path


def test_routing_files_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / "src/ai_watermark_toolkit/routing/service.py").exists()
    assert (root / "src/ai_watermark_toolkit/api/routes/routing.py").exists()
    assert (root / "data/model_routing.json").exists()
    tools = json.loads((root / "mcp/tools.json").read_text(encoding="utf-8"))["tools"]
    names = {t["name"] for t in tools}
    assert "routing_status" in names and "routing_decide" in names and "routing_configure" in names
