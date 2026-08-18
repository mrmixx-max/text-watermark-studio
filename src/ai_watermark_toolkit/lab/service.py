from __future__ import annotations

from ..forensics.key_registry import KeyRegistry
from .family_registry import list_families
from .plugin_loader import get_family_plugins


class WatermarkLabService:
    """Lab facade that wires the registered key material into family plugins.

    The sampling_bias (KGW) family needs a registered secret to do real
    detect/embed; without one it returns a "requires_registered_secret_key"
    no-op. This service reads the first registered KGW key from the registry
    and passes it (plus level/context/gamma options) through to every plugin,
    so /api/lab/embed and /api/lab/detect-all are real operations once a key
    is registered. Explicit options always win over registry defaults.
    """

    def __init__(self, registry: KeyRegistry | None = None):
        self.plugins = get_family_plugins()
        self.registry = registry if registry is not None else KeyRegistry(
            'data/key_registry.json')

    def families(self):
        return list_families()

    def capabilities(self):
        return {slug: plugin.capability() for slug, plugin in self.plugins.items()}

    def _kgw_options(self, options: dict | None) -> dict:
        """Merge explicit options with the first registered KGW key.

        Pulls the secret (and key-level gamma) of the first registered KGW key
        so the sampling_bias family can actually detect/embed. Explicit
        options (secret/gamma/level/context/seed) take precedence.
        """
        opts = dict(options or {})
        if not opts.get('secret'):
            for key in self.registry.list_keys():
                family = key.get('family', '')
                if key.get('secret') and family in ('kgw', 'unknown', ''):
                    opts.setdefault('secret', key['secret'])
                    if key.get('gamma') is not None:
                        opts.setdefault('gamma', key['gamma'])
                    break
        return opts

    def detect_all(self, text: str, options: dict | None = None):
        opts = self._kgw_options(options)
        return {slug: plugin.detect(text, opts) for slug, plugin in self.plugins.items()}

    def embed_with(self, family: str, text: str, options: dict | None = None):
        plugin = self.plugins.get(family)
        if not plugin:
            return {'error': 'unknown_family'}
        return plugin.embed(text, self._kgw_options(options))

    def demo_with(self, family: str, options: dict | None = None):
        plugin = self.plugins.get(family)
        if not plugin:
            return {'error': 'unknown_family'}
        if not callable(getattr(plugin, 'demo', None)):
            return {'error': 'demo_not_supported'}
        return plugin.demo(dict(options or {}))
