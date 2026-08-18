"""Verhaltens-Tests für die Kern-Layer (nicht Existenz-Checks).

Diese Suite prüft, dass die Module TUN was sie sollen — nicht nur,
dass Dateien existieren. Ergänzt die v8x-Struktur-Tests.
"""

from __future__ import annotations

from ai_watermark_toolkit.ingest import read_text
from ai_watermark_toolkit.report import sha256_text
from ai_watermark_toolkit.strip_markup import strip_markup
from ai_watermark_toolkit.transform.dilute import dilute_text
from ai_watermark_toolkit.transform.strategies.rule_rewrite import apply_rule_rewrite


# ---------------------------------------------------------------------------
# strip_markup (Layer B) — vorher komplett ungetestet
# ---------------------------------------------------------------------------
class TestStripMarkup:
    def test_removes_html_comments(self):
        r = strip_markup("<p>sichtbar</p><!-- geheim -->")
        assert "geheim" not in r.text
        assert "sichtbar" in r.text
        assert r.removed_comments >= 1

    def test_removes_hidden_style_spans(self):
        r = strip_markup('<span style="display:none">unsichtbar</span>')
        assert "display:none" not in r.text
        assert r.removed_hidden_spans >= 1

    def test_keeps_visible_text_intact(self):
        r = strip_markup("Normaler Text ohne Markup.")
        assert "Normaler Text" in r.text


# ---------------------------------------------------------------------------
# rule_rewrite — Flexions-Regeln (der Fix aus dem Deepcheck)
# ---------------------------------------------------------------------------
class TestRuleRewrite:
    def test_german_stock_opener(self):
        assert "Heute" in apply_rule_rewrite("In der heutigen digitalen Welt ist X.")

    def test_inflected_buzzword_nahtlose(self):
        out = apply_rule_rewrite("wir bieten nahtlose Lösungen")
        assert "reibungslose" in out
        assert "nahtlose" not in out

    def test_inflected_buzzword_nahtlosen(self):
        out = apply_rule_rewrite("mit nahtlosen Übergängen")
        assert "reibungslosen" in out

    def test_synergien(self):
        out = apply_rule_rewrite("wir heben Synergien")
        assert "Zusammenspiel" in out
        assert "Synergien" not in out

    def test_leveragen_german(self):
        out = apply_rule_rewrite("wir leveragen Technologie")
        assert "nutzen" in out

    def test_word_order_variant(self):
        out = apply_rule_rewrite("Heute ist es wichtig zu betonen, dass X.")
        assert "zu betonen" not in out


# ---------------------------------------------------------------------------
# dilute_text — Kern-Pipeline
# ---------------------------------------------------------------------------
class TestDilute:
    def test_standard_intensity_reduces_markers(self):
        text = "In der heutigen digitalen Welt ist es wichtig zu betonen, dass wir nahtlose Synergien heben."
        r = dilute_text(text, intensity="standard")
        for bad in ("digitalen Welt", "zu betonen", "nahtlose", "Synergien"):
            assert bad not in r.text, f"{bad!r} sollte ersetzt sein"

    def test_freezes_codeblocks(self):
        code = '```python\nprint("keep me")\n```'
        text = f"{code}\nNahtlose Lösungen."
        r = dilute_text(text, intensity="standard")
        assert 'print("keep me")' in r.text
        assert r.frozen_blocks == 1

    def test_light_intensity_returns_text(self):
        r = dilute_text("X und Y. Z und W.", intensity="light")
        assert r.intensity == "light"
        assert isinstance(r.text, str)


# ---------------------------------------------------------------------------
# ingest + report — klein, aber deterministisch
# ---------------------------------------------------------------------------
class TestIngestReport:
    def test_ingest_reads_stdin_text(self):
        r = read_text(stdin_text="Hallo Welt")
        assert "Hallo Welt" in r.text

    def test_sha256_is_stable(self):
        assert sha256_text("abc") == sha256_text("abc")
        # Format: "sha256:<64-hex>" — matches the report schema ("input_hash": "sha256:...")
        assert sha256_text("abc").startswith("sha256:")
        assert len(sha256_text("abc")) == 7 + 64
