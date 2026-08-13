"""Tests for invariant-feature watermarking (Yoo et al., ACL 2023, light).

Covers the core architecture: state selection, codebook round-trip,
corruption robustness, and the semantic_structure lab family.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from ai_watermark_toolkit.forensics.invariant import (
    _ollama_infill,
    corrupt,
    detect_anchors,
    embed,
    extract,
    state_of,
)
from ai_watermark_toolkit.lab.families.semantic_structure import FamilyPlugin


DEMO_TEXT = (
    'Der schnelle braune Fuchs springt über den faulen Hund. '
    'Dieser wichtige Test zeigt die robuste Wasserzeichen-Methode. '
    'Die neue Technik ist einfach und klar zu erklären.'
)


def test_detect_anchors_finds_keywords_and_proper_nouns():
    tokens = 'Berlin ist die große Hauptstadt von Deutschland'.split()
    anchors = detect_anchors(tokens)
    anchor_words = {tokens[i] for i in anchors}
    assert 'Berlin' in anchor_words
    assert 'Deutschland' in anchor_words
    # stopwords and lowercase function words are never anchors
    assert 'ist' not in anchor_words
    assert 'die' not in anchor_words


def test_state_masks_never_include_anchors():
    state = state_of(DEMO_TEXT)
    anchor_set = set(state['anchors'])
    assert anchor_set  # there are anchors
    assert all(m not in anchor_set for m in state['masks'])


def test_roundtrip_embeds_and_recovers_message():
    msg = '101101'
    wm = embed(DEMO_TEXT, msg)
    assert wm['bits_embedded'] == len(msg)
    det = extract(wm['text'], DEMO_TEXT)
    assert det['bits'].startswith(msg)
    assert det['confidence'] == 1.0


def test_unmarked_text_does_not_decode_as_valid_bits():
    det = extract(DEMO_TEXT, DEMO_TEXT)
    # original tokens are excluded from the codebook -> no valid bit reads
    assert set(det['bits']) <= {'?'}
    assert det['confidence'] == 0.0


def test_corruption_preserves_bits_on_non_anchor_tokens():
    msg = '101101'
    wm = embed(DEMO_TEXT, msg)
    corrupted = corrupt(wm['text'], ratio=0.05, seed=1, mode='substitute')
    det = extract(corrupted, DEMO_TEXT)
    # substitution targets non-anchor tokens; if no mask position was hit,
    # all bits survive. Either way the recovered prefix must stay intact
    # unless a mask position itself was corrupted.
    if det['confidence'] == 1.0:
        assert det['bits'].startswith(msg)
    else:
        assert det['confidence'] > 0.0


def test_family_plugin_detect_reports_state():
    fp = FamilyPlugin()
    r = fp.detect(DEMO_TEXT)
    assert r['supported'] is True
    assert r['n_anchors'] > 0
    assert r['n_masks'] > 0
    assert 'invariant_feature_state_yoo2023' in r['notes']


def test_family_plugin_demo_roundtrip_ok():
    fp = FamilyPlugin()
    r = fp.demo()
    assert r['roundtrip_ok'] is True
    assert r['embedded_bits'] == len(r['extracted_bits'])
    assert r['confidence_after_corruption'] > 0.0


def test_family_plugin_explain_lists_anchors_and_masks():
    fp = FamilyPlugin()
    r = fp.explain(DEMO_TEXT)
    assert r['supported'] is True
    assert r['explanation']['n_anchors'] > 0
    assert r['explanation']['n_masks'] > 0


def test_ollama_infill_rejects_meta_text(monkeypatch):
    """Chatty/tool responses must never seed codebook candidates."""
    import json
    import urllib.request

    def fake_urlopen(req, timeout=30):
        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return json.dumps({'response': 'The user wants me to complete a German sentence by replacing the mask'}).encode()
        return FakeResp()

    monkeypatch.setattr(urllib.request, 'urlopen', fake_urlopen)
    result = _ollama_infill('Der schnelle braune Fuchs', 1, 'fake-model', timeout=5)
    assert result == []  # meta rambling rejected -> caller falls back to bank


def test_ollama_infill_rejects_stopword_only(monkeypatch):
    """All-stopword filler answers must not seed candidates."""
    import json
    import urllib.request

    def fake_urlopen(req, timeout=30):
        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return json.dumps({'response': 'the user wants'}).encode()
        return FakeResp()

    monkeypatch.setattr(urllib.request, 'urlopen', fake_urlopen)
    result = _ollama_infill('Der schnelle braune Fuchs', 1, 'fake-model', timeout=5)
    assert result == []
