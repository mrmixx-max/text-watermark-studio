from __future__ import annotations

from .base import LabFamily


class FamilyPlugin(LabFamily):
    slug = 'semantic_structure'

    def capability(self) -> dict:
        return {'embed': True, 'detect': True, 'explain': True, 'demo': True}

    def detect(self, text: str, options: dict | None = None) -> dict:
        hits = text.lower().count('in summary') + text.lower().count('overall')
        return {'family': self.slug, 'supported': True, 'score': min(0.8, hits * 0.3), 'notes': ['semantic_structure_demo']}

    def embed(self, text: str, options: dict | None = None) -> dict:
        return {'family': self.slug, 'supported': True, 'text': text + ' Overall, the structure remains consistent.', 'notes': ['demo_semantic_structure_embed']}
