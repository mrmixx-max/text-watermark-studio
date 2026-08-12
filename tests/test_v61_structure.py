from pathlib import Path


def test_streams_files_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / 'src/ai_watermark_toolkit/streams/redis_streams.py').exists()
    assert (root / 'src/ai_watermark_toolkit/workers/streams_worker.py').exists()
    assert (root / 'src/ai_watermark_toolkit/api/routes/streams.py').exists()


def test_env_example_contains_stream_settings():
    root = Path(__file__).resolve().parents[1]
    text = (root / '.env.example').read_text(encoding='utf-8')
    assert 'AI_WM_STREAM_KEY=' in text
    assert 'AI_WM_DLQ_STREAM_KEY=' in text
    assert 'AI_WM_MAX_RETRIES=' in text
