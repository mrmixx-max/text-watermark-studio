import py_compile
from pathlib import Path


def test_python_sources_compile(tmp_path):
    root = Path(__file__).resolve().parents[1]
    for i, p in enumerate((root / "src").rglob("*.py")):
        py_compile.compile(str(p), doraise=True, cfile=str(tmp_path / f"v104-{i}.pyc"))


def test_ui_uses_hx_request_headers():
    root = Path(__file__).resolve().parents[1]
    html = (root / "src/ai_watermark_toolkit/web/index.html").read_text(encoding="utf-8")
    assert "HX-Request" in html
