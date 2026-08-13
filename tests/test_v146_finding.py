"""KI-Erklärungs-Befund (C5, 2026-08-13) — Evidenzklassen statt Schuld-Scoring.

Contract under test (Blaupause: dissertation-ai-authorship-audit):
- classify_finding(): Detektor-Ergebnis -> Evidenzklasse A/B/C:
  * markierter Text (detect, z >= 4, greenlist) -> C (technischer Indikator,
    NIE allein beweisend — auch bei z = 13.6!)
  * Redlist-Vorzeichen (redlist_detected, z < 0) -> A (reproduzierbares,
    keyed-Verifikations-Artefakt)
  * Bonferroni-adjustierter p-Wert < alpha -> A
  * konsistente Segmente (alle mean_z > 4) -> A
  * ΔZ mit removed:true -> B (Vergleichsbefund)
  * e_value detected -> C (ein E-Wert upgrade NIEMALS allein auf A/B)
  * ohne Kontext-Parameter -> context_missing:true (Evidenzklasse D nicht
    belegbar — ehrlich)
- Befund-Struktur: finding_id (F-xxxxxxxx), evidence_class, category,
  observation, beleg, possible_explanations >= 2, exculpatory, risk,
  priority (0-5), recommended_next_steps nicht leer.
- Anti-Hype: priority = PRÜFbedarf, nicht Schuld; verdict_text stellt NIE
  "KI-generiert" als Feststellung fest ("mit KI-Unterstützung vereinbar,
  beweist es nicht" / "Herkunft nicht bestimmbar").
- build_finding_report(): bündelt detect+e_value+delta_z, evidence_matrix,
  priority = max, signierter Befund (HMAC) verifizierbar.
- Determinismus: gleicher Text/Key -> gleiche finding_id.
- CLI ai-wm finding: JSON-Default, Exit 0 (Befund ist das Ergebnis), 2 =
  Input-Fehler; --sign -> verifizierbar.
- API POST /api/forensics/finding: 401 ohne Key, 200 mit, Struktur; Secret
  server-side aus der Registry.

No data/ writes: core/CLI tests use raw secrets; API tests monkeypatch the
route's registry AND audit logger.
"""

import json
import os
import random
import subprocess
import sys
from pathlib import Path

import pytest

from ai_watermark_toolkit.forensics.finding import (
    build_finding_report,
    classify_finding,
)
from ai_watermark_toolkit.forensics.key_registry import KeyRegistry
from ai_watermark_toolkit.forensics.kgw import (
    DEFAULT_GAMMA,
    detect_kgw,
    detect_multi_key,
    green_token,
    mark_greenlist,
)
from ai_watermark_toolkit.forensics.frequent_vocab import FREQUENT_VOCAB
from ai_watermark_toolkit.forensics.e_value import e_detect
from ai_watermark_toolkit.forensics.delta_z import delta_z
from ai_watermark_toolkit.forensics.signed_report import verify_report

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"

KEY = "demo-kgw-secret-0001"
GAMMA = 0.25
MARK_SEED = 0
SHUFFLE_SEED = 42

TEXT = (
    "Local AI models are crucial for maintaining user privacy and ensuring "
    "secure interactions with data processing. This reduces the amount of "
    "personal information shared with third parties. On-device processing "
    "keeps sensitive details under your control. The result is a lower risk "
    "of breaches and stronger protection. People gain more confidence when "
    "their data stays local and private systems keep everything on device "
    "without sending anything to remote servers or external infrastructure."
)

# Redlist-Korpus (test_v132-Muster): Silbenwörter, aus denen der Generator
# aus dem KOMPLEMENT der Greenlist wählt (z -> stark negativ, reproduzierbar).
_SIL1 = ("ba be bi bo bu ca ce ci co cu da de di do du fa fe fi fo fu "
         "ga ge gi go gu ka ke ki ko ku la le li lo lu ma me mi mo mu "
         "na ne ni no nu pa pe pi po pu ra re ri ro ru sa se si so su "
         "ta te ti to tu va ve vi vo vu wa we wi wo wu za ze zi zo zu").split()
_SIL2 = ("an en in on un ar er ir or ur al el il ol ul at et it ot ut "
         "as es is os us").split()
REDLIST_VOCAB = [s1 + s2 for s1 in _SIL1 for s2 in _SIL2]
REDLIST_KEY = "test-secret-alpha-001"


def generate_redlist(seed_token: str, key: str, n: int = 400,
                     gamma: float = DEFAULT_GAMMA, seed: int = 7) -> str:
    """KGW redlist generator (test_v132 pattern): picks from the COMPLEMENT."""
    rng = random.Random(seed)
    out = [seed_token]
    prev = seed_token
    for _ in range(n):
        red_cands = [c for c in REDLIST_VOCAB
                     if not green_token(c, prev, key, gamma)]
        chosen = rng.choice(red_cands) if red_cands else rng.choice(REDLIST_VOCAB)
        out.append(chosen)
        prev = chosen
    return " ".join(out)


def _shuffle(text: str, seed: int = SHUFFLE_SEED) -> str:
    """Word shuffle with the attack_matrix seed (42) — deterministic."""
    rng = random.Random(seed)
    words = text.split()
    rng.shuffle(words)
    return " ".join(words)


@pytest.fixture(scope="module")
def marked() -> str:
    """Deterministic marked text (seed 0). z = 13.6083, >= 4."""
    return mark_greenlist(TEXT, KEY, vocab=FREQUENT_VOCAB, seed=MARK_SEED)["text"]


def run_cli(args, stdin=None, cwd=None):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC)
    base = [sys.executable, "-m", "ai_watermark_toolkit.cli"]
    return subprocess.run(base + args, capture_output=True, text=True,
                          input=stdin, env=env, cwd=cwd or REPO)


# ---------------------------------------------------------------- classify
class TestClassifyFinding:
    def test_marked_text_is_class_c(self, marked):
        """Ein grüner z-Score (z = 13.6!) ist ein TECHNISCHER INDIKATOR -> C.

        Die Anti-Hype-Regel: selbst ein überwältigender Z-Wert aus der
        keyed-Detektion ist nie allein beweisend — nur Redlist-Vorzeichen,
        Bonferroni-p und konsistente Segmente heben auf Klasse A.
        """
        d = detect_multi_key(marked, [{"key_id": KEY, "family": "kgw",
                                       "secret": KEY}])
        best = d["best"]
        assert best["z_score"] >= 4.0, best
        f = classify_finding(d)
        assert f["evidence_class"] == "C", f
        assert f["category"] == "Detektion"
        assert f["priority"] == 3  # Prüfbedarf mittel, nicht Schuld
        assert f["risk"] == "medium"
        # Klasse-C-Regel sichtbar in der Beobachtung
        assert "nie allein beweisend" in f["observation"] or "Evidenzklasse C" in f["observation"]

    def test_redlist_is_class_a(self):
        """Redlist-Vorzeichen: reproduzierbares, keyed-Verifikations-Artefakt -> A."""
        text = generate_redlist("start", REDLIST_KEY)
        r = detect_kgw(text, REDLIST_KEY)
        assert r["verdict"] == "redlist_detected", r
        assert r["z_score"] < -4.0
        f = classify_finding(r)
        assert f["evidence_class"] == "A", f
        assert f["category"] == "Redlist"
        assert f["priority"] == 5
        assert f["risk"] == "high"

    def test_redlist_weak_stays_class_c(self):
        """Schwaches Redlist-Signal (|z| < 4) hebt NICHT auf Klasse A."""
        r = {"verdict": "weak_redlist_signal", "signal": "redlist",
             "z_score": -2.5, "p_value": 0.012}
        f = classify_finding(r)
        assert f["evidence_class"] == "C", f
        assert f["category"] == "Redlist"
        assert f["priority"] == 2

    def test_bonferroni_p_adjusted_is_class_a(self):
        """Bonferroni-adjustierter p-Wert < alpha -> überprüfbarer Befund A."""
        r = {"verdict": "no_signal", "z_score": 2.1, "p_value": 0.4,
             "best_p_adjusted": 0.0001, "tested_keys": 5,
             "note": "bonferroni_adjusted_over_5_keys"}
        f = classify_finding(r)
        assert f["evidence_class"] == "A", f
        assert f["priority"] == 4

    def test_unadjusted_p_value_never_class_a(self):
        """Nur der UNADJUSTIERTE p-Wert bleibt Klasse C (Einzelhypothese)."""
        r = {"verdict": "watermark_detected", "signal": "greenlist",
             "z_score": 9.0, "p_value": 1e-12, "n_tokens": 300}
        f = classify_finding(r)
        assert f["evidence_class"] == "C", f

    def test_consistent_segments_is_class_a(self):
        """Konsistente Segmente (alle mean_z > 4, >= 2 Segmente) -> A."""
        r = {"verdict": "no_signal", "z_score": 0.1,
             "segments": [{"mean_z": 9.0}, {"mean_z": 8.5}, {"mean_z": 12.0}]}
        f = classify_finding(r)
        assert f["evidence_class"] == "A", f

    def test_single_segment_not_class_a(self):
        """Ein einzelnes Segment ist nur der ganze Text — kein Klasse-A-Beleg."""
        r = {"verdict": "no_signal", "z_score": 0.1,
             "segments": [{"mean_z": 9.0}]}
        f = classify_finding(r)
        assert f["evidence_class"] == "C", f

    def test_delta_z_removed_is_class_b(self, marked):
        """ΔZ mit removed:true -> Vergleichsbefund, Klasse B."""
        dz = delta_z(marked, _shuffle(marked), KEY)
        assert dz["removed"] is True
        f = classify_finding(dz)
        assert f["evidence_class"] == "B", f
        assert f["category"] == "Delta-Z"
        assert f["priority"] == 4

    def test_delta_z_not_removed_stays_class_c(self, marked):
        """ΔZ ohne Signalwechsel (removed:false) ist KEIN Klasse-B-Beleg."""
        dz = delta_z(marked, marked, KEY)
        assert dz["removed"] is False
        f = classify_finding(dz)
        assert f["evidence_class"] == "C", f

    def test_e_value_detected_stays_class_c(self, marked):
        """E-Wert detected -> C. Ein E-Wert upgrade NIEMALS allein auf A/B."""
        ev = e_detect(marked, KEY)
        assert ev["detected"] is True, ev
        f = classify_finding(ev)
        assert f["evidence_class"] == "C", f
        assert f["category"] == "E-Wert"
        assert f["priority"] == 3
        assert f["risk"] == "medium"

    def test_no_signal_low_priority(self):
        r = detect_kgw(TEXT, KEY)  # unmarkierter Text, z ~ 0
        assert r["verdict"] == "no_signal"
        f = classify_finding(r)
        assert f["evidence_class"] == "C"
        assert f["priority"] == 1
        assert f["risk"] == "low"

    def test_too_short(self):
        r = detect_kgw("kurz", KEY)
        assert r["verdict"] == "too_short"
        f = classify_finding(r)
        assert f["evidence_class"] == "C"
        assert f["priority"] == 1

    def test_context_missing_without_context(self, marked):
        """Ohne Kontext-Parameter -> context_missing:true (Klasse D ehrlich)."""
        d = detect_multi_key(marked, [{"key_id": KEY, "family": "kgw",
                                       "secret": KEY}])
        f = classify_finding(d)
        assert f["context_missing"] is True
        assert any("Kontext" in e for e in f["exculpatory"])

    def test_context_provided_clears_flag(self, marked):
        """Institutionelle Regel / Entstehungshistorie -> context_missing:false."""
        d = detect_multi_key(marked, [{"key_id": KEY, "family": "kgw",
                                       "secret": KEY}])
        ctx = {"institutional_rule": "KI-Nutzung muss deklariert werden",
               "origin_history": "Entwurf 2026-01, 3 Versionen, Betreuerfeedback"}
        f = classify_finding(d, context=ctx)
        assert f["context_missing"] is False
        assert f["context_notes"]["institutional_rule"]
        assert f["context_notes"]["origin_history"]

    def test_empty_context_dict_is_missing(self, marked):
        """Ein leeres context-Dict zählt als fehlender Kontext (keine Regel)."""
        d = detect_multi_key(marked, [{"key_id": KEY, "family": "kgw",
                                       "secret": KEY}])
        assert classify_finding(d, context={})["context_missing"] is True


# ---------------------------------------------------------------- Struktur
class TestFindingStructure:
    def _marked_finding(self, marked):
        d = detect_multi_key(marked, [{"key_id": KEY, "family": "kgw",
                                       "secret": KEY}])
        return classify_finding(d)

    def test_full_schema(self, marked):
        f = self._marked_finding(marked)
        assert f["finding_id"].startswith("F-")
        assert len(f["finding_id"]) == 10  # F- + 8 hex
        assert f["evidence_class"] in ("A", "B", "C", "D")
        assert isinstance(f["observation"], str) and f["observation"]
        assert isinstance(f["beleg"], dict) and "z_score" in f["beleg"]
        assert isinstance(f["priority"], int) and 0 <= f["priority"] <= 5
        assert f["risk"] in ("low", "medium", "high")
        assert f["context_missing"] in (True, False)

    def test_possible_explanations_at_least_two(self, marked):
        for f in (self._marked_finding(marked),
                  classify_finding({"verdict": "redlist_detected",
                                    "signal": "redlist", "z_score": -11.5}),
                  classify_finding({"removed": True, "delta_z": 5.0,
                                    "z_before": 9.0, "z_after": 2.0,
                                    "verdict_before": "watermark_detected",
                                    "verdict_after": "no_signal"}),
                  classify_finding({"e_value": 99.0, "detected": True,
                                    "verdict": "e_value_detected",
                                    "threshold": 20.0, "n_tokens": 50})):
            assert len(f["possible_explanations"]) >= 2, f
            assert len(f["exculpatory"]) >= 1, f
            assert f["recommended_next_steps"], f

    def test_beleg_carries_numbers(self, marked):
        f = self._marked_finding(marked)
        assert f["beleg"]["z_score"] >= 4.0
        assert f["beleg"]["verdict"] == "watermark_detected"

    def test_delta_z_finding_beleg(self, marked):
        dz = delta_z(marked, _shuffle(marked), KEY)
        f = classify_finding(dz)
        assert f["beleg"]["delta_z"] > 0
        assert f["beleg"]["removed"] is True

    def test_anti_hype_priority_is_int_not_probability(self, marked):
        """priority ist ein int 0-5 (Prüfbedarf), nie eine Prozentzahl."""
        f = self._marked_finding(marked)
        assert isinstance(f["priority"], int)
        assert not isinstance(f["priority"], float)

    def test_no_guilt_language_in_observation(self, marked):
        """Der Befund beschreibt ein Signal, nie einen Täter."""
        f = self._marked_finding(marked)
        lower = f["observation"].lower()
        assert "betrug" not in lower
        assert "schuld" not in lower


# ---------------------------------------------------------------- Report
class TestBuildFindingReport:
    def test_bundles_modules(self, marked):
        d = detect_multi_key(marked, [{"key_id": KEY, "family": "kgw",
                                       "secret": KEY}])
        ev = e_detect(marked, KEY)
        dz = delta_z(marked, _shuffle(marked), KEY)
        rep = build_finding_report({"detect": d, "e_value": ev, "delta_z": dz},
                                   key_id=KEY)
        assert rep["report_type"] == "ki-erklaerungs-befund"
        assert len(rep["findings"]) == 3
        classes = {f["evidence_class"] for f in rep["findings"]}
        assert classes == {"B", "C"}
        assert rep["summary"]["findings_total"] == 3
        assert rep["summary"]["class_b"] == 1
        assert rep["summary"]["context_missing"] is True
        assert rep["priority"] == 4  # max der Einzelprioritäten (B=4 > C=3)
        assert len(rep["evidence_matrix"]) == 3
        row = rep["evidence_matrix"][0]
        assert set(row) >= {"finding_id", "evidence_class", "category",
                            "observation", "risk", "priority",
                            "possible_explanations", "next_step"}

    def test_flat_detect_result_accepted(self, marked):
        d = detect_multi_key(marked, [{"key_id": KEY, "family": "kgw",
                                       "secret": KEY}])
        rep = build_finding_report(d, key_id=KEY)
        assert len(rep["findings"]) == 1
        assert rep["findings"][0]["evidence_class"] == "C"

    def test_verdict_text_never_concludes_ai_generated(self, marked):
        """Anti-Hype: 'KI-generiert' erscheint NIE als Feststellung."""
        d = detect_multi_key(marked, [{"key_id": KEY, "family": "kgw",
                                       "secret": KEY}])
        ev = e_detect(marked, KEY)
        dz = delta_z(marked, _shuffle(marked), KEY)
        rep = build_finding_report({"detect": d, "e_value": ev, "delta_z": dz},
                                   key_id=KEY)
        assert "KI-generiert" not in rep["verdict_text"]
        assert "KI-Unterstützung vereinbar" in rep["verdict_text"]
        assert "nicht" in rep["verdict_text"]  # beweist es nicht

    def test_verdict_text_herkunft_not_bestimmbar(self, marked):
        d = detect_multi_key(marked, [{"key_id": KEY, "family": "kgw",
                                       "secret": KEY}])
        rep = build_finding_report(d, key_id=KEY)
        assert "Herkunft nicht" in rep["verdict_text"]

    def test_verdict_text_no_signal_case(self):
        r = detect_kgw(TEXT, KEY)  # unmarkiert -> no_signal
        rep = build_finding_report(r, key_id=KEY)
        assert rep["priority"] == 1
        assert "keine belastbaren technischen Indikatoren" in rep["verdict_text"]
        assert "KI-generiert" not in rep["verdict_text"]

    def test_verdict_text_class_a_case(self):
        """Klasse A: vertiefte Prüfung angezeigt, aber keine Feststellung."""
        r = {"verdict": "redlist_detected", "signal": "redlist",
             "z_score": -11.55, "p_value": 1e-20}
        rep = build_finding_report(r, key_id=REDLIST_KEY)
        assert rep["priority"] == 5
        assert "dringend angezeigt" in rep["verdict_text"]
        assert "KI-generiert" not in rep["verdict_text"]
        assert "beweisen sie" in rep["verdict_text"]

    def test_schlussfolgerung_hinweis(self, marked):
        d = detect_multi_key(marked, [{"key_id": KEY, "family": "kgw",
                                       "secret": KEY}])
        rep = build_finding_report(d, key_id=KEY)
        assert "keine KI-Nutzung, kein Plagiat und keine Täuschung" in rep["schlussfolgerung_hinweis"]

    def test_signed_report_valid(self, marked):
        d = detect_multi_key(marked, [{"key_id": KEY, "family": "kgw",
                                       "secret": KEY}])
        signed = build_finding_report(d, key_id=KEY, sign_secret="hmac-secret-1")
        sig = signed["signature"]
        assert sig["algorithm"] == "hmac-sha256"
        assert sig["key_id"] == KEY
        assert verify_report(signed, "hmac-secret-1")["valid"] is True
        assert verify_report(signed, "wrong-secret")["valid"] is False

    def test_unsigned_report_has_no_signature(self, marked):
        d = detect_multi_key(marked, [{"key_id": KEY, "family": "kgw",
                                       "secret": KEY}])
        rep = build_finding_report(d, key_id=KEY)
        assert "signature" not in rep

    def test_deterministic_finding_id(self, marked):
        """Gleicher Text/Key -> gleiche finding_id (reproduzierbar)."""
        d1 = detect_multi_key(marked, [{"key_id": KEY, "family": "kgw",
                                        "secret": KEY}])
        d2 = detect_multi_key(marked, [{"key_id": KEY, "family": "kgw",
                                        "secret": KEY}])
        assert classify_finding(d1)["finding_id"] == classify_finding(d2)["finding_id"]
        # Verschiedener Schlüssel -> verschiedene ID
        other = {"verdict": "no_signal", "z_score": 0.2, "p_value": 0.9}
        assert classify_finding(other)["finding_id"] != classify_finding(d1)["finding_id"]

    def test_priority_is_max_of_findings(self, marked):
        d = detect_multi_key(marked, [{"key_id": KEY, "family": "kgw",
                                       "secret": KEY}])  # C, prio 3
        rl = {"verdict": "redlist_detected", "signal": "redlist",
              "z_score": -11.55, "p_value": 1e-20}  # A, prio 5
        rep = build_finding_report({"detect": d, "delta_z": rl}, key_id=KEY)
        assert rep["priority"] == 5


# ---------------------------------------------------------------- CLI
class TestCliFinding:
    def _write(self, tmp_path, name, text):
        f = tmp_path / name
        f.write_text(text, encoding="utf-8")
        return f

    def test_cli_roundtrip_exit_0_json(self, tmp_path, marked):
        f = self._write(tmp_path, "marked.txt", marked)
        r = run_cli(["finding", str(f), "--key", KEY], cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout)
        assert out["report_type"] == "ki-erklaerungs-befund"
        assert out["findings"][0]["evidence_class"] == "C"
        assert out["findings"][0]["context_missing"] is True
        assert "KI-generiert" not in out["verdict_text"]

    def test_cli_e_value_and_delta_z_combined(self, tmp_path, marked):
        f = self._write(tmp_path, "b.txt", marked)
        a = self._write(tmp_path, "a.txt", _shuffle(marked))
        r = run_cli(["finding", str(f), "--key", KEY, "--e-value",
                     "--delta-z", str(a)], cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout)
        assert len(out["findings"]) == 3
        classes = {x["evidence_class"] for x in out["findings"]}
        assert classes == {"B", "C"}
        cats = {x["category"] for x in out["findings"]}
        assert {"Delta-Z", "E-Wert", "Detektion"} <= cats

    def test_cli_sign_verifiable(self, tmp_path, marked):
        f = self._write(tmp_path, "b.txt", marked)
        r = run_cli(["finding", str(f), "--key", KEY, "--sign", "cli-secret-1"],
                    cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        signed = json.loads(r.stdout)
        assert signed["signature"]["algorithm"] == "hmac-sha256"
        assert verify_report(signed, "cli-secret-1")["valid"] is True

    def test_cli_output_file(self, tmp_path, marked):
        f = self._write(tmp_path, "b.txt", marked)
        out = tmp_path / "finding.json"
        r = run_cli(["finding", str(f), "--key", KEY, "-o", str(out)],
                    cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        assert json.loads(out.read_text(encoding="utf-8"))["findings"][0]["evidence_class"] == "C"

    def test_cli_stdin(self, tmp_path, marked):
        r = run_cli(["finding", "--stdin", "--key", KEY], stdin=marked,
                    cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        assert json.loads(r.stdout)["findings"][0]["evidence_class"] == "C"

    def test_cli_missing_key_exit_2(self, tmp_path, marked):
        f = self._write(tmp_path, "b.txt", marked)
        r = run_cli(["finding", str(f)], cwd=tmp_path)
        assert r.returncode == 2
        assert "--key" in r.stderr

    def test_cli_missing_input_exit_2(self, tmp_path):
        r = run_cli(["finding", "--key", KEY], cwd=tmp_path)
        assert r.returncode == 2
        assert "input file" in r.stderr

    def test_cli_missing_file_exit_2(self, tmp_path):
        r = run_cli(["finding", str(tmp_path / "nope.txt"), "--key", KEY],
                    cwd=tmp_path)
        assert r.returncode == 2
        assert "file not found" in r.stderr.lower()

    def test_cli_deterministic_finding_id(self, tmp_path, marked):
        f = self._write(tmp_path, "b.txt", marked)
        r1 = run_cli(["finding", str(f), "--key", KEY], cwd=tmp_path)
        r2 = run_cli(["finding", str(f), "--key", KEY], cwd=tmp_path)
        id1 = json.loads(r1.stdout)["findings"][0]["finding_id"]
        id2 = json.loads(r2.stdout)["findings"][0]["finding_id"]
        assert id1 == id2
        assert id1.startswith("F-")


# ---------------------------------------------------------------- API
class TestApiFinding:
    def _client(self, tmp_path, monkeypatch):
        from fastapi.testclient import TestClient
        from ai_watermark_toolkit.api import fastapi_app
        from ai_watermark_toolkit.api.routes import forensics as forensics_route

        reg = KeyRegistry(str(tmp_path / "keys.json"))
        monkeypatch.setattr(forensics_route, "keys", reg)
        # audit writes data/audit.log — silence it (no data/ writes in tests)
        monkeypatch.setattr(forensics_route, "audit",
                            type("DummyAudit", (), {"write": lambda self, p: p})())
        return TestClient(fastapi_app.app)

    def _register(self, client, key_id="find-api-1", secret=KEY):
        client.post("/api/forensics/keys",
                    json={"key_id": key_id, "family": "kgw", "secret": secret,
                          "gamma": GAMMA})

    def test_api_requires_auth(self, tmp_path, monkeypatch, marked):
        from types import SimpleNamespace
        from ai_watermark_toolkit.api.middleware import auth as auth_mod
        c = self._client(tmp_path, monkeypatch)
        self._register(c)
        monkeypatch.setattr(auth_mod, "settings",
                            SimpleNamespace(api_key="test-secret"))
        body = {"text": marked, "key_id": "find-api-1"}
        r = c.post("/api/forensics/finding", json=body)
        assert r.status_code == 401
        r = c.post("/api/forensics/finding", json=body,
                   headers={"X-API-Key": "test-secret"})
        assert r.status_code == 200, r.text
        assert r.json()["report_type"] == "ki-erklaerungs-befund"

    def test_api_finding_structure(self, tmp_path, monkeypatch, marked):
        c = self._client(tmp_path, monkeypatch)
        self._register(c)
        r = c.post("/api/forensics/finding",
                   json={"text": marked, "key_id": "find-api-1"})
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["key_id"] == "find-api-1"
        assert out["findings"][0]["evidence_class"] == "C"
        assert out["findings"][0]["context_missing"] is True
        assert "secret" not in json.dumps(out)
        assert "KI-generiert" not in out["verdict_text"]
        assert isinstance(out["priority"], int) and 0 <= out["priority"] <= 5

    def test_api_e_value_option(self, tmp_path, monkeypatch, marked):
        c = self._client(tmp_path, monkeypatch)
        self._register(c)
        r = c.post("/api/forensics/finding",
                   json={"text": marked, "key_id": "find-api-1", "e_value": True})
        assert r.status_code == 200, r.text
        out = r.json()
        assert len(out["findings"]) == 2
        cats = {x["category"] for x in out["findings"]}
        assert "E-Wert" in cats

    def test_api_delta_z_option(self, tmp_path, monkeypatch, marked):
        c = self._client(tmp_path, monkeypatch)
        self._register(c)
        r = c.post("/api/forensics/finding",
                   json={"text": marked, "key_id": "find-api-1",
                         "delta_z": {"text_after": _shuffle(marked)}})
        assert r.status_code == 200, r.text
        out = r.json()
        assert len(out["findings"]) == 2
        classes = {x["evidence_class"] for x in out["findings"]}
        assert "B" in classes  # removed:true -> Vergleichsbefund

    def test_api_delta_z_transform_option(self, tmp_path, monkeypatch, marked):
        c = self._client(tmp_path, monkeypatch)
        self._register(c)
        r = c.post("/api/forensics/finding",
                   json={"text": marked, "key_id": "find-api-1",
                         "delta_z": {"transform": "shuffle"}})
        assert r.status_code == 200, r.text
        classes = {x["evidence_class"] for x in r.json()["findings"]}
        assert "B" in classes

    def test_api_sign_true_signed_with_registry_secret(self, tmp_path, monkeypatch, marked):
        """sign=true -> Report signiert mit dem REGISTRY-Secret (= KEY hier)."""
        c = self._client(tmp_path, monkeypatch)
        self._register(c)
        r = c.post("/api/forensics/finding",
                   json={"text": marked, "key_id": "find-api-1", "sign": True})
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["signature"]["algorithm"] == "hmac-sha256"
        assert verify_report(out, KEY)["valid"] is True

    def test_api_unknown_key_404(self, tmp_path, monkeypatch, marked):
        c = self._client(tmp_path, monkeypatch)
        r = c.post("/api/forensics/finding",
                   json={"text": marked, "key_id": "nope"})
        assert r.status_code == 404

    def test_api_body_secret_ignored(self, tmp_path, monkeypatch, marked):
        """Secret NIE im Body: key_id muss registriert sein."""
        c = self._client(tmp_path, monkeypatch)
        r = c.post("/api/forensics/finding",
                   json={"text": marked, "key_id": "find-api-1",
                         "secret": "forged-in-body"})
        assert r.status_code == 404  # nicht registriert -> kein Server-Secret

    def test_api_delta_z_missing_text_after_400(self, tmp_path, monkeypatch, marked):
        c = self._client(tmp_path, monkeypatch)
        self._register(c)
        r = c.post("/api/forensics/finding",
                   json={"text": marked, "key_id": "find-api-1",
                         "delta_z": {}})
        assert r.status_code == 400

    def test_api_priority_scaling_redlist(self, tmp_path, monkeypatch):
        """Redlist-Text -> priority 5 über die API (Klasse A)."""
        c = self._client(tmp_path, monkeypatch)
        self._register(c, key_id="rl-api-1", secret=REDLIST_KEY)
        red = generate_redlist("start", REDLIST_KEY)
        r = c.post("/api/forensics/finding",
                   json={"text": red, "key_id": "rl-api-1"})
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["findings"][0]["evidence_class"] == "A"
        assert out["priority"] == 5
        assert out["findings"][0]["risk"] == "high"
