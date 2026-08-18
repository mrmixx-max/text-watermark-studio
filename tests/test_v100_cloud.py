import json
from pathlib import Path


def test_cloud_files_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / "src/ai_watermark_toolkit/cloud/service.py").exists()
    assert (root / "src/ai_watermark_toolkit/api/routes/cloud.py").exists()
    tools = json.loads((root / "mcp/tools.json").read_text(encoding="utf-8"))["tools"]
    names = {t["name"] for t in tools}
    assert "cloud_request_upload" in names and "cloud_confirm_upload" in names
