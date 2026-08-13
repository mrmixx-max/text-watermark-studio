"""test_v137_security_truth.py — Runde-2-Funde F1/F2/F3 (vervollständigt nach Agent-Abbruch).

F1: API-Auth wirkt, sobald AI_WM_API_KEY gesetzt ist (401 ohne Key auf sensitive Routen).
F2: `ai-wm report --key <key_id>` löst über die Registry auf (kein falsches Negativ).
F3: key_registry.json nicht im git-Tracking; Demo-Key bootet bei fehlender Datei;
    parallele add_key verlieren keine Keys.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

from ai_watermark_toolkit.core.config import settings
from ai_watermark_toolkit.forensics.key_registry import KeyRegistry
from ai_watermark_toolkit.forensics.kgw import mark_greenlist

from fastapi.testclient import TestClient
import ai_watermark_toolkit.api.fastapi_app as fastapi_app
import ai_watermark_toolkit.api.routes.forensics as forensics_route

KEY_A = "kgw-secret-a-0001"
KEY_B = "kgw-secret-b-0002"


class _NullAudit:
    def log(self, *a, **k):
        return None

    def write(self, *a, **k):
        return None


def _tmp_registry(tmp_path, entries):
    reg = KeyRegistry(path=tmp_path / "reg.json")
    for e in entries:
        reg.add_key(e)
    return reg


def _api_client(tmp_path, monkeypatch, entries):
    reg = _tmp_registry(tmp_path, entries)
    monkeypatch.setattr(forensics_route, "keys", reg)
    monkeypatch.setattr(forensics_route, "audit", _NullAudit())
    return TestClient(fastapi_app.app)


def _run_cli(args, cwd):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO / "src")
    return subprocess.run(
        [sys.executable, "-m", "ai_watermark_toolkit.cli"] + args,
        capture_output=True, text=True, env=env, cwd=str(cwd),
    )


def _cli_registry(tmp_path: Path, entries: list[dict]) -> Path:
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "key_registry.json").write_text(
        json.dumps({"keys": entries}), encoding="utf-8")
    return tmp_path


# ---- F1: Auth wirkt mit gesetztem API-Key ---------------------------------

@pytest.fixture
def api_key_enabled(monkeypatch):
    # settings is a frozen dataclass; bypass via object.__setattr__
    old = settings.api_key
    object.__setattr__(settings, "api_key", "test-api-key-123")
    yield
    object.__setattr__(settings, "api_key", old)


class TestApiAuthEnforced:
    def test_embed_401_without_key(self, api_key_enabled, tmp_path, monkeypatch):
        c = _api_client(tmp_path, monkeypatch,
                        [{"key_id": "a", "family": "kgw", "secret": KEY_A}])
        r = c.post("/api/forensics/embed",
                   json={"text": "hello world", "key_id": "a"})
        assert r.status_code == 401, r.text

    def test_embed_200_with_key(self, api_key_enabled, tmp_path, monkeypatch):
        c = _api_client(tmp_path, monkeypatch,
                        [{"key_id": "a", "family": "kgw", "secret": KEY_A}])
        r = c.post("/api/forensics/embed",
                   json={"text": "hello world", "key_id": "a"},
                   headers={"X-API-Key": "test-api-key-123"})
        assert r.status_code == 200, r.text

    def test_keys_401_without_key(self, api_key_enabled, tmp_path, monkeypatch):
        c = _api_client(tmp_path, monkeypatch,
                        [{"key_id": "a", "family": "kgw", "secret": KEY_A}])
        r = c.get("/api/forensics/keys")
        assert r.status_code == 401, r.text

    def test_detect_401_without_key(self, api_key_enabled, tmp_path, monkeypatch):
        c = _api_client(tmp_path, monkeypatch,
                        [{"key_id": "a", "family": "kgw", "secret": KEY_A}])
        r = c.post("/api/forensics/detect", json={"text": "hello world"})
        assert r.status_code == 401, r.text


# ---- F2: report --key löst Registry auf ------------------------------------

class TestReportKeyResolution:
    def test_cli_report_key_id_detects_marked_text(self, tmp_path):
        cwd = _cli_registry(tmp_path,
                            [{"key_id": "a", "family": "kgw", "secret": KEY_A}])
        f = tmp_path / "marked.txt"
        marked = mark_greenlist(
            "The quick brown fox jumps over the lazy dog near the river bank "
            "while the sun sets slowly behind the old mill and the children "
            "play in the field with great joy every evening.",
            KEY_A, 0.25, seed=42, level="word", context=1)["text"]
        f.write_text(marked, encoding="utf-8")
        r = _run_cli(["report", str(f), "--key", "a"], cwd)
        assert r.returncode == 0, r.stderr
        html = next(cwd.glob("tws-report-*.html"))
        content = html.read_text(encoding="utf-8").lower()
        assert ("greenlist-wasserzeichen" in content
                or "watermark_detected" in content
                or "signifikant" in content), content[:500]

    def test_cli_report_raw_secret_detects_marked_text(self, tmp_path):
        cwd = _cli_registry(tmp_path,
                            [{"key_id": "a", "family": "kgw", "secret": KEY_A}])
        f = tmp_path / "marked.txt"
        marked = mark_greenlist(
            "The quick brown fox jumps over the lazy dog near the river bank "
            "while the sun sets slowly behind the old mill and the children "
            "play in the field with great joy every evening.",
            KEY_A, 0.25, seed=42, level="word", context=1)["text"]
        f.write_text(marked, encoding="utf-8")
        r = _run_cli(["report", str(f), "--key", KEY_A], cwd)
        assert r.returncode == 0, r.stderr
        html = next(cwd.glob("tws-report-*.html"))
        content = html.read_text(encoding="utf-8").lower()
        assert ("greenlist-wasserzeichen" in content
                or "watermark_detected" in content
                or "signifikant" in content), content[:500]


# ---- F3: Registry nicht getrackt / Demo-Bootstrap / parallele Adds ----------

class TestKeyRegistryHygiene:
    def test_key_registry_not_in_git_tracking(self):
        gitignore = (REPO / ".gitignore").read_text(encoding="utf-8")
        assert "data/key_registry.json" in gitignore

    def test_registry_boots_demo_key_when_file_missing(self, tmp_path, monkeypatch):
        # Default-Pfad (data/key_registry.json relativ zum CWD) bootet Demo-Keys
        monkeypatch.chdir(tmp_path)
        reg = KeyRegistry()
        ids = [k["key_id"] for k in reg.list_keys()]
        assert "demo-kgw-1" in ids

    def test_parallel_adds_lose_no_keys(self, tmp_path):
        reg = KeyRegistry(path=tmp_path / "reg.json")
        barrier = threading.Barrier(8)

        def add(i):
            barrier.wait()
            reg.add_key({"key_id": f"key-{i}", "family": "kgw",
                         "secret": f"secret-{i}"})

        threads = [threading.Thread(target=add, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        ids = [k["key_id"] for k in reg.list_keys()]
        assert all(f"key-{i}" in ids for i in range(8)), ids
