from __future__ import annotations

from .base import LabFamily


class FamilyPlugin(LabFamily):
    slug = 'sampling_bias'

    def capability(self) -> dict:
        return {'embed': True, 'detect': True, 'explain': True, 'demo': True}

    def detect(self, text: str, options: dict | None = None) -> dict:
        return {'family': self.slug, 'supported': True, 'score': 0.22, 'notes': ['placeholder_for_decoder_control_required']}

    def embed(self, text: str, options: dict | None = None) -> dict:
        return {'family': self.slug, 'supported': False, 'text': text, 'notes': ['real_embed_requires_generation_pipeline']}
