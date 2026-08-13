from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

# Demo key material for a fresh checkout: the canonical registry boots from
# these when data/key_registry.json does not exist yet. The demo KGW secret is
# public by design (documented in the notes); replace for real use by adding
# your own key via the CLI/API. Keeping the demo key in code (not in a
# committed data file) means key material is never version-controlled.
DEMO_KEYS: list[dict] = [
    {"key_id": "demo-green-1", "family": "greenlist_bias", "status": "active",
     "owner": "local", "trigger_phrase": "", "notes": "demo heuristic key"},
    {"key_id": "demo-semantic-1", "family": "semantic_pattern", "status": "active",
     "owner": "local", "trigger_phrase": "furthermore", "notes": "demo semantic key"},
    {"key_id": "demo-kgw-1", "family": "kgw", "status": "active", "owner": "local",
     "trigger_phrase": "", "notes": "demo KGW key — public demo secret, replace for real use",
     "secret": "demo-kgw-secret-0001", "gamma": 0.25},
]

DEFAULT_PATH = "data/key_registry.json"

# Per-path threading locks so parallel add_key calls (threads or processes
# sharing the same registry file) never lose keys to a read-modify-write race.
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    key = str(path)
    with _locks_guard:
        lock = _locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _locks[key] = lock
        return lock


class KeyRegistry:
    """JSON-file registry of forensic keys, with demo-key bootstrap.

    A missing file is NOT created on read: the canonical registry
    (``data/key_registry.json``) boots from the in-memory demo key so a fresh
    checkout works without committing key material, while custom/test paths
    boot empty. The file is only written by ``add_key``, and writes are atomic
    (tempfile + os.replace) and serialized per path.
    """

    def __init__(self, path: str | Path = DEFAULT_PATH,
                 seed_demo: bool | None = None):
        self.path = Path(path)
        if seed_demo is None:
            # Only the canonical registry location auto-seeds the demo key;
            # explicit paths (tests, custom registries) start empty.
            seed_demo = self.path == Path(DEFAULT_PATH)
        self._seed_demo = bool(seed_demo)

    def _demo_data(self) -> dict:
        return {"keys": [dict(k) for k in DEMO_KEYS]}

    def load(self) -> dict:
        if not self.path.exists():
            return self._demo_data() if self._seed_demo else {"keys": []}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"keys": []}

    def list_keys(self) -> list[dict]:
        return self.load().get("keys", [])

    def add_key(self, item: dict) -> dict:
        with _lock_for(self.path):
            data = self.load()
            keys = data.setdefault("keys", [])
            keys.append(dict(item))
            self._write_atomic(data)
        return item

    def _write_atomic(self, data: dict) -> None:
        # Atomic write: dump to a temp file in the same directory, then
        # os.replace() it over the target. A crash mid-write can never leave a
        # half-written registry, and concurrent readers see either the old or
        # the new file, never a torn one.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
                fh.flush()
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
