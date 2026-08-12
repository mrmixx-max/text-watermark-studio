from __future__ import annotations

import json
from pathlib import Path
from string import Template

REGISTRY_PATH = Path(__file__).resolve().parents[3] / 'data' / 'prompts' / 'registry.json'


class PromptRegistryService:
    def __init__(self, path: Path | None = None):
        self.path = path or REGISTRY_PATH

    def _load(self):
        return json.loads(self.path.read_text(encoding='utf-8'))

    def _save(self, data):
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    def list_templates(self):
        return self._load()['templates']

    def get_template(self, template_id: str, version: str | None = None):
        matches = [t for t in self.list_templates() if t['id'] == template_id]
        if version:
            matches = [t for t in matches if t['version'] == version]
        if not matches:
            raise ValueError('template_not_found')
        if version:
            return matches[0]
        stable = [m for m in matches if m.get('channel') == 'stable']
        return stable[0] if stable else matches[0]

    def render(self, template_id: str, variables: dict, version: str | None = None):
        item = self.get_template(template_id, version)
        user_template = item['user_template']
        rendered = user_template
        for key, value in variables.items():
            rendered = rendered.replace('{{' + key + '}}', str(value))
        return {
            'id': item['id'],
            'version': item['version'],
            'channel': item.get('channel'),
            'provider': item.get('provider'),
            'model': item.get('model'),
            'parameters': item.get('parameters', {}),
            'system_prompt': item.get('system_prompt', ''),
            'user_prompt': rendered,
        }

    def create_version(self, payload: dict):
        data = self._load()
        data['templates'].append(payload)
        self._save(data)
        return payload
