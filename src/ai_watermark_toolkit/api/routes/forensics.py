from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from ..middleware.auth import require_api_key
from ...forensics.key_registry import KeyRegistry
from ...forensics.ensemble import ensemble_detect
from ...forensics.audit import AuditLogger
from ...forensics.kgw import detect_multi_key, mark_greenlist
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


@router.get('/keys', summary='List registered forensic keys')
def list_keys():
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
def detect(req: DetectRequest):
    registry = keys.list_keys()
    result = ensemble_detect(req.text, registry, window=req.window,
                             level=req.level, context=req.context)
    # Real KGW multi-key detection (sign-preserving |Z| + Bonferroni) so a
    # redlist watermark (negative z) surfaces instead of being clamped to
    # "no_reliable_signal" by the ensemble's positive-only score scale.
    kgw = detect_multi_key(req.text, registry, level=req.level, context=req.context)
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
def embed(req: EmbedRequest):
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
