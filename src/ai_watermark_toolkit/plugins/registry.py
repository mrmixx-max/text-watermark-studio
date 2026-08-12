from __future__ import annotations

from .base import DetectorPlugin


class SimpleHeuristicPlugin(DetectorPlugin):
    name = 'simple_heuristic'

    def detect(self, text: str, key_meta: dict) -> dict:
        trigger = key_meta.get('trigger_phrase', '')
        score = 0.7 if trigger and trigger.lower() in text.lower() else 0.1
        return {'score': score, 'plugin': self.name, 'notes': ['heuristic_only']}


def get_plugins() -> list[DetectorPlugin]:
    return [SimpleHeuristicPlugin()]
