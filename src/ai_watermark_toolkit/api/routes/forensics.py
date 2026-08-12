from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from ...forensics.key_registry import KeyRegistry
from ...forensics.ensemble import ensemble_detect
from ...forensics.audit import AuditLogger
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


class DetectRequest(BaseModel):
    text: str
    operator: str = 'local-user'
    window: int = 400


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
