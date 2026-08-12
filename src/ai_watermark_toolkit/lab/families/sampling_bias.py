from __future__ import annotations

from .base import LabFamily
from ...forensics.kgw import detect_kgw, embed_kgw, DEFAULT_GAMMA


class FamilyPlugin(LabFamily):
    slug = 'sampling_bias'

    def capability(self) -> dict:
        return {'embed': True, 'detect': True, 'explain': True, 'demo': False}

    def detect(self, text: str, options: dict | None = None) -> dict:
        opts = options or {}
        secret = opts.get('secret')
        if not secret:
            return {'family': self.slug, 'supported': True, 'score': 0.0,
                    'notes': ['kgw_detection_requires_registered_secret_key']}
        r = detect_kgw(text, secret, gamma=opts.get('gamma', DEFAULT_GAMMA))
        score = min(0.99, max(0.0, (r['z_score'] or 0.0) / 4.0))
        return {'family': self.slug, 'supported': True, 'score': round(score, 4), 'kgw': r}

    def embed(self, text: str, options: dict | None = None) -> dict:
        opts = options or {}
        secret = opts.get('secret')
        if not secret:
            return {'family': self.slug, 'supported': True, 'text': text,
                    'notes': ['kgw_embedding_requires_registered_secret_key']}
        result = embed_kgw(text, secret, gamma=opts.get('gamma', DEFAULT_GAMMA))
        result['family'] = self.slug
        result['supported'] = True
        return result
