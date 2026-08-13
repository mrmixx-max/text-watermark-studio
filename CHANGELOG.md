# Changelog

## Unreleased — prompt optimizer (real evaluator loop) + TUI cursor navigation

- **Local corpus similarity** (`ai-wm similarity`): MinHash fingerprinting
  against a user-owned corpus with fundstelle evidence and an explicit
  honest boundary — literal overlap, not plagiarism claims, no web crawl.
- **TUI**: header sub-title "by Erik Gieske" + splash credit line.

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
- **TUI**: cursor keys (↑/↓) now drive the menu from any focus (app-level
  priority bindings); Enter runs the selected action everywhere.
- **Prompt registry fix**: `get_template` now returns the newest stable
  version by semver (previously first-in-list) — promotion/rollback target
  the correct version.

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
- Prompt registry, automatic prompt optimization, multi-agent feedback loop.
- Graph knowledge + community detection; auto-correction rewrite engine.
- Unified export (Markdown/HTML/JSON/CSV/TXT); cloud upload; model routing.
- MCP tool manifest (`mcp/tools.json`) and Hermes plugin bundle (`hermes/`).

## 0.1.0 — Initial publishing-ready release

- CLI commands: detect, clean, dilute, pipeline, batch, serve
- FastAPI app and local web UI
- Docker and GitHub Actions setup
- Tests, issue templates, release workflow, and MIT license
