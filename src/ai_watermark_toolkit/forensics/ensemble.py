from __future__ import annotations

from statistics import mean

from .kgw import DEFAULT_GAMMA, detect_kgw


def segment_text(text: str, window: int = 400) -> list[str]:
    if not text:
        return []
    return [text[i:i+window] for i in range(0, len(text), window)]


def score_segment(text: str, key_meta: dict) -> dict:
    hints = []
    score = 0.0
    family = key_meta.get('family', 'unknown')
    heuristic_components: dict[str, float] = {}
    if family == 'kgw' and key_meta.get('secret'):
        # Real KGW Z-score test per segment, normalized to [-0.99, 0.99]:
        # z >= 4 -> ~0.95, z <= -4 -> ~-0.95 (redlist), linear-ish in between.
        r = detect_kgw(text, key_meta['secret'], gamma=key_meta.get('gamma') or DEFAULT_GAMMA)
        z = r['z_score'] or 0.0
        score = min(0.99, max(-0.99, z / 4.0 * 0.95))
        if r['verdict'] == 'watermark_detected':
            hints.append('kgw_z_above_4')
        elif r['verdict'] == 'weak_signal':
            hints.append('kgw_z_above_2')
        elif r['verdict'] == 'redlist_detected':
            hints.append('kgw_z_below_minus_4')
        elif r['verdict'] == 'weak_redlist_signal':
            hints.append('kgw_z_below_minus_2')
        return {'score': round(score, 4), 'hints': hints, 'family': family,
                'z_score': z, 'verdict': r['verdict'], 'signal': r['signal']}
    trigger = key_meta.get('trigger_phrase', '')
    if trigger and trigger.lower() in text.lower():
        score += 0.65
        hints.append('trigger_phrase_match')
    # P0-3: Heuristik-Beiträge sind sichtbare Beobachtungen, keine
    # Wasserzeichen-Statistik. Die Komponenten werden separat exponiert —
    # ein 'furthermore'-Zähler darf im Verdict nie wie ein Z-Score wirken.
    if family == 'greenlist_bias':
        comma = min(0.25, text.count(',') * 0.01)
        score += comma
        heuristic_components['comma_bias'] = round(comma, 4)
    elif family == 'semantic_pattern':
        further = min(0.25, text.lower().count('furthermore') * 0.08)
        score += further
        heuristic_components['furthermore_bias'] = round(further, 4)
    out: dict = {'score': round(min(score, 0.99), 4), 'hints': hints, 'family': family}
    if heuristic_components:
        out['heuristic_components'] = heuristic_components
    return out


def ensemble_detect(text: str, keys: list[dict], window: int = 400,
                    level: str = "word", context: int = 1,
                    kgw_results: dict[str, dict] | None = None,
                    exclude_demo: bool = False) -> dict:
    segments = segment_text(text, window=window)
    per_key = []
    excluded_demo = 0
    for key in keys:
        if exclude_demo and key.get('is_demo'):
            excluded_demo += 1
            continue
        if key.get('family') == 'kgw' and key.get('secret'):
            # KGW: one Z-test over the WHOLE text (statistics need n), not per segment.
            # Normalize z to the [-0.99, 0.99] score scale; the SIGN must survive
            # so a redlist watermark (z < 0) is not silently clamped to zero.
            # `kgw_results` (optional, keyed by key_id) lets callers reuse a
            # single detect_multi_key pass instead of re-hashing every key.
            r = (kgw_results or {}).get(key.get('key_id'))
            if r is None:
                r = detect_kgw(text, key['secret'], gamma=key.get('gamma') or DEFAULT_GAMMA,
                               level=level, context=context)
            z = r['z_score'] or 0.0
            per_key.append({
                'key_id': key.get('key_id', 'unknown'),
                'family': 'kgw',
                'avg_score': round(min(0.99, max(-0.99, z / 4.0)), 4),
                'z_score': round(z, 4),
                'verdict': r['verdict'],
                'signal': r['signal'],
                'segments': [r],
                'is_demo': bool(key.get('is_demo')),
            })
            continue
        seg_scores = [score_segment(seg, key) for seg in segments] or [score_segment(text, key)]
        avg = mean([s['score'] for s in seg_scores]) if seg_scores else 0.0
        per_key.append({
            'key_id': key.get('key_id', 'unknown'),
            'family': key.get('family', 'unknown'),
            'avg_score': round(avg, 4),
            'segments': seg_scores,
            'is_demo': bool(key.get('is_demo')),
        })
    ensemble_score = mean([k['avg_score'] for k in per_key]) if per_key else 0.0
    kgw_keys = [k for k in per_key if k.get('family') == 'kgw']
    heuristic_keys = [k for k in per_key if k.get('family') != 'kgw']
    kgw_score = mean([k['avg_score'] for k in kgw_keys]) if kgw_keys else None
    heuristic_score = mean([k['avg_score'] for k in heuristic_keys]) if heuristic_keys else None
    # KGW verdicts (two-sided) must surface as the TOP-LEVEL verdict: a
    # redlist watermark (z <= -4 / -2) is a finding, not "no reliable signal".
    kgw_verdicts = [k.get('verdict') for k in kgw_keys
                    if k.get('verdict')]
    if 'redlist_detected' in kgw_verdicts:
        verdict = 'redlist_detected'
    elif 'weak_redlist_signal' in kgw_verdicts:
        verdict = 'weak_redlist_signal'
    elif 'watermark_detected' in kgw_verdicts or (kgw_keys and ensemble_score >= 0.7):
        verdict = 'strong_consistent_signal'
    elif kgw_keys and ensemble_score >= 0.35:
        verdict = 'weak_or_mixed_signal'
    elif not kgw_keys and heuristic_score is not None:
        # P0-3: Ohne KGW-Statistik kann Heuristik (Komma-/furthermore-Zähler,
        # trigger_phrase) nie ein Wasserzeichen-Signal behaupten — sie ist
        # eine Beobachtung, kein Beweis.
        verdict = 'heuristic_hints_only'
    else:
        verdict = 'no_reliable_signal'
    return {
        'ensemble_score': round(ensemble_score, 4),
        'kgw_score': round(kgw_score, 4) if kgw_score is not None else None,
        'heuristic_score': round(heuristic_score, 4) if heuristic_score is not None else None,
        'verdict': verdict,
        'segments_total': len(segments),
        'excluded_demo_keys': excluded_demo,
        'per_key': per_key,
    }
