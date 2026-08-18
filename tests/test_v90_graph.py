import json
from pathlib import Path


def test_graph_routes_and_tools_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / "src/ai_watermark_toolkit/graph_memory/service.py").exists()
    assert (root / "src/ai_watermark_toolkit/api/routes/graph.py").exists()
    assert (root / "data/graph/schema.json").exists()
    data = json.loads((root / "mcp/tools.json").read_text(encoding="utf-8"))
    names = {tool["name"] for tool in data["tools"]}
    assert "graph_ingest_fact" in names and "graph_subgraph" in names and "graph_schema" in names
