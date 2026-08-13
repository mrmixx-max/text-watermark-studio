from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from ..middleware.auth import require_api_key
from ...forensics.key_registry import KeyRegistry
from ...forensics.signed_report import sign_report, verify_report
from ...forensics.ensemble import ensemble_detect
from ...forensics.audit import AuditLogger
from ...forensics.kgw import detect_multi_key, mark_greenlist
from ...forensics.delta_z import delta_z, delta_z_report, delta_z_transform
from ...plugins.registry import get_plugins

router = APIRouter(prefix='/api/forensics', tags=['forensics'])
keys = KeyRegistry('data/key_registry.json')
audit = AuditLogger('data/audit_log.jsonl')


class KeyCreateRequest(BaseModel):
    key_id: str
    family: str = 'unknown'
    status: str = 'active'
    owner: str = 'local'
    trigger_phrase: str = ''
    notes: str = ''
    secret: str | None = None
    gamma: float | None = None


class DetectRequest(BaseModel):
    text: str
    operator: str = 'local-user'
    window: int = 400
    level: str = 'word'
    context: int = 1


class EmbedRequest(BaseModel):
    text: str
    key_id: str
    level: str = 'word'
    context: int = 1
    seed: int | None = None
    gamma: float | None = None


class ReportSignRequest(BaseModel):
    payload: dict
    key_id: str
    algorithm: str = 'hmac-sha256'


class ReportVerifyRequest(BaseModel):
    signed: dict
    key_id: str | None = None


class DeltaZRequest(BaseModel):
    """ΔZ check: two-text mode (text_before+text_after) OR transform mode.

    The key is always a REGISTERED key_id — the secret is resolved
    server-side from the KeyRegistry and never travels in the request body
    (audit 2026-08-13, report-sign pattern). ``sign=True`` attaches a
    signed_report HMAC block using the key's registry secret.
    """
    text_before: str | None = None
    text_after: str | None = None
    text: str | None = None
    key_id: str
    level: str = 'word'
    context: int = 1
    transform: str | None = None
    truncate_fraction: float = 0.6
    seed: int = 42
    sign: bool = False


@router.get('/keys', summary='List registered forensic keys')
def list_keys(_auth: None = Depends(require_api_key)):
    # strip the secret field — a registry key's secret must never be
    # readable through the API (audit 2026-08-13)
    public = [{k: v for k, v in item.items() if k != 'secret'}
              for item in keys.list_keys()]
    return {'keys': public}


@router.post('/keys', summary='Register a forensic detection key')
def add_key(req: KeyCreateRequest,
            _auth: None = Depends(require_api_key)):
    item = keys.add_key(req.model_dump())
    audit.write({'event': 'add_key', 'key_id': item['key_id']})
    return item


@router.post('/detect', summary='Run ensemble multi-key forensic detection')
def detect(req: DetectRequest, _auth: None = Depends(require_api_key)):
    registry = keys.list_keys()
    # ONE KGW pass: detect_multi_key returns the full per-key detect_kgw
    # results; the ensemble reuses them instead of re-hashing every key
    # (audit 2026-08-13: was 2x tokenize+hash per request).
    kgw = detect_multi_key(req.text, registry, level=req.level, context=req.context)
    kgw_keys = [k for k in registry
                if k.get('family') == 'kgw' and k.get('secret')]
    kgw_results = {k['key_id']: r
                   for k, r in zip(kgw_keys, kgw.get('results', []))}
    result = ensemble_detect(req.text, registry, window=req.window,
                             level=req.level, context=req.context,
                             kgw_results=kgw_results)
    top_verdict = result['verdict']
    best = kgw.get('best')
    # The best |Z| key carries the authoritative two-sided verdict; surface it
    # as the top-level verdict so redlist_detected/weak_redlist_signal reach
    # API consumers directly.
    if best is not None and best.get('verdict') in (
            'redlist_detected', 'weak_redlist_signal', 'watermark_detected'):
        top_verdict = best['verdict']
    plugin_hits = []
    for key in registry:
        for plugin in get_plugins():
            plugin_hits.append({'key_id': key.get('key_id'), **plugin.detect(req.text, key)})
    payload = {'verdict': top_verdict, 'result': result, 'kgw': kgw,
               'plugin_hits': plugin_hits}
    audit.write({'event': 'detect', 'operator': req.operator,
                 'keys_used': [k.get('key_id') for k in registry],
                 'verdict': top_verdict})
    return payload


@router.post('/embed', summary='Embed a KGW watermark into text with a registered key')
def embed(req: EmbedRequest, _auth: None = Depends(require_api_key)):
    key = next((k for k in keys.list_keys() if k.get('key_id') == req.key_id), None)
    if key is None:
        raise HTTPException(status_code=404, detail=f'key_not_found: {req.key_id}')
    if not key.get('secret'):
        raise HTTPException(status_code=400, detail='key_has_no_secret')
    gamma = req.gamma if req.gamma is not None else (key.get('gamma') or 0.25)
    # Deterministic greenlist imposition (z > 4 guaranteed) instead of the
    # best-effort synonym rewrite that "may stay below the detection threshold".
    result = mark_greenlist(req.text, key['secret'], gamma=gamma,
                            level=req.level, context=req.context, seed=req.seed)
    result['key_id'] = req.key_id
    audit.write({'event': 'embed', 'key_id': req.key_id,
                 'replacements': result['replacements']})
    return result


@router.post('/report-sign', summary='Sign a forensic findings payload with a registered key (secret stays server-side)')
def report_sign(req: ReportSignRequest, _auth: None = Depends(require_api_key)):
    """Sign a findings payload server-side.

    The secret NEVER travels in the request body: it is resolved from the
    KeyRegistry by key_id. Only hmac-sha256 is offered here (registry secrets
    are symmetric); ML-DSA keypairs are operator-managed via
    ``ai-wm report-sign --algorithm mldsa-44|65|87``.
    """
    key = next((k for k in keys.list_keys() if k.get('key_id') == req.key_id), None)
    if key is None:
        raise HTTPException(status_code=404, detail=f'key_not_found: {req.key_id}')
    if not key.get('secret'):
        raise HTTPException(status_code=400, detail='key_has_no_secret')
    if req.algorithm != 'hmac-sha256':
        raise HTTPException(
            status_code=400,
            detail='server-side signing uses registry secrets (hmac-sha256); '
                   'for ML-DSA (mldsa-44/65/87) run ai-wm report-sign with a local keypair')
    return sign_report(req.payload, key['secret'], key_id=req.key_id,
                       algorithm='hmac-sha256')


@router.post('/report-verify', summary='Verify a signed forensic findings document against a registered key')
def report_verify(req: ReportVerifyRequest, _auth: None = Depends(require_api_key)):
    """Verify a signed document with the registry secret of the signing key.

    key_id is taken from the request or, when absent, from the document's
    signature block. ML-DSA-44 documents need the public key, which the
    server does not hold — those verify locally via ``ai-wm report-verify``.
    """
    sig = (req.signed or {}).get('signature') if isinstance(req.signed, dict) else None
    key_id = req.key_id or (sig or {}).get('key_id')
    if not key_id:
        raise HTTPException(status_code=400, detail='key_id_required')
    if not isinstance(req.signed, dict) or not isinstance(sig, dict):
        raise HTTPException(status_code=400, detail='malformed_signed_document')
    if isinstance(sig.get('algorithm'), str) and sig.get('algorithm').startswith('mldsa'):
        raise HTTPException(
            status_code=400,
            detail='ML-DSA (mldsa-44/65/87) verification requires the public key — '
                   'run ai-wm report-verify with --public-key')
    key = next((k for k in keys.list_keys() if k.get('key_id') == key_id), None)
    if key is None:
        raise HTTPException(status_code=404, detail=f'key_not_found: {key_id}')
    if not key.get('secret'):
        raise HTTPException(status_code=400, detail='key_has_no_secret')
    return verify_report(req.signed, key['secret'])


@router.post('/delta-z', summary='ΔZ check: measure KGW watermark strength before vs after (removal with receipt)')
def delta_z_endpoint(req: DeltaZRequest, _auth: None = Depends(require_api_key)):
    """ΔZ check as a service (C4, IMATAG-style verification).

    Two modes, selected by the body:
    - two-text: ``{text_before, text_after, key_id}`` — measures the ΔZ
      between the two texts.
    - transform: ``{text, key_id, transform}`` — applies a stdlib transform
      (clean|truncate|shuffle|reformat) server-side and measures its ΔZ.

    The key secret is ALWAYS resolved server-side from the KeyRegistry —
    a raw secret in the body is never accepted (the key_id must be
    registered). ``sign=true`` attaches a signed_report HMAC block (secret =
    the key's registry secret, like /api/forensics/report-sign).

    removed:true is a FINDING (before provable, after not) — the response is
    still 200; it is not an error.
    """
    key = next((k for k in keys.list_keys() if k.get('key_id') == req.key_id), None)
    if key is None:
        raise HTTPException(status_code=404, detail=f'key_not_found: {req.key_id}')
    if not key.get('secret'):
        raise HTTPException(status_code=400, detail='key_has_no_secret')
    if req.transform:
        if req.text is None:
            raise HTTPException(status_code=400, detail='text_required_for_transform')
        result = delta_z_transform(
            req.text, req.key_id, method=req.transform,
            level=req.level, context=req.context, registry=keys,
            seed=req.seed, truncate_fraction=req.truncate_fraction,
        )
    else:
        if req.text_before is None or req.text_after is None:
            raise HTTPException(
                status_code=400,
                detail='text_before_and_text_after_required (or text+transform)')
        result = delta_z(req.text_before, req.text_after, req.key_id,
                         level=req.level, context=req.context, registry=keys)
    if req.sign:
        result = delta_z_report(result, key['secret'], key_id=req.key_id)
    audit.write({'event': 'delta_z', 'key_id': req.key_id,
                 'transform': req.transform, 'removed': result.get('removed'),
                 'delta_z': result.get('delta_z')})
    return result
