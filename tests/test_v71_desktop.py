from pathlib import Path


def test_desktop_files_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / "desktop/python_gui/app.py").exists()
    assert (root / "desktop/packaging/windows/build.ps1").exists()
    assert (root / "desktop/packaging/macos/build.sh").exists()
    assert (root / "desktop/packaging/linux/build.sh").exists()
