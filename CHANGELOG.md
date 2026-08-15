# Changelog

## 2.2.1 — Editor marking invalidation + report language selection

- **Stale highlight fix** (`ui/desktop/editor.py`): greenlist substitution
  markings are now cleared the moment the editor text changes (typing,
  paste, undo, wrap toggle). Previously, offsets were only invalidated on
  file load, so editing after an embed painted the highlights on the wrong
  words — including after Ctrl+Z, which the placeholder text promises.
- **Cleanup** (`ui/desktop/editor.py`): removed dead `textCursor()` base
  assignments in `_repaint_markings`, removed a redundant module-level
  `QTextDocument` import (already imported at the top) with a misleading
  comment, and dropped an inline `QTextEdit` import.
- **Report language** (`forensics/finding.py`, `forensics/report.py`):
  every human-readable text field (observation, possible_explanations,
  exculpatory, recommended_next_steps, verdict_text,
  schlussfolgerung_hinweis, HTML report badge/sections/recommendation) is
  now localized. Default stays `"de"` (backward compatible — all existing
  tests match unchanged); `lang="en"` switches the text fields to English.
  Structured fields (evidence_class, category, priority, risk, beleg)
  stay language-neutral by design. Surface: `--lang de|en` on the CLI
  finding command, `lang` field on the `/finding` API request, and a
  language combo in the desktop toolbar.
- **Tests**: `tests/test_v100_desktop_editor.py` covers typing, undo, and
  re-embed after edits (offscreen, PySide6 optional dep);
  `tests/test_v148_finding_lang.py` covers DE default, EN switch, unknown
  lang fallback, HTML report and CLI paths.

## 2.2.0 — Desktop text editor with substitution highlighting

- **Desktop editor** (`ui/desktop`): the text area is now a real editor —
  line numbers, find bar (Ctrl+F, Enter/Shift+Enter, wrap-around, yellow
  match highlight), current-line highlight, status bar (line/column +
  character count), soft-wrap toggle (Bearbeiten menu), and drag-and-drop
  file loading. The editor replaces the plain text box for embed/detect
  workflows.
- **Substitution highlighting**: `mark_greenlist` and `embed_kgw` now
  return `substitutions` — exact character offsets in the *final* text
  (`start`, `end`, `original`, `replacement`) plus `green_rate_after`.
  Backwards compatible: new keys only, existing consumers unaffected. The
  desktop app highlights every greenlist-substituted token green after
  embed, so you see exactly what the watermark changed.
- **CI**: publish workflow is idempotent (`skip_existing` instead of a 400
  failure on re-publish).
- **Docs**: MarkDiffusion roadmap decision recorded (issue #1, no code).

## 2.1.0 — MarkLLM-compatible KGW interop + GHCR

- **MarkLLM interop**: KGW mark/detect is byte-identical to the reference
  MarkLLM implementation (verified against `markllm==0.1.5`, `interop/markllm.py`).
- **GHCR image**: `ghcr.io/mrmixx-max/text-watermark-studio` published on
  tags via `docker-publish` workflow; README documents Docker + MarkLLM
  usage.

## 2.0.1 — Hardening, forensics suite, desktop app

Released incrementally; highlights from the v2.0.0..v2.0.1 range (see git
history for the full list):

- **Desktop app** (`ui/desktop`): Qt-free `DesktopController` over the core
  forensics, PySide6 main window, PyInstaller + Inno Setup installer,
  `build-desktop` CI.
- **Forensics depth**: e-value detection (LR-martingale, anytime-valid,
  Bonferroni), signature filtering with honest FPR control, delta-Z checks,
  signed forensic reports (HMAC + optional ML-DSA-44), AI-explanatory
  finding reports (evidence classes A-D), invariant-feature watermarking
  (Yoo et al. 2023), generation-time sampling bias (synthetic sampler MVP,
  honestly labeled as post-hoc approximation).
- **Local corpus similarity** (`ai-wm similarity`): MinHash fingerprinting
  against a user-owned corpus with fundstelle evidence and an explicit
  honest boundary — literal overlap, not plagiarism claims, no web crawl.
- **Multi-model local backend**: `ai-wm llm install|list|use|status` — pull
  any model through the Ollama API (streamed progress, verified, config
  updated), switch between installed models, list everything the local
  Ollama knows. TUI menu entry 18 does the same from the Path field. Not
  locked to EuroLLM anymore.
- **Prompt optimizer rebuilt** (was a 20-line demo stub): locked eval set,
  one-variable candidates, deterministic metrics with hard protected-term
  guardrail, baseline hashing, promotion only on improvement, immutable
  versioning + rollback through the prompt registry. API routes replace the
  demo endpoints (`/api/optimization/evals|candidates|optimize|promote|history|rollback`).
- **TUI**: menu-driven Textual interface (`ai-wm tui`), cursor keys (↑/↓)
  drive the menu from any focus; Enter runs the selected action everywhere;
  header sub-title "by Erik Gieske".
- **Prompt registry fix**: `get_template` now returns the newest stable
  version by semver (previously first-in-list) — promotion/rollback target
  the correct version.
- Security hardening (F1-F6), MCP manifest to 76 tools, OpenAPI 3.1 spec,
  EN user guide + DE Benutzerhandbuch (print PDFs via maintainer script),
  repo relabel to independent verification.

## 2.0.0 — Model-grade detection + the measurement suite

The major bump closes the detector's documented approximation gap and adds
the measurement/forensics tooling around it.

- **BPE token level** (`forensics/kgw.py`): `detect_kgw`, `mark_greenlist`
  and `tokenize` accept `level="word"|"bpe"`. BPE runs the greenlist over
  cl100k subword tokens at word boundaries — the exact surface a real
  tokenizer feeds sampling watermarks. Mark and detect round-trip on the
  same level. `tiktoken` is an optional extra: `pip install
  text-watermark-studio[bpe]`.
- **Attack matrix** (`benchmarks/attack_matrix.py`): structural, dilute
  (light/standard/aggressive), unicode spam, and word shuffle against a
  marked text — measures the Z-score drop per attack, prints the table,
  writes `attack_matrix.json`. Honest finding: style attacks do not break
  the mark; word permutation does.
- **SynthID-style sweep** (`benchmarks/synthid_sweep.py`): gamma ×
  paraphrase-rate grid producing the detection curve (Z vs. rewording
  strength), writes `synthid_sweep.json`.
- **Findings report** (`forensics/report.py` + `ai-wm report`): one-command
  self-contained HTML forensics report (KGW stats, unicode table, text,
  recommendation) with optional `--pdf` rendering via Edge headless.
- **Directory watcher** (`forensics/watcher.py` + `ai-wm watch`): stdlib
  polling scan of a folder, JSON lines with metadata + provenance findings
  per file, `--once` for scripts/tests, `--interval` for continuous runs.

## 1.0.0 — Keyed forensics: detect AND embed, on text AND files

The major release. The studio gained what no comparable tool ships: proof,
not hope — a real statistical detector, its inverse (embedding), and the
same pair on the file layer.

### Detection (the proof)

- **Real KGW statistical watermark detector** (`forensics/kgw.py`): PRF
  greenlist per token, Z-score test over the whole text, p-value.
- **Multi-key support** with Bonferroni adjustment. Right key → `Z >= 4`;
  wrong key → `no signal`. Verified by a same-PRF mini-generator in tests.
- Extended Unicode classes: full bidi family (LRE/RLE/LRO/RLO/PDF, isolates),
  zero-width, BOM, Mongolian VS, deprecated format chars, tag block,
  variation selectors — **plus an opt-in aggressive mode** for script
  fillers (Braille blank, Hangul, object replacement) that standard mode
  leaves alone.

### Embedding (the inverse)

- **KGW embed** (text): rewrites content words into greenlist positions;
  the detector finds them again. Round-trip tested.
- **File provenance** (`metadata/provenance.py`): signed HMAC marks embedded
  into PNG/JPEG/SVG/PDF/DOCX/ODT/HTML/MD; detect verifies the signature.
  Tamper → `valid: false`; unknown key → `valid: false`.

### File metadata layer

- **C2PA / EXIF / XMP stripping** for PNG/JPEG/SVG/PDF/DOCX/ODT/HTML/MD,
  stdlib-only. Verifiable per-removal actions; soft-binding documented.

### Rewriting

- Structural + **backtranslate** modes: backtranslate is the literature-standard
  two-hop attack (text → English → original), two LLM calls; honest rule-based
  fallback without an LLM backend.
- Rewriting integrated into the pipeline:
  `detect → clean → dilute → rewrite → detect`.

### SynthID

- **Pixel-scoring adapter** (`metadata/synthid.py` + `score_synthid_cli.py`).
- One-command bootstrap (`scripts/setup_synthid.sh`) and a
  `Dockerfile.synthid` that builds from upstream source (no redistribution).

### Console UI

- ASCII banner + colored pretty reports. JSON remains the default output.

### Documentation

- **Vendor-notes reference files** (Claude, Gemini/SynthID, OpenAI) in the
  studio-lab skill — class-level provenance surfaces, honestly de-scoped.
- Honest "what removing a text watermark costs" disclaimer.

### Quality

- 169 tests, Windows + Linux verified, CI (ubuntu + Redis container) green.

## 0.9.2 — Taxonomy-driven watermarking lab

Plugin families for Unicode, lexical, syntactic, format/layout, sampling/logit
bias, semantic/structure, localized provenance, training-time ownership.

- Document layer (txt/md/rtf/docx/odt/pdf/epub), PyMuPDF-first extraction.
- RAG chunking: fixed, recursive, markdown-aware, page-aware, semantic-lite.
- LLM rewriting: provider abstraction for Ollama, OpenAI, Anthropic.
- Prompt registry, automatic prompt optimization. Multi-agent loop: minimal
  demo scaffold (2 hardcoded drafts, API routes, MCP hooks) — not the full
  critic/refiner loop; use the optimizer service for real evaluator loops.
- Graph knowledge + community detection; auto-correction rewrite engine.
- Unified export (Markdown/HTML/JSON/CSV/TXT); cloud upload; model routing.
- MCP tool manifest (`mcp/tools.json`) and Hermes plugin bundle (`hermes/`).

## 0.1.0 — Initial publishing-ready release

- CLI commands: detect, clean, dilute, pipeline, batch, serve
- FastAPI app and local web UI
- Docker and GitHub Actions setup
- Tests, issue templates, release workflow, and MIT license
