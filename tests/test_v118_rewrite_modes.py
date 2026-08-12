"""Behavioral tests for structural + backtranslate rewrite modes (2026-08-13).

Contract:
- Without LLM: 'structural' reorders sentences (keeps first/last), backtranslate
  degrades honestly to the structural shuffle and says so in the change log.
- With LLM: 'backtranslate' makes exactly TWO model calls (EN -> original),
  'structural' one. Prompts for the phases exist and are distinct.
"""

import pytest

from ai_watermark_toolkit.rewrite.service import RewriteService
from ai_watermark_toolkit.llm.providers import build_rewrite_prompt, PROMPTS

TEXT = (
    "The first sentence establishes context. "
    "The second provides the main argument. "
    "The third gives supporting evidence. "
    "The fourth draws the conclusion."
)


class TestStructuralNoLlm:
    def test_rotates_middle_sentences(self):
        svc = RewriteService()
        res = svc.rewrite(TEXT, mode='structural')
        assert res['mode'] == 'structural'
        assert res['rewritten'] != TEXT
        # first + last sentence stay anchored
        assert res['rewritten'].startswith('The first sentence')
        assert res['rewritten'].endswith('draws the conclusion.')
        assert res['metrics']['similarity_ratio'] < 1.0

    def test_few_sentences_vary_openings(self):
        svc = RewriteService()
        res = svc.rewrite("One thing matters. Another follows. Third is last.", mode='structural')
        # too few sentences -> openings varied, meaning intact
        assert 'One thing matters' in res['rewritten']


class TestBacktranslateNoLlm:
    def test_degrades_to_structural_with_honest_note(self):
        svc = RewriteService()
        res = svc.rewrite(TEXT, mode='backtranslate')
        assert res['mode'] == 'backtranslate'
        assert any('No-LLM path' in s for s in res['change_log'])
        assert 'backend' not in res  # no-LLM path has no backend key


class TestBacktranslateLlm:
    def test_two_llm_calls(self, monkeypatch):
        svc = RewriteService(llm_backend=True)
        calls = []

        def fake_llm(text, mode='clarity'):
            calls.append(mode)
            return f"EN:{text}" if mode == 'backtranslate_phase1' else "DE-RESULT"

        monkeypatch.setattr(svc, '_llm_rewrite', fake_llm)
        res = svc.rewrite(TEXT, mode='backtranslate', use_llm=True)
        assert len(calls) == 2
        assert calls[0] == 'backtranslate_phase1'
        assert calls[1] == 'backtranslate_phase2'
        assert res['rewritten'] == 'DE-RESULT'
        assert res['backend'] == 'local-llm'
        assert any('Two-hop' in s for s in res['change_log'])

    def test_structural_one_llm_call(self, monkeypatch):
        svc = RewriteService(llm_backend=True)
        calls = []

        def fake_llm(text, mode='clarity'):
            calls.append(mode)
            return "RESTRUCTURED"

        monkeypatch.setattr(svc, '_llm_rewrite', fake_llm)
        res = svc.rewrite(TEXT, mode='structural', use_llm=True)
        assert calls == ['structural']
        assert res['rewritten'] == 'RESTRUCTURED'


class TestPrompts:
    def test_phase_prompts_exist_and_differ(self):
        p1 = build_rewrite_prompt("x", style='backtranslate_phase1')['prompt']
        p2 = build_rewrite_prompt("x", style='backtranslate_phase2')['prompt']
        assert 'Translate the user' in p1
        assert 'back into its original language' in p2
        assert p1 != p2

    def test_structural_prompt_mentions_reorder(self):
        p = build_rewrite_prompt("x", style='structural')['prompt']
        assert 'reorder' in p or 'Restructure' in p

    def test_unknown_style_falls_back_to_clarity(self):
        p = build_rewrite_prompt("x", style='nonsense')['prompt']
        assert 'clear, direct style' in p
