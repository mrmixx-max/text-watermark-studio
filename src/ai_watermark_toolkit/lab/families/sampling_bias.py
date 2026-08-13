from __future__ import annotations

from .base import LabFamily
from ...forensics.kgw import DEFAULT_GAMMA, detect_kgw, mark_greenlist


class FamilyPlugin(LabFamily):
    slug = 'sampling_bias'

    def capability(self) -> dict:
        return {'embed': True, 'detect': True, 'explain': True, 'demo': True}

    def detect(self, text: str, options: dict | None = None) -> dict:
        opts = options or {}
        secret = opts.get('secret')
        if not secret:
            return {'family': self.slug, 'supported': True, 'score': 0.0,
                    'notes': ['kgw_detection_requires_registered_secret_key']}
        gamma = opts.get('gamma', DEFAULT_GAMMA)
        level = opts.get('level', 'word')
        context = opts.get('context', 1)
        r = detect_kgw(text, secret, gamma=gamma, level=level, context=context)
        score = min(0.99, max(-0.99, (r['z_score'] or 0.0) / 4.0))
        return {'family': self.slug, 'supported': True, 'score': round(score, 4), 'kgw': r}

    def embed(self, text: str, options: dict | None = None) -> dict:
        """Post-hoc text rewrite (STANDARD path).

        Greenlist-marks existing text deterministically (mark_greenlist) so
        its content words land in the greenlist and the detector recovers the
        watermark (z > 4) with the same key. Respects the level/context/gamma
        options the product's deterministic embed path exposes. The
        generation-time logit bias is a SEPARATE, experimental operation
        (see demo()) that GENERATES new text under sampling bias rather than
        rewriting an existing text.
        """
        opts = options or {}
        secret = opts.get('secret')
        if not secret:
            return {'family': self.slug, 'supported': True, 'text': text,
                    'notes': ['kgw_embedding_requires_registered_secret_key']}
        gamma = opts.get('gamma', DEFAULT_GAMMA)
        level = opts.get('level', 'word')
        context = opts.get('context', 1)
        result = mark_greenlist(text, secret, gamma=gamma, level=level,
                                context=context, seed=opts.get('seed'))
        result['family'] = self.slug
        result['supported'] = True
        return result

    def demo(self, options: dict | None = None) -> dict:
        """Demonstrate the EXPERIMENTAL generation-time KGW logit bias.

        Generates synthetic text under an additive greenlist logit bias
        (generation/kgw_sampler.py) and detects it with the same key. This
        is a mechanics proof, not a production generator; the post-hoc
        rewrite in embed() remains the standard path. Measured with the
        deterministic sampler: bias=2.0, gamma=0.5 -> green_rate ~0.88 and
        z >> 4; unbiased control stays at ~gamma.
        """
        from ...generation.kgw_sampler import generate_marked_text
        opts = options or {}
        secret = opts.get('secret') or 'demo-sampling-bias-key'
        gamma = opts.get('gamma', 0.5)
        bias = opts.get('bias_strength', 2.0)
        context = opts.get('context', 1)
        gen = generate_marked_text(
            prefix=opts.get('prefix', ''),
            vocab=None,
            key=secret,
            gamma=gamma,
            bias_strength=bias,
            n_tokens=opts.get('n_tokens', 200),
            seed=opts.get('seed', 0),
            context=context,
        )
        det = detect_kgw(gen['text'], secret, gamma, context=context)
        return {
            'family': self.slug,
            'supported': True,
            'demo': True,
            'note': 'generation_time_logit_bias (experimental, deterministic synthetic sampler)',
            'generated': gen,
            'detected': det,
        }
