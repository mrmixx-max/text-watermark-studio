from pathlib import Path


def test_ops_files_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / "src/ai_watermark_toolkit/api/routes/ops.py").exists()
    assert (root / "src/ai_watermark_toolkit/api/middleware/request_id.py").exists()
    assert (root / "src/ai_watermark_toolkit/api/middleware/prometheus.py").exists()
    assert (root / "src/ai_watermark_toolkit/observability/metrics.py").exists()


def test_env_example_contains_metrics_flag():
    root = Path(__file__).resolve().parents[1]
    text = (root / ".env.example").read_text(encoding="utf-8")
    assert "AI_WM_ENABLE_METRICS=" in text
