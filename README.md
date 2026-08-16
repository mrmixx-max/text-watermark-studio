# Text Watermark Studio — Watermarking Lab Edition

![CI](https://github.com/mrmixx-max/text-watermark-studio/actions/workflows/python-ci.yml/badge.svg)
![Release](https://github.com/mrmixx-max/text-watermark-studio/actions/workflows/release.yml/badge.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

![Text Watermark Studio 2.0.0 — verify, measure, prove. Keyed watermark verification. 100% local, no cloud, zero telemetry, MIT.](docs/tws-infographic.png)

Text Watermark Studio v1.0.0 adds a taxonomy-driven watermarking lab with plugin families for Unicode, lexical, syntactic, format/layout, sampling-bias (post-hoc text rewrite + experimental generation-time sampler), semantic/structure, localized provenance and training-time ownership workflows. Installable: `pip install text-watermark-studio`.

📖 **Documentation:** [User Guide (EN)](docs/USER-GUIDE.md) · [Benutzerhandbuch (DE)](docs/BENUTZERHANDBUCH.md) · [Measurement First — Manifest](docs/measurement-first.md)

![Local AI Watermark Laboratory — workstation concept](docs/lab-workstation.png)

![Hero card](docs/tws-hero-card.png)

## Quickstart

Requires Python 3.10+.

> **Sales catalogs:** [English](docs/marketing/tws-catalog-2026-en.html) · [Deutsch](docs/marketing/tws-catalog-2026-de.html) — one tool, seven application fields. Guides: [User Guide (EN)](docs/USER-GUIDE.md) · [Benutzerhandbuch (DE)](docs/BENUTZERHANDBUCH.md).

```bash
# Install from PyPI (the CLI + library)
pip install text-watermark-studio

# Or from source (editable, with test deps)
python -m venv .venv
# Windows: .\.venv\Scripts\activate | macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"

# CLI
ai-wm detect tests/fixtures/ai_sample_de.txt --lang de
ai-wm clean tests/fixtures/stego_zwsp.txt -o clean.txt
ai-wm dilute tests/fixtures/ai_sample_en.txt -o diluted.txt --intensity standard
ai-wm pipeline tests/fixtures/ai_sample_de.txt -o out.txt --report report.json
ai-wm serve --host 127.0.0.1 --port 8080

# Tests
pytest -q

# API server
uvicorn ai_watermark_toolkit.api.fastapi_app:app --host 127.0.0.1 --port 8080
```

> **Note:** the CLI + library are on PyPI. The SynthID bootstrap
> (`scripts/setup_synthid.sh`), the `Dockerfile.synthid`, and the bundled
> Hermes skills live in this repository, not the wheel — they are operator
> tooling and skill bundles, not runtime modules. Clone the repo for those.

Alternatively, run the whole stack via Docker:

```bash
docker compose up --build
```

Or pull the published image from GitHub Container Registry:

```bash
docker pull ghcr.io/mrmixx-max/text-watermark-studio:latest
docker run -p 8080:8080 ghcr.io/mrmixx-max/text-watermark-studio
```

The GHCR image runs the FastAPI service as a non-root user on port 8080 —
fully local, no cloud, zero telemetry.

Windows users: the Makefile detects `OS=Windows_NT` and uses `.venv\Scripts` paths automatically. `scripts/publish-check.ps1` runs the full check (venv, install, tests, build) in PowerShell. Desktop packaging for Windows lives in `desktop/packaging/windows/build.ps1`.

## Desktop app (Windows)

A thin PySide6 wrapper around **the same core forensics** that CLI/API/TUI
use — **no server, no network**: menus and buttons call the core functions
directly (Detect, Embed, Report, Sign, Verify, KGW demo). The entry point for
non-developers (law firms, institutions): paste text → pick a key → detect.
The app lives in `src/ai_watermark_toolkit/ui/desktop/` (Qt-free
`DesktopController` + PySide6 shell).

**Features**

- **Detect** — KGW Z-score + e-process (anytime-valid) against the selected
  key or all registered keys; JSON result in the panel
- **Embed** — `mark_greenlist`: text is greenlist-marked (guaranteed
  detectable, Z>4), result replaces the editor text (Ctrl+Z undoes it);
  every substituted token is **highlighted green** so you can see exactly
  what the watermark changed (offsets come from the core via the
  `substitutions` return key)
- **Report** — self-contained HTML report (`build_report`) to `Downloads`
  (fallback: temp directory)
- **Sign/Verify** — sign report JSON (HMAC-SHA256, registry secret; ML-DSA
  (quantum-resistant) via CLI: `ai-wm report-keygen`/`report-sign`) and verify
- **KGW demo** — synthetic generation-time bias (mechanism proof, no LLM)
- Key selection, status bar (line/column, character & word count), JSON
  result panel, file dialog, **drag & drop a file onto the editor**
- **Real text editor**: line numbers, Find bar (Ctrl+F, Enter/Shift+Enter,
  wrap-around), line-wrap toggle (Ctrl+Shift+W), current-line highlight

**Run (source)**

```bash
pip install PySide6        # optional GUI-only dependency (core stays stdlib-first, no pyproject entry)
python -m ai_watermark_toolkit.ui.desktop.app
```

**Build (Windows)**

```bash
pip install PySide6 pyinstaller
pip install -e .
pyinstaller packaging/tws-desktop.spec     # -> dist/tws-desktop.exe (onefile, windowed)
iscc packaging/tws-setup.iss              # -> dist/TWS-Setup.exe (Inno Setup)
```

CI: `.github/workflows/build-desktop.yml` (manual or tag `v*` on
windows-latest: PyInstaller → choco Inno Setup → ISCC → Artifacts).

**Installation and the honest SmartScreen hurdle**

`TWS-Setup.exe` installs to `%ProgramFiles%\TextWatermarkStudio`. Without a
code-signing certificate the installer is **unsigned** — Windows SmartScreen
shows "Unknown publisher" and requires "More info → Run anyway". That is
expected and not a bug. A code-signing certificate (OV/EV, ~$100–300/year)
removes the warning; this is a budget decision — the optional signing step
is commented out in the workflow (certificate as secret
`WINDOWS_CERT_BASE64`/`WINDOWS_CERT_PASSWORD`).

**Keys**: the app reads `data/key_registry.json` (read-only, same contract as
CLI/TUI). Create keys via `POST /api/forensics/keys` (`ai-wm serve`) or via
registry entry; without a KGW key with a secret the app reports that honestly
instead of silently creating a registry. The installer does not install any
keys — the registry stays an operator concern.

## Why a lab edition

Recent taxonomies and surveys split text watermarking into multiple families with different assumptions, requirements and threat models. Existing-text methods, generation-time methods and model-level provenance do not collapse into one universal technique, so the product is structured as a lab with family plugins and capability axes rather than a single misleading detector.

## Statistical watermark detection (KGW)

The forensics layer now includes a real KGW-style statistical detector (`src/ai_watermark_toolkit/forensics/kgw.py`): per token, a pseudorandom hash over `(key, previous_token, token)` decides greenlist membership, and a one-sided Z-test over the whole text separates a watermarked green-rate (~100% for text generated with the matching key) from the expected ~25% of normal text. Multi-key detection tests every registered `kgw`-family key and reports per-key Z-scores with a Bonferroni-style adjustment.

What it detects, honestly: texts generated **with this exact scheme and key**. It is not a universal detector for unknown vendor schemes — key and hash scheme must match. Word-level tokens approximate model tokenizers. Behavioral tests (`tests/test_v113_kgw_detector.py`) include a mini KGW generator that shares the detector's PRF: correct key → Z ≥ 4, wrong key → no signal.

**Generation-time bias (experimental):** `src/ai_watermark_toolkit/generation/kgw_sampler.py` now implements the *real* generation-time half of KGW — an additive greenlist logit bias applied during autoregressive sampling (the step that maps 1:1 onto a `logit_bias` table in llama.cpp / OpenAI-style decoders). It is a deterministic, dependency-free mechanics proof, not a production generator: it samples synthetic tokens from a plain token→logit table and round-trips through the same `detect_kgw` detector. Tests (`tests/test_v134_kgw_sampler.py`) show bias=2.0, γ=0.5 → green_rate ≈ 0.88 (control ≈ 0.5), z ≫ 4 with the right key and context window, no signal for the wrong key or a mismatched window. The post-hoc text rewrite remains the standard embed path; llama.cpp `logit_bias` over a GGUF model is the documented production route (needs a MSVC/CMake build on Windows and is intentionally not a hard dependency).

## Signed forensic findings (auditability, quantum-safe optional)

Every detect/report run can be turned into a **self-signed, auditable document**: `ai-wm report-sign` / `report-verify` / `report-keygen` (or `POST /api/forensics/report-sign` for registry-keyed HMAC). Default is **HMAC-SHA256 over canonical JSON — pure stdlib, zero dependencies**. When the optional `cryptography` library (≥ 50) is installed, the same pipeline signs with **ML-DSA (FIPS 204) — NIST-standardized, quantum-safe signatures**: `--algorithm mldsa-44` (default), `mldsa-65` or `mldsa-87`. ML-DSA signatures are non-deterministic (two signatures of the same payload differ, both verify), the private key is a seed-sized PEM (~128 B) whose public key is derived on load (stable round-trip), and verification is order-safe (`verify(signature, data)` — signature first, regression-tested). Measured signature sizes: **2420 B (44) / 3309 B (65) / 4627 B (87)**. The stdlib HMAC path stays the default and works everywhere; ML-DSA is the quantum-safe option for findings that must stay verifiable past the quantum transition. Tests: `tests/test_v140_signed_report.py` (C3 contract) + `tests/test_v143_mldsa_hardening.py` (PEM round-trip, non-determinism, verify-order trap, context=b"" pure mode, 65/87, label trust).

## Included families

- Unicode / zero-width — full bidi + zero-width family (ZWSP/ZWNJ/ZWJ, LRE/RLE/LRO/RLO/PDF, LRI/RLI/FSI/PDI, word joiner, BOM, Mongolian VS, deprecated format chars, tag block, variation selectors) **plus an opt-in aggressive mode** for script-specific fillers (Braille blank, Hangul fillers, object replacement) that standard mode deliberately leaves alone
- Lexical choice
- Syntactic pattern
- Format / layout
- Sampling / logit bias — post-hoc text-rewrite KGW (standard) **plus an experimental generation-time sampler** (`src/ai_watermark_toolkit/generation/kgw_sampler.py`): a deterministic, dependency-free sampler applies an additive logit bias to greenlist tokens during generation. At γ=0.5, bias=2.0 it reaches green_rate ≈ 0.88 and `detect_kgw` recovers it with z ≫ 4, while the unbiased control stays at ≈ γ and a wrong context window collapses the signal (measured 2026-08-13: the real Ollama generator itself shows no greenlist bias, so post-hoc rewrite remains the standard path)
- Semantic / structure
- Localized provenance
- Training-time / ownership

## MarkLLM-compatible interop (reference-verified)

`src/ai_watermark_toolkit/interop/markllm.py` reimplements the exact KGW
greenlist scheme from the **MarkLLM reference toolkit** (THU-BPM/MarkLLM,
EMNLP 2024, Apache-2.0): `torch.randperm` PRF seeded by `(hash_key * f)`,
left-window context, `time`/`f` scheme, and the same Z-score formula. The
interop tests (`tests/test_markllm_interop.py`) verify **byte-identical
greenlists and identical z-scores against the real MarkLLM implementation** —
texts watermarked by the reference toolkit are detected by this detector with
the same key, and vice versa. Optional extra: `pip install "text-watermark-studio[markllm]"`.

## Important limit

This edition includes demo implementations and architectural plugin slots, not universal real-world detectors or embedders for every family. Many families require decoder control, model access, parser stacks or secret key material outside a text-only local lab.

## MCP tools

The lab now ships with an MCP tool manifest under `mcp/tools.json` and a Hermes-compatible plugin bundle under `hermes/`. The manifest exposes API-backed tools for health, readiness, pipeline runs, forensics, labs, ops status and streams.

## Bundled Hermes skills

`hermes/skills/` contains agent skills that work with the studio and its ecosystem:

- `chameleon-universal-tarntarnung` — universal text camouflage: restructure any AI-written text (academic, business, informal) to drop its statistical fingerprint while preserving meaning
- `ai-text-detection-lab` — multi-signal AI-text detection: stylistic, statistical, semantic, structural, provenance and author-comparison evidence with transparent uncertainty instead of binary verdicts
- `dewatermarking-pipeline` — end-to-end removal chain: detect → clean → dilute → local-LLM rewrite → detect, with measured before/after marker reports (verified with EuroLLM-9B: 5 markers to 0)
- `text-forensics-workflow` — full forensic case workflow: secure material, extract text/metadata, scan Unicode + markers, weigh evidence, produce a documented verdict
- `text-watermark-studio-lab` — the studio's own lab skill

Install into Hermes with `hermes skill install <path>` or copy the folder under `~/AppData/Local/hermes/skills/`. Each SKILL.md is MIT-licensed like the repo.

## Document formats

The v1.0.0 edition adds a document layer for txt, markdown, rtf, docx, odt, pdf and epub workflows. Pandoc is widely used as a universal document converter for docx, rtf, odt, epub, markdown and pdf-oriented flows, while specialized libraries like pypdf, python-docx, odfpy, EbookLib and striprtf cover format-specific extraction and manipulation use cases. Current API support focuses on normalization and export pathways through `/api/documents/*`, with Hermes/MCP exposure for agent use.

## File metadata cleaning (C2PA / EXIF / XMP)

The metadata layer strips AI provenance marks from files — stdlib-only, no external tools required:

| Format | What it removes |
| --- | --- |
| PNG | `eXIf` EXIF chunk, XMP hint chunks (`iTXt`/`zTXt`/`tEXt`), C2PA/JUMBF detection |
| JPEG | `APP1` EXIF + XMP segments, `APP11` XMP/AI metadata, C2PA/JUMBF detection |
| SVG | `<metadata>`/RDF blocks, `data-ai-*` provenance attributes |
| PDF | XMP metadata streams (byte-level), Producer/Creator Info entries (best-effort; exiftool remains stronger) |
| DOCX | `customXml/` parts, docProps scrub (creator, lastModifiedBy, revision) |
| ODT | `meta.xml` generator entries |
| HTML | AI `<meta>` tags, JSON-LD provenance blocks, `data-ai*` attributes |
| Markdown | YAML frontmatter AI keys (generated_by, model_name, ...) |

API: `POST /api/metadata/inspect` and `POST /api/metadata/clean` (multipart upload). CLI: `ai-wm file-inspect <file>` and `ai-wm file-clean <file> -o <out>`. Verifiable actions are reported per removal; C2PA *soft binding* (in-content marks re-linking a remote manifest) and pixel-domain marks remain out of scope.

### Embed and detect your own file watermark

The metadata layer also works in the other direction: `POST /api/metadata/embed` inserts a **signed provenance mark** (key_id + HMAC-SHA256 signature) into PNG/JPEG/SVG/PDF/DOCX/ODT/HTML/MD, using the same key registry as the KGW text detector. `POST /api/metadata/detect` (CLI: `ai-wm file-embed` / `ai-wm file-detect`) extracts the mark and verifies the signature against registered secrets:

- Same key → `valid: true` (HMAC over the original content)
- Tampered content → mark found, `valid: false`
- Unknown key → found but invalid
- Stream formats (png/jpeg/svg/html/md) bind the whole content; container formats (docx/odt) bind the main content part (documented)

Round-trip tested for every format (`tests/test_v116_file_provenance.py`).

### SynthID pixel scoring (external adapter)

Real SynthID detection needs the upstream research codebook (~220 MB, non-commercial Research License) from `aloshdenny/reverse-SynthID`. The studio ships an **adapter**, not the codebook: with a local checkout (env `REVERSE_SYNTHID_DIR`), `POST /api/metadata/synthid-score` runs the upstream scorer and returns its verdict; without one it reports `available: false` honestly. Detection/scoring only — pixel-domain watermark removal is out of scope.

**Bootstrap (one command):**

```bash
# Clones upstream, creates a venv, installs scorer-only deps.
scripts/setup_synthid.sh

# Score an image (or via the API endpoint).
export REVERSE_SYNTHID_DIR=~/reverse-SynthID
ai-wm image-score shot.png --synthid-dir ~/reverse-SynthID
```

**Or run it in Docker (builds from upstream source, no redistribution):**

```bash
docker build -f Dockerfile.synthid -t text-watermark-studio-synthid .
docker run --rm -v "$(pwd):/data" text-watermark-studio-synthid /data/shot.png
```

`setup_synthid.sh` accepts `--dir PATH`, `--ref REF`, `--full` (installs the full upstream requirements, which adds torch/diffusers for the VAE bypass this project does not use), and `--verify`, which runs a real score on a generated test image after setup — so "it works" is proven rather than assumed. The upstream code remains under its own Research License and is never bundled.

### End-to-end proof against a real model

The detector isn't just tested against its own mini-generator. `benchmarks/kgw_e2e_proof.py` runs the full round-trip against a **real local model** (Ollama EuroLLM-9B): the model generates fresh text, `mark_greenlist` imposes the KGW greenlist on the model's *actual* token choices, and the detector must recover it:

- Unmarked model text → `no_signal` (z ≈ 0.6)
- Marked + right key → `watermark_detected` (z ≈ 15.9)
- Marked + wrong key → `no_signal` (z ≈ −0.2)

The proof uses `gamma=0.5` (a free KGW parameter; higher gamma raises detectability but lifts the control baseline variance — documented, not hidden). The marker substitutes from a frequency vocabulary (`forensics/frequent_vocab.py`), not synonyms, and does not preserve word-for-word nuance — this is the honest signal-imposition approximation of token-sampling watermarks.

## v2.0.0: model-grade detection + measurement suite

- **BPE token level**: `detect_kgw(text, key, level="bpe")` over cl100k subword tokens (`pip install text-watermark-studio[bpe]`)
- **Attack matrix**: `python benchmarks/attack_matrix.py` — measures Z-score drop per attack
- **SynthID-style sweep**: `python benchmarks/synthid_sweep.py` — gamma × paraphrase-rate detection curve
- **Findings report**: `ai-wm report file.txt --key <key> [--pdf]` — self-contained HTML/PDF forensics report
- **Directory watcher**: `ai-wm watch ./docs` — JSON lines per file
- **Local corpus similarity**: `ai-wm similarity text.txt --corpus ./archiv` — MinHash vs YOUR OWN documents, honest literal-overlap boundary
- **Menu-driven TUI**: `ai-wm tui` — 25 actions, keyboard shortcuts, in-menu Ollama pull (`[tui]` extra)
- **OpenAPI 3.1 spec**: [docs/openapi.json](docs/openapi.json) — generated from the live FastAPI route table

## v2.3.0: trajectory, multi-bit payload, adversarial evaluation

- **Z-score trajectory**: `ai-wm trace file.txt --key <key> [--window 500 --step 250 --threshold 4]`
  — sliding-window KGW detection over a long document. The whole-doc Z-test
  averages away local signals; the trajectory shows WHERE the watermark is
  (marked chapter inside a clean manuscript), merging adjacent finding
  windows into spans with word offsets and peak Z. Human report by default,
  JSON via `--json`/`-o`.
- **Multi-bit payload (invariant features)**: `ai-wm payload embed file.txt
  --payload "user-42" -o wm.txt` and `ai-wm payload extract wm.txt
  --reference file.txt` — embed a text payload (user id, timestamp, run id)
  via the Yoo et al. (ACL 2023) invariant-feature codebook. Self-delimiting
  UTF-8 encoding; extraction needs the ORIGINAL text as reference state
  (both parties share the invariant anchors). Capacity = 1 bit per mask
  position — short payloads, honest warning + exit 1 when the text is too
  small.
- **Adversarial evaluation**: `ai-wm evade file.txt --key <key>
  [--target-z 3.9 --max-changes N --ollama-model <m>]` — white-box stress
  test of the studio's OWN KGW scheme: greedily replaces greenlisted tokens
  with non-green alternatives until Z drops below the target, measuring the
  cost (changes, change ratio, word overlap, per-change Z trajectory).
  Optional Ollama infill for natural candidates. Honest scope: known key,
  own scheme — measures the robustness floor, not field resistance.

> **Full inventory:** every additional module (RAG chunking, prompt registry + optimizer, graph memory, community detection, rewrite engine, exports, cloud upload, local-LLM routing, HTMX hardening) is documented in [docs/FEATURES.md](docs/FEATURES.md) with its honest status. Multi-agent loop is a **minimal demo scaffold** — do not rely on it in production.
