# Dead-Code & Complexity-Reduktion — Analysebericht

**Projekt:** text-watermark-studio (v108-deep-debug)
**Pfad:** `C:\Users\webma\Downloads\tws-v108\text-watermark-studio-v108-deep-debug`
**Tools:** `ruff 0.16.3`, `vulture 2.x`, `radon`, `pycode_similar`, AST-basierte Analyse
**Python:** 3.11.15

---

## 1. Zusammenfassung

| Kategorie | Ergebnis |
|---|---|
| Ungenutzter Code (`vulture --min-confidence 80`) | **keine** (nach Kreuzreferenzierung mit Tests) |
| Ungenutzter Code (`vulture --min-confidence 60`) | **37 Funde** — 13 echter Dead-Code, 24 False-Positives (Framework-Hooks, dekorierte Routen, Dataclass-Felder) |
| Funktionen mit zyklomat. Komplexität > 10 | **59** (radon cc) |
| Code-Duplikate > 5 Zeilen | **1 klares Duplikat** (innerhalb `_isobmff`), 2 strukturelle Duplikat-Muster |
| Stalte `__init__.py` Exports | **3** Probleme (Version-Mismatch, falscher `__all__`-Eintrag) |
| Tote Branches | **0** konstante Bedingungen, **0** unerreichbarer Code. 1 subtile Variable-Shadowing-Fragilität. |

---

## 2. Ungenutzter Code (Dead Code)

### 2a. Ganztödules Modul

| Datei:Zeile | Element | Problem |
|---|---|---|
| `src/ai_watermark_toolkit/api/server.py` (ganz) | `Handler` (BaseHTTPRequestHandler), `do_GET`, `do_POST`, `_json`, `_html`, `serve()` | **Ein komplett alternatives, veraltetes HTTP-Server-Modul.** Wird nirgends importiert (weder in `src/` noch in `tests/`). Der CLI-`serve`-Befehl verwendet `uvicorn.run(...)` mit der FastAPI-App (`api/fastapi_app.py:1548`). Das ganze Modul ist toter Code. |

### 2b. Tote Klassen & Konstanten (100 % Conf.)

| Datei:Zeile | Element | Problem | Lösungsvorschlag |
|---|---|---|---|
| `documents/models.py:7` | `DocumentPayload` (dataclass) | Klasse wird nirgendwo definiert, importiert oder getestet. Eine `to_dict()`-Methode ist vorhanden, aber nie aufgerufen. | Entfernen oder in `__init__.py` exportieren, falls Teil der Public-API. |
| `forensics/delta_z.py:58` | `TRANSFORM_NOTES` (dict) | Dokumentations-Dict, das nie gelesen wird. `TRANSFORM_METHODS` (Zeile 56) und `_TRANSFORM_META` (Zeile 82) werden verwendet, `TRANSFORM_NOTES` nicht. | Entfernen — die Notes sind als Docstrings bereits in `_apply_transform` und `_transform_rewrite` dokumentiert. |
| `forensics/finding.py:52` | `LANGS` (tuple) | `("de", "en")` — definiert aber nie verwendet (die Strings `"de"`/`"en"` werden direkt in `_TEXTS` verwendet). | Entfernen oder als Literal in den Stellen, die sie brauchen, einsetzen. |
| `forensics/frs.py:95` | `VERDICTS` (tuple) | Definiert aber nie referenziert. Die Verdichts-Strings werden direkt im Code verwendet. | Entfernen. |
| `metadata/pdf_watermark.py:38` | `WM_TYPES` (tuple) | `WM_TYPES = (WM_SPACING, WM_METADATA, WM_COLOR)`. Die Einzelkonstanten `WM_SPACING`, `WM_METADATA`, `WM_COLOR` werden verwendet, aber `WM_TYPES` selbst nie. | Entfernen. |
| `observability/metrics.py:9` | `STREAM_JOBS_TOTAL` (prometheus Counter) | Definiert aber nie initialisiert, inkrementiert oder importiert. Die anderen 3 Counter/Gauges derselben Datei (`DLQ_REPLAYS_TOTAL`, `STREAM_PENDING_GAUGE`, `STREAM_DEAD_LETTER_GAUGE`) werden in `api/routes/ops.py` verwendet. | Entfernen — ist nur die 1 von 4 Metriken, die nicht genutzt wird. |
| `ui/web/forms.py:33` | `rewrite_svc = RewriteService()` | Instanz wird am Module-Level erzeugt, aber nirgends verwendet. Es gibt eine `RewriteService` aus `rewrite.service`, die stateless ist — die Instanz ist überflüssig. | Entfernen. |
| `ui/banner.py:23` | `WHITE` (ANSI-Farbkonstante) | Definiert (`WHITE = "\033[97m"`) aber nie referenziert. Andere Konstanten (`TEAL`, `RED`, `GREEN`, `DIM`, `BOLD`, `GOLD`, `RESET`) werden verwendet. | Entfernen. |
| `ui/web/dashboard.py:47` | `bump_stat()` | Funktion mit Signatur `(name: str, **ctx)` — deklariert als SignalRx-Handler, aber nirgendwo aufgerufen, weder in `src/` noch in `tests/`. | Entfernen. |

### 2c. Tote Methoden (niemand ruft sie auf)

| Datei:Zeile | Element | Problem | Lösungsvorschlag |
|---|---|---|---|
| `queue/redis_queue.py:43` | `RedisQueueService.next_job()` | Methode ist definiert, aber `RedisQueueService` wird nur zur `enqueue()`/`depth()`-Operation benutzt (in `api/routes/queue.py` und `ui/web/forms.py`). `next_job` wird nie aufgerufen. | Entfernen oder dokumentieren, warum der Worker-Pfad fehlt. |
| `queue/redis_queue.py:50` | `RedisQueueService.update_status()` | Wie oben — nie aufgerufen. `_update_status_pos` in `app.py` ist eine andere Methode. | Entfernen oder implementieren. |
| `lab/families/semantic_structure.py:61` | `SemanticStructureFamily.explain()` | **Einzige** `explain()`-Implementierung in der ganzen `lab/families/`- Hierarchie. Wird in `src/` (außerhalb von Tests) nirgends aufgerufen. Die anderen Familien deklarieren `"explain": True` in `capability()` aber implementieren die Methode nicht — das ist inkonsistent. | Entfernen oder in die `LabFamily`-Basis-Klasse heben und dort dokumentieren, dass `explain` nicht implementiert ist. |

### 2d. Tote Parameter (Unused Parameters)

| Datei:Zeile | Element | Problem | Lösungsvorschlag |
|---|---|---|---|
| `metadata/service.py:313` | `custom_dir` in `_zip_container()` | Parameter wird von `_docx` (`"customXml"`) und `_odt` (`None`) übergeben, aber **niemals im Funktionskörper verwendet**. Der Code hardcodiert `"customXml/"` an den Zeilen 323 und 338. | Verwenden (z. B. `n.startswith(custom_dir + "/")` wenn `custom_dir`), oder entfernen, wenn keine Variable `custom_dir` mehr als feste Zeichenkette nötig ist. |
| `plugins/audio_watermark.py:346` | `watermark` in `AudioWatermark.embed()` | Stub-Methode, die sofort `NotImplementedError` raise. Parameter wird nie gelesen. | Entfernen (`raise NotImplementedError(...)` reicht). |
| `plugins/code_watermark.py:187` | `watermark` in `CodeWatermark.embed()` | Wie oben. | Entfernen. |
| `plugins/video_watermark.py:331` | `watermark` in `VideoWatermark.embed()` | Wie oben. | Entfernen. |
| `forensics/watcher.py:99` | `signum, frame` in `_shutdown()` | Signal-Handler-Callback erfordert diese Parameter (Signal-Signatur), aber sie werden nicht verwendet. | Mit `del signum, frame` am Anfang oder Umbenennung in `_signum, _frame` markieren. |

### 2e. False-Positives von `vulture` (wichtig für Interpretration)

`vulture` hat **24** weitere Elemente als "unused" gemeldet, die **falsch** sind:

- **Alle API-Routen** in `api/routes/*.py` (z. B. `list_communities`, `formats`, `report_sign`, `detect`, `formats`, `finding_endpoint`, `create_job`) — alle sind mit `@router.get(...)` / `@router.post(...)` dekoriert und via `app.include_router(...)` registriert (alle 20 Router in `fastapi_app.py:102-123`).
- **Alle Textual-TUI-Methods** in `ui/tui.py` (`action_*`, `on_mount`, `compose`, `worker_*`) — werden dynamisch vom Textual-Framework aufgerufen.
- **Alle Middleware-`dispatch` Methoden** — überschreiben `BaseHTTPMiddleware.dispatch`.
- **`do_GET`/`do_POST`** in `api/server.py` + `_check_riff`/`_check_isobmff` Overrides — überschreiben Basisklassen-Methoden.
- **`WorkerSettings`** in `workers/arq_worker.py` und seine Attribute (`functions`, `on_startup`, `on_shutdown`) — arq liest diese dynamisch.
- **Dataclass-Felder** (`comments_removed`, `hidden_spans_removed`, `repeated_bigram_ratio`, `sentence_count`, `visibility`, `robustness`, `detectability`, `requirements`, `normalized`, `source`, `visibility`, `robustness`, etc.) — werden über Konstruktoren positionell/keyword-Argumente gesetzt und via `asdict()` serialisiert; `vulture` kann das nicht nachvollverfolgen.
- **`serve`** in `api/server.py:63` — fälschlicherweise als "unused function" gemeldet; siehe 2a, es ist dead code deshalb.

---

## 3. Funktionen mit hoher zyklomatischer Komplexität (> 10)

Quelle: `radon cc src/ -n B -s` (Filter: Rating C und schlechter = Komplexität ≥ 11)

### Kategorie F (Komplexität 26+)

| Komplexität | Datei:Zeile | Funktion | Refactoring-Vorschlag |
|---|---|---|---|
| **226** | `cli.py:106` | `main()` | AST-Symbol-Building + Dispatch sind in einer einzigen 1490-zeiligen-Funktion. Argumente für alle Subparser werden inline definiert, gefolgt von einem riesigen `if args.cmd == "...":`-Dispatch-Ketten. **Vorschlag:** Subparser-Building in `_register_commands(sub)` extrahieren; Dispatch in ein `dict` (Befehlsname → Handler-Funktion) umwandeln. Damit sinkt `main` von 226 auf < 10. |
| **37** | `forensics/ensemble.py:62` | `ensemble_detect()` | Kombiniert: Model-Iteration, E-Value-Berechnung, Signatur-Filter, Ergebnis-Aggregation in einer Schleife mit vielen verzweigten Bedingungen. **Vorschlag:** `_score_segment()` extrahieren (bereits existiert als separate Funktion `score_segment` mit Komplexität 14 — aufräumen, damit `ensemble_detect` nur noch aggregiert). |

### Kategorie D (Komplexität 16–25)

| Komplexität | Datei:Zeile | Funktion | Refactoring-Vorschlag |
|---|---|---|---|
| **27** | `metadata/service.py:394` | `_isobmff()` | Siehe Abschnitt 4 — die Box-Scanning-Logik ist innerhalb der Funktion **doppelt** (Top-Level + Sub-Boxes). Extrahiere `_should_drop_box(fourcc, payload) -> str \| None`. |
| **27** | `forensics/signed_report.py:295` | `verify_report()` | Mischt: Payload-Parsing, HMAC-Verifikation, ML-DSA-Verifikation, Fehlerbericht-Aufbau. **Vorschlag:** `_verify_hmac(payload, secret) -> bool` und `_verify_mldsa(payload, public_key) -> bool` extrahieren. |
| **24** | `forensics/kgw.py:579` | `mark_greenlist()` | Kombiniert Tokenisierung, Hash-Berechnung, Grünlings-Markierung, Score-Tracking. **Vorschlag:** Phase "tokenize" und Phase "mark" trennen. `|green|_score_segment` extrahieren. |
| **23** | `batch.py:36` | `process_batch()` | `if/elif` Kette für `mode`-Dispatch (`detect`/`clean`/`dilute`/`embed`/`else`). **Vorschlag:** `mode` → Handler-Funktion `dict`-Dispatch. Außerdem: `verified`, `z_score`, `green_rate` sind nur innerhalb des `embed`+`verify` Branches definiert (siehe Abschnitt 6). |
| **22** | `metadata/service.py:194` | `_jpeg()` | Marker-Parsing + Segment-Dropping + C2PA-Check in einer Funktion. **Vorschlag:** `_parse_jpeg_segments(data)` und `_strip_jpeg_segment(seg, marker)` extrahieren. |

### Kategorie C (Komplexität 11–15)

| Komplexität | Datei:Zeile | Funktion | Refactoring-Vorschlag |
|---|---|---|---|
| **15** | `metadata/service.py:150` | `_png()` | Wie `_jpeg`/`_webp`: Chunk-Iterierung + Drop-Detection + C2PA-Check. **Vorschlag:** Gemeinsames `_strip_metadata_chunks(data, is_png=True)`-Helfer. |
| **15** | `metadata/service.py:472` | `_webp()` | Siehe `_png`/`_jpeg` — ähnliches RIFF-Chunk-Pattern. |
| **15** | `metadata/service.py:312` | `_zip_container()` | Hat den nicht-verwendeten `custom_dir`-Parameter (siehe 2d). + `customXml/` hardcodiert. |
| **15** | `metadata/provenance.py:177` | `_detect_text()` | Format-Erkennung für Text-Dateien. **Vorschlag:** `if ext == ...` → Dict-Dispatch. |
| **15** | `forensics/report.py:119` | `build_report()` | Mischt Section-Generierung. **Vorschlag:** Section-Builders extrahieren (`_evidence_section()`, `_risk_section()`). |
| **15** | `forensics/frs.py:115` | `compute_frs()` | 12 Kriterien, 3 Gates. **Vorschlag:** Gate-Checks in `_assess_gate(gate, criteria) -> bool` extrahieren. |
| **15** | `community/service.py:25` | `detect()` | **Vorschlag:** Strukturieren (Community-Detection vs. Scoring trennen). |
| **14** | `plugins/video_watermark.py:181` | `_scan_boxes_recursive()` | Rekursive Box-Traversal. |
| **14** | `plugins/audio_watermark.py:187` | `_check_isobmff()` | Box-Parsing — Duplikat von `_scan_boxes_recursive`. |
| **14** | `plugins/audio_watermark.py:194` | `_check_riff()` | RIFF-Parsing — ähnlich wie `_webp` in metadata/service.py. |
| **14** | `llm/service.py:100` | `install_model()` | Mischt Validation + Download + Config-Persist. |
| **14** | `forensics/invariant.py:337` | `candidate_sets()` | Komplexe Kombinatorik. |
| **14** | `forensics/ensemble.py:14` | `score_segment()` | Teil von `ensemble_detect` (siehe oben). |
| **14** | `api/routes/forensics.py:330` | `finding_endpoint()` | HTTP-Handler mit verschachteltem Fehler-Handling. |
| **14** | `api/routes/forensics.py:238` | `report_verify()` | **Vorschlag:** `if algorithm == ...` → Dict-Dispatch. |
| **13** | `plugins/video_watermark.py:66` | `detect()` | **Vorschlag:** Extract-`_parse_riff`/`_parse_isobmff` Helfer (Duplikat von metadata/service.py). |
| **13** | `plugins/audio_watermark.py:80` | `detect()` | Wie oben. |
| **13** | `metadata/docx_repair.py:231` | `repair_docx()` | **Vorschlag:** Extract `_extract_text`, `_rebuild_rels` Helfer. |
| **13** | `llm/router.py:261` | `ModelRouter.execute()` | Provider-If/elif-Kette. **Vorschlag:** `provider` → Handler-Instanz `dict`. |
| **13** | `forensics/trace.py:172` | `format_trace()` | **Vorschlag:** Section-Formatierung extrahieren. |
| **13** | `forensics/kgw.py:724` | `embed_kgw()` | **Vorschlag:** Tokenize/Mask/Score-Phasen trennen. |
| **13** | `api/routes/forensics.py:143` | `detect()` | HTTP-Handler. **Vorschlag:** Parameter-Resolution in `_resolve_detect_args()` extrahieren. |
| **12** | `metadata/service.py:125` | `_dispatch()` | **Klares Kandidat für Dict-Dispatch:** `if ext in (...)` → `{ext: handler}`-Lookup-Tabelle. |
| **12** | `metadata/provenance.py:127` | `_detect_jpeg()` | Wie `_dispatch` — Format-Checks. |
| **12** | `graph_memory/service.py:83` | `subgraph()` | |
| **12** | `forensics/kgw.py:287` | `_filter_pairs()` | |
| **12** | `forensics/invariant.py:167` | `select_mask_positions()` | |
| **12** | `forensics/invariant.py:135` | `detect_anchors()` | |
| **12** | `forensics/finding.py:646` | `build_finding_report()` | |
| **12** | `forensics/finding.py:450` | `_priority_risk()` | |
| **12** | `forensics/encoding_detect.py` | `_latin1_confidence()` | |
| **12** | `community/service.py:67` | `summarize()` | |
| **11** | `ui/tui.py:418` | `action_report_verify()` | Textual-Action mit verschachtelter Logik. |
| **11** | `rewrite/service.py:153` | `rewrite()` | **Vorschlag:** `mode` → Handler-Dict. |
| **11** | `prompts/service.py:22` | `get_template()` | **Vorschlag:** Template-Name → Loader-Dict. |
| **11** | `metadata/provenance.py:301` | `embed_provenance()` | |
| **11** | `metadata/pdf_watermark.py:143` | `detect_spacing_watermark()` | |
| **11** | `forensics/trace.py:62` | `trace_kgw()` | |
| **11** | `forensics/finding.py:544` | `classify_finding()` | |
| **11** | `forensics/encoding_detect.py` | `_detect_mixed_encoding()` | |
| **11** | `cli.py:1556` | `main_entry()` | Wrapper um `main()` — relativ simpel, aber `main()`-Delegation zählt. |

**Gesamt: 59 Funktionen** mit Komplexität > 10. Die 5 schlimmsten (> 20) sind: `main` (226), `ensemble_detect` (37), `_isobmff` (27), `verify_report` (27), `mark_greenlist` (24).

---

## 4. Code-Duplikate (> 5 Zeilen)

### Duplikat 1: `_isobmff` — doppelte Box-Scanning-Logik (Intra-Funktion)

**Datei:** `metadata/service.py:394-463` (Funktion `_isobmff`, Komplexität 27)

Die Box-Prüf-Logik ist **zweimal** identisch implementiert:

```python
# Top-Level Boxes (Zeilen 408-420)
if fourcc in _C2PA_BOXES or name.lower().startswith("c2"):
    rep.actions.append(f"removed_top_level_{name}_c2pa_box")
    removed += header + len(payload)
    continue
if fourcc == b"uuid":
    if payload.startswith(XMP_UUID):
        rep.actions.append(f"removed_top_level_{name}_xmp_uuid_box")
        removed += header + len(payload)
        continue
    if _AI_KEY_HINTS.search(payload[:512]):
        rep.actions.append(f"removed_top_level_{name}_ai_uuid_box")
        removed += header + len(payload)
        continue
```

```python
# Sub-Boxes inside `meta` (Zeilen 428-444) — fast identisch, nur Präfix "meta_subbox"
if s_fourcc in _C2PA_BOXES or s_name.lower().startswith("c2"):
    rep.actions.append(f"removed_meta_subbox_{s_name}_c2pa")
    sub_removed += s_header + len(s_payload)
    continue
if s_fourcc == b"uuid":
    if s_payload.startswith(XMP_UUID):
        rep.actions.append(f"removed_meta_subbox_{s_name}_xmp")
        sub_removed += s_header + len(s_payload)
        continue
    if _AI_KEY_HINTS.search(s_payload[:512]):
        rep.actions.append(f"removed_meta_subbox_{s_name}_ai_uuid")
        sub_removed += s_header + len(s_payload)
        continue
if s_fourcc in (b"xml ", b"bxml") and _AI_KEY_HINTS.search(s_payload[:512]):
    rep.actions.append(f"removed_meta_subbox_{s_name}_xml_metadata")
    sub_removed += s_header + len(s_payload)
    continue
```

**Lösungsvorschlag:** Eine Helferfunktion extrahieren:
```python
def _classify_box(fourcc: bytes, payload: bytes, prefix: str) -> str | None:
    """Return an action-name if the box should be dropped, else None."""
    name = fourcc.decode("latin1", "replace")
    if fourcc in _C2PA_BOXES or name.lower().startswith("c2"):
        return f"removed_{prefix}_{name}_c2pa_box"
    if fourcc == b"uuid":
        if payload.startswith(XMP_UUID):
            return f"removed_{prefix}_{name}_xmp_uuid_box"
        if _AI_KEY_HINTS.search(payload[:512]):
            return f"removed_{prefix}_{name}_ai_uuid_box"
    if fourcc in (b"xml ", b"bxml") and _AI_KEY_HINTS.search(payload[:512]):
        return f"removed_{prefix}_{name}_xml_metadata"
    return None
```
Damit sinkt `_isobmff` um ~10 Punkte Komplexität und das Duplikat wird eliminiert.

### Duplikat 2: Format-spezifische Metadata-Cleaner (`_png`, `_jpeg`, `_webp`)

**Datei:** `metadata/service.py:150-501`

`_png`, `_jpeg` und `_webp` teilen ein identisches **5-Schritte-Muster**:
1. `MetaReport` erzeugen
2. Magic-Bytes validieren (`data[:N] != ...`)
3. Chunk/Segment-Iterator mit `drop`-Detection (AI-Metadata-Hints)
4. Wenn `clean`: bereinigte Ausgabe zusammenbauen
5. C2PA-Jumbf-Marker am Ende detektieren (`b"jumbf" in data.lower() or b"c2pa" in data.lower()`)

pycode_similar hat sie nicht als > 60 % identisch klassifiziert (unterschiedliche Variablennamen und Format-spezifische Logik), aber der **Struktur- und Abschlusscode ist dupliziert**. Schritt 5 ist in allen drei Funktionen **buchstäblich identisch** (2 Zeilen):
```python
if b"jumbf" in data.lower() or b"c2pa" in data.lower():
    rep.hard_bound_c2pa_present = True
    rep.actions.append("c2pa_jumbf_markers_detected_not_removed")
```

**Lösungsvorschlag:** Einen Helfer `_finalize_c2pa_check(rep, data)` extrahieren und die Iterierungs-Logik über eine Callback-Struktur vereinigen (höhere Abstraktion, Medium-Risiko).

### Duplikat 3: `_dispatch` vs. `verify_clean`-if/elif-Muster

**Datei:** `metadata/service.py:125-146` (`_dispatch`) und `metadata/service.py:76-122` (`verify_clean`)

`_dispatch` (Komplexität 12) ist eine `if/elif`-Kette:
```python
if ext in ("png",): return _png(data, clean)
if ext in ("jpg", "jpeg"): return _jpeg(data, clean)
if ext == "webp": return _webp(data, clean)
...
```
→ **Vorschlag:** Dict-Dispatch:
```python
_DISPATCH = {"png": _png, "jpg": _jpeg, "jpeg": _jpeg, "webp": _webp, ...}
handler = _DISPATCH.get(ext)
if handler is None:
    return MetaReport(format=ext or "unknown", actions=["unsupported_format"])
return handler(data, clean)
```

---

## 5. `__init__.py` Exports — Staleness-Prüfung

### Stalte / fehlerhafte Exports

| Datei | Problem |
|---|---|
| `src/ai_watermark_toolkit/__init__.py:20` | `__all__ = ["detect_text", "pipeline", "run_pipeline"]`. Der Eintrag `"pipeline"` ist **nicht importiert** — nur `from .pipeline import detect_text, run_pipeline` (Zeile 21). `"pipeline"` funktioniert nur als Nebeneffekt (das Submodul wird als Attribut gesetzt), aber `from ai_watermark_toolkit import *` würde `AttributeError` erzeugen, wenn jemand den Import ändert. |
| `src/ai_watermark_toolkit/__init__.py:20` | `__version__ = "2.4.1"` — **stale**. `pyproject.toml:7` sagt `version = "2.4.3"`. |
| `src/ai_watermark_toolkit/ui/banner.py:17` | `__version__ = "2.0.0"` — eine **dritte** Versionsnummer. WIRD exportiert über `ui/__init__.py` (`from .banner import __version__`). Abweichende Versionierung zwischen Banner (2.0.0), Hauptpaket init (2.4.1) und pyproject (2.4.3). |

### Leere `__init__.py` (keine Probleme)

Diese `__init__.py`-Dateien sind **leer** (kein `__all__`, keine Imports):
- `forensics/__init__.py`, `metrics/__init__.py`, `plugins/__init__.py`, `transform/__init__.py`, `lab/__init__.py`, `lab/families/__init__.py`, `documents/__init__.py`, `metadata/__init__.py`

Das ist akzeptabel für interne Subpackages (keine stale exports). Die Public-API wird über `ai_watermark_toolkit/__init__.py` gesteuert, das `detect_text` und `run_pipeline` exportiert.

---

## 6. Tote / toten Branches

### 6a. Konstante Bedingungen (`if True:` / `if False:`)

**Keine gefunden.** `grep` nach Mustern wie `if True:`, `if False:`, `if 0:`, `if 1:` liefert keine Treffer in `src/`.

### 6b. Unerreichbarer Code (nach `return`/`break`/`continue`/`raise`)

AST-Analyse (`_dead_branches.py`): **0 Instanzen** von Statements unmittelbar nach `return`/`break`/`continue`/`raise` in derselben Anweisungssequenz.

### 6c. Gefährliche Variable-Definition (Subtil)

**Datei:** `batch.py:36` — `process_batch()` (Komplexität 23)

Die Variablen `verified`, `z_score`, `green_rate` (Zeilen 102-104) werden **nur innerhalb** des Zweigs `elif mode == "embed": if verify:` definiert. Aber in Zeilen 126-128 werden sie referenziert:
```python
verified=verified if mode == "embed" and verify else None,
z_score=z_score if mode == "embed" and verify else None,
green_rate=green_rate if mode == "embed" and verify else None,
```

Dies funktioniert **nur** weil Python das Ternary-LHS nicht auswertet, wenn die Bedingung `False` ist (Lazy-Evaluation). Wenn jemand die Struktur ändert (z. B. `verified or None` statt `verified if ... else None`), würde `NameError` auftreten.

**Lösungsvorschlag:** Die Variablen zu Beginn der Schleife (vor dem `if mode == ...`-Block) auf `None` initialisieren:
```python
verified = z_score = green_rate = None
```

### 6d. `else`-Branch fängt mehr als beabsichtigt ab

**Datei:** `batch.py:114` — `process_batch()`

```python
if mode == "detect": ...
elif mode == "clean": ...
elif mode == "dilute": ...
elif mode == "embed": ...
else:  # fängt "pipeline" UND jeden anderen Modus ein!
    out, report = run_pipeline(text, ...)
```

Der `else`-Zweig ist als "pipeline-Modus" gedacht, fängt aber **auch ungültige Modi** ein (da der CLI `choices=["detect","clean","dilute","pipeline","embed"]` das einschränkt, passiert es zur Laufzeit nicht). Ist aber fragil.

**Lösungsvorschlag:** `elif mode == "pipeline":` + `else: raise ValueError(f"unknown batch mode: {mode}")`.

---

## 7. Methodik & Verifikation

| Check | Tool | Befehl | Ergebnis |
|---|---|---|---|
| Ungenannte Imports/Variablen (src) | `ruff` | `ruff check --select F src/` | ✅ Alle bestanden (kein ungenannter Code) |
| Ungenannte Imports/Variablen (tests) | `ruff` | `ruff check --select F tests/` | ✅ Alle bestanden |
| Dead Code Detection | `vulture --min-confidence 80` | `vulture --min-confidence 80 src/` | ✅ 0 Funde (80%-Schwelle) |
| Dead Code Detection (sensibler) | `vulture --min-confidence 60` | `vulture --min-confidence 60 src/` | 37 Funde → 13 echter Dead-Code, 24 False-Positives |
| False-Positive-Filterung | Manuelle Kreuzreferenz | `grep -rn --include="*.py" <symbol> src/ tests/` | Alle 37 Funde verifiziert |
| Zyklomatische Komplexität | `radon cc` | `python -m radon cc src/ -n B -s --json` | 59 Funktionen mit Komplexität > 10 |
| Code-Duplikate | `pycode_similar` + manuelle Analyse | AST-basierter Vergleich | 3 Duplikat-Muster identifiziert |
| `__init__.py` Exports | AST-Analyse | Prüfung von `__all__` vs. tatsächlichen Imports | 3 Probleme gefunden |
| Tote Branches (Konstanten) | `grep` | Suche nach `if True:`/`if False:`/`if 0:` | 0 gefunden |
| Unerreichbarer Code | AST-Analyse | Prüfung nach `return`/`break`/`continue`/`raise` | 0 Instanzen |
| Unreachable-dispatch | Manuelle Analyse | Vergleich Subparser vs. Dispatch-Handler | ✅ Alle übereinstimmend |

### Wichtig: Interpretationsregeln für `vulture`-False-Positives

`vulture` analysiert nur `src/` und kann nicht erkennen, dass:
1. **Dekorierte Funktionen** (`@router.get`, `@router.post`) als Routen registriert sind
2. **Framework-HOOKS** (`action_*`, `on_mount`, `compose`, `dispatch`) dynamisch aufgerufen werden
3. **Dataclass-Felder** über `__init__`/`asdict` verwendet werden
4. **Test-Dateien** Funktionen Klassen importieren und verwenden (vulture sieht nur `src/`)

Diese wurden alle manuell per `grep` in `src/` **und** `tests/` verifizert.
