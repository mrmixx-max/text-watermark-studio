"""Behavioral tests for the product-truth-gap fixes (2026-08-13).

Four verified gaps closed:
1. Redlist sign + Bonferroni were dead in the API/CLI (detect_multi_key had
   zero call-sites; the ensemble clamped negative z to 0 -> "no_reliable_signal").
2. mark_greenlist (deterministic, z>4) was un-wired — CLI/API/TUI used the
   best-effort embed_kgw and the TUI hardcoded a demo key.
3. context (c) + BPE level were exposed nowhere in the product path.
4. report.py produced a false verdict ("UNBEKANNT" / "Text zu kurz") for
   redlist findings and mislabeled the two-sided p-value as "einseitig".

These tests are filesystem-safe: API tests monkeypatch the route registry and
audit logger onto tmp_path / stubs (never data/); CLI tests run in a tmp cwd
with their own data/key_registry.json.
"""

import json
import os
import random
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ai_watermark_toolkit.api import fastapi_app
from ai_watermark_toolkit.api.routes import forensics as forensics_route
from ai_watermark_toolkit.forensics.ensemble import ensemble_detect
from ai_watermark_toolkit.forensics.kgw import (
    DEFAULT_GAMMA,
    detect_kgw,
    detect_multi_key,
    green_token,
    mark_greenlist,
)
from ai_watermark_toolkit.forensics.key_registry import KeyRegistry
from ai_watermark_toolkit.forensics.report import build_report

REPO = Path(__file__).resolve().parents[1]

# Syllable-generated pseudo-vocab (mirrors test_v113/v132): enough DISTINCT
# (prev, token) pairs so the Z-test's independence assumption holds.
_SIL1 = ("ba be bi bo bu ca ce ci co cu da de di do du fa fe fi fo fu "
         "ga ge gi go gu ka ke ki ko ku la le li lo lu ma me mi mo mu "
         "na ne ni no nu pa pe pi po pu ra re ri ro ru sa se si so su "
         "ta te ti to tu va ve vi vo vu wa we wi wo wu za ze zi zo zu").split()
_SIL2 = ("an en in on un ar er ir or ur al el il ol ul at et it ot ut "
         "as es is os us").split()
VOCAB = [s1 + s2 for s1 in _SIL1 for s2 in _SIL2]

KEY_A = "test-secret-alpha-001"
KEY_B = "test-secret-beta-002"

EMBED_TEXT = (
    "Local AI models protect user privacy by processing information on the "
    "device instead of sending everything to a remote server. This approach "
    "reduces the amount of personal data shared with outside systems and "
    "gives people direct control over their information. The result is a "
    "lower risk of breaches and a stronger security posture. People trust "
    "systems that keep their data nearby and handle processing transparently. "
    "Organizations benefit because sensitive records never leave the building, "
    "and compliance becomes easier when data remains under local control. "
    "Small devices can now run capable models without depending on external "
    "services, which removes network latency and protects against outages. "
    "The same principle applies to healthcare, finance, and public services, "
    "where confidentiality is not optional but a legal requirement."
)


def generate_redlist(seed_token: str, key: str, n: int = 400,
                     gamma: float = DEFAULT_GAMMA, seed: int = 7) -> str:
    """KGW redlist generator: pick from the COMPLEMENT of the greenlist."""
    rng = random.Random(seed)
    out = [seed_token]
    prev = seed_token
    for _ in range(n):
        red_cands = [c for c in VOCAB if not green_token(c, prev, key, gamma)]
        chosen = rng.choice(red_cands) if red_cands else rng.choice(VOCAB)
        out.append(chosen)
        prev = chosen
    return " ".join(out)


def generate_greenlist(seed_token: str, key: str, n: int = 400,
                       gamma: float = DEFAULT_GAMMA, seed: int = 7) -> str:
    """KGW greenlist generator: greedy pick from the greenlist."""
    rng = random.Random(seed)
    out = [seed_token]
    prev = seed_token
    for _ in range(n):
        green_cands = [c for c in VOCAB if green_token(c, prev, key, gamma)]
        chosen = rng.choice(green_cands) if green_cands else rng.choice(VOCAB)
        out.append(chosen)
        prev = chosen
    return " ".join(out)


class _NullAudit:
    def write(self, payload: dict) -> dict:
        return payload


def _tmp_registry(tmp_path: Path, entries: list[dict]) -> KeyRegistry:
    reg = KeyRegistry(str(tmp_path / "keys.json"))
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


# ---- FUND 1: redlist sign + Bonferroni in the product path -----------------

class TestRedlistProductPath:
    def test_detect_multi_key_redlist_signed_best(self):
        text = generate_redlist("start", KEY_B)
        keys = [
            {"key_id": "a", "family": "kgw", "secret": KEY_A},
            {"key_id": "b", "family": "kgw", "secret": KEY_B},
        ]
        r = detect_multi_key(text, keys)
        assert r["tested_keys"] == 2
        assert r["best"]["key_id"] == "b", r
        assert r["best"]["verdict"] == "redlist_detected", r
        assert r["best"]["z_score"] < -4.0, r
        assert 0.0 < r["best_p_adjusted"] <= 1.0, r

    def test_ensemble_preserves_redlist_verdict(self):
        text = generate_redlist("start", KEY_A)
        keys = [{"key_id": "a", "family": "kgw", "secret": KEY_A}]
        r = ensemble_detect(text, keys)
        assert r["verdict"] == "redlist_detected", r
        assert r["per_key"][0]["z_score"] < -4.0, r
        # sign is preserved in the normalized score, not clamped to 0
        assert r["per_key"][0]["avg_score"] < 0.0, r

    def test_api_detect_redlist_top_level_verdict(self, tmp_path, monkeypatch):
        c = _api_client(tmp_path, monkeypatch,
                        [{"key_id": "a", "family": "kgw", "secret": KEY_A}])
        text = generate_redlist("start", KEY_A)
        r = c.post("/api/forensics/detect", json={"text": text})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["verdict"] == "redlist_detected", body
        assert body["kgw"]["best"]["verdict"] == "redlist_detected", body
        assert body["kgw"]["best"]["z_score"] < -4.0, body
        assert body["kgw"]["best_p_adjusted"] is not None, body

    def test_cli_detect_key_redlist_verdict(self, tmp_path):
        cwd = _cli_registry(tmp_path,
                            [{"key_id": "a", "family": "kgw", "secret": KEY_A}])
        f = tmp_path / "red.txt"
        f.write_text(generate_redlist("start", KEY_A), encoding="utf-8")
        r = _run_cli(["detect", str(f), "--key", "a"], cwd)
        assert r.returncode == 1, r.stderr
        data = json.loads(r.stdout)
        assert data["verdict"] == "redlist_detected", data
        assert data["signal"] == "redlist", data
        assert data["z_score"] < -4.0, data

    def test_cli_detect_key_greenlist_verdict(self, tmp_path):
        cwd = _cli_registry(tmp_path,
                            [{"key_id": "a", "family": "kgw", "secret": KEY_A}])
        f = tmp_path / "green.txt"
        f.write_text(generate_greenlist("start", KEY_A), encoding="utf-8")
        r = _run_cli(["detect", str(f), "--key", "a"], cwd)
        assert r.returncode == 1, r.stderr
        data = json.loads(r.stdout)
        assert data["verdict"] == "watermark_detected", data
        assert data["z_score"] >= 4.0, data


# ---- FUND 2: deterministic embedding wired into CLI/API --------------------

class TestDeterministicEmbed:
    def test_api_embed_deterministic_mark_z_gt_4(self, tmp_path, monkeypatch):
        c = _api_client(tmp_path, monkeypatch,
                        [{"key_id": "k", "family": "kgw", "secret": KEY_A,
                          "gamma": 0.25}])
        r = c.post("/api/forensics/embed",
                   json={"text": EMBED_TEXT, "key_id": "k",
                         "level": "word", "context": 1})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["key_id"] == "k"
        assert body["replacements"] > 0, body
        det = detect_kgw(body["text"], KEY_A)
        assert det["verdict"] == "watermark_detected", det
        assert det["z_score"] >= 4.0, det

    def test_cli_embed_deterministic_mark_z_gt_4(self, tmp_path):
        cwd = _cli_registry(tmp_path,
                            [{"key_id": "k", "family": "kgw", "secret": KEY_A,
                              "gamma": 0.25}])
        f = tmp_path / "in.txt"
        f.write_text(EMBED_TEXT, encoding="utf-8")
        r = _run_cli(["embed", str(f), "--key", "k", "--seed", "42"], cwd)
        assert r.returncode == 0, r.stderr
        emb = r.stdout.strip()
        assert emb and emb != EMBED_TEXT
        det = detect_kgw(emb, KEY_A)
        assert det["verdict"] == "watermark_detected", det
        assert det["z_score"] >= 4.0, det


# ---- FUND 3: context + level exposed ---------------------------------------

class TestContextLevelExposure:
    def test_api_embed_context_roundtrip(self, tmp_path, monkeypatch):
        c = _api_client(tmp_path, monkeypatch,
                        [{"key_id": "k", "family": "kgw", "secret": KEY_A,
                          "gamma": 0.5}])
        r = c.post("/api/forensics/embed",
                   json={"text": EMBED_TEXT, "key_id": "k", "context": 4})
        assert r.status_code == 200, r.text
        body = r.json()
        d4 = detect_kgw(body["text"], KEY_A, 0.5, context=4)
        assert d4["verdict"] == "watermark_detected", d4
        d1 = detect_kgw(body["text"], KEY_A, 0.5, context=1)
        assert d1["verdict"] != "watermark_detected", d1

    def test_cli_embed_context_flag_accepted(self, tmp_path):
        cwd = _cli_registry(tmp_path,
                            [{"key_id": "k", "family": "kgw", "secret": KEY_A,
                              "gamma": 0.5}])
        f = tmp_path / "in.txt"
        f.write_text(EMBED_TEXT, encoding="utf-8")
        r = _run_cli(["embed", str(f), "--key", "k", "--context", "4",
                      "--level", "word", "--seed", "3"], cwd)
        assert r.returncode == 0, r.stderr
        emb = r.stdout.strip()
        d4 = detect_kgw(emb, KEY_A, 0.5, context=4)
        assert d4["verdict"] == "watermark_detected", d4


# ---- FUND 4: report.py redlist verdict + two-sided label -------------------

class TestReportRedlist:
    def test_report_redlist_badge_and_recommendation(self):
        text = generate_redlist("start", KEY_A)
        html = build_report(text, KEY_A)
        assert "REDLIST-SIGNAL NACHGEWIESEN" in html
        assert "Redlist-Signal nachgewiesen" in html
        assert "Z<=-4" in html
        assert "UNBEKANNT" not in html

    def test_report_pvalue_label_two_sided(self):
        html = build_report("short text for the report", KEY_A)
        assert "zweiseitig" in html
        assert "einseitig" not in html

    def test_report_weak_redlist_badge(self):
        text = generate_redlist("start", KEY_A, n=25)
        html = build_report(text, KEY_A)
        assert "SCHWACHES REDLIST-SIGNAL" in html
        assert "Schwaches Redlist-Signal" in html
