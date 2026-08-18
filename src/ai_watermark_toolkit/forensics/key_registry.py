from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path

# Demo key material for a fresh checkout: the canonical registry boots from
# these when data/key_registry.json does not exist yet. The demo KGW secret is
# public by design (documented in the notes); replace for real use by adding
# your own key via the CLI/API. Keeping the demo key in code (not in a
# committed data file) means key material is never version-controlled.
DEMO_KEYS: list[dict] = [
    {"key_id": "demo-green-1", "family": "greenlist_bias", "status": "active",
     "owner": "local", "trigger_phrase": "", "notes": "demo heuristic key",
     "is_demo": True},
    {"key_id": "demo-semantic-1", "family": "semantic_pattern", "status": "active",
     "owner": "local", "trigger_phrase": "furthermore", "notes": "demo semantic key",
     "is_demo": True},
    {"key_id": "demo-kgw-1", "family": "kgw", "status": "active", "owner": "local",
     "trigger_phrase": "", "notes": "demo KGW key — public demo secret, replace for real use",
     "secret": "demo-kgw-secret-0001", "gamma": 0.25, "is_demo": True},  # nosec B105  # intentional public demo secret, not a real credential
]

DEFAULT_PATH = "data/key_registry.json"

# Raw-secret masking (P0-4): when a caller passes a raw secret where a
# key_id is expected, the secret must NEVER appear in reports, signatures or
# finding JSON. The reported identity becomes a one-way SHA-256 prefix —
# enough to correlate documents of the same key, not enough to recover or
# brute-force the secret (64 bits of the digest, no plaintext).
SECRET_KEY_ID_PREFIX = "secret:"  # nosec B105  # URL-like prefix constant, not a credential
SECRET_KEY_ID_DIGEST_CHARS = 16


def mask_secret_key_id(secret: str) -> str:
    """Mask a raw secret into a safe public key identifier.

    ``secret:<hex(sha256(secret))[:16]>`` — deterministic per secret, so
    repeated runs of the same raw secret produce the same masked key_id
    (documents stay correlatable), while the secret itself never lands in
    JSON output, signed documents or HTML reports.
    """
    digest = hashlib.sha256(str(secret).encode("utf-8")).hexdigest()
    return f"{SECRET_KEY_ID_PREFIX}{digest[:SECRET_KEY_ID_DIGEST_CHARS]}"


def is_masked_key_id(key_id: str) -> bool:
    """True when ``key_id`` is a masked raw-secret identifier."""
    return isinstance(key_id, str) and key_id.startswith(SECRET_KEY_ID_PREFIX)

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


class RegistryCorruptError(ValueError):
    """The registry file exists but cannot be read/parsed (P0-5).

    Raised instead of silently returning ``{'keys': []}`` — a silent empty
    registry would hide key loss. The original file is left untouched and a
    safety copy is created at ``backup_path`` so the operator can recover
    every key; ``add_key`` refuses to overwrite a corrupt file.
    """

    def __init__(self, path, backup_path, reason: str):
        self.path = Path(path)
        self.backup_path = Path(backup_path)
        self.reason = reason
        super().__init__(
            f"key registry corrupt: {self.path} — {reason}. "
            f"Safety backup: {self.backup_path} (restore it, then retry)."
        )


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

    def _backup_corrupt(self) -> Path:
        """Safety copy of a corrupt registry file (original stays untouched)."""
        backup = self.path.with_name(f"{self.path.name}.{time.time_ns()}.corrupt.bak")
        shutil.copy2(self.path, backup)
        return backup

    def _raise_corrupt(self, reason: str) -> "RegistryCorruptError":
        return RegistryCorruptError(self.path, self._backup_corrupt(), reason)

    def _parse_file(self) -> dict:
        """Read + validate the registry file; raises RegistryCorruptError.

        Validation: the JSON document must be an object whose ``keys``
        member (when present) is a list. Anything else is corruption — a
        later ``add_key`` would otherwise crash mid-append or silently
        drop all existing keys on the next write.
        """
        try:
            raw = self.path.read_text(encoding="utf-8")
        except OSError as e:
            raise self._raise_corrupt(f"unreadable ({type(e).__name__}: {e})") from e
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise self._raise_corrupt(f"invalid JSON ({e})") from e
        if not isinstance(data, dict):
            raise self._raise_corrupt(
                f"JSON root is {type(data).__name__}, expected an object")
        if data.get("keys") is not None and not isinstance(data.get("keys"), list):
            raise self._raise_corrupt(
                f"'keys' member is {type(data.get('keys')).__name__}, expected a list")
        return data

    def load(self) -> dict:
        if not self.path.exists():
            return self._demo_data() if self._seed_demo else {"keys": []}
        return self._parse_file()

    def list_keys(self) -> list[dict]:
        return self.load().get("keys", [])

    def add_key(self, item: dict) -> dict:
        with _lock_for(self.path):
            data = self.load()
            keys = data.setdefault("keys", [])
            keys.append(dict(item))
            # Validate the on-disk file AGAIN right before the replace: a
            # file that turned corrupt between load() and now must never be
            # overwritten (that would destroy every registered key).
            if self.path.exists():
                self._parse_file()
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
