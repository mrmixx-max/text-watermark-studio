from pathlib import Path
import json


def test_forensics_files_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / "src/ai_watermark_toolkit/forensics/key_registry.py").exists()
    assert (root / "src/ai_watermark_toolkit/forensics/ensemble.py").exists()
    assert (root / "src/ai_watermark_toolkit/forensics/audit.py").exists()
    assert (root / "src/ai_watermark_toolkit/api/routes/forensics.py").exists()


def test_demo_key_registry_present():
    root = Path(__file__).resolve().parents[1]
    data = json.loads((root / "data/key_registry.json").read_text(encoding="utf-8"))
    assert len(data["keys"]) >= 2
