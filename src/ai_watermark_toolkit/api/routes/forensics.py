from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ...forensics.key_registry import KeyRegistry
from ...forensics.ensemble import ensemble_detect
from ...forensics.audit import AuditLogger
from ...forensics.kgw import embed_kgw
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


class EmbedRequest(BaseModel):
    text: str
    key_id: str


@router.get('/keys', summary='List registered forensic keys')
def list_keys():
    return {'keys': keys.list_keys()}


@router.post('/keys', summary='Register a forensic detection key')
def add_key(req: KeyCreateRequest):
    item = keys.add_key(req.model_dump())
    audit.write({'event': 'add_key', 'key_id': item['key_id']})
    return item


@router.post('/detect', summary='Run ensemble multi-key forensic detection')
def detect(req: DetectRequest):
    registry = keys.list_keys()
    result = ensemble_detect(req.text, registry, window=req.window)
    plugin_hits = []
    for key in registry:
        for plugin in get_plugins():
            plugin_hits.append({'key_id': key.get('key_id'), **plugin.detect(req.text, key)})
    payload = {'result': result, 'plugin_hits': plugin_hits}
    audit.write({'event': 'detect', 'operator': req.operator, 'keys_used': [k.get('key_id') for k in registry], 'verdict': result['verdict']})
    return payload


@router.post('/embed', summary='Embed a KGW watermark into text with a registered key')
def embed(req: EmbedRequest):
    key = next((k for k in keys.list_keys() if k.get('key_id') == req.key_id), None)
    if key is None:
        raise HTTPException(status_code=404, detail=f'key_not_found: {req.key_id}')
    if not key.get('secret'):
        raise HTTPException(status_code=400, detail='key_has_no_secret')
    result = embed_kgw(req.text, key['secret'], gamma=key.get('gamma') or 0.25)
    result['key_id'] = req.key_id
    audit.write({'event': 'embed', 'key_id': req.key_id, 'replacements': result['replacements']})
    return result
