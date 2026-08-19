"""Tests for report.py"""

import json

from ai_watermark_toolkit.report import sha256_text, write_json


def test_sha256_text():
    result = sha256_text("hello")
    assert result.startswith("sha256:")
    assert len(result) == 7 + 64


def test_write_json(tmp_path):
    path = tmp_path / "test.json"
    data = {"key": "value", "number": 42}
    write_json(str(path), data)
    assert path.exists()
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded == data
