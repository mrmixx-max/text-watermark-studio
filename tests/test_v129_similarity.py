"""Tests for the local corpus similarity check (2026-08-13).

Contract: deterministic MinHash comparison against a user-owned corpus,
literal-overlap detection with fundstelle evidence, honest boundary —
heavily paraphrased text scores LOW (documented, not hidden), and
binary/unreadable files are skipped without crashing.
"""

from pathlib import Path

from ai_watermark_toolkit.forensics.similarity import (
    check_similarity, _minhash, _jaccard, render_text, render_json)


TEXT_A = (
    "Die Angeklagten haben am Abend des 14. März die Fenster des Rathauses "
    "beschädigt und sind danach in unbekannte Richtung geflohen. Die Polizei "
    "bittet um Hinweise aus der Bevölkerung."
)
TEXT_A_COPY = TEXT_A  # identical
TEXT_A_EDITED = TEXT_A + "\n\nErgänzung: Zeugen werden gebeten, sich zu melden."
TEXT_PARAPHRASED = (
    "Am Abend des vierzehnten dritten Monats sollen die Beschuldigten die "
    "Fensterfronten des Verwaltungsgebäudes zerstört haben. Anschließend "
    "flüchteten sie in eine unbekannte Richtung, wie die Behörden mitteilen. "
    "Die Ermittler hoffen auf sachdienliche Hinweise."
)
TEXT_UNRELATED = (
    "Klimatische Veränderungen beeinflussen die Wanderrouten von Zugvögeln "
    "seit Jahrzehnten messbar. Ornithologen dokumentieren die Verschiebungen "
    "mit standardisierten Beobachtungsprotokollen."
)


def _corpus(tmp_path: Path) -> dict[str, Path]:
    d = tmp_path / "corpus"
    d.mkdir()
    (d / "a_original.txt").write_text(TEXT_A, encoding="utf-8")
    (d / "b_edited.txt").write_text(TEXT_A_EDITED, encoding="utf-8")
    (d / "c_unrelated.txt").write_text(TEXT_UNRELATED, encoding="utf-8")
    (d / "d_binary.png").write_bytes(b"\x89PNG\x00\x00binary-not-text")
    return {"dir": d, "original": d / "a_original.txt"}


class TestCore:
    def test_identical_text_scores_high(self, tmp_path):
        c = _corpus(tmp_path)
        r = check_similarity(TEXT_A, [c["dir"]])
        top = r["findings"][0]
        assert top["similarity"] > 0.95
        assert top["verdict"] == "high"
        assert top["fundstellen"]  # evidence quotes present

    def test_unrelated_scores_low(self, tmp_path):
        d = tmp_path / "only_unrelated"
        d.mkdir()
        (d / "c_unrelated.txt").write_text(TEXT_UNRELATED, encoding="utf-8")
        r = check_similarity(TEXT_A, [d])
        assert r["top_similarity"] < 0.2
        assert not r["findings"]

    def test_deterministic(self, tmp_path):
        c = _corpus(tmp_path)
        r1 = check_similarity(TEXT_A_EDITED, [c["dir"]])
        r2 = check_similarity(TEXT_A_EDITED, [c["dir"]])
        assert r1["top_similarity"] == r2["top_similarity"]

    def test_threshold_controls_findings(self, tmp_path):
        d = tmp_path / "only_original"
        d.mkdir()
        (d / "a_original.txt").write_text(TEXT_A, encoding="utf-8")
        # edited variant scores ~0.76: below a 0.99 threshold -> no findings
        r_strict = check_similarity(TEXT_A_EDITED, [d], threshold=0.99)
        assert not r_strict["findings"]
        # above a 0.7 threshold -> finding appears
        r_loose = check_similarity(TEXT_A_EDITED, [d], threshold=0.7)
        assert r_loose["findings"]

    def test_binary_files_skipped_not_crashed(self, tmp_path):
        c = _corpus(tmp_path)
        r = check_similarity(TEXT_A, [c["dir"]])
        assert r["corpus"]["skipped"] == 1
        assert any("d_binary.png" in s for s in r["corpus"]["skipped_paths"])

    def test_short_text_falls_back_to_smaller_shingles(self):
        sig, _ = _minhash("kurzer text")
        assert sig  # hashes something instead of crashing

    def test_empty_text_scores_zero(self, tmp_path):
        c = _corpus(tmp_path)
        r = check_similarity("", [c["dir"]])
        assert r["top_similarity"] == 0.0
        assert not r["findings"]

    def test_accepts_str_paths_like_tui(self, tmp_path):
        """Direct callers (TUI action_similarity) pass plain strings for the
        corpus dir; check_similarity takes TEXT as input, so the caller must
        read the file first — mirror the TUI flow exactly."""
        c = _corpus(tmp_path)
        text = c["original"].read_text(encoding="utf-8")
        r = check_similarity(text, [str(c["dir"])])
        assert r["top_similarity"] >= 0.95


class TestHonestBoundary:
    def test_paraphrase_scores_low(self, tmp_path):
        """The documented boundary: MinHash sees literal overlap, not
        meaning. A paraphrased rewrite must NOT be reported as high."""
        c = _corpus(tmp_path)
        r = check_similarity(TEXT_PARAPHRASED, [c["dir"]])
        assert r["top_similarity"] < 0.4, (
            "paraphrase scored too high — the honest boundary regressed")
        assert not r["findings"]


class TestRender:
    def test_render_text_and_json(self, tmp_path):
        c = _corpus(tmp_path)
        r = check_similarity(TEXT_A, [c["dir"]])
        assert "Similarity check" in render_text(r)
        assert '"findings"' in render_json(r)


class TestJaccard:
    def test_signature_identity(self):
        sig_a, _ = _minhash(TEXT_A)
        sig_b, _ = _minhash(TEXT_A)
        assert _jaccard(sig_a, sig_b) == 1.0
