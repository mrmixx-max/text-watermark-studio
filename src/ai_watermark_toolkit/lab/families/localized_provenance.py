from __future__ import annotations

from .base import LabFamily


class FamilyPlugin(LabFamily):
    slug = 'localized_provenance'

    def capability(self) -> dict:
        return {'embed': True, 'detect': True, 'explain': True, 'demo': True}

    def detect(self, text: str, options: dict | None = None) -> dict:
        segments = [text[i:i+180] for i in range(0, len(text), 180)]
        return {'family': self.slug, 'supported': True, 'score': 0.35, 'segments': [{'segment': i+1, 'score': 0.35 + (0.1 if 'furthermore' in s.lower() else 0)} for i, s in enumerate(segments)], 'notes': ['localized_demo']}

    def embed(self, text: str, options: dict | None = None) -> dict:
        return {'family': self.slug, 'supported': False, 'text': text, 'notes': ['localized_embed_requires_family_specific_pipeline']}
