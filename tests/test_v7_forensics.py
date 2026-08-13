from pathlib import Path
import json


def test_forensics_files_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / "src/ai_watermark_toolkit/forensics/key_registry.py").exists()
    assert (root / "src/ai_watermark_toolkit/forensics/ensemble.py").exists()
    assert (root / "src/ai_watermark_toolkit/forensics/audit.py").exists()
    assert (root / "src/ai_watermark_toolkit/api/routes/forensics.py").exists()


def test_demo_key_registry_present(tmp_path):
    # Registry-Bootstrap erzeugt Demo-Keys — die Datei selbst ist bewusst
    # untracked (data/ im .gitignore), also über die API testen, nicht über
    # die Datei-Existenz im Checkout.
    from ai_watermark_toolkit.forensics.key_registry import KeyRegistry
    reg = KeyRegistry(str(tmp_path / "keys.json"))
    keys = reg.list_keys()
    assert len(keys) >= 2
