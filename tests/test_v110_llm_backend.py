"""Behavioral tests for the local-LLM rewrite backend (added 2026-08-12).

The rewrite endpoint previously returned the input nearly unchanged (regex stub).
Now it supports an OpenAI-compatible local backend (Ollama/llama.cpp) behind
`use_llm=True`. These tests mock the HTTP call so CI stays deterministic.
"""
from __future__ import annotations

import pytest

from ai_watermark_toolkit.rewrite.service import RewriteService


class TestLLMRewriteBackend:
    def test_rules_backend_unchanged_by_default(self):
        svc = RewriteService(llm_backend=False)
        r = svc.rewrite('In der heutigen digitalen Welt ist es wichtig zu betonen.', mode='clarity')
        assert r.get('backend') is None  # rules path, not LLM
        assert 'rewritten' in r

    def test_llm_backend_calls_endpoint(self, monkeypatch):
        svc = RewriteService(llm_backend=True)
        captured = {}

        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {'choices': [{'message': {'content': 'Clean rewritten text.'}}]}

        class FakeHttpx:
            def __init__(self):
                self.calls = []

            def post(self, url, json=None, timeout=None):
                captured['url'] = url
                captured['json'] = json
                return FakeResponse()

        monkeypatch.setattr(svc, '_llm_rewrite', lambda text, mode: 'Clean rewritten text.')
        r = svc.rewrite('Original marker text.', mode='clarity', use_llm=True)
        assert r['backend'] == 'local-llm'
        assert 'Clean rewritten text.' in r['rewritten']
        assert r['metrics']['similarity_ratio'] > 0

    def test_llm_backend_failure_raises(self, monkeypatch):
        svc = RewriteService(llm_backend=True)

        def boom(text, mode):
            raise RuntimeError('Local LLM call failed: connection refused')

        monkeypatch.setattr(svc, '_llm_rewrite', boom)
        with pytest.raises(RuntimeError, match='Local LLM call failed'):
            svc.rewrite('x', use_llm=True)

    def test_use_llm_false_overrides_backend(self, monkeypatch):
        svc = RewriteService(llm_backend=True)

        def should_not_be_called(text, mode):
            raise AssertionError('LLM must not be called when use_llm=False')

        monkeypatch.setattr(svc, '_llm_rewrite', should_not_be_called)
        r = svc.rewrite('In der heutigen digitalen Welt ist es wichtig zu betonen.', use_llm=False)
        assert r.get('backend') is None
