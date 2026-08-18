# Release v2.0.0 — Text Watermark Studio

> **Watermarking Lab Edition** · 100% local · zero telemetry · MIT

![Text Watermark Studio 2.0.0 — verify, measure, prove.](docs/tws-infographic.png)

We're thrilled to announce the **v2.0.0 stable release** of Text Watermark Studio — a complete, taxonomy-driven watermarking laboratory that runs entirely on your machine.

---

## What's New in v2.0.0

### New Commands

| Command | What it does |
|---|---|
| `remove` | Best-effort watermark removal: clean + dilute + structural rewrite with honest reporting |
| `delta-z` | Measure KGW watermark strength before vs. after an attack — the receipt that proves the delta |
| `finding` | Generate a KI-Erklärungs-Befund (C5) with evidence classes A-D and check priority 0-5 |
| `report-sign` | Sign a forensic findings payload — HMAC-SHA256 (zero deps) or ML-DSA FIPS 204 (quantum-safe) |
| `report-verify` | Verify a signed forensic findings document |
| `report-keygen` | Generate an ML-DSA keypair for signing |
| `kgw-sample` | Generate synthetic KGW-bias text and detect it (experimental) |
| `similarity` | MinHash comparison against your own corpus — honest boundary, no cloud |
| `llm` | Manage local Ollama backend: install, list, use, status |
| `batch` | Run any mode over a directory of files (now with `--verify` for embed) |
| `tui` | Launch the 25-action menu-driven terminal UI |

### Forensics Upgrades

- **E-process detection** — Anytime-valid e-value testing with early-stopping and Bonferroni correction for multi-key runs
- **Signature filtering** — Opt-in `--signature-filter` for FPR control on repetitive-token texts (arXiv 2606.18430v2)
- **ML-DSA quantum-safe signatures** — FIPS 204 post-quantum signing for forensic reports via `cryptography` ≥ 50
- **ΔZ measurement** — Quantify exactly how much an attack degraded the watermark signal

### Desktop App (Windows)

- PySide6 wrapper around the same core forensics used by CLI/API/TUI
- Detect, Embed, Report, Sign/Verify, KGW Example — no server, no network
- Target audience: law firms, institutions, non-developers

### API & Infrastructure

- FastAPI server with 22 route modules (text, forensics, documents, RAG, LLM, prompts, multi-agent, export, cloud, ops)
- 25-action TUI (textual) for terminal-first operators
- Docker multi-stage builds with non-root user
- GitHub Actions CI: matrix testing (Python 3.10–3.12, Ubuntu + Windows), linting, security scanning, coverage

---

## Installation

```bash
# From PyPI
pip install text-watermark-studio

# With BPE token-level detection
pip install text-watermark-studio[bpe]

# With the terminal UI
pip install text-watermark-studio[tui]

# From source
git clone https://github.com/mrmixx-max/text-watermark-studio.git
cd text-watermark-studio
python -m venv .venv
# Windows: .\.venv\Scripts\activate | macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
```

---

## Quickstart

```bash
# Detect AI markers and unicode stego
ai-wm detect article.txt

# Clean invisible characters
ai-wm clean article.txt -o clean.txt

# Measure watermark strength before/after removal
ai-wm delta-z before.txt after.txt --key mykey

# Generate a signed forensic finding
ai-wm finding article.txt --key mykey --sign --secret "$SECRET"

# Launch the TUI
ai-wm tui

# Serve the API
ai-wm serve --host 127.0.0.1 --port 8080
```

---

## Honest Limits

This edition includes demo implementations and architectural plugin slots, not universal real-world detectors or embedders for every family. Many families require decoder control, model access, parser stacks, or secret key material outside a text-only local lab.

Text watermarks live in **the wording itself**: the signal is spread across token choices, so nearly every sentence carries a little of it. Removal means rewording, not restructuring. The `remove` command is the honest path: it does what can be done locally and reports exactly what changed.

---

## Links

- **Repository:** https://github.com/mrmixx-max/text-watermark-studio
- **PyPI:** https://pypi.org/project/text-watermark-studio
- **Documentation:** docs/USER-GUIDE.md · docs/API.md · docs/TUI-GUIDE.md · docs/DEVELOPER-GUIDE.md
- **Changelog:** CHANGELOG.md
- **License:** MIT

---

*Built with ❤️ for researchers, journalists, and anyone who needs to prove — not just claim — what's in a text.*
