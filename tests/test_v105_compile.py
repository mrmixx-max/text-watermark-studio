import py_compile
from pathlib import Path


def test_all_python_compiles(tmp_path):
    """Every .py under src/ must compile.

    py_compile writes its .pyc into a per-run tmp_path instead of the real
    __pycache__ — concurrent pytest processes would otherwise race on the
    shared .pyc files (Windows PermissionError under load).
    """
    root = Path(__file__).resolve().parents[1]
    for i, p in enumerate((root / "src").rglob("*.py")):
        py_compile.compile(str(p), doraise=True, cfile=str(tmp_path / f"v105-{i}.pyc"))
