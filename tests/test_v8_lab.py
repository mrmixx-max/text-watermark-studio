from pathlib import Path


def test_lab_files_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / "src/ai_watermark_toolkit/lab/service.py").exists()
    assert (root / "src/ai_watermark_toolkit/lab/family_registry.py").exists()
    assert (root / "src/ai_watermark_toolkit/api/routes/lab.py").exists()
    assert (root / "src/ai_watermark_toolkit/lab/families/unicode_zero_width.py").exists()
    assert (root / "src/ai_watermark_toolkit/lab/families/sampling_bias.py").exists()
