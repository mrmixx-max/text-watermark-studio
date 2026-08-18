"""E1-E5 Fix-Runde (Runde-3-Expositions-Check): Kontext-Dimension,
TUI-Exposition, API/MCP detect e_value+signature_filter, Doku-Wahrheit,
FRS-Kern (Forensic Readiness Score).

Muster: markierter Text via mark_greenlist(seed=0) -> z_before 13.6083,
Registry im tmp_path (data/ wird nie beschrieben).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ai_watermark_toolkit.forensics.finding import build_finding_report
from ai_watermark_toolkit.forensics.frequent_vocab import FREQUENT_VOCAB
from ai_watermark_toolkit.forensics.frs import compute_frs
from ai_watermark_toolkit.forensics.key_registry import KeyRegistry
from ai_watermark_toolkit.forensics.kgw import mark_greenlist
from ai_watermark_toolkit.forensics.signed_report import verify_report

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"

KEY = "demo-kgw-secret-0001"

TEXT = (
    "Local AI models are crucial for maintaining user privacy and ensuring "
    "secure interactions with data processing. This reduces the amount of "
    "personal information shared with third parties. On-device processing "
    "keeps sensitive details under your control. The result is a lower risk "
    "of breaches and stronger protection. People gain more confidence when "
    "their data stays local and private systems keep everything on device "
    "without sending anything to remote servers or external infrastructure."
)


@pytest.fixture(scope="module")
def marked() -> str:
    emb = mark_greenlist(TEXT, KEY, vocab=FREQUENT_VOCAB, seed=0)
    return emb["text"]


def run_cli(args, stdin=None, cwd=None):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC)
    base = [sys.executable, "-m", "ai_watermark_toolkit.cli"]
    return subprocess.run(base + args, capture_output=True, text=True,
                          input=stdin, env=env, cwd=cwd or REPO)


def make_registry(tmp_path, key_id="e1-key-1", secret="e1-secret-1"):
    reg = KeyRegistry(str(tmp_path / "keys.json"))
    reg.add_key({"key_id": key_id, "family": "kgw", "secret": secret})
    return reg


# ---------------------------------------------------------------- E5: FRS-Kern
class TestFrs:
    def test_default_score_is_31(self):
        frs = compute_frs()
        assert frs["score"] == 31, frs
        assert frs["max_score"] == 60
        assert len(frs["criteria"]) == 12

    def test_default_gates_and_verdict(self):
        frs = compute_frs()
        assert frs["gates"]["G1"]["met"] is False  # Korpus-Studie fehlt (ehrlich)
        assert frs["gates"]["G2"]["met"] is True   # ΔZ-Paradox gemessen
        assert frs["gates"]["G3"]["met"] is True   # deterministisch
        assert frs["verdict"] == "NOT_FORENSIC_READY"
        assert frs["basis"] == "self_assessed"
        assert "Korpus-Studie" in frs["limit_note"]

    def test_verdict_rules_strict(self):
        # Score hoch + Gate offen = NOT
        frs = compute_frs(scores=dict.fromkeys(("T1", "T2", "T3", "T4", "L1", "L2", "L3", "L4", "O1", "O2", "O3", "O4"), 5))
        assert frs["score"] == 60
        assert frs["gates"]["G1"]["met"] is False
        assert frs["verdict"] == "NOT_FORENSIC_READY"

        # Score >= 40 + alle Gates + self_assessed = CONDITIONALLY
        frs = compute_frs(scores={"T2": 5, "L3": 5, "O1": 5},  # +3+3+3 = 40
                          gates={"G1": {"met": True, "note": "Studie vorliegend"}})
        assert frs["score"] == 40
        assert all(g["met"] for g in frs["gates"].values())
        assert frs["verdict"] == "CONDITIONALLY_READY"

        # self_assessed kann NIE FORENSIC_READY erreichen (kein Selbst-Gütesiegel)
        frs = compute_frs(basis="validated",
                          scores={"T2": 5, "L3": 5, "O1": 5},
                          gates={"G1": {"met": True, "note": "Studie vorliegend"}})
        assert frs["verdict"] == "FORENSIC_READY"

    def test_frs_block_in_signed_report(self, marked):
        results = {"detect": {"verdict": "watermark_detected",
                              "z_score": 13.6, "p_value": 1e-8}}
        frs = compute_frs()
        report = build_finding_report(results, key_id=KEY, frs=frs,
                                      sign_secret=KEY)
        assert report["frs"]["score"] == 31
        assert report["frs"]["verdict"] == "NOT_FORENSIC_READY"
        # FRS-Block wird MIT-signiert (sign_report hasht den ganzen Payload)
        ver = verify_report(report, KEY)
        assert ver["valid"] is True
        assert report["frs"]["score"] == 31


# ------------------------------------------------------- E1: Kontext-Dimension
class TestFindingContext:
    def test_cli_institutional_rule_sets_context(self, tmp_path, marked):
        inp = tmp_path / "in.txt"
        inp.write_text(marked, encoding="utf-8")
        r = run_cli(["finding", str(inp), "--key", KEY,
                     "--institutional-rule", "Prüfungsordnung §5 Abs. 2"])
        assert r.returncode == 0, r.stderr
        report = json.loads(r.stdout)
        assert report["findings"][0]["context_missing"] is False
        assert "Prüfungsordnung" in json.dumps(report, ensure_ascii=False)

    def test_cli_origin_history_sets_context(self, tmp_path, marked):
        inp = tmp_path / "in.txt"
        inp.write_text(marked, encoding="utf-8")
        r = run_cli(["finding", str(inp), "--key", KEY,
                     "--origin-history", "Entstanden in Klausur vom 03.07."])
        assert r.returncode == 0, r.stderr
        report = json.loads(r.stdout)
        assert report["findings"][0]["context_missing"] is False
        assert "Klausur" in json.dumps(report, ensure_ascii=False)

    def test_cli_without_context_still_honest(self, tmp_path, marked):
        inp = tmp_path / "in.txt"
        inp.write_text(marked, encoding="utf-8")
        r = run_cli(["finding", str(inp), "--key", KEY])
        assert r.returncode == 0, r.stderr
        report = json.loads(r.stdout)
        assert report["findings"][0]["context_missing"] is True  # ohne Kontext ehrlich begrenzt

    def test_api_context_dict_sets_context(self, marked):
        from types import SimpleNamespace

        from fastapi.testclient import TestClient

        import ai_watermark_toolkit.api.middleware.auth as auth_mod
        from ai_watermark_toolkit.api import fastapi_app
        auth_mod.settings = SimpleNamespace(api_key="test-secret")
        client = TestClient(fastapi_app.app)
        resp = client.post("/api/forensics/finding",
                           json={"text": marked, "key_id": "demo-kgw-1",
                                 "context": {"institutional_rule": "APO §12"}},
                           headers={"X-API-Key": "test-secret"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["findings"][0]["context_missing"] is False
        assert "APO" in json.dumps(body, ensure_ascii=False)


# ------------------------------------------- E3: API/MCP detect neue Felder
class TestDetectApiFields:
    def _client(self, monkeypatch):
        from types import SimpleNamespace

        from fastapi.testclient import TestClient

        import ai_watermark_toolkit.api.middleware.auth as auth_mod
        from ai_watermark_toolkit.api import fastapi_app
        monkeypatch.setattr(auth_mod, "settings",
                            SimpleNamespace(api_key="test-secret"))
        return TestClient(fastapi_app.app)

    def test_detect_without_flags_keeps_old_shape(self, marked, monkeypatch):
        resp = self._client(monkeypatch).post(
            "/api/forensics/detect",
            json={"text": marked, "key_id": KEY},
            headers={"X-API-Key": "test-secret"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "e_value" not in body
        assert "signature_filtered" not in body
        assert body.get("verdict") == "watermark_detected"

    def test_detect_with_e_value_flag(self, marked, monkeypatch):
        resp = self._client(monkeypatch).post(
            "/api/forensics/detect",
            json={"text": marked, "key_id": KEY, "e_value": True},
            headers={"X-API-Key": "test-secret"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body.get("e_value") is not None
        assert "detected" in body["e_value"]

    def test_detect_with_signature_filter_flag(self, marked, monkeypatch):
        resp = self._client(monkeypatch).post(
            "/api/forensics/detect",
            json={"text": marked, "key_id": KEY, "signature_filter": True},
            headers={"X-API-Key": "test-secret"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "signature_filtered" in body


# ----------------------------------------------------------- E2: TUI-Exposition
class TestTuiExposition:
    def test_menu_has_25_and_all_actions_exist(self):
        from ai_watermark_toolkit.ui.tui import MENU, SHORT_HELP, StudioTUI
        assert len(MENU) == 25
        app = StudioTUI()
        for _, action_id in MENU:
            method = "action_" + action_id.replace("-", "_")
            assert hasattr(app, method), f"missing {method}"
            assert action_id in SHORT_HELP, f"missing help {action_id}"
        # Kern-Verkaufsfeatures sind in der TUI erreichbar (E2-Kern)
        for wanted in ("delta-z", "finding", "report-sign", "report-verify",
                       "report-keygen"):
            assert any(wanted == a for _, a in MENU), wanted


# ------------------------------------------- E1-Desktop: Controller-Signatur
class TestDesktopContext:
    def test_build_report_accepts_context(self, tmp_path, marked):
        from ai_watermark_toolkit.ui.desktop.controller import DesktopController
        ctrl = DesktopController()
        report = ctrl.build_report(marked, "demo-kgw-1", context={
            "institutional_rule": "PO §5", "origin_history": "Klausur"})
        assert report["context"]["provided"] is True
        assert "institutional_rule" in report["context"]["keys"]
