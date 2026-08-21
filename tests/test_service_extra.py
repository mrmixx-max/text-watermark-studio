"""Tests for LocalLLMService new methods: list_models, use_model, _ollama."""

import pytest

from ai_watermark_toolkit.llm.service import LocalLLMService


@pytest.fixture
def tmp_cfg(tmp_path):
    return tmp_path / "llm.json"


@pytest.fixture
def svc(tmp_cfg):
    return LocalLLMService(path=tmp_cfg)


def test_list_models_empty(svc):
    assert svc.list_models() == []


def test_list_models_with_variant(svc):
    svc.configure(model_variant="gemma-4-E4B")
    models = svc.list_models()
    assert len(models) == 1
    assert models[0]["name"] == "gemma-4-E4B"
    assert models[0]["installed"] is False


def test_list_models_installed(svc):
    svc.configure(model_variant="qwen3-30b-a3b", installed=True)
    models = svc.list_models()
    assert models[0]["installed"] is True


def test_use_model(svc):
    result = svc.use_model("lfm2-24b")
    assert result["model_variant"] == "lfm2-24b"
    assert svc.load()["model_variant"] == "lfm2-24b"


def test_use_model_updates_config(svc):
    svc.configure(model_variant="old-model")
    svc.use_model("new-model")
    assert svc.load()["model_variant"] == "new-model"


def test_configure_and_get_sampling(svc):
    from ai_watermark_toolkit.llm.service import SamplingConfig

    cfg = SamplingConfig(temperature=0.5, top_p=0.9)
    svc.configure_sampling(cfg)
    result = svc.get_sampling_config()
    assert result.temperature == 0.5
    assert result.top_p == 0.9


def test_configure_sampling_dict(svc):
    svc.configure_sampling({"temperature": 0.3, "top_k": 40})
    result = svc.get_sampling_config()
    assert result.temperature == 0.3
    assert result.top_k == 40


def test_status(svc):
    svc.configure(model_variant="test-model", server_base_url="http://localhost:11434")
    status = svc.status()
    assert status["model_variant"] == "test-model"
    assert status["server_base_url"] == "http://localhost:11434"


def test_ollama_uses_config_url(svc, monkeypatch):
    """Test that _ollama reads server_base_url from config."""
    svc.configure(server_base_url="http://ollama-test:11434")
    captured = {}

    class FakeResponse:
        def read(self):
            return b'{"models": []}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["method"] = req.method
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    svc._ollama("/api/tags")
    assert captured["url"] == "http://ollama-test:11434/api/tags"
    assert captured["method"] == "GET"


def test_ollama_post_with_payload(svc, monkeypatch):
    svc.configure(server_base_url="http://localhost:11434")
    captured = {}

    class FakeResponse:
        def read(self):
            return b'{"status": "ok"}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    def fake_urlopen(req, timeout=None):
        captured["data"] = req.data
        captured["method"] = req.method
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    svc._ollama("/api/show", method="POST", payload={"name": "test"})
    assert captured["method"] == "POST"
    assert b'"name": "test"' in captured["data"]
