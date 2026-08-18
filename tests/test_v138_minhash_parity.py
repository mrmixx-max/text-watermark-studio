"""Regression: MinHash-Refactor F4 (2026-08-13).

Paritäts-Nachweis: Die 128x-SHA256-Implementierung (alte Signaturen) wurde
durch 1x-SHA256 + splitmix64-Bitmixing-Permutationen ersetzt und der Corpus
wird jetzt signatur-gecacht (keyed mtime/groesse). Verhalten muss erhalten
bleiben:

- Identische Texte -> exakt 1.0 (beide Implementierungen, exakte Parität),
- Unabhängige Texte -> exakt 0.0,
- Reihenfolge, Verdicts und Fundstellen-Zahl auf dem Fixture-Corpus
  IDENTISCH zum Alt-Snapshot (vor dem Refactor gemessen),
- Scores innerhalb der MinHash-Estimator-Varianz (|diff| <= 0.06 bei 128
  Permutationen; Std-Fehler ~ 1/sqrt(128) ~ 0.088),
- Corpus-Signatur-Cache: zweiter Aufruf identisches Ergebnis, Invalidation
  bei Dateiänderung, clear_signature_cache() wirkt.

Alt-Snapshot (gemessen mit HEAD eb05b9c, vor dem Refactor) ist als
Konstanten eingefroren — die neue Implementierung muss sie reproduzieren.
"""

from pathlib import Path

from ai_watermark_toolkit.forensics.similarity import (
    _jaccard,
    _minhash,
    _verdict,
    check_similarity,
    clear_signature_cache,
)

TEXT_A = (
    "Die Angeklagten haben am Abend des 14. März die Fenster des Rathauses "
    "beschädigt und sind danach in unbekannte Richtung geflohen. Die Polizei "
    "bittet um Hinweise aus der Bevölkerung."
)
TEXT_A_EDITED = TEXT_A + "\n\nErgänzung: Zeugen werden gebeten, sich zu melden."
TEXT_PARAPHRASED = (
    "Am Abend des vierzehnten dritten Monats sollen die Beschuldigten die "
    "Fensterfronten des Verwaltungsgebäudes zerstört haben. Anschließend "
    "flüchteten sie in eine unbekannte Richtung, wie die Behörden mitteilen."
)
TEXT_UNRELATED = (
    "Klimatische Veränderungen beeinflussen die Wanderrouten von Zugvögeln "
    "seit Jahrzehnten messbar. Ornithologen dokumentieren die Verschiebungen "
    "mit standardisierten Beobachtungsprotokollen."
)

# e_long.txt im Fixture-Corpus: exakt der Inhalt, den der Alt-Snapshot gemessen
# hat (20-Satz-Pool aus dem Bench, dreifach wiederholt) — Parität erfordert
# byte-identische Fixture-Dateien.
_SENTENCES = [
    "Die Angeklagten haben am Abend des 14. Maerz die Fenster des Rathauses beschädigt.",
    "Die Polizei bittet um Hinweise aus der Bevölkerung zu dem Vorfall in der Innenstadt.",
    "Klimatische Veränderungen beeinflussen die Wanderrouten von Zugvögeln seit Jahrzehnten.",
    "Ornithologen dokumentieren die Verschiebungen mit standardisierten Beobachtungsprotokollen.",
    "Der Bericht fasst die aktuellen Erkenntnisse aus mehreren Fachbereichen zusammen.",
    "Analysten haben die Daten geprüft und mit früheren Ergebnissen verglichen.",
    "Das neue Verfahren reduziert den Aufwand und erhöht gleichzeitig die Genauigkeit.",
    "Die Untersuchungskommission tagt wöchentlich und protokolliert alle Entscheidungen.",
    "Ein sorgfältig geplantes Experiment bestätigt die zentrale Hypothese der Studie.",
    "Die Ergebnisse wurden unabhängig repliziert und statistisch abgesichert.",
    "The report summarizes current findings across several independent research domains.",
    "Researchers compared the new dataset with earlier measurements from the same region.",
    "A carefully designed experiment confirms the central hypothesis of the study.",
    "All findings were replicated independently and secured with statistical tests.",
    "The committee meets weekly and records every decision in a public protocol.",
    "Weather patterns in the coastal region shift gradually with the changing climate.",
    "Historians analyze the documents using standardized source criticism methods.",
    "The investigation focused on the events that took place on the evening of March 14.",
    "Witnesses were asked to contact the authorities with any relevant information.",
    "Die Ermittler hoffen auf sachdienliche Hinweise aus der Bevölkerung.",
]
TEXT_LONG = "\n\n".join(_SENTENCES) * 3

# Alt-Snapshot (128x-SHA256-Implementierung, vor dem F4-Refactor gemessen).
OLD_SNAPSHOT = {
    "text_a": {
        "order": ["a_original.txt", "b_edited.txt", "e_long.txt", "c_unrelated.txt", "d_paraphrase.txt"],
        "verdicts": {
            "a_original.txt": "high",
            "b_edited.txt": "high",
            "e_long.txt": "low",
            "c_unrelated.txt": "none",
            "d_paraphrase.txt": "none",
        },
        "overlaps": {
            "a_original.txt": 3,
            "b_edited.txt": 3,
            "e_long.txt": 3,
            "c_unrelated.txt": 0,
            "d_paraphrase.txt": 0,
        },
        "scores": {
            "a_original.txt": 1.0,
            "b_edited.txt": 0.7578,
            "e_long.txt": 0.0312,
            "c_unrelated.txt": 0.0,
            "d_paraphrase.txt": 0.0,
        },
    },
    "text_a_edited": {
        "order": ["b_edited.txt", "a_original.txt", "e_long.txt", "c_unrelated.txt", "d_paraphrase.txt"],
        "verdicts": {
            "b_edited.txt": "high",
            "a_original.txt": "high",
            "e_long.txt": "low",
            "c_unrelated.txt": "none",
            "d_paraphrase.txt": "none",
        },
        "overlaps": {
            "b_edited.txt": 3,
            "a_original.txt": 3,
            "e_long.txt": 3,
            "c_unrelated.txt": 0,
            "d_paraphrase.txt": 0,
        },
        "scores": {
            "b_edited.txt": 1.0,
            "a_original.txt": 0.7578,
            "e_long.txt": 0.0312,
            "c_unrelated.txt": 0.0,
            "d_paraphrase.txt": 0.0,
        },
    },
    "paraphrase": {
        "order": ["d_paraphrase.txt", "a_original.txt", "b_edited.txt", "c_unrelated.txt", "e_long.txt"],
        "verdicts": {
            "d_paraphrase.txt": "high",
            "a_original.txt": "none",
            "b_edited.txt": "none",
            "c_unrelated.txt": "none",
            "e_long.txt": "none",
        },
        "overlaps": {
            "d_paraphrase.txt": 3,
            "a_original.txt": 0,
            "b_edited.txt": 0,
            "c_unrelated.txt": 0,
            "e_long.txt": 0,
        },
        "scores": {
            "d_paraphrase.txt": 1.0,
            "a_original.txt": 0.0,
            "b_edited.txt": 0.0,
            "c_unrelated.txt": 0.0,
            "e_long.txt": 0.0,
        },
    },
    "unrelated": {
        "order": ["c_unrelated.txt", "e_long.txt", "a_original.txt", "b_edited.txt", "d_paraphrase.txt"],
        "verdicts": {
            "c_unrelated.txt": "high",
            "e_long.txt": "low",
            "a_original.txt": "none",
            "b_edited.txt": "none",
            "d_paraphrase.txt": "none",
        },
        "overlaps": {
            "c_unrelated.txt": 3,
            "e_long.txt": 3,
            "a_original.txt": 0,
            "b_edited.txt": 0,
            "d_paraphrase.txt": 0,
        },
        "scores": {
            "c_unrelated.txt": 1.0,
            "e_long.txt": 0.0156,
            "a_original.txt": 0.0,
            "b_edited.txt": 0.0,
            "d_paraphrase.txt": 0.0,
        },
    },
}

# MinHash-Estimator-Varianz bei 128 Permutationen: Std-Fehler ~ 1/sqrt(128)
# ~ 0.088. Die neue Permutationsfamilie (splitmix64 statt 128x-SHA256) ist
# eine ANDERE, aber gleichwertige Zufallspermutation — Scores dürfen um
# maximal 0.06 abweichen (unter einem Std-Fehler), Reihenfolge/Verdicts
# müssen exakt bleiben.
SCORE_TOLERANCE = 0.06


def _corpus(tmp_path: Path) -> Path:
    d = tmp_path / "corpus"
    d.mkdir()
    (d / "a_original.txt").write_text(TEXT_A, encoding="utf-8")
    (d / "b_edited.txt").write_text(TEXT_A_EDITED, encoding="utf-8")
    (d / "c_unrelated.txt").write_text(TEXT_UNRELATED, encoding="utf-8")
    (d / "d_paraphrase.txt").write_text(TEXT_PARAPHRASED, encoding="utf-8")
    (d / "e_long.txt").write_text(TEXT_LONG, encoding="utf-8")
    return d


def _full_rows(report: dict) -> dict[str, dict]:
    """Alle Scores+Fundstellen aus einem check_similarity-Report (threshold=0)."""
    out = {}
    for f in report["findings"]:
        name = Path(f["path"]).name
        out[name] = {
            "similarity": f["similarity"],
            # Verdict immer mit dem Produkt-Threshold 0.4 (der Report
            # wurde hier mit threshold=0.0 erzeugt, um ALLE Dateien zu
            # sehen — dessen Verdicts wären dadurch verzerrt).
            "verdict": _verdict(f["similarity"], 0.4),
            "overlaps": len(f["fundstellen"]),
        }
    return out


class TestMinHashParity:
    """Neue Implementierung reproduziert die Alt-Ergebnisse (Snapshot)."""

    def test_identical_input_exact_parity(self, tmp_path):
        d = _corpus(tmp_path)
        cases = {
            TEXT_A: "a_original.txt",
            TEXT_A_EDITED: "b_edited.txt",
            TEXT_PARAPHRASED: "d_paraphrase.txt",
            TEXT_UNRELATED: "c_unrelated.txt",
        }
        for text, fname in cases.items():
            r = check_similarity(text, [d], threshold=0.0, top=20)
            rows = _full_rows(r)
            assert rows[fname]["similarity"] == 1.0, (fname, rows[fname])
            sig_a, _ = _minhash(text)
            sig_b, _ = _minhash(text)
            assert _jaccard(sig_a, sig_b) == 1.0

    def test_snapshot_order_and_verdicts_identical(self, tmp_path):
        d = _corpus(tmp_path)
        inputs = {
            "text_a": TEXT_A,
            "text_a_edited": TEXT_A_EDITED,
            "paraphrase": TEXT_PARAPHRASED,
            "unrelated": TEXT_UNRELATED,
        }
        for name, text in inputs.items():
            r = check_similarity(text, [d], threshold=0.0, top=20)
            rows = _full_rows(r)
            got_order = sorted(rows, key=lambda n: (-rows[n]["similarity"], n))
            exp_order = OLD_SNAPSHOT[name]["order"]
            # Reihenfolge exakt wie im Alt-Snapshot (bei 0.0-Bindungen
            # original-Reihenfolge: Pfad-Sortierung wie check_similarity)
            assert [n for n in exp_order if rows[n]["similarity"] > 0] == [
                n for n in got_order if rows[n]["similarity"] > 0
            ], (name, got_order)
            for fname, exp_v in OLD_SNAPSHOT[name]["verdicts"].items():
                assert rows[fname]["verdict"] == exp_v, (name, fname, rows[fname])
            for fname, exp_o in OLD_SNAPSHOT[name]["overlaps"].items():
                assert rows[fname]["overlaps"] == exp_o, (name, fname, rows[fname])

    def test_snapshot_scores_within_estimator_tolerance(self, tmp_path):
        d = _corpus(tmp_path)
        inputs = {
            "text_a": TEXT_A,
            "text_a_edited": TEXT_A_EDITED,
            "paraphrase": TEXT_PARAPHRASED,
            "unrelated": TEXT_UNRELATED,
        }
        for name, text in inputs.items():
            r = check_similarity(text, [d], threshold=0.0, top=20)
            rows = _full_rows(r)
            for fname, exp_score in OLD_SNAPSHOT[name]["scores"].items():
                diff = abs(rows[fname]["similarity"] - exp_score)
                assert diff <= SCORE_TOLERANCE, (
                    f"{name}/{fname}: old={exp_score} new={rows[fname]['similarity']} diff={diff} > {SCORE_TOLERANCE}"
                )

    def test_exact_zero_for_unrelated_files(self, tmp_path):
        d = _corpus(tmp_path)
        r = check_similarity(TEXT_UNRELATED, [d], threshold=0.0, top=20)
        rows = _full_rows(r)
        assert rows["a_original.txt"]["similarity"] == 0.0
        assert rows["b_edited.txt"]["similarity"] == 0.0
        assert rows["d_paraphrase.txt"]["similarity"] == 0.0

    def test_permutation_quality_signature_has_spread(self):
        """128 Permutationen liefern verschiedene Werte (keine Kollapsen)."""
        sig, _ = _minhash(TEXT_LONG)
        assert len(sig) == 128
        assert len(set(sig)) > 64, "zu viele kollidierte Permutationsminima"


class TestSignatureCache:
    def test_second_call_identical_and_cached(self, tmp_path):
        d = _corpus(tmp_path)
        clear_signature_cache()
        r1 = check_similarity(TEXT_A, [d])
        r2 = check_similarity(TEXT_A, [d])
        assert r1 == r2  # Cache darf das Ergebnis nicht verändern (Parität)
        assert r1["top_similarity"] > 0.95

    def test_cache_invalidates_on_file_change(self, tmp_path):
        d = _corpus(tmp_path)
        clear_signature_cache()
        f = d / "c_unrelated.txt"
        r_before = check_similarity(TEXT_A, [d], threshold=0.0, top=20)
        score_before = _full_rows(r_before)["c_unrelated.txt"]["similarity"]
        assert score_before == 0.0
        # Datei ändern: Inhalt wird Teil von TEXT_A -> Score muss deutlich steigen
        f.write_text(TEXT_A + "\n" + TEXT_A, encoding="utf-8")
        r_after = check_similarity(TEXT_A, [d], threshold=0.0, top=20)
        score_after = _full_rows(r_after)["c_unrelated.txt"]["similarity"]
        assert score_after > score_before + 0.5, score_after

    def test_clear_signature_cache_forces_rehash(self, tmp_path):
        d = _corpus(tmp_path)
        clear_signature_cache()
        r1 = check_similarity(TEXT_A, [d])
        clear_signature_cache()
        r2 = check_similarity(TEXT_A, [d])
        assert r1 == r2  # nach clear() frisch gerechnet -> gleiches Ergebnis

    def test_skipped_binary_cached_too(self, tmp_path):
        d = _corpus(tmp_path)
        (d / "z_binary.png").write_bytes(b"\x89PNG\x00\x00binary-not-text")
        clear_signature_cache()
        r1 = check_similarity(TEXT_A, [d])
        r2 = check_similarity(TEXT_A, [d])
        assert r1 == r2
        assert any("z_binary.png" in s for s in r1["corpus"]["skipped_paths"])
