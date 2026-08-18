import json
from pathlib import Path


def test_export_files_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / "src/ai_watermark_toolkit/exporting/service.py").exists()
    assert (root / "src/ai_watermark_toolkit/api/routes/exporting.py").exists()
    tools = json.loads((root / "mcp/tools.json").read_text(encoding="utf-8"))["tools"]
    assert any(t["name"] == "export_run" for t in tools)
