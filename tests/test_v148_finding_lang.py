"""v148 — Finding/Report-Sprache wählbar (i18n DE/EN).

Kern-Contract: ``build_finding_report`` und ``build_report`` liefern mit
Default ``lang="de"`` exakt die bisherigen deutschen Texte (Abwärtskompati-
bilität, alle Alt-Tests matchen unverändert). Mit ``lang="en"`` werden alle
menschenlesbaren Textfelder englisch; die strukturierten Felder
(evidence_class, category, priority, risk, beleg) bleiben sprachneutral.

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
from ai_watermark_toolkit.forensics.kgw import mark_greenlist, detect_multi_key
from ai_watermark_toolkit.forensics.frequent_vocab import FREQUENT_VOCAB
from ai_watermark_toolkit.forensics.report import build_report

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


# ---------------------------------------------------------------- finding
def test_default_is_german(marked):
    """Ohne lang-Argument bleiben alle Texte deutsch (Alt-Contract)."""
    results = {"detect": detect_multi_key(marked, [{"key_id": "k",
                                                    "secret": KEY}]),
               "e_value": None, "delta_z": None}
    rep = build_finding_report(results, key_id="k")
    assert rep["lang"] == "de"
    f = rep["findings"][0]
    # deutsche Schlüsselphrasen der Evidenzklasse A (marked text, z>=4)
    assert "Wasserzeichen" in f["observation"]
    assert "KI" in rep["verdict_text"] or "nicht" in rep["verdict_text"]
    assert "Täuschung" in rep["schlussfolgerung_hinweis"]


def test_english_finding(marked):
    """lang='en' liefert englische Textfelder, strukturierte Felder identisch."""
    results = {"detect": detect_multi_key(marked, [{"key_id": "k",
                                                    "secret": KEY}]),
               "e_value": None, "delta_z": None}
    de = build_finding_report(results, key_id="k")
    en = build_finding_report(results, key_id="k", lang="en")
    assert en["lang"] == "en"
    f_de = de["findings"][0]
    f_en = en["findings"][0]
    # strukturierte Felder: sprachneutral
    assert f_de["evidence_class"] == f_en["evidence_class"]
    assert f_de["category"] == f_en["category"]
    assert f_de["priority"] == f_en["priority"]
    assert f_de["risk"] == f_en["risk"]
    assert f_de["beleg"] == f_en["beleg"]
    # Textfelder: übersetzt
    assert "watermark" in f_en["observation"].lower()
    assert "Wasserzeichen" not in f_en["observation"]
    assert "AI" in en["verdict_text"]
    assert "KI" not in en["verdict_text"]
    assert "deception" in en["schlussfolgerung_hinweis"].lower()
    # Erklärungen und Schritte nicht leer und englisch
    assert f_en["possible_explanations"]
    assert f_en["recommended_next_steps"]
    assert all("ä" not in s and "ö" not in s and "ü" not in s
               for s in f_en["possible_explanations"] + f_en["exculpatory"]
               + f_en["recommended_next_steps"])


def test_unknown_lang_falls_back_to_german(marked):
    """Unbekannte Sprache fällt auf Deutsch zurück (kein KeyError)."""
    results = {"detect": detect_multi_key(marked, [{"key_id": "k",
                                                    "secret": KEY}])}
    rep = build_finding_report(results, key_id="k", lang="fr")
    assert rep["lang"] == "fr"  # Echo des Requests, Texte aber deutsch
    assert "Wasserzeichen" in rep["findings"][0]["observation"]


# ---------------------------------------------------------------- HTML report
def test_html_report_de_default():
    de = build_report(TEXT, KEY, key_label="demo")
    assert "Forensik-Befund" in de
    assert "Erstellt" in de
    assert "<html lang=\"de\">" in de
    assert "WASSERZEICHEN" in de or "KEIN SIGNAL" in de or "TEXT ZU KURZ" in de


def test_html_report_en():
    en = build_report(TEXT, KEY, key_label="demo", lang="en")
    assert "Forensic Finding" in en
    assert "Created" in en
    assert "<html lang=\"en\">" in en
    assert "WATERMARK" in en or "NO SIGNAL" in en or "TEXT TOO SHORT" in en
    assert "Forensik-Befund" not in en
    assert "Erstellt" not in en


# ---------------------------------------------------------------- CLI
def test_cli_finding_lang_en(tmp_path, marked):
    """CLI finding --lang en liefert englischen verdict_text."""
    src = tmp_path / "marked.txt"
    src.write_text(marked, encoding="utf-8")
    r = run_cli(["finding", str(src), "--key", KEY, "--lang", "en"],
                cwd=str(tmp_path))
    assert r.returncode == 0, r.stderr
    rep = json.loads(r.stdout)
    assert rep["lang"] == "en"
    assert "AI" in rep["verdict_text"]
    assert "KI" not in rep["verdict_text"]
    assert "watermark" in rep["findings"][0]["observation"].lower()


def test_cli_finding_lang_default_de(tmp_path, marked):
    """CLI finding ohne --lang bleibt deutsch (Abwärtskompatibilität)."""
    src = tmp_path / "marked.txt"
    src.write_text(marked, encoding="utf-8")
    r = run_cli(["finding", str(src), "--key", KEY],
                cwd=str(tmp_path))
    assert r.returncode == 0, r.stderr
    rep = json.loads(r.stdout)
    assert rep["lang"] == "de"
    assert "Wasserzeichen" in rep["findings"][0]["observation"]
