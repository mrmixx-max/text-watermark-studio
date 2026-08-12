from __future__ import annotations


class LabFamily:
    slug = 'base'

    def capability(self) -> dict:
        return {'embed': False, 'detect': False, 'explain': True, 'demo': False}

    def detect(self, text: str, options: dict | None = None) -> dict:
        return {'family': self.slug, 'supported': False, 'score': 0.0, 'notes': ['not_implemented']}

    def embed(self, text: str, options: dict | None = None) -> dict:
        return {'family': self.slug, 'supported': False, 'text': text, 'notes': ['not_implemented']}
