"""Tests for ui/web/forms.py"""

from unittest.mock import MagicMock, patch

import pytest

from ai_watermark_toolkit.ui.web import forms


class TestRender:
    def test_render_returns_pre_block(self):
        data = {"key": "value"}
        result = forms._render(data)
        assert "<pre" in result
        assert "</pre>" in result
        assert "key" in result

    def test_render_preserves_json(self):
        data = {"key": "value", "number": 42}
        result = forms._render(data)
        assert "42" in result


class TestFormDetect:
    @pytest.mark.anyio
    async def test_form_detect(self):
        with patch.object(forms.text_svc, "detect", return_value={"verdict": "clean"}):
            response = await forms.form_detect(text="hello world", lang="en", aggressive="")
        assert response.status_code == 200
        body = response.body.decode()
        assert "clean" in body


class TestFormClean:
    @pytest.mark.anyio
    async def test_form_clean(self):
        with patch.object(forms.text_svc, "clean", return_value={"text": "cleaned"}):
            response = await forms.form_clean(text="hello", nfkc="", fold_confusables="")
        assert response.status_code == 200


class TestFormDilute:
    @pytest.mark.anyio
    async def test_form_dilute(self):
        with patch.object(forms.text_svc, "dilute", return_value={"text": "diluted"}):
            response = await forms.form_dilute(text="hello", intensity="standard")
        assert response.status_code == 200


class TestFormEmbed:
    @pytest.mark.anyio
    async def test_form_embed_missing_key(self):
        response = await forms.form_embed(text="hello", key="", gamma="", level="word", context="1")
        assert response.status_code == 200
        body = response.body.decode()
        assert "key is required" in body


class TestFormListKeys:
    @pytest.mark.anyio
    async def test_form_list_keys(self):
        with patch("ai_watermark_toolkit.ui.web.forms.KeyRegistry") as mock_cls:
            mock_reg = MagicMock()
            mock_reg.list_keys.return_value = [{"key_id": "test"}]
            mock_cls.return_value = mock_reg
            response = await forms.form_list_keys()
        assert response.status_code == 200


class TestFormAddKey:
    @pytest.mark.anyio
    async def test_form_add_key(self):
        with patch("ai_watermark_toolkit.ui.web.forms.KeyRegistry") as mock_cls:
            mock_reg = MagicMock()
            mock_reg.add_key.return_value = {"key_id": "new_key"}
            mock_cls.return_value = mock_reg
            response = await forms.form_add_key(key_id="new_key", family="kgw", status="active", owner="local")
        assert response.status_code == 200


class TestFormLabDetect:
    @pytest.mark.anyio
    async def test_form_lab_detect(self):
        with patch("ai_watermark_toolkit.lab.service.WatermarkLabService") as mock_cls:
            mock_svc = MagicMock()
            mock_svc.detect_all.return_value = {"test": "result"}
            mock_cls.return_value = mock_svc
            response = await forms.form_lab_detect(text="hello world")
        assert response.status_code == 200


class TestFormLlmStatus:
    @pytest.mark.anyio
    async def test_form_llm_status(self):
        with patch.object(forms.llm_svc, "status", return_value={"status": "ok"}):
            response = await forms.form_llm_status()
        assert response.status_code == 200


class TestFormLlmConfigure:
    @pytest.mark.anyio
    async def test_form_llm_configure(self):
        with patch.object(forms.llm_svc, "configure", return_value={"configured": True}):
            response = await forms.form_llm_configure(
                server_base_url="http://localhost:8080/v1",
                model_variant="test",
                installed="true",
            )
        assert response.status_code == 200
