from pathlib import Path
import json


def test_debug_helpers_and_routes_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / 'src/ai_watermark_toolkit/api/response_utils.py').exists()
    text = (root / 'src/ai_watermark_toolkit/api/routes/exporting.py').read_text(encoding='utf-8')
    assert 'parse_metadata_field' in text
    text2 = (root / 'src/ai_watermark_toolkit/api/routes/routing.py').read_text(encoding='utf-8')
    assert 'checkbox_to_bool' in text2
