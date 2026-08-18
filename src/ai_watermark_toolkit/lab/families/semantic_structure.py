from __future__ import annotations

from ...forensics.invariant import corrupt, embed, extract, state_of
from .base import LabFamily


class FamilyPlugin(LabFamily):
    slug = 'semantic_structure'

    def capability(self) -> dict:
        return {'embed': True, 'detect': True, 'explain': True, 'demo': True}

    def detect(self, text: str, options: dict | None = None) -> dict:
        """Report the invariant state (anchors + masks) of a text.

        Unlike the old phrase-count demo, this runs Phase 1 of the Yoo et al.
        method: anchor detection (keywords / proper nouns) and mask selection.
        A non-trivial number of anchors indicates the text has structure
        suitable for invariant watermarking. For actual bit recovery use
        ``embed``/``extract`` with the same options.
        """
        opts = options or {}
        state = state_of(text, max_masks=opts.get('max_masks'))
        n_anchors = len(state['anchors'])
        n_masks = len(state['masks'])
        score = min(0.95, (n_anchors * 0.12) + (n_masks * 0.06))
        return {
            'family': self.slug,
            'supported': True,
            'score': round(score, 4),
            'anchors': [state['tokens'][i] for i in state['anchors'][:20]],
            'n_anchors': n_anchors,
            'n_masks': n_masks,
            'notes': ['invariant_feature_state_yoo2023'],
        }

    def embed(self, text: str, options: dict | None = None) -> dict:
        """Embed a multi-bit message at invariant mask positions (Yoo 2023).

        Options:
        - ``message``: binary string ('0101...'). If omitted, embeds a
          deterministic test pattern derived from the text hash.
        - ``max_masks``: cap on mask positions (payload vs robustness).
        - ``candidates``: optional {index: [word, ...]} override.
        - ``ollama_infill`` + ``ollama_model``: use local Ollama for candidates.
        """
        opts = dict(options or {})
        message = opts.get('message')
        if message is None:
            import hashlib
            digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
            message = ''.join('1' if c in '13579bdf' else '0' for c in digest[:32])
        result = embed(text, message, opts)
        result['family'] = self.slug
        result['supported'] = True
        result['message'] = message
        result['notes'] = ['invariant_feature_embed_yoo2023']
        return result

    def explain(self, text: str, options: dict | None = None) -> dict:
        state = state_of(text, max_masks=(options or {}).get('max_masks'))
        tokens = state['tokens']
        return {
            'family': self.slug,
            'supported': True,
            'explanation': {
                'principle': 'Mask positions are pinned to invariant anchors '
                             '(keywords/proper nouns) so corruption that '
                             'preserves utility cannot move the state.',
                'anchors': [tokens[i] for i in state['anchors'][:20]],
                'masks': [tokens[i] for i in state['masks'][:20]],
                'n_anchors': len(state['anchors']),
                'n_masks': len(state['masks']),
            },
        }

    def demo(self, options: dict | None = None) -> dict:
        """Round-trip demo: embed -> extract, plus corruption robustness."""
        opts = dict(options or {})
        text = opts.get('text') or (
            'Der schnelle braune Fuchs springt über den faulen Hund. '
            'Dieser wichtige Test zeigt die robuste Wasserzeichen-Methode. '
            'Die neue Technik ist einfach und klar zu erklären.'
        )
        message = opts.get('message') or '101101'
        wm = embed(text, message, opts)
        det = extract(wm['text'], text, opts)
        # corruption robustness: corrupt the WATERMARKED text (5% substitution
        # of non-anchor tokens), then extract against the original reference
        corrupted = corrupt(wm['text'], ratio=0.05, seed=opts.get('seed', 1), mode='substitute')
        det_corrupt = extract(corrupted, text, opts)
        return {
            'family': self.slug,
            'supported': True,
            'demo': True,
            'note': 'invariant_feature_yoo2023 round-trip + 5% corruption',
            'original': text,
            'watermarked': wm['text'],
            'embedded_bits': wm['bits_embedded'],
            'extracted_bits': det['bits'],
            'roundtrip_ok': det['bits'].startswith(message),
            'corrupted_sample': corrupted,
            'extracted_after_corruption': det_corrupt['bits'],
            'confidence_after_corruption': det_corrupt['confidence'],
        }
