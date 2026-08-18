# Text Watermark Studio — Watermarking Lab Edition

![CI](https://github.com/mrmixx-max/text-watermark-studio/actions/workflows/python-ci.yml/badge.svg)
![Release](https://github.com/mrmixx-max/text-watermark-studio/actions/workflows/release.yml/badge.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

![Text Watermark Studio 2.4.1 — verify, measure, prove. Keyed watermark verification. 100% local, no cloud, zero telemetry, MIT.](docs/tws-infographic.png)

Text Watermark Studio v2.4.1 is a taxonomy-driven watermarking lab with plugin families for Unicode, lexical, syntactic, format/layout, sampling-bias (post-hoc text rewrite + experimental generation-time sampler), semantic/structure, localized provenance and training-time ownership workflows. Installable: `pip install text-watermark-studio`.

📖 **Documentation:** [User Guide (EN)](docs/USER-GUIDE.md) · [Benutzerhandbuch (DE)](docs/BENUTZERHANDBUCH.md) · [API Reference](docs/API.md) · [TUI Guide](docs/TUI-GUIDE.md) · [Developer Guide](docs/DEVELOPER-GUIDE.md) · [MCP Integration](HERMES_MCP_INTEGRATION.md) · [Measurement First — Manifest](docs/measurement-first.md) · [Measurement vs. viral strippers](docs/comparison.md)

**New in v2.4.1 (v108):** `remove` command, `delta-z` measurement, `finding` (KI-Erklärungs-Befund C5), signed forensic reports (`report-sign`/`report-verify`/`report-keygen`), ML-DSA quantum-safe signatures, e-process detection, signature filtering, local corpus similarity, prompt optimizer, multi-model Ollama backend, batch embed with `--verify`, `--quiet` mode, watch `--kgw`, and 25-action TUI.

## Quickstart

Requires Python 3.10+.

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

## Changelog

See [CHANGELOG.md](CHANGELOG.md) and [docs/CHANGELOG.md](docs/CHANGELOG.md) for version history.

## Desktop app (Windows)

A thin PySide6 wrapper around **the same core forensics** that CLI/API/TUI
use — **no server, no network**: menus and buttons call the core functions
directly (Detect, Embed, Report, Sign, Verify, KGW demo). The entry point for
non-developers (law firms, institutions): paste text → pick a key → detect.
The app lives in `src/ai_watermark_toolkit/ui/desktop/` (Qt-free
`DesktopController` + PySide6 shell).

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

## CLI Reference (v108)

### Core commands

| Command | Description |
|---|---|
| `detect` | Scan text for unicode stego + AI phrasing markers |
| `clean` | Strip invisible-character layer |
| `dilute` | Rewrite marker-heavy phrasing (3 intensities) |
| `embed` | Impose a greenlist mark (keyed) |
| `pipeline` | Full chain: detect → clean → dilute → rewrite → detect |
| `remove` | Best-effort watermark removal: clean + dilute + structural rewrite |
| `report` | Self-contained HTML forensics report (KGW), optional `--pdf` |

### New commands (v108)

| Command | Description |
|---|---|
| `delta-z` | ΔZ check: measure KGW watermark strength before vs after (removal with receipt) |
| `finding` | KI-Erklärungs-Befund (C5): Evidenzklassen A-D, Prüfpriorität 0-5, signed |
| `report-sign` | Sign a forensic findings payload (HMAC-SHA256 or ML-DSA FIPS 204) |
| `report-verify` | Verify a signed forensic findings document |
| `report-keygen` | Generate an ML-DSA keypair for signing |
| `kgw-sample` | Generate synthetic KGW-bias text and detect it (experimental) |
| `similarity` | MinHash comparison against YOUR OWN corpus (honest boundary) |
| `llm` | Manage local model backend: `install`, `list`, `use`, `status` |
| `batch` | Run a mode over every file in a directory (now with `--verify` for embed) |
| `tui` | Launch the 25-action menu-driven terminal UI |

### Global flags

| Flag | Description |
|---|---|
| `--quiet`, `-q` | Suppress status messages on stderr (machine-readable output only) |

### Batch mode

```bash
ai-wm batch INPUT_DIR OUTPUT_DIR [--mode detect|clean|dilute|pipeline|embed]
              [--lang auto|de|en] [--intensity ...] [--key KEY]
              [--verify]   # for --mode embed: run detection after embedding to confirm Z>4
```

### Removal command

```bash
ai-wm remove INPUT [-o OUTPUT] [--intensity standard] [--rewrite-mode structural]
               [--use-llm] [--aggressive] [--json]
```

Chains clean → dilute → rewrite to degrade the watermark signal as far as possible. With `--use-llm` forces the local LLM backend for a stronger rewrite.

### Delta-Z measurement

```bash
ai-wm delta-z BEFORE AFTER --key KEY [--level word|bpe] [--context N]
ai-wm delta-z BEFORE --transform clean|truncate|shuffle|reformat --key KEY
```

Measures KGW watermark strength before/after an attack. The `--transform` mode applies a stdlib transform to a single file and measures its ΔZ. With `--sign`, the result is signed for auditability.

### Signed forensic reports

```bash
ai-wm report-keygen --algorithm mldsa-44|65|87 --output-dir ./keys
ai-wm report-sign finding.json --secret SECRET -o signed.json
ai-wm report-sign finding.json --algorithm mldsa-44 --private-key keys/mldsa_private.pem
ai-wm report-verify signed.json --secret SECRET
```

Default: HMAC-SHA256 (stdlib, zero deps). Optional: ML-DSA (FIPS 204, quantum-safe) with `cryptography` ≥ 50.

## Statistical watermark detection (KGW)

The forensics layer includes a real KGW-style statistical detector (`src/ai_watermark_toolkit/forensics/kgw.py`): per token, a pseudorandom hash over `(key, previous_token, token)` decides greenlist membership, and a one-sided Z-test over the whole text separates a watermarked green-rate (~100% for text generated with the matching key) from the expected ~25% of normal text.

**Generation-time bias (experimental):** `src/ai_watermark_toolkit/generation/kgw_sampler.py` implements the real generation-time half of KGW — an additive greenlist logit bias applied during autoregressive sampling. At γ=0.5, bias=2.0 it reaches green_rate ≈ 0.88 and `detect_kgw` recovers it with z ≫ 4.

**E-process detection (v108):** Anytime-valid e-process detection (`--e-value`) provides an alternative statistical test with early-stopping capability and Bonferroni correction for multi-key runs.

**Signature filtering (v108):** Opt-in `--signature-filter` for FPR control on texts dominated by one repetitive token (arXiv 2606.18430v2).

## Included families

- Unicode / zero-width — full bidi + zero-width family + opt-in aggressive mode
- Lexical choice
- Syntactic pattern
- Format / layout
- Sampling / logit bias — post-hoc KGW + experimental generation-time sampler
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

## MCP tools

The lab ships with an MCP tool manifest under `mcp/tools.json` and a Hermes-compatible plugin bundle under `hermes/`. The manifest exposes API-backed tools for health, readiness, pipeline runs, forensics, labs, ops status, streams, documents, RAG, LLM, routing, prompts, optimization, multi-agent, graph, community, rewrite, export, cloud, and metadata.

See [HERMES_MCP_INTEGRATION.md](HERMES_MCP_INTEGRATION.md) for setup and usage.

## Bundled Hermes skills

`hermes/skills/` contains agent skills that work with the studio and its ecosystem:

- `chameleon-universal-tarntarnung` — universal text camouflage: restructure any AI-written text (academic, business, informal) to drop its statistical fingerprint while preserving meaning
- `ai-text-detection-lab` — multi-signal AI-text detection: stylistic, statistical, semantic, structural, provenance and author-comparison evidence with transparent uncertainty instead of binary verdicts
- `dewatermarking-pipeline` — end-to-end removal chain: detect → clean → dilute → local-LLM rewrite → detect, with measured before/after marker reports (verified with EuroLLM-9B: 5 markers to 0)
- `text-forensics-workflow` — full forensic case workflow: secure material, extract text/metadata, scan Unicode + markers, weigh evidence, produce a documented verdict
- `text-watermark-studio-lab` — the studio's own lab skill

Install into Hermes with `hermes skill install <path>` or copy the folder under `~/AppData/Local/hermes/skills/`. Each SKILL.md is MIT-licensed like the repo.

## API server

```bash
ai-wm serve --port 8000
```

FastAPI app with routes for text processing, metadata, forensics, labs, documents, RAG, LLM, routing, prompts, optimization, multi-agent, graph, community, rewrite, export, cloud, and ops. Swagger UI at `/docs`, ReDoc at `/redoc`.

See [docs/API.md](docs/API.md) for the full API reference.

## Document formats

The document layer supports txt, markdown, rtf, docx, odt, pdf and epub workflows. API: `/api/documents/*`.

## File metadata cleaning (C2PA / EXIF / XMP)

| Format | What it removes |
| --- | --- |
| PNG | `eXIf` EXIF chunk, XMP hint chunks, C2PA/JUMBF detection |
| JPEG | `APP1` EXIF + XMP segments, `APP11` XMP/AI metadata, C2PA/JUMBF detection |
| WebP | EXIF / XMP metadata chunks from the RIFF container, C2PA/JUMBF detection |
| AVIF / HEIC | ISOBMFF metadata boxes (`meta/`), EXIF / XMP, C2PA/JUMBF detection |
| SVG | `<metadata>`/RDF blocks, `data-ai-*` provenance attributes |
| PDF | XMP metadata streams, Producer/Creator Info entries |
| DOCX | `customXml/` parts, docProps scrub |
| ODT | `meta.xml` generator entries |
| HTML | AI `<meta>` tags, JSON-LD provenance blocks |
| Markdown | YAML frontmatter AI keys |

API: `POST /api/metadata/inspect` and `POST /api/metadata/clean` (multipart upload). CLI: `ai-wm file-inspect <file>` and `ai-wm file-clean <file> -o <out>`.

### Embed and detect your own file watermark

The metadata layer also works in the other direction: `POST /api/metadata/embed` inserts a **signed provenance mark** (key_id + HMAC-SHA256 signature) into PNG/JPEG/SVG/PDF/DOCX/ODT/HTML/MD, using the same key registry as the KGW text detector. `POST /api/metadata/detect` (CLI: `ai-wm file-embed` / `ai-wm file-detect`) extracts the mark and verifies the signature against registered secrets.

### SynthID pixel scoring (external adapter)

Real SynthID detection needs the upstream research codebook (~220 MB, non-commercial Research License) from `aloshdenny/reverse-SynthID`. The studio ships an **adapter**, not the codebook: with a local checkout (env `REVERSE_SYNTHID_DIR`), `POST /api/metadata/synthid-score` runs the upstream scorer and returns its verdict; without one it reports `available: false` honestly.

```bash
scripts/setup_synthid.sh --verify
export REVERSE_SYNTHID_DIR=~/reverse-SynthID
ai-wm image-score shot.png --synthid-dir ~/reverse-SynthID
```

Or run it in Docker (builds from upstream source, no redistribution):

```bash
docker build -f Dockerfile.synthid -t text-watermark-studio-synthid .
docker run --rm -v "$(pwd):/data" text-watermark-studio-synthid /data/shot.png
```

### End-to-end proof against a real model

The detector isn't just tested against its own mini-generator. `benchmarks/kgw_e2e_proof.py` runs the full round-trip against a **real local model** (Ollama EuroLLM-9B): the model generates fresh text, `mark_greenlist` imposes the KGW greenlist on the model's *actual* token choices, and the detector must recover it.

## v2.4.1: model-grade detection + measurement suite

- **BPE token level**: `detect_kgw(text, key, level="bpe")` over cl100k subword tokens (`pip install text-watermark-studio[bpe]`)
- **Attack matrix**: `python benchmarks/attack_matrix.py` — measures Z-score drop per attack
- **SynthID-style sweep**: `python benchmarks/synthid_sweep.py` — gamma × paraphrase-rate detection curve
- **Findings report**: `ai-wm report file.txt --key <key> [--pdf]` — self-contained HTML/PDF forensics report
- **Directory watcher**: `ai-wm watch ./docs` — JSON lines per file
- **Local corpus similarity**: `ai-wm similarity text.txt --corpus ./archiv` — MinHash vs YOUR OWN documents, honest literal-overlap boundary
- **Menu-driven TUI**: `ai-wm tui` — 25 actions, keyboard shortcuts, in-menu Ollama pull (`[tui]` extra)
- **OpenAPI 3.1 spec**: [docs/openapi.json](docs/openapi.json) — generated from the live FastAPI route table

## v2.3.0: trajectory, multi-bit payload, adversarial evaluation

- **Z-score trajectory**: `ai-wm trace file.txt --key <key> [--window 500 --step 250 --threshold 4]` — sliding-window KGW detection over a long document
- **Multi-bit payload (invariant features)**: `ai-wm payload embed file.txt --payload "user-42" -o wm.txt` and `ai-wm payload extract wm.txt --reference file.txt` — embed a text payload via the Yoo et al. (ACL 2023) invariant-feature codebook
- **Adversarial evaluation**: `ai-wm evade file.txt --key <key> [--target-z 3.9 --max-changes N --ollama-model <m>]` — white-box stress test of the studio's OWN KGW scheme

## v2.4.0 / v2.4.1: ΔZ measurement, --verify, extended format support

- **ΔZ (delta-z) transform**: `ai-wm delta-z file.txt --key <key> --transform clean|truncate|shuffle|reformat|rewrite` — measure watermark strength before vs after a single-file transform
- **`--verify` flag**: `ai-wm file-clean file.png -o clean.png --verify` — re-inspects the cleaned file and reports `verified_clear | residual_hard_bound | no_c2pa_present`, proving the metadata strip actually worked rather than assuming
- **Extended format support**: AVIF, HEIC, WebP metadata inspection and cleaning (C2PA / EXIF / XMP) alongside the existing PNG/JPEG pipeline

## Local LLM integration

```bash
ai-wm llm list                  # all models the local Ollama knows
ai-wm llm install llama3.2:3b   # pull via the Ollama API + select
ai-wm llm use qwen-coder        # switch to an installed model
ai-wm llm status                # current backend config
```

Any OpenAI-compatible endpoint works via `LOCAL_LLM_BASE_URL` + `LOCAL_LLM_MODEL`.

## Important limit

This edition includes demo implementations and architectural plugin slots, not universal real-world detectors or embedders for every family. Many families require decoder control, model access, parser stacks or secret key material outside a text-only local lab.

## What removing a text watermark costs (honest disclaimer)

Text watermarks live in **the wording itself**: the signal is spread across token choices, so nearly every sentence carries a little of it. Removal means rewording, not restructuring. Rewording degrades the copy. The `remove` command is the honest path: it does what can be done locally and reports exactly what changed.

## License

MIT · Repository: <https://github.com/mrmixx-max/text-watermark-studio>
PyPI: <https://pypi.org/project/text-watermark-studio>
