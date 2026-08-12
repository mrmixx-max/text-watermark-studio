from pathlib import Path
import json


def test_pdf_route_and_mcp_tools_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / 'src/ai_watermark_toolkit/api/routes/pdf.py').exists()
    assert (root / 'src/ai_watermark_toolkit/pdf/service.py').exists()
    data = json.loads((root / 'mcp/tools.json').read_text(encoding='utf-8'))
    names = {tool['name'] for tool in data['tools']}
    assert 'pdf_strategy' in names
    assert 'pdf_extract_window' in names
