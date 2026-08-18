from pathlib import Path


def test_forensics_files_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / "src/ai_watermark_toolkit/forensics/key_registry.py").exists()
    assert (root / "src/ai_watermark_toolkit/forensics/ensemble.py").exists()
    assert (root / "src/ai_watermark_toolkit/forensics/audit.py").exists()
    assert (root / "src/ai_watermark_toolkit/api/routes/forensics.py").exists()


def test_demo_key_registry_present(tmp_path):
    # P0-3-Semantik: Demo-Keys nur mit explizitem seed_demo=True (bzw. am
    # kanonischen Registry-Pfad); explizite Test-Pfade starten leer — sonst
    # fälschen öffentlich bekannte Demo-Secrets frische Installationen.
    from ai_watermark_toolkit.forensics.key_registry import KeyRegistry

    reg_empty = KeyRegistry(str(tmp_path / "keys.json"))
    assert reg_empty.list_keys() == []
    reg_demo = KeyRegistry(str(tmp_path / "demo.json"), seed_demo=True)
    keys = reg_demo.list_keys()
    assert len(keys) >= 2
