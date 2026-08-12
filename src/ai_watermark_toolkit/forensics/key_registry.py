from __future__ import annotations

import json
from pathlib import Path


class KeyRegistry:
    def __init__(self, path: str | Path = 'data/key_registry.json'):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(json.dumps({'keys': []}, ensure_ascii=False, indent=2), encoding='utf-8')

    def load(self) -> dict:
        return json.loads(self.path.read_text(encoding='utf-8'))

    def add_key(self, item: dict) -> dict:
        data = self.load()
        data['keys'].append(item)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        return item

    def list_keys(self) -> list[dict]:
        return self.load().get('keys', [])
