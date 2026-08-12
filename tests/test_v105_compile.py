from pathlib import Path
import py_compile

def test_all_python_compiles():
    root = Path(__file__).resolve().parents[1]
    for p in (root / 'src').rglob('*.py'):
        py_compile.compile(str(p), doraise=True)
