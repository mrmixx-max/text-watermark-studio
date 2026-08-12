from __future__ import annotations

from statistics import mean

from .kgw import detect_kgw, DEFAULT_GAMMA


def segment_text(text: str, window: int = 400) -> list[str]:
    if not text:
        return []
    return [text[i:i+window] for i in range(0, len(text), window)]


def score_segment(text: str, key_meta: dict) -> dict:
    hints = []
    score = 0.0
    family = key_meta.get('family', 'unknown')
    if family == 'kgw' and key_meta.get('secret'):
        # Real KGW Z-score test per segment, normalized to [0, 1]:
        # z >= 4 -> 0.95, z <= 0 -> ~0, linear-ish in between.
        r = detect_kgw(text, key_meta['secret'], gamma=key_meta.get('gamma') or DEFAULT_GAMMA)
        z = r['z_score'] or 0.0
        score = min(0.99, max(0.0, z / 4.0 * 0.95))
        if r['verdict'] == 'watermark_detected':
            hints.append('kgw_z_above_4')
        elif r['verdict'] == 'weak_signal':
            hints.append('kgw_z_above_2')
        return {'score': round(score, 4), 'hints': hints, 'family': family, 'z_score': z}
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
        if key.get('family') == 'kgw' and key.get('secret'):
            # KGW: one Z-test over the WHOLE text (statistics need n), not per segment.
            # Normalize z to the [0,1] score scale the verdict thresholds assume.
            r = detect_kgw(text, key['secret'], gamma=key.get('gamma') or DEFAULT_GAMMA)
            z = r['z_score'] or 0.0
            per_key.append({
                'key_id': key.get('key_id', 'unknown'),
                'family': 'kgw',
                'avg_score': round(min(0.99, z / 4.0), 4),
                'segments': [r],
            })
            continue
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
