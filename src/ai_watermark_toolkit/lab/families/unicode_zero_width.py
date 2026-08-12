from __future__ import annotations

from .base import LabFamily


class FamilyPlugin(LabFamily):
    slug = 'unicode_zero_width'

    def capability(self) -> dict:
        return {'embed': True, 'detect': True, 'explain': True, 'demo': True}

    def detect(self, text: str, options: dict | None = None) -> dict:
        return {'family': self.slug, 'supported': True, 'score': 0.92 if '\u200b' in text or '\u200c' in text else 0.08, 'notes': ['zero_width_scan_demo']}

    def embed(self, text: str, options: dict | None = None) -> dict:
        return {'family': self.slug, 'supported': True, 'text': text + '\u200b', 'notes': ['demo_zero_width_embedded']}
