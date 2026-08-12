from __future__ import annotations

import json
import re
import os
from difflib import SequenceMatcher
from typing import Dict

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None

from ..llm.providers import build_rewrite_prompt


class RewriteService:
    def __init__(self, llm_backend: bool = False):
        self.fillers = {'very': '', 'really': '', 'actually': '', 'basically': '', 'quite': '', 'just': ''}
        self.llm_backend = llm_backend
        self.llm_base = os.getenv('LOCAL_LLM_BASE_URL', 'http://127.0.0.1:11434/v1')
        self.llm_model = os.getenv('LOCAL_LLM_MODEL', 'eurollm-9b')

    def _llm_rewrite(self, text: str, mode: str = 'clarity') -> str:
        """Call an OpenAI-compatible local endpoint (Ollama/llama.cpp)."""
        if httpx is None:
            raise RuntimeError('httpx not installed — cannot use LLM backend')
        prompt_data = build_rewrite_prompt(text, style=mode)
        payload = {
            'model': self.llm_model,
            'messages': [{'role': 'user', 'content': prompt_data['prompt']}],
            'temperature': 0.6,
            'max_tokens': 600,
        }
        try:
            resp = httpx.post(
                f"{self.llm_base}/chat/completions",
                json=payload,
                timeout=180.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return data['choices'][0]['message']['content'].strip()
        except Exception as e:
            raise RuntimeError(f'Local LLM call failed: {e}') from e

    def _protect(self, text: str):
        protected: Dict[str, str] = {}
        patterns = [
            r'\b\d+(?:[\.,]\d+)?%?\b',
            r'\b[A-Z][a-zA-Z0-9_-]{1,}\b',
            r'"[^"]+"',
            r"'[^']+'",
        ]
        idx = 0
        for pat in patterns:
            for m in list(re.finditer(pat, text)):
                original = m.group(0)
                token = f'__PROTECTED_{idx}__'
                if original in text:
                    text = text.replace(original, token, 1)
                    protected[token] = original
                    idx += 1
        return text, protected

    def _restore(self, text: str, protected: Dict[str, str]):
        for k, v in protected.items():
            text = text.replace(k, v)
        return text

    def _grammar_light(self, text: str):
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\s+([,.;:!?])', r'\1', text)
        text = re.sub(r'([,.;:!?])(\w)', r'\1 \2', text)
        text = re.sub(r'\bi\b', 'I', text)
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        out = []
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            s = s[0].upper() + s[1:] if len(s) > 1 else s.upper()
            out.append(s)
        return ' '.join(out)

    def _clarify(self, text: str):
        words = text.split()
        cleaned = []
        for w in words:
            key = re.sub(r'[^A-Za-z]', '', w).lower()
            if key in self.fillers and len(words) > 8:
                continue
            cleaned.append(w)
        text = ' '.join(cleaned)
        text = text.replace(' in order to ', ' to ')
        text = text.replace(' due to the fact that ', ' because ')
        text = text.replace(' at this point in time ', ' now ')
        return text

    def _tone(self, text: str, mode: str):
        if mode == 'formal':
            text = text.replace("can't", 'cannot').replace("won't", 'will not').replace("don't", 'do not')
        elif mode == 'concise':
            text = re.sub(r'\b(it is important to note that|it should be noted that)\b', '', text, flags=re.I)
        elif mode == 'plain':
            text = text.replace('utilize', 'use').replace('commence', 'start').replace('approximately', 'about')
        return re.sub(r'\s+', ' ', text).strip()

    def rewrite(self, text: str, mode: str = 'clarity', preserve: bool = True, use_llm: bool | None = None):
        original = text
        use_llm = self.llm_backend if use_llm is None else use_llm
        if use_llm:
            llm_out = self._llm_rewrite(text, mode)
            similarity = round(SequenceMatcher(None, original, llm_out).ratio(), 4)
            return {
                'original': original,
                'rewritten': llm_out,
                'mode': mode,
                'protected_preservation': preserve,
                'backend': 'local-llm',
                'metrics': {
                    'char_delta': len(llm_out) - len(original),
                    'word_count_original': len(original.split()),
                    'word_count_rewritten': len(llm_out.split()),
                    'similarity_ratio': similarity,
                },
                'change_log': [
                    f'Local LLM rewrite via {self.llm_model} ({self.llm_base}).',
                    f'Applied rewrite mode: {mode}.',
                ],
            }
        protected = {}
        if preserve:
            text, protected = self._protect(text)
        text = self._grammar_light(text)
        if mode in {'clarity', 'concise', 'plain', 'formal'}:
            text = self._clarify(text)
            text = self._tone(text, mode)
        text = self._grammar_light(text)
        if preserve:
            text = self._restore(text, protected)
        similarity = round(SequenceMatcher(None, original, text).ratio(), 4)
        return {
            'original': original,
            'rewritten': text,
            'mode': mode,
            'protected_preservation': preserve,
            'metrics': {
                'char_delta': len(text) - len(original),
                'word_count_original': len(original.split()),
                'word_count_rewritten': len(text.split()),
                'similarity_ratio': similarity,
            },
            'change_log': [
                'Normalized whitespace and punctuation.',
                'Applied light grammar correction.',
                f'Applied rewrite mode: {mode}.',
                'Protected tokens preserved.' if preserve else 'Protection disabled.'
            ]
        }
