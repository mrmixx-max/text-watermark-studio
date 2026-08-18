from fastapi.testclient import TestClient

from ai_watermark_toolkit.api.fastapi_app import app


def test_diff_endpoint():
    client = TestClient(app)
    r = client.post("/api/studio/diff", json={"original": "a\nb", "modified": "a\nc"})
    assert r.status_code == 200
    data = r.json()
    assert len(data["rows"]) == 2


def test_export_zip_endpoint():
    client = TestClient(app)
    r = client.post(
        "/api/studio/export/zip", json={"text": "Furthermore, this helps.", "lang": "en", "intensity": "standard"}
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
