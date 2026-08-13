from pathlib import Path
import py_compile


def test_all_python_compiles_after_deep_debug(tmp_path):
    """Every .py under src/ must compile.

    py_compile writes its .pyc into a per-run tmp_path instead of the real
    __pycache__ of the source tree. That removes the Windows PermissionError
    race where concurrent pytest/xdist processes collided on the same .pyc
    files, making this test fail spuriously under full load.
    """
    root = Path(__file__).resolve().parents[1]
    cache_dir = tmp_path / "pycache"
    cache_dir.mkdir()
    for p in (root / "src").rglob("*.py"):
        py_compile.compile(
            str(p),
            doraise=True,
            cfile=str(cache_dir / (p.name + ".pyc")),
        )
