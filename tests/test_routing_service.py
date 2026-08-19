"""Tests for routing/service.py"""

import pytest

from ai_watermark_toolkit.routing import service


@pytest.fixture
def svc(tmp_path):
    return service.ModelRoutingService(path=tmp_path / "routing.json")


class TestModelRoutingService:
    def test_init_creates_file(self, svc):
        assert svc.path.exists()

    def test_load_returns_data(self, svc):
        data = svc.load()
        assert "profiles" in data
        assert "default" in data["profiles"]

    def test_save_writes_data(self, svc):
        data = {"profiles": {}, "last_decision": "test", "history": []}
        saved = svc.save(data)
        assert saved["last_decision"] == "test"
        assert svc.path.exists()

    def test_load_missing_file(self, tmp_path):
        svc = service.ModelRoutingService(path=tmp_path / "missing.json")
        data = svc.load()
        assert "profiles" in data
