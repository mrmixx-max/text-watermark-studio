# Test-Coverage & Test-Qualitäts-Analyse: text-watermark-studio v1.08

> **Methodik:** Vollständige Test-Suite (1.101 Tests, 10 skipped) via `coveragepy` mit Branch-Coverage gemessen. Dauer, Coverage und fehlende Zeilen analysiert. Source-Code der kritischen Pfade gelesen und geprüft.

**Gesamtergebnis:** 59,83 % Coverage — **FAIL** (Threshold: 70 %, `pyproject.toml` Zeile 82).

---

## 1. Coverage-Heatmap (nach Priorität)

### 🔴 Kritisch niedrige Coverage (< 60 %) — Security-/Forensik-Kerne

| Modul | Cover | Miss | Kritische Lücken |
|---|---|---|---|
| `forensics/watcher.py` | **56 %** | 38 | Signal-Handler, Polling-Loop, KGW-Key-Loading, Fingerprint-Fehlerpfad |
| `metadata/synthid.py` | **56 %** | 15 | **`subprocess.run` ohne `args`** (Zeile 63) — Crash-Bug; Score-Pfad komplett ungetestet |
| `metadata/service.py` | **81 %** | 62 | `inspect`-/ `clean`-/Error-Pfade für Office/PDF |
| `api/routes/metadata.py` | **26 %** | 47 | Alle Endpoints außer 21 — `inspect`, `clean`, `embed`, `detect`, `synthid-score` |
| `api/routes/ops.py` | **41 %** | 18 | Health, Metrics, DLQ-Replay, Auth-Request-Logging |
| `exporting/service.py` | **23 %** | 39 | Export-Pfade (JSON/Markdown/PDF), Error-Handling |
| `batch.py` | **53 %** | 39 | Batch-Processing-Loop, Abort-Logik |
| `stream/redis_streams.py` | **24 %** | 55 | Nahezu alle Redis-Consumer-Paths |

### 🟡 Forensik-Module (60–90 %)

| Modul | Cover | Miss | Kritische Lücken |
|---|---|---|---|
| `forensics/report.py` | **73 %** | 11 | `render_pdf` (Zeilen 230–254) — Edge-Headless-PDF; `include_text` mit `len < 2000` |
| `forensics/invariant.py` | **78 %** | 40 | `_extract_codebook_candidates` (313–334); Burstiness-Tier 2–20; Ollama-Infill-Pfad |
| `forensics/audit.py` | **57 %** | 11 | `read_audit` (24–33); `AuditLogger.read` (52) — Audit-Trails ungetestet |
| `forensics/ensemble.py` | **77 %** | 15 | `score_segment` KGW-Zweig (22–33) — **Dead Code** (KGW wird separat behandelt) |
| `forensics/evader.py` | **79 %** | 22 | `_ollama_candidates` (289–320) — Ollama-Evasion-Pfad |
| `forensics/key_registry.py` | **80 %** | 18 | Korruptions-Handling (104–107, 135–137, 152–161, 197–200) |
| `forensics/encoding_detect.py` | **83 %** | 32 | UTF-16-Fallbacks, Mixed-Encoding-Filter, chardet-Fallback |
| `forensics/delta_z.py` | **95 %** | 3 | Type-Guard (287), Transform-Type-Guard (353), Text-Too-Long-Omitted (369) |
| `forensics/kgw.py` | **96 %** | 7 | `n < 10` BPE-Filter (486–502); Redlist-Parität (671) |
| `forensics/signed_report.py` | **88 %** | 16 | ML-DSA-Fehlerpfade (143–144, 163–164, 264→266); Tamper-Detection |
| `llm/service.py` | **78 %** | 19 | SSRF-Schutz (72), HTTPError/URLError (87–88), Config-Methoden (27–28, 41–49) |

### 🟢 Gut getestet (≥ 90 %)

`e_value.py` **100 %**, `frequent_vocab.py` **100 %**, `strip_markup.py` **100 %**, `similarity.py` **93 %**, `frs.py` **90 %**, `delta_z.py` **95 %**, `kgw.py` **96 %`.**

### ⚪ 0 % Coverage — UI / Infrastruktur (UI-Treiber ausgelassen)

| Modul | Cover | Bemerkung |
|---|---|---|
| `ui/desktop/app.py` | 0 % (467 Stmts) | PySide6 fehlt in CI → 5 Tests skipped |
| `ui/desktop/editor.py` | 0 % (204 Stmts) | PySide6 fehlt |
| `ui/web/dashboard.py` | 0 % (68 Stmts) | Keine UI-Tests |
| `ui/web/forms.py` | 0 % (211 Stmts) | Keine UI-Tests |
| `ui/tui.py` | 15 % (576 Stmts) | TUI-Interaktions-Logik kaum getestet |
| `api/server.py` | 0 % (50 Stmts) | Standalone-Server-Einstiegspunkt |
| `workers/arq_worker.py` | 0 % (25 Stmts) | Worker-Setup |
| `workers/streams_worker.py` | 0 % (48 Stmts) | Stream-Consumer |
| `interop/markllm.py` | 0 % (65 Stmts) | `markllm` fehlt → 1 Test skipped |
| `metadata/score_synthid_cli.py` | 0 % (27 Stmts) | SynthID-CLI-Wrapper |
| `documents/models.py` | 0 % (9 Stmts) | Datenmodelle |
| `cli.py` | **5,5 %** (904 Stmts) | **Getestet via Subprocess** — Coverage wird nicht erfasst |

> **CLI-Paradoxon:** `cli.py` hat nur 5,5 % import-basierte Coverage, obwohl es ~70 CLI-Subprocess-Tests gibt. Die Tests führen `python -m ai_watermark_toolkit.cli` als Separatprozess aus — `coveragepy` trackt nur den importierten Prozess. **Subprocess-Coverage via `coverage run -p` oder `coverage enable_subprocess` wäre hier nötig.**

---

## 2. Ungetestetekritische Pfade

### 2.1 Crash-Bug: `synthid.py` Zeile 63–68

```python
proc = subprocess.run(  # ← FEHLT: args=[venv_python, str(scorer), str(img)]
    capture_output=True,
    text=True,
    timeout=300,
    env=env,
)
```

`subprocess.run()` wird **ohne den Befehl** aufgerufen → `TypeError: __init__() missing 1 required positional argument: 'args'`. Dieser Pfad ist nur erreichbar, wenn `venv_py.exists()`, `codebook.exists()`, `scorer.exists()` und `img.exists()` alle `True` sind — derzeit komplett ungetestet (100 % der Tests nutzen Mock-Checkouts ohne echte Scoring-Pfade).

### 2.2 `watcher.py` — Datei-Monitoring & Audit-Trail (56 %)

| Zeilen | Pfad | Risiko |
|---|---|---|
| 24–25 | `_fingerprint()` OSError → `""` | Fingprint-Fehler fallen stillschweigend |
| 65–71 | KGW-Detektion in `scan_file()` | **Produktions-Pfad** — aktuelle Datei-Scan-Logik ungetestet |
| 101 | `_shutdown`-Signal-Handler | KeyboardInterrupt-Handling |
| 109–116 | `--kgw`-Flag, KeyRegistry-Laden, `warn_no_keys` | Startup-Fehler nicht abgefangen |
| 145–168 | Polling-Loop, Stale-File-Pruning | Hintergrund-Monitoring ungetestet |

### 2.3 `encoding_detect.py` — Encoding-Fallbacks (83 %)

| Zeilen | Pfad | Risiko |
|---|---|---|
| 95–109 | UTF-16 LE/BE Decoding + Surrogat-Erkennung | UTF-16-Daten werden nicht verarbeitet |
| 164, 169–170, 180–185 | BOM-Länge, Wide-Char-Detection, Decode-Fehler | Mixed-Encoding-Daten führen zu falschen Ergebnissen |
| 238, 263–270, 293, 332–334 | Mixed-Encoding-Segment-Filter, Conversion-Attack | Encoding-Watermark-Attack (z. B. UTF-7/UTF-8-Weißwäsche) nicht erkannt |
| 366, 381, 407–408 | chardet/pyarrow Fallback, `_latin1_confidence` | Fallback-Pfade ungetestet |

### 2.4 `key_registry.py` — Korruptions-Schutz (80 %)

| Zeilen | Pfad | Risiko |
|---|---|---|
| 104–107 | `RegistryCorruptError.__init__` | Exception-Konstruktor nie instanziiert |
| 135–137 | `_backup_corrupt()` | Backup-Logik für korrupte Registry |
| 152–161 | `_parse_file` — OSError, JSONDecodeError, non-dict root, non-list `keys` | **Kritisch:** Ein korruptes `key_registry.json` lässt `add_key` crashen oder alle Keys löschen |
| 197–200 | `_write_atomic` — Crash-Recovery `except BaseException` | Atomicity-Garantie unverifiziert |

### 2.5 `delta_z.py` — Edge-Cases (95 %, aber kritisch)

| Zeilen | Pfad | Risiko |
|---|---|---|
| 287 | `TypeError` bei Nicht-String-Input | API könnte intern crashen statt HTTP 422 |
| 353 | `TypeError` in `delta_z_transform` | Gleiche Gefahr |
| 369 | `transformed_text_omitted=True` (Text > 1000 Zeichen) | **Getestet?** — `max_transformed_chars=1000` Default, aber Test-Texte sind < 1000 |

### 2.6 `report.py` — PDF-Rendering (73 %)

| Zeilen | Pfad | Risiko |
|---|---|---|
| 180 | `include_text=True` mit `len(text) <= 2000` | Kurzer Text wird nicht im Report angezeigt |
| 230–254 | `render_pdf()` — Edge-Headless-PDF-Export | **Produktions-Feature für forensische Berichte** — 0 % getestet |

### 2.7 `invariant.py` — Codebook-Extraktion (78 %)

| Zeilen | Pfad | Risiko |
|---|---|---|
| 153 | Ollama-Infill-Fehler (Timeout/Verbindung) | Best-Effort-Pfad für Invariant-Wasserzeichen |
| 313–334 | `_extract_codebook_candidates()` — Comma-Split, Stopword-Filter, Top-K-Dedup | **Kern des Invariant-Wasserzeichens** — 0 % getestet |
| 360, 362–363, 370, 403, 407 | Candidate-Sets, Bit-Encoding/Decoding | Invariant-Detektion unvollständig |

### 2.8 `ensemble.py` — Dead Code in `score_segment` (77 %)

| Zeilen | Pfad | Risiko |
|---|---|---|
| 22–33 | KGW-Zweig in `score_segment()` | **Dead Code:** `ensemble_detect` behandelt KGW-Keys separat (Zeilen 78–102) und ruft `score_segment` nur für **nicht-KGW**-Keys auf. Der KGW-Zweig (Zeile 19: `if family == "kgw"`) ist **erreichbar, aber nie ausgeführt** → False-Sense-of-Security, wartet als Falle für zukünftige Refactoring |
| 125 | `watermark_detected` in `kgw_verdicts` | Nur teilweise via Ensemble-Path erreicht |
| 129 | `weak_or_mixed_signal` — `ensemble_score >= 0.35` | Schwaches-Signal-Schwellen-Grenzfall |

### 2.9 `evader.py` — Evasion-Analyse (79 %)

| Zeilen | Pfad | Risiko |
|---|---|---|
| 289–320 | `_ollama_candidates()` — Ollama-Evasion via urllib | Evasion-Simulation via LLM — komplett ungetestet, nur Mock-URL |

### 2.10 `llm/service.py` — SSRF-Schutz & Config (78 %)

| Zeilen | Pfad | Risiko |
|---|---|---|
| 72 | `_validate_url_scheme()` — Non-HTTP(S) Schema | **SSRF-Schutz** nur deklariert, nicht getestet |
| 27–28, 41–49 | `configure()` — Server-URL, Model-Variant, installiert-Flag | Config-Pfad für LLM-Backend-Setup |
| 87–88 | HTTPError / URLError Handling | Netzwerk-Fehler nicht abgefangen und getestet |

### 2.11 `api/routes/forensics.py` — Error-Pfade (92 %, aber kritisch)

| Zeilen | Pfad | Risiko |
|---|---|---|
| 200, 202 | `embed()` — `key_not_found`, `key_has_no_secret` | 404/400-Fehler nicht getestet |
| 248, 250 | `report_verify()` — `key_id_required`, `malformed_signed_document` | Input-Validierung brüchig |
| 291, 294 | `delta_z_endpoint()` — `key_has_no_secret`, `text_required_for_transform` | 400-Fehler nicht getestet |
| 352 | `finding_endpoint()` — `key_has_no_secret` | 400-Fehler nicht getestet |

---

## 3. Langsame Tests (> 5 s) — Top 15

| # | Dauer | Test | Optimierung |
|---|---|---|---|
| 1 | **27,79 s** | `test_v141_e_value::test_long_text_no_overflow` | `generate_watermarked(n=2000)` = O(2000×400) SHA256 — Text als Fixture cachen |
| 2 | **18,17 s** | `test_v141_e_value::test_very_long_text_e_value_capped_not_crashing` | `generate_watermarked(n=5000)` = O(5000×400) — Text als Fixture cachen |
| 3 | **9,52 s** | `test_watermark_perf::test_trace_kgw_latency_budget` | Latenz-Budget-Test mit Import-Overhead |
| 4 | **8,94 s** | `test_watermark_perf::test_detect_kgw_latency_budget` | Siehe oben — Budget-Tests sollten `time.sleep` eliminieren |
| 5 | **8,41 s** | `test_watermark_perf::test_mark_greenlist_latency_budget` | Siehe oben |
| 6 | **8,16 s** | `test_v132_redlist_signal::test_redlist_text_detected_negative_z` | Subprocess-CLI-Aufruf inkl. Python-Startup |
| 7 | **7,68 s** | `test_v132_redlist_signal::test_greenlist_text_keeps_greenlist_signal` | Subprocess-CLI-Aufruf |
| 8 | **7,41 s** | `test_v132_redlist_signal::test_wrong_key_redlist_text_is_no_signal` | Subprocess-CLI-Aufruf |
| 9 | **7,07 s** | `test_v134_kgw_sampler::test_bias_pushes_green_rate_above_gamma` | Subprocess-CLI-Aufruf |
| 10 | **7,03 s** | `test_v141_e_value::test_marked_text_is_e_detected` | Subprocess-CLI-Aufruf |
| 11 | **6,95 s** | `test_v113_kgw_detector::test_ensemble_uses_kgw_path` | Subprocess-CLI-Aufruf |
| 12 | **6,79 s** | `test_v113_kgw_detector::test_multi_key_finds_correct_key` | Subprocess-CLI-Aufruf |
| 13 | **6,59 s** | `test_v135_product_truth_gaps::test_report_redlist_badge_and_recommendation` | Subprocess-CLI-Aufruf |
| 14 | **6,45 s** | `test_v146_finding::test_redlist_is_class_a` | Subprocess-CLI-Aufruf |
| 15 | **6,32 s** | `test_v141_e_value::test_short_marked_text_z_below_4_e_detected` | Subprocess-CLI-Aufruf |

**Gemeinsames Muster:** Die meisten langsamen Tests (> 5 s) nutzen `subprocess.run([sys.executable, "-m", "ai_watermark_toolkit.cli", ...])` für CLI-Tests. Jeder Aufruf kostet ~5–7 s Python-Startup. **Optimierung:** Diese Tests als **Subprocess-gecachte Fixtures** oder **direkte Import-Tests** umstellen (wie `test_v155_cli_coverage.py` bereits für Helper-Funktionen tut).

Die beiden e_value-Tests sind langsam wegen der O(n×400)-Generierung — `green_token()` führt pro Kandidat einen `hashlib.sha256` aus. Mit einem **geseeded Cache** für `_pools()` oder durch Verwendung einer kleineren Vokabulargröße (`FREQUENT_VOCAB` vs. 400-Wort-VOCAB) ließe sich dies auf < 3 s reduzieren.

---

## 4. Mock-Tests: Realitätsnähe-Analyse

### ✅ Gute Mock-Praxis (realistisch)

**CLI-Helper-Tests (`test_v155_cli_coverage.py`):**
- Testet `_resolve_key_arg`, `_resolve_key`, `_read`, `main_entry` als **direkte Import-Tests** (kein Subprocess).
- Mock-Scope ist klein und fokussiert auf reine Logik (Key-File-Priorität, Stdin vs. File, Error-Wrapper).
- **Keine False-Sense-of-Security** — diese Tests validieren die tatsächliche Entscheidungslogik.

**Security-Tests (`test_v130_api_security.py`):**
- `monkeypatch.setattr(forensics_route, "keys", reg)` ersetzt die KeyRegistry im Route-Modul.
- Testet Auth-Enforcement, Secret-Redaction und 404-Pfade mit isolierten Registries.
- **Realistisch** — die Route-Logik wird mit echten (tmp-path) Registries getestet.

### ⚠️ False-Sense-of-Security-Mocks

**1. LLM-Backend-Tests (`test_v110_llm_backend.py` — 3 Tests):**
```python
monkeypatch.setattr(svc, "_llm_rewrite", lambda text, mode: "Clean rewritten text.")
```
- Der gesamte HTTP-Layer (`urllib.request.urlopen` → Ollama/llama.cpp) wird durch ein Lambda ersetzt.
- `FakeHttpx` und `FakeResponse` Klassen sind **definiert, aber nie verwendet** (Dummy-Code).
- **Problem:** Wenn sich das API-Response-Format von Ollama ändert (z. B. `choices[0].message.content`), bemerken diese Tests es nicht.
- **Lösung:** Mindestens 1 Test mit `monkeypatch.setattr(urllib.request, "urlopen", ...)` als echter HTTP-Stub, der das Response-Parsing validiert.

**2. SynthID-Tests (`test_v121_synthid_bootstrap.py` — 5 Tests):**
- Tests nur die Pfad-Erkennung (`venv_py.exists()`, `codebook.exists()`) — aber **niemals den Score-Pfad**.
- Der kritische Bug in `score_synthid()` (Zeile 63, fehlendes `args`) ist **unsichtbar** für alle Tests, weil die Mock-Checkouts nie alle Voraussetzungen erfüllen.
- **Problem:** 0 % Coverage vom eigentlichen Scoring-Logik.
- **Lösung:** Test mit `monkeypatch.setattr(subprocess, "run", ...)` der den `args`-Parameter validiert — würde den Bug unterschwellen.

**3. Desktop-Editor-Tests (`test_v100_desktop_editor.py` — 5 Tests, alle skipped):**
- Alle 5 Tests sind **skipped** wegen fehlendem `PySide6`.
- `ui/desktop/app.py` hat **0 %** Coverage — die gesamte Desktop-Event-Loop ist ungetestet.
- **Risiko:** Der Desktop-Client ist das primäre Produktions-Frontend, aber hat keine Coverage-Brushügung.

---

## 5. Vorgeschlagene neue Tests (Priorität)

> **Format:** `(P0 = kritisch, P1 = hoch, P2 = mittel)`

### P0 — Sofort (hoher Risiko / Crash-Bug)

| # | Test-Vorschlag | Modul | Priorität | Begründung |
|---|---|---|---|---|
| **1** | `test_score_synthid_missing_args_param` | `synthid.py` | **P0** | Validiert dass `subprocess.run` einen `args`-Parameter erhält. **Bug-Bestätigung** — würde aktuell `TypeError` auslösen. Nutze `monkeypatch.setattr(subprocess, "run", spy)` und prüfe `spy.call_args[0]`. |
| **2** | `test_key_registry_corrupt_json_raises` | `key_registry.py` | **P0** | Schreibe eine Datei mit `{}` + `keys: "not-a-list"` + ungültigem JSON. Prüfe dass `RegistryCorruptError` mit Backup entsteht und `add_key` nicht alle Keys zerstört. |
| **3** | `test_delta_z_rejects_non_string` | `delta_z.py` | **P0** | `delta_z(123, "text", KEY)` → muss `TypeError` mit klarem Message werfen. Schützt API vor Intern-500. |
| **4** | `test_delta_z_transform_truncation_omitted` | `delta_z.py` | **P0** | `delta_z_transform(text_long > 1000, KEY, method="clean")` → `transformed_text_omitted=True`, kein Feld. Aktuell ungetestet (Zeile 369). |

### P1 — Hoch (mittelbarer Risiko)

| # | Test-Vorschlag | Modul | Priorität | Begründung |
|---|---|---|---|---|
| **5** | `test_report_render_pdf_with_edge` | `report.py` | **P1** | Mock `subprocess.run` für Edge-Pfad → prüfe PDF-Path-Logik. Aktuell 0 % (Zeilen 230–254). |
| **6** | `test_llm_service_ssrf_rejected_schemes` | `llm/service.py` | **P1** | `_validate_url_scheme("file://...", "ftp://...", "gopher://")` → muss `ValueError` erheben. SSRF-Schutz nur deklariert, nicht getestet (Zeile 72). |
| **7** | `test_ensemble_score_segment_kgw_is_dead_code` | `ensemble.py` | **P1** | Explizit testen, dass `score_segment(text, {"family":"kgw", ...})` den KGW-Pfad erreicht — **oder** das Dead-Code-Lock entfernen. Verhindert zukünftige Regression. |
| **8** | `test_invariant_codebook_candidates_extraction` | `invariant.py` | **P1** | Teste `_extract_codebook_candidates()` mit gültigen und randigen Eingaben (rambling, stopwords-only, > 4 Wörter). Kern des Invariant-Wasserzeichens ungetestet. |
| **9** | `test_signing_path_registry_error_routes` | `api/routes/forensics.py` | **P1** | POST `/embed`, `/delta-z`, `/finding` mit `key_id` nicht in Registry → 404. Und `key_id` ohne Secret → 400. Aktuell 8 Error-Pfade (Zeilen 200, 202, 291, 294, 352) ungetestet. |
| **10** | `test_e_value_long_text_fixture_cached` | `test_v141_e_value.py` | **P1** | Text-Generierung als `@pytest.fixture(scope="module")` cachen → reduziert 27,8 s + 18,2 s → < 5 s pro Test. |

### P2 — Mittel (Coverage-Verbesserung)

| # | Test-Vorschlag | Modul | Priorität | Begründung |
|---|---|---|---|---|
| **11** | `test_audit_read_corrupt_line` | `audit.py` | **P2** | `read_audit()` mit einer Zeile mit defektem JSON → muss übersprungen werden. Aktuell ungetestet (Zeilen 24–33). |
| **12** | `test_encoding_detect_utf16_paths` | `encoding_detect.py` | **P2** | Teste UTF-16 LE/BE mit BOM und ohne, chardet-Fallback, Mixed-Encoding-Segmente. 32 ungetestete Zeilen. |
| **13** | `test_watcher_signal_shutdown_and_kgw_keys` | `watcher.py` | **P2** | Signal-Handler-Registrierung, `--kgw`-Flag mit KeyRegistry, Warnung wenn keine Keys. Aktuell 38 ungetestete Zeilen. |
| **14** | `test_signature_deep_burstiness_tiers` | `signature_deep.py` | **P2** | Alle Burstiness-CV-Tiers (0.2–0.35, 0.35–0.5, 0.5–0.7, > 0.7) testen — aktuell nur `< 0.2` getestet. |
| **15** | `test_signed_report_mldsa_error_paths` | `signed_report.py` | **P2** | ML-DSA nicht verfügbar → `RuntimeError` mit klarer Message. Aktuell 16 ungetestete Zeilen. |
| **16** | `test_metadata_route_full_coverage` | `api/routes/metadata.py` | **P2** | Alle 5 Endpoints (`/inspect`, `/clean`, `/embed`, `/detect`, `/synthid-score`) testen — aktuell nur 26 % Coverage. |

---

## 6. Subprocess-Coverage-Lücke

**`cli.py` hat 5,5 % Coverage** trotz ~70 CLI-Tests, weil alle CLI-Tests über `subprocess.run` laufen. **Lösung:**

```toml
# pyproject.toml
[tool.coverage.run]
source = ["src"]
branch = true
omit = ["tests/*", "*/__pycache__/*"]
concurrency = ["multiprocessing", "thread"]
disable_warnings = ["subprocess"]
```

Oder: `coverage run -p python -m pytest` + `coverage combine` für Subprocess-Tracking.

---

## 7. Zusammenfassung & Aktions-Prioritäten

| Ebene | Anzahl | Modulen/Tests |
|---|---|---|
| 🔴 P0 (Sofort) | 4 Tests | synthid Bug, key_registry Korruption, delta_z Type-Guards |
| 🟡 P1 (Hoch) | 6 Tests | report/render_pdf, LRN SSRF, ensemble Dead-Code, invariant Codebook, forensics Error-Routes, e_value Fixture-Optimierung |
| 🟢 P2 (Mittel) | 6 Tests | audit read, encoding_detect UTF-16, watcher Signal, signature_deep Tiers, signed_report ML-DSA, metadata Route-Full |
| ⚠️ Optimierung | 2 Gruppen | Subprocess-Coverage aktivieren; e_value-Generierung cachen |

**Coverage-Ziel 70 % ist aktuell um ~10 %punkte verfehlt (59,83 %).** Schätzungsweise **50–80 neue Tests** in den P0–P1-Bereichen (Fokus: Error-Pfade, Edge-Cases, Subprocess-Tracking) würden den Coverage um ~8–12 %punkte steigern und auf **> 70 %** kommen lassen.

**Kritischster Bug:** `synthid.py:63` — `subprocess.run()` ohne `args`-Parameter. Wird erst in Produktion mit echter SynthID-Checkout sichtbar. **Sofortiger Fix erforderlich.**

---

*Report generiert aus: `coverage.py` Datenbank + `pytest --durations=0` — Testlauf 2026-08-19.*
*Hilfsdateien: `_cov_missing.py`, `_missing_lines.txt` (Coverage-Abfrage-Skripte, im Projekt-Root, können nach Report-Erstellung gelöscht werden.)*
