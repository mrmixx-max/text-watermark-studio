from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ROUTING_PATH = ROOT / 'data' / 'model_routing.json'
DEFAULT = {
  'profiles': {
    'default': {
      'primary': {'id': 'local-eurollm', 'kind': 'local', 'base_url': 'http://127.0.0.1:8080/v1', 'model': 'mradermacher/EuroLLM-9B-Instruct-2512-GGUF'},
      'fallbacks': [
        {'id': 'cloud-mid', 'kind': 'cloud', 'base_url': 'https://api.example.com/v1', 'model': 'mid-tier-chat'},
        {'id': 'cloud-mini', 'kind': 'cloud', 'base_url': 'https://api.example.com/v1', 'model': 'mini-chat'}
      ],
      'timeouts_ms': {'local': 1200, 'cloud': 4000},
      'rules': {
        'on_timeout': 'fallback',
        'on_5xx': 'fallback',
        'on_429': 'fallback_immediate',
        'on_context_overflow': 'use_larger_context',
        'on_invalid_output': 'fallback'
      }
    }
  },
  'last_decision': None,
  'history': []
}

class ModelRoutingService:
    def __init__(self, path: Path | None = None):
        self.path = path or ROUTING_PATH
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(DEFAULT, ensure_ascii=False, indent=2), encoding='utf-8')

    def load(self):
        data = json.loads(self.path.read_text(encoding='utf-8'))
        data.setdefault('profiles', DEFAULT['profiles'])
        data.setdefault('last_decision', None)
        data.setdefault('history', [])
        return data

    def save(self, data):
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        return data

    def status(self):
        data = self.load()
        return {
            'profiles': data.get('profiles', {}),
            'last_decision': data.get('last_decision'),
            'history': data.get('history', [])[-10:]
        }

    def decide(self, task: str = 'general', profile: str = 'default', need_large_context: bool = False, privacy_mode: bool = False):
        data = self.load()
        prof = data['profiles'].get(profile) or data['profiles']['default']
        route = prof.get('primary', DEFAULT['profiles']['default']['primary']).copy()
        fallback_chain = list(prof.get('fallbacks', []))
        reason = ['primary_default']
        if privacy_mode:
            route = prof.get('primary', DEFAULT['profiles']['default']['primary']).copy()
            reason.append('privacy_prefers_local')
        elif need_large_context and fallback_chain:
            route = fallback_chain[0].copy()
            reason.append('context_overflow_prefers_fallback')
        elif task in {'factcheck', 'validation', 'summarization'}:
            reason.append('task_allows_escalation')
        decision = {
            'profile': profile,
            'task': task,
            'selected': route,
            'fallback_chain': fallback_chain,
            'timeouts_ms': prof.get('timeouts_ms', {}),
            'reason': reason,
            'decided_at': datetime.now(timezone.utc).isoformat()
        }
        data['last_decision'] = decision
        data.setdefault('history', []).append(decision)
        data['history'] = data['history'][-50:]
        self.save(data)
        return decision

    def configure(self, payload: dict):
        data = self.load()
        profile = payload.get('profile', 'default')
        config = payload.get('config', {})
        existing = data['profiles'].get(profile, {})
        merged = {**existing, **config}
        merged.setdefault('primary', DEFAULT['profiles']['default']['primary'])
        merged.setdefault('fallbacks', DEFAULT['profiles']['default']['fallbacks'])
        merged.setdefault('timeouts_ms', DEFAULT['profiles']['default']['timeouts_ms'])
        merged.setdefault('rules', DEFAULT['profiles']['default']['rules'])
        data['profiles'][profile] = merged
        self.save(data)
        return {'ok': True, 'profile': profile, 'config': merged}
