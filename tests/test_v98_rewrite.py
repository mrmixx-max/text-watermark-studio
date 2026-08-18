import json
from pathlib import Path


def test_rewrite_files_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / "src/ai_watermark_toolkit/rewrite/service.py").exists()
    assert (root / "src/ai_watermark_toolkit/api/routes/rewrite.py").exists()
    tools = json.loads((root / "mcp/tools.json").read_text(encoding="utf-8"))["tools"]
    assert any(t["name"] == "rewrite_run" for t in tools)
