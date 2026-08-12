from __future__ import annotations

from .family_registry import list_families
from .plugin_loader import get_family_plugins


class WatermarkLabService:
    def __init__(self):
        self.plugins = get_family_plugins()

    def families(self):
        return list_families()

    def capabilities(self):
        return {slug: plugin.capability() for slug, plugin in self.plugins.items()}

    def detect_all(self, text: str):
        return {slug: plugin.detect(text, {}) for slug, plugin in self.plugins.items()}

    def embed_with(self, family: str, text: str):
        plugin = self.plugins.get(family)
        if not plugin:
            return {'error': 'unknown_family'}
        return plugin.embed(text, {})
