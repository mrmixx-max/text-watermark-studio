from pathlib import Path
import py_compile

def test_python_sources_compile():
    root = Path(__file__).resolve().parents[1]
    for p in (root / 'src').rglob('*.py'):
        py_compile.compile(str(p), doraise=True)

def test_ui_uses_hx_request_headers():
    root = Path(__file__).resolve().parents[1]
    html = (root / 'src/ai_watermark_toolkit/web/index.html').read_text(encoding='utf-8')
    assert 'HX-Request' in html
