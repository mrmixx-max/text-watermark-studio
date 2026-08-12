from fastapi.testclient import TestClient

from ai_watermark_toolkit.api.fastapi_app import app


def test_health():
    client = TestClient(app)
    r = client.get('/health')
    assert r.status_code == 200
    assert r.json()['ok'] is True


def test_detect_endpoint():
    client = TestClient(app)
    r = client.post('/api/detect', json={'text': 'Furthermore, this helps.', 'lang': 'en'})
    assert r.status_code == 200
    data = r.json()
    assert 'layers' in data
