# Changelog

## 2.4.3 — CI/CD hardening + lint cleanup

- **CI: ruff lint config fixed** — simplified `select` to bug-rules only (`F`), removed unknown rule codes from `ignore` that broke CI on newer ruff versions.
- **Bug fix: missing import** (`cli.py`): added `from dataclasses import asdict` — `F821 undefined name` in report generation.
- **Bug fix: unused variable** (`cli.py`): removed unused `tui_parser` variable (`F841`).
- **Bug fix: redundant json.dumps** (`cli.py`): fixed `RUF001` duplicate ternary in detect output formatting.
- **Formatting**: applied `ruff format` across 114 src + 88 test files (whitespace, line wrapping).
- **PyPI publish**: added `environment: pypi` to `pypi-publish.yml` for OIDC trusted publishing compliance.
- **Docs**: added `CHANGELOG.md` entries for all prior untracked fixes.

## 2.4.2 — security hardening + CLI features + C2PA verify

- **Security: timing-safe API key comparison** (`api/middleware/auth.py`): replaced `x_api_key != settings.api_key` with `hmac.compare_digest()` to prevent timing side-channel attacks on the API-key gate.
- **Security: SSRF prevention** (`llm/service.py`, `optimization/service.py`): added `_validate_url_scheme()` that rejects non-HTTP(S) URLs before any `urllib.request.urlopen()` call — prevents SSRF via `OLLAMA_BASE_URL` / `LOCAL_LLM_BASE_URL` env-var injection.
- **Security: bandit nosec annotations** — all 29 bandit findings now carry justified `# nosec` comments (B311 seeded RNG for non-crypto use, B310 hardcoded localhost URL, B105 intentional demo secrets, B404/B603 subprocess with list args only). No new unannotated findings.
- **New: `ai-wm remove`** (`cli.py`): best-effort watermark removal chaining `clean → dilute → rewrite`. Honest de-scoping: statistical marks live in wording, so removal means rewording. Supports `--use-llm` for forced local-LLM rewriting, `--intensity`, `--rewrite-mode`, `--json`.
- **New: batch embed mode** (`cli.py`, `batch.py`): `ai-wm batch --mode embed --key <key_id>` embeds KGW greenlist watermarks into a directory of text files. Supports `--level`, `--context`, `--gamma`, `--seed`, and `--verify` (runs detection post-embed to confirm Z > 4).
- **New: `ai-wm watch --kgw`** (`cli.py`, `forensics/watcher.py`): opt-in KGW text detection during directory watching — runs `detect_multi_key` on text files using registered KGW keys with secrets.
- **New: `--quiet/-q`** (`cli.py`): suppresses stderr status messages for scripted/machine-readable use; stdout JSON untouched.
- **Watch: graceful shutdown** (`forensics/watcher.py`): SIGTERM/SIGINT handlers break the polling loop cleanly instead of running forever.
- **Watch: stale-entry pruning** (`forensics/watcher.py`): entries for deleted files are removed from the `known` dict, preventing unbounded memory growth on long-running watches.
- **Bug fix: Windows ANSI** (`ui/banner.py`): replaced `os.system("")` with `ctypes.windll.kernel32.SetConsoleMode()` for enabling ANSI escape sequences — safer, no shell call.
- **Bug fix: input validation** (`cli.py`): `--interval <= 0`, `--context < 1`, and `--gamma` outside `(0, 0.5]` now exit with code 2 and a clear error message.
- **Logging hygiene** (`cli.py`, `streams/redis_streams.py`): bare `pass` in exception handlers replaced with `logger.debug(exc_info=True)` so failures are traceable without cluttering output.
- **MCP: `forensics_embed` manifest entry** (`mcp/tools.json`): updated description and reordered for consistency.
- **`ai-wm file-clean --verify`**: cleans the file, then RE-INSPECTS the cleaned bytes and reports an honest C2PA before/after verdict — `verified_clear` (markers gone), `residual_hard_bound` (markers survive the container strip), `no_c2pa_present`, or `unsupported_format`.
- `_isobmff`/`_webp` now set `hard_bound_c2pa_present` on inspect (was only PNG/JPEG/PDF) so `verify_clean` works for AVIF/HEIC/WebP.
- **Performance: BPE tokenization cache** (`forensics/kgw.py`): added `_bpe_subwords_cached()` for repeated BPE encoding.
- **Performance: regex pre-compilation** (`forensics/invariant.py`): word-cleaning regex now pre-compiled as `_WORD_CLEAN_RE`.
- **Performance: batch hot loop** (`batch.py`): replaced `__import__('json')` with top-level import.
- **Dead-code removal** — unused imports removed across 6 files.

## 2.4.0 — AVIF/HEIC + WebP metadata stripping

- **ISOBMFF (AVIF/HEIC) stripping** (`metadata/service.py`): drops top-level and `meta`-subbox `jumb`/`c2pa` boxes (C2PA/JUMBF content credentials) and XMP-carrying `uuid` boxes (standard XMP UUID), plus AI-hint `uuid`/`xml `/`bxml` sub-boxes. 64-bit largesize boxes handled; innocent sub-boxes (hdlr, mdat, ...) preserved. Verified with re-parse + marker-gone asserts.
- **WebP (RIFF) stripping**: drops EXIF / "XMP " / C2PA chunks and AI-hint ICCP profiles while preserving VP8/VP8L image chunks.
- `file-inspect` / `file-clean` support the new formats automatically (dispatch by extension; SUPPORTED extended).
- **Test env independence**: new `tests/conftest.py` autouse fixture patches the auth middleware settings to the empty-key dev default — the local `.env` (AI_WM_API_KEY set, fail-closed) used to break every API test suite written for the documented dev convention. Suites that exercise auth (v130/v137/v145) patch the middleware's settings object themselves.
- **Tests**: `tests/test_v153_metadata_avif_webp.py` (10 tests); full suite 630 passed, 10 skipped.

## 2.3.1 — Rewrite/Paraphrase in the ΔZ core

- **`rewrite` transform in `ai-wm delta-z`** (`forensics/delta_z.py`): the paraphrase path is now a first-class transform — no longer "deliberately NOT part of the product path". `ai-wm delta-z <file> --transform rewrite --key <key>` measures what an actual paraphrase attack does to the KGW signal. Rule-based `structural` mode is the default (no LLM, CI-safe); `--rewrite-mode <clarity|concise|plain|formal|structural|backtranslate>` and `--use-llm` select modes / the local Ollama backend. Honest boundary (documented in module + CLI): a strong LLM rewrite can collapse z (`removed:true`), but that is REGENERATION, not "cleaning" — ΔZ proves signal change, never cleaner honesty. Light structural edits keep `removed:false` (measured: ΔZ ≈ 0.8–0.9 on a z=13.6 mark).
- **API**: `/api/forensics/delta-z` accepts `rewrite_mode` + `use_llm` for transform mode; docstring documents the 5th transform.
- **Bugfix**: `RewriteService._protect` replaced finditer+replace (index shifting mangled URLs — the word pattern hit "Com" inside "example.com" — and leaked nested protected tokens) with a single `re.sub` callback pass. URLs are matched first. Numbers, URLs, quotes and proper nouns now survive every rewrite mode.
- **Tests**: `tests/test_v149_delta_z_rewrite.py` (8 tests: transform method, rule-based no-LLM path, honest no-false-removal, protected-token survival, mode validation, CLI exit 0 / mode flag / JSON output file).

## 2.3.0 — Z-score trajectory, multi-bit payload, adversarial evaluation

- **Z-score trajectory** (`forensics/trace.py`, `ai-wm trace`): sliding-window KGW detection over long documents. The whole-document Z-test averages away local signals; the trajectory reports per-window Z with word offsets, marks finding windows (Z >= threshold, default 4.0), merges adjacent findings into spans with peak Z and text excerpts, and keeps too-short windows with `reliable: False`. CLI: `ai-wm trace file.txt --key <key> [--window --step --threshold --json]`. Demo: 600-word marked block in a 3000-word document found at peak Z=21.0 while whole-doc Z stayed 2.26.
- **Multi-bit payload** (`forensics/invariant.py`, `ai-wm payload`): embed and recover text payloads (user ids, timestamps, run ids) via the invariant-feature codebook (Yoo et al., ACL 2023, light). `encode_payload`/`decode_payload` use a self-delimiting 16-bit length prefix; `embed_payload`/`extract_payload` wrap the codebook. `?` in unused codebook capacity no longer invalidates the payload (only `?` inside the prefix/body does). CLI: `ai-wm payload embed <file> --payload <str> -o wm.txt`, `ai-wm payload extract <wm.txt> --reference <original>`; capacity warning + exit 1 when the text is too small.
- **Adversarial evaluation** (`forensics/evader.py`, `ai-wm evade`): white-box stress test of the studio's own KGW scheme. Greedy loop replaces greenlisted tokens with non-green alternatives until Z drops below the target; the report measures changes, change ratio, similarity, word overlap and the per-change Z trajectory. Optional Ollama infill. Demo: Z 14.49 → 3.70 with 74/432 changes (17.1%), 66.4% word overlap. Honest scope: known key, own scheme — robustness floor, not field resistance.
- **Tests**: 23 new tests (v150 trace, v151 payload, v152 evader) — full suite 612 passed, 10 skipped.

## 2.2.1 — Editor marking invalidation + report language selection

- **Stale highlight fix** (`ui/desktop/editor.py`): greenlist substitution markings are now cleared the moment the editor text changes (typing, paste, undo, wrap toggle). Previously, offsets were only invalidated on file load, so editing after an embed painted the highlights on the wrong words — including after Ctrl+Z, which the placeholder text promises.
- **Cleanup** (`ui/desktop/editor.py`): removed dead `textCursor()` base assignments in `_repaint_markings`, removed a redundant module-level `QTextDocument` import (already imported at the top) with a misleading comment, and dropped an inline `QTextEdit` import.
- **Report language** (`forensics/finding.py`, `forensics/report.py`): every human-readable text field (observation, possible_explanations, exculpatory, recommended_next_steps, verdict_text, schlussfolgerung_hinweis, HTML report badge/sections/recommendation) is now localized. Default stays `"de"` (backward compatible — all existing tests match unchanged); `lang="en"` switches the text fields to English. Structured fields (evidence_class, category, priority, risk, beleg) stay language-neutral by design. Surface: `--lang de|en` on the CLI finding command, `lang` field on the `/finding` API request, and a language combo in the desktop toolbar.
- **Tests**: `tests/test_v100_desktop_editor.py` covers typing, undo, and re-embed after edits (offscreen, PySide6 optional dep); `tests/test_v148_finding_lang.py` covers DE default, EN switch, unknown lang fallback, HTML report and CLI paths.

## 2.2.0 — Desktop text editor with substitution highlighting

- **Desktop editor** (`ui/desktop`): the text area is now a real editor — line numbers, find bar (Ctrl+F, Enter/Shift+Enter, wrap-around, yellow match highlight), current-line highlight, status bar (line/column + character count), soft-wrap toggle (Bearbeiten menu), and drag-and-drop file loading. The editor replaces the plain text box for embed/detect workflows.
- **Substitution highlighting**: `mark_greenlist` and `embed_kgw` now return `substitutions` — exact character offsets in the *final* text (`start`, `end`, `original`, `replacement`) plus `green_rate_after`. Backwards compatible: new keys only, existing consumers unaffected. The desktop app highlights every greenlist-substituted token green after embed, so you see exactly what the watermark changed.
- **CI**: publish workflow is idempotent (`skip_existing` instead of a 400 failure on re-publish).
- **Docs**: MarkDiffusion roadmap decision recorded (issue #1, no code).

## 2.1.0 — MarkLLM-compatible KGW interop + GHCR

- **MarkLLM interop**: KGW mark/detect is byte-identical to the reference MarkLLM implementation (verified against `markllm==0.1.5`, `interop/markllm.py`).
- **GHCR image**: `ghcr.io/mrmixx-max/text-watermark-studio` published on tags via `docker-publish` workflow; README documents Docker + MarkLLM usage.

## 2.0.1 — Hardening, forensics suite, desktop app

Released incrementally; highlights from the v2.0.0..v2.0.1 range (see git history for the full list):

- **Desktop app** (`ui/desktop`): Qt-free `DesktopController` over the core forensics, PySide6 main window, PyInstaller + Inno Setup installer, `build-desktop` CI.
- **Forensics depth**: e-value detection (LR-martingale, anytime-valid, Bonferroni), signature filtering with honest FPR control, delta-Z checks, signed forensic reports (HMAC + optional ML-DSA-44), AI-explanatory finding reports (evidence classes A-D), invariant-feature watermarking (Yoo et al. 2023), generation-time sampling bias (synthetic sampler MVP, honestly labeled as post-hoc approximation).
- **Local corpus similarity** (`ai-wm similarity`): MinHash fingerprinting against a user-owned corpus with fundstelle evidence and an explicit honest boundary — literal overlap, not plagiarism claims, no web crawl.
- **Multi-model local backend**: `ai-wm llm install|list|use|status` — pull any model through the Ollama API (streamed progress, verified, config updated), switch between installed models, list everything the local Ollama knows. TUI menu entry 18 does the same from the Path field. Not locked to EuroLLM anymore.
- **Prompt optimizer rebuilt** (was a 20-line demo stub): locked eval set, one-variable candidates, deterministic metrics with hard protected-term guardrail, baseline hashing, promotion only on improvement, immutable versioning + rollback through the prompt registry. API routes replace the demo endpoints (`/api/optimization/evals|candidates|optimize|promote|history|rollback`).
- **TUI**: menu-driven Textual interface (`ai-wm tui`), cursor keys (↑/↓) drive the menu from any focus; Enter runs the selected action everywhere; header sub-title "by Erik Gieske".
- **Prompt registry fix**: `get_template` now returns the newest stable version by semver (previously first-in-list) — promotion/rollback target the correct version.
- Security hardening (F1-F6), MCP manifest to 76 tools, OpenAPI 3.1 spec, EN user guide + DE Benutzerhandbuch (print PDFs via maintainer script), repo relabel to independent verification.

## 2.0.0 — Model-grade detection + the measurement suite

The major bump closes the detector's documented approximation gap and adds the measurement/forensics tooling around it.

- **BPE token level** (`forensics/kgw.py`): `detect_kgw`, `mark_greenlist` and `tokenize` accept `level="word"|"bpe"`. BPE runs the greenlist over cl100k subword tokens at word boundaries — the exact surface a real tokenizer feeds sampling watermarks. Mark and detect round-trip on the same level. `tiktoken` is an optional extra: `pip install text-watermark-studio[bpe]`.
- **Attack matrix** (`benchmarks/attack_matrix.py`): structural, dilute (light/standard/aggressive), unicode spam, and word shuffle against a marked text — measures the Z-score drop per attack, prints the table, writes `attack_matrix.json`. Honest finding: style attacks do not break the mark; word permutation does.
- **SynthID-style sweep** (`benchmarks/synthid_sweep.py`): gamma × paraphrase-rate grid producing the detection curve (Z vs. rewording strength), writes `synthid_sweep.json`.
- **Findings report** (`forensics/report.py` + `ai-wm report`): one-command self-contained HTML forensics report (KGW stats, unicode table, text, recommendation) with optional `--pdf` rendering via Edge headless.
- **Directory watcher** (`forensics/watcher.py` + `ai-wm watch`): stdlib polling scan of a folder, JSON lines with metadata + provenance findings per file, `--once` for scripts/tests, `--interval` for continuous runs.

## 1.0.0 — Keyed forensics: detect AND embed, on text AND files

The major release. The studio gained what no comparable tool ships: proof, not hope — a real statistical detector, its inverse (embedding), and the same pair on the file layer.

### Detection (the proof)

- **Real KGW statistical watermark detector** (`forensics/kgw.py`): PRF greenlist per token, Z-score test over the whole text, p-value.
- **Multi-key support** with Bonferroni adjustment. Right key → `Z >= 4`; wrong key → `no signal`. Verified by a same-PRF mini-generator in tests.
- Extended Unicode classes: full bidi family (LRE/RLE/LRO/RLO/PDF, isolates), zero-width, BOM, Mongolian VS, deprecated format chars, tag block, variation selectors — **plus an opt-in aggressive mode** for script fillers (Braille blank, Hangul, object replacement) that standard mode leaves alone.

### Embedding (the inverse)

- **KGW embed** (text): rewrites content words into greenlist positions; the detector finds them again. Round-trip tested.
- **File provenance** (`metadata/provenance.py`): signed HMAC marks embedded into PNG/JPEG/SVG/PDF/DOCX/ODT/HTML/MD; detect verifies the signature. Tamper → `valid: false`; unknown key → `valid: false`.

### File metadata layer

- **C2PA / EXIF / XMP stripping** for PNG/JPEG/SVG/PDF/DOCX/ODT/HTML/MD, stdlib-only. Verifiable per-removal actions; soft-binding documented.

### Rewriting

- Structural + **backtranslate** modes: backtranslate is the literature-standard two-hop attack (text → English → original), two LLM calls; honest rule-based fallback without an LLM backend.
- Rewriting integrated into the pipeline: `detect → clean → dilute → rewrite → detect`.

### SynthID

- **Pixel-scoring adapter** (`metadata/synthid.py` + `score_synthid_cli.py`).
- One-command bootstrap (`scripts/setup_synthid.sh`) and a `Dockerfile.synthid` that builds from upstream source (no redistribution).

### Console UI

- ASCII banner + colored pretty reports. JSON remains the default output.

### Documentation

- **Vendor-notes reference files** (Claude, Gemini/SynthID, OpenAI) in the studio-lab skill — class-level provenance surfaces, honestly de-scoped.
- Honest "what removing a text watermark costs" disclaimer.

### Quality

- 169 tests, Windows + Linux verified, CI (ubuntu + Redis container) green.

## 0.9.2 — Taxonomy-driven watermarking lab

Plugin families for Unicode, lexical, syntactic, format/layout, sampling/logit bias, semantic/structure, localized provenance, training-time ownership.

- Document layer (txt/md/rtf/docx/odt/pdf/epub), PyMuPDF-first extraction.
- RAG chunking: fixed, recursive, markdown-aware, page-aware, semantic-lite.
- LLM rewriting: provider abstraction for Ollama, OpenAI, Anthropic.
- Prompt registry, automatic prompt optimization. Multi-agent loop: minimal demo scaffold (2 hardcoded drafts, API routes, MCP hooks) — not the full critic/refiner loop; use the optimizer service for real evaluator loops.
- Graph knowledge + community detection; auto-correction rewrite engine.
- Unified export (Markdown/HTML/JSON/CSV/TXT); cloud upload; model routing.
- MCP tool manifest (`mcp/tools.json`) and Hermes plugin bundle (`hermes/`).

## 0.1.0 — Initial publishing-ready release

- CLI commands: detect, clean, dilute, pipeline, batch, serve
- FastAPI app and local web UI
- Docker and GitHub Actions setup
- Tests, issue templates, release workflow, and MIT license
