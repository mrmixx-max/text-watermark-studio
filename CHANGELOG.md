# Changelog

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
