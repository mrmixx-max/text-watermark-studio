from __future__ import annotations

from statistics import mean


def segment_text(text: str, window: int = 400) -> list[str]:
    if not text:
        return []
    return [text[i:i+window] for i in range(0, len(text), window)]


def score_segment(text: str, key_meta: dict) -> dict:
    hints = []
    score = 0.0
    family = key_meta.get('family', 'unknown')
    trigger = key_meta.get('trigger_phrase', '')
    if trigger and trigger.lower() in text.lower():
        score += 0.65
        hints.append('trigger_phrase_match')
    if family == 'greenlist_bias':
        score += min(0.25, text.count(',') * 0.01)
    elif family == 'semantic_pattern':
        score += min(0.25, text.lower().count('furthermore') * 0.08)
    return {'score': round(min(score, 0.99), 4), 'hints': hints, 'family': family}


def ensemble_detect(text: str, keys: list[dict], window: int = 400) -> dict:
    segments = segment_text(text, window=window)
    per_key = []
    for key in keys:
        seg_scores = [score_segment(seg, key) for seg in segments] or [score_segment(text, key)]
        avg = mean([s['score'] for s in seg_scores]) if seg_scores else 0.0
        per_key.append({
            'key_id': key.get('key_id', 'unknown'),
            'family': key.get('family', 'unknown'),
            'avg_score': round(avg, 4),
            'segments': seg_scores,
        })
    ensemble_score = mean([k['avg_score'] for k in per_key]) if per_key else 0.0
    if ensemble_score >= 0.7:
        verdict = 'strong_consistent_signal'
    elif ensemble_score >= 0.35:
        verdict = 'weak_or_mixed_signal'
    else:
        verdict = 'no_reliable_signal'
    return {
        'ensemble_score': round(ensemble_score, 4),
        'verdict': verdict,
        'segments_total': len(segments),
        'per_key': per_key,
    }
