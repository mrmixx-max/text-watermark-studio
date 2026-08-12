"""Behavioral tests for API route fixes found in the 2026-08-12 route smoke.

Found & fixed:
1. documents/formats called missing DocumentService.supported() -> 500
2. documents/load called missing DocumentService.load_text() -> 500
3. jobs/{id} FileNotFoundError leaked as 500 instead of a clean 404
4. redis routes accessed request.app.state.redis without guard -> AttributeError
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from ai_watermark_toolkit.api.fastapi_app import app
from ai_watermark_toolkit.documents.service import DocumentService
from ai_watermark_toolkit.services.job_service import JobService


class TestDocumentService:
    def test_supported_returns_formats(self):
        svc = DocumentService()
        assert svc.supported() == ['md', 'markdown', 'txt', 'text']

    def test_load_text_returns_loaded_document(self):
        svc = DocumentService()
        doc = svc.load_text('test.md', '  Hallo Welt  ')
        assert doc.filename == 'test.md'
        assert doc.format == 'md'
        assert doc.normalized == 'Hallo Welt'
        assert 'chars' in doc.metadata
        d = doc.to_dict()
        assert d['filename'] == 'test.md'

    def test_load_text_falls_back_to_txt(self):
        svc = DocumentService()
        doc = svc.load_text('report.xyz', 'body')
        assert doc.format == 'txt'


class TestJobService:
    def test_get_job_unknown_raises_404(self, tmp_path):
        svc = JobService(state_dir=str(tmp_path))
        with pytest.raises(HTTPException) as exc:
            svc.get_job('does-not-exist')
        assert exc.value.status_code == 404


class TestRouteSmoke:
    def test_documents_formats_route(self):
        c = TestClient(app)
        r = c.get('/api/documents/formats')
        assert r.status_code == 200
        assert 'md' in r.json()

    def test_documents_load_route(self):
        c = TestClient(app)
        r = c.post('/api/documents/load', json={'filename': 'x.md', 'content': 'hi'})
        assert r.status_code == 200
        assert r.json()['filename'] == 'x.md'

    def test_core_detect_route(self):
        c = TestClient(app)
        r = c.post('/api/detect', json={'text': 'In der heutigen digitalen Welt ist es wichtig zu betonen.', 'lang': 'de'})
        assert r.status_code == 200
        assert 'layers' in r.json()

    def test_rewrite_rules_route(self):
        c = TestClient(app)
        r = c.post('/api/rewrite/run', json={'text': 'Test text here.', 'mode': 'clarity'})
        assert r.status_code == 200
        # Rules backend by default: no 'backend' key (only LLM path sets it)
        assert r.json().get('backend') is None
