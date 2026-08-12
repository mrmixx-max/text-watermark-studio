from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Dict

class RewriteService:
    def __init__(self):
        self.fillers = {'very': '', 'really': '', 'actually': '', 'basically': '', 'quite': '', 'just': ''}

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

    def rewrite(self, text: str, mode: str = 'clarity', preserve: bool = True):
        original = text
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
