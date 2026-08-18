# Text Watermark Studio — User Guide

Version 2.4.1 · MIT · 100% local, zero telemetry

This guide covers everything the toolkit can do, how to verify that it works,
and — with equal care — what it honestly cannot do.

---

## 1. Overview

Text Watermark Studio is a local forensics laboratory for AI text and file
watermarks. It runs entirely on your machine; nothing is sent to a cloud.

It works in both directions:

- **Detect** marks that others left behind — invisible unicode, AI phrasing
  patterns, and statistical sampling watermarks (KGW family).
- **Remove** them — clean, dilute, rewrite.
- **Prove** findings — a Z-score you can defend, not a "looks like AI" vibe.
- **Protect** your own content — greenlist marks on text, HMAC provenance
  signatures on files.

Supported surfaces:

| Surface | Detect | Clean | Embed | Detect-own |
|---|---|---|---|---|
| Text (unicode / phrasing) | ✅ | ✅ | — | — |
| Text (statistical, KGW) | ✅ | — | ✅ | ✅ |
| Files (metadata: C2PA/EXIF/XMP) | ✅ | ✅ | — | — |
| Files (provenance, HMAC) | ✅ | — | ✅ | ✅ |
| Images (SynthID pixels) | ✅ (via external checkpoint) | — | — | — |

---

## 2. Installation

Requires Python 3.10+.

```bash
# Core install
pip install text-watermark-studio

# With BPE token-level detection (cl100k via tiktoken)
pip install text-watermark-studio[bpe]

# With the menu-driven terminal UI (textual)
pip install text-watermark-studio[tui]
```

From source:

```bash
git clone https://github.com/mrmixx-max/text-watermark-studio.git
cd text-watermark-studio
python -m venv .venv
# Windows: .\.venv\Scripts\activate | macOS/Linux: source .venv/bin/activate
pip install -e ".[dev,bpe]"
```

Verify the install:

```bash
ai-wm --help
ai-wm detect --help
```

---

## 3. Quickstart

```bash
# Scan a text for invisible characters and AI markers
ai-wm detect article.txt

# JSON output (default; --pretty for humans)
ai-wm detect article.txt --json

# Clean the unicode layer, write to a new file
ai-wm clean article.txt -o clean.txt

# Rewrite marker-heavy phrasing (three intensities)
ai-wm dilute clean.txt --intensity standard -o diluted.txt

# Run the whole chain: detect -> clean -> dilute -> detect
ai-wm pipeline article.txt -o final.txt

# Batch process a directory
ai-wm batch ./input ./output --mode detect

# Start the API server (22 route modules)
ai-wm serve --host 127.0.0.1 --port 8080

# Launch the web dashboard
ai-wm dashboard --port 8080

# Launch the terminal UI (25 actions)
ai-wm tui
```

### API example (curl)

```bash
# Start the server
ai-wm serve &

# Detect markers via API
curl -s http://127.0.0.1:8080/api/detect \
  -H "Content-Type: application/json" \
  -d '{"text": "Some text to analyze..."}' | python -m json.tool

# Clean unicode via API
curl -s http://127.0.0.1:8080/api/clean \
  -H "Content-Type: application/json" \
  -d '{"text": "Text with hidden marks", "nfkc": true}' | python -m json.tool
```

### Python example

```python
from ai_watermark_toolkit.pipeline import detect_text, run_pipeline
from ai_watermark_toolkit.transform.clean import clean_text
from ai_watermark_toolkit.forensics.kgw import detect_kgw

# Detect markers
result = detect_text("Your text here")
print(f"Unicode count: {result['layers']['unicode']['count']}")
print(f"High-confidence markers: {result['layers']['markers']['high']}")

# Clean unicode
cleaned = clean_text("Text with hidden marks", nfkc=True)
print(cleaned.text)

# KGW statistical detection
kgw_result = detect_kgw("Text to test", key="my-key", level="word")
print(f"Z-score: {kgw_result['z_score']}, Verdict: {kgw_result['verdict']}")
```

---

## 4. Concepts: the three layers

AI systems mark output on three layers. None are visible to the eye.

**Layer 1 — Invisible characters.** Bidirectional controls (LRE, RLE, LRO,
RLO, PDF, isolates), zero-width spaces, joiners, tag blocks, deprecated
format characters. Survive copy-paste, change nothing visually.

**Layer 2 — Style markers.** Statistical fingerprints in phrasing: 18 AI
phrasing patterns including inflected forms.

**Layer 3 — Statistical watermarks.** KGW, SynthID-text and relatives bias
token choice *during generation*. No character, no phrase — a distribution.
Detectable only with the right key and a statistical test (Z-score).

Layers 1 and 2 are removed with `clean`/`dilute`. Layer 3 is measured, not
removed: `detect_kgw` reports whether a mark is present, with a score.

---

## 5. CLI reference

7 subcommands. Exit codes: `0` clean, `1` findings/error/unavailable,
`2` input error. `ai-wm tui` launches the menu-driven terminal UI (see §6).

### detect
```bash
ai-wm detect [input] [--stdin] [--lang auto|de|en] [--json] [-o OUTPUT]
```
Finds unicode/stego and AI phrasing markers. `--lang` selects the marker
language (`auto` detects automatically).

### clean
```bash
ai-wm clean [input] [--stdin] [--nfkc] [--fold-confusables] [-o OUTPUT]
            [--report REPORT]
```
Strips the unicode layer. `--nfkc` normalizes compatibility forms,
`--fold-confusables` maps lookalike glyphs.

### dilute
```bash
ai-wm dilute [input] [--stdin] --intensity light|standard|aggressive [-o OUTPUT]
```
Rewrites marker-heavy phrasing, 33 rules with protected tokens.

## 5b. Full feature access: API, TUI, Desktop, Python

The CLI covers the core text pipeline (detect/clean/dilute/pipeline/batch).
The full forensics feature set is available through:

| Interface | How to start | What it adds |
|---|---|---|
| **API server** | `ai-wm serve` | 22 route modules: forensics (KGW detect/embed/delta-z/finding/report-sign/verify), metadata, documents, PDF, RAG, LLM, routing, prompts, optimization, multi-agent, graph, community, export, cloud upload, queue/streams |
| **TUI** | `ai-wm tui` | 25-action menu: detect, clean, dilute, embed, pipeline, report, rewrite, file inspect/clean/embed/detect, SynthID scoring, watch, benchmarks, system state, update |
| **Desktop GUI** | `python -m ai_watermark_toolkit.ui.desktop.app` | PySide6 GUI: detect, embed, report, sign/verify, KGW demo — no server, no network |
| **Python** | `from ai_watermark_toolkit.forensics import ...` | Direct access to all modules: `kgw`, `e_process`, `delta_z`, `finding`, `signed_report`, `trace`, `invariant` (payload), `evader`, `watcher`, `similarity`, `encoding_detect` |

See [API.md](API.md) for the full REST endpoint reference.
See [TUI-GUIDE.md](TUI-GUIDE.md) for the terminal UI guide.
See [../desktop/README.md](../desktop/README.md) for the desktop app.

### pipeline
```bash
ai-wm pipeline [input] [--stdin] [--lang auto|de|en] [--nfkc]
               [--fold-confusables] --intensity light|standard|aggressive
               [--rewrite-mode clarity|concise|plain|formal|structural|backtranslate]
               [--aggressive] [-o OUTPUT] [--report REPORT]
```
The full chain: detect → clean → dilute → rewrite → detect. `rewrite_mode`
defaults to off; enable it explicitly.

### batch
```bash
ai-wm batch INPUT_DIR OUTPUT_DIR [--mode detect|clean|dilute|pipeline]
              [--lang auto|de|en] [--intensity ...] [--report REPORT]
```
Runs a mode over every file in a directory.

### serve
```bash
ai-wm serve [--host HOST] [--port PORT]
```
Starts the FastAPI server (see §13).

## 6. Menu-driven terminal UI

```bash
ai-wm tui
```

A menu-driven Textual interface (install with
`pip install text-watermark-studio[tui]`). Dark studio theme matching the
repo's hero infographic. 25 menu entries — detect, clean, dilute, embed,
pipeline, report, rewrite, the four file tools, SynthID scoring, directory
watch, both benchmarks, system state, and update.

Navigation:

- `↑`/`↓` move through the menu from anywhere (app-level priority bindings
  — cursor keys drive the menu even while the Path field is focused)
- `Enter` runs the selected action
- letter shortcuts: `d` detect · `c` clean · `e` embed · `p` pipeline ·
  `r` report · `s` splash · `q` quit · `^p` command palette
- the Path field at the bottom takes a file or directory path; most actions
  read it, then write results to the output panel

**Update:** entry 17 checks the installed version against PyPI and runs
`pip install --upgrade text-watermark-studio` when a newer release exists.

**Burn-in:** `python benchmarks/tui_burnin.py` drives all 25 actions through
a real sample file headlessly and fails loudly on any exception — the
pre-release gate for the UI.

![Menu-driven studio TUI](../docs/tws-tui.png)

---

## 7. KGW statistical watermark detection

The detector implements the KGW (Kirchenbauer et al.) greenlist scheme:

1. A PRF hash of `(key, previous token)` selects a greenlist of ~γ of the
   vocabulary.
2. Watermarked text uses green tokens more often than chance.
3. The Z-score of the green count tests that bias: `Z = (green − γn) /
   √(nγ(1−γ))`.

Verdicts: `Z ≥ 4.0` watermark_detected · `2.0 ≤ Z < 4` weak_signal ·
`Z < 2.0` no_signal. `γ` defaults to 0.25 (`--gamma` on `embed`,
`DEFAULT_GAMMA` in `forensics/kgw.py`).

### Multi-key with Bonferroni

`detect_multi_key(text, keys)` tests a list of keys and applies Bonferroni
correction so that running many keys does not inflate false positives.

### Token levels

```python
from ai_watermark_toolkit.forensics.kgw import detect_kgw

detect_kgw(text, "my-key", level="word")   # fast approximation (default)
detect_kgw(text, "my-key", level="bpe")    # cl100k subwords, model-grade
```

`level="bpe"` hashes greenlist over cl100k subword tokens **at word
boundaries** — the surface a real tokenizer feeds sampling watermarks. Mark
and detect round-trip on the same level. `level="word"` lowercases and
scores whole words.

### The end-to-end proof

`benchmarks/kgw_e2e_proof.py` runs the full round-trip against a real local
model (default `eurollm-9b:latest` via Ollama): generate text → impose the
greenlist on the foreign model's own tokens → detect. Measured:

| Measurement | Result |
|---|---|
| Unmarked model text, right key | z = 0.6, no signal |
| Marked text, right key | **z = 15.9, watermark_detected** |
| Marked text, wrong key | z = −0.2, no signal |

---

## 8. Embedding your own marks

**Text (via TUI/Desktop/API):** Use the Embed action in the TUI (`ai-wm tui`),
the Desktop GUI, or `POST /api/forensics/embed`. In Python code:
`mark_greenlist()` imposes the greenlist by substituting green words from a
frequency pool. The mark is keyed: only the key holder detects it; a wrong
key reports no signal.

Honest caveat: substitutions come from a frequency vocabulary, not
synonyms — word-for-word nuance is not preserved. This is the documented
approximation of token-sampling watermarking from text-only rewriting.

**Files:** see §8.

Keys live in `data/key_registry.json`. The shipped `demo-kgw-1` key carries
a public demo secret — replace it before real use:

```json
{"keys": [{"key_id": "my-key", "family": "kgw", "status": "active",
           "owner": "local", "secret": "<your-secret>"}]}
```

---

## 9. File provenance (HMAC)

Use the File Embed/File Detect actions in the TUI (`ai-wm tui`), the Desktop
GUI, or `POST /api/metadata/embed` and `POST /api/metadata/detect`. Sign files
with an HMAC over the original content and store the mark in the file
(XMP-style packet). 8 formats: PNG, JPEG, SVG, PDF, DOCX, ODT, HTML, Markdown.

Properties:

- **Content-bound:** flipping any byte of the content breaks the signature.
- **Keyed:** only the secret holder can set *or* forge a valid mark.
- **`found`/`valid` pair:** distinguishes "wrong key" from "tampered
  content".

```bash
ai-wm file-embed  report.pdf --key my-key -o signed.pdf
ai-wm file-detect signed.pdf --key my-key --json
# {"found": true, "valid": true, ...}
```

---

## 10. Metadata stripping (C2PA / EXIF / XMP)

Use the File Inspect/File Clean actions in the TUI (`ai-wm tui`), the Desktop
GUI, or `POST /api/metadata/inspect` and `POST /api/metadata/clean`. Inspect
and strip metadata:

- PNG: eXIf, XMP chunks
- JPEG: APP1/APP11 segments
- **WebP: EXIF / XMP metadata chunks from the RIFF container**
- **AVIF / HEIC: ISOBMFF metadata boxes, EXIF / XMP**
- SVG: `<metadata>` elements
- PDF: XMP metadata streams
- DOCX/ODT: custom parts

Stdlib-only (zipfile, xml.etree, binary chunk parsers) — no dependency
weight.

---

## 11. SynthID (pixel scoring)

SynthID's model is not redistributable here (220 MB, non-commercial
research license). The toolkit ships an adapter + bootstrap that builds it
from source when you choose to:

```bash
scripts/setup_synthid.sh --verify
```

`--verify` runs a real scoring pass on a generated test image after setup —
proof of "it actually works", not "it should work". Then:

Use the Image Score action in the TUI (`ai-wm tui`), the Desktop GUI, or
`POST /api/metadata/synthid-score`.

Without the checkpoint, the action honestly reports `available: false`.
The adapter never pretends.

---

## 12. Rewrite engine

Use the Rewrite action in the TUI (`ai-wm tui`), the Desktop GUI, or
`POST /api/rewrite/run`. The rewrite engine provides:

- **structural** — rule-based sentence rotation, first/last sentences
  anchored. Deterministic, no LLM.
- **backtranslate** — two LLM calls (DE→EN→DE) using the local LLM backend.
  Without a backend it degrades honestly to a structural shuffle and says so
  in the change log.

Local LLM backend (Ollama, OpenAI-compatible):

```bash
export LOCAL_LLM_ENABLED=1
export LOCAL_LLM_BASE_URL=http://127.0.0.1:11434/v1
export LOCAL_LLM_MODEL=eurollm-9b
```

**Any local model, not just EuroLLM** — the studio manages the Ollama
backend directly:

```bash
ai-wm llm list                  # all models the local Ollama knows
ai-wm llm install llama3.2:3b   # pull via the Ollama API + select
ai-wm llm use qwen-coder        # switch to an installed model
ai-wm llm status                # current backend config
```

`install` streams pull progress, verifies the model landed and points the
config (and `LOCAL_LLM_MODEL`) at it. Same action in the TUI: menu entry 18,
model name in the Path field.

---

## 13. Findings report & directory watcher

Use the Report action in the TUI (`ai-wm tui`), the Desktop GUI, or
`POST /api/forensics/finding` to produce a structured forensic finding
evidence classes A-D, priority 0-5, with optional signing.

Use the Watch action in the TUI or `POST /api/metadata/inspect` per file
to poll a directory and emit metadata + provenance findings. Built for
newsrooms, editors, incident response.

---

## 14. Benchmarks

Three reproducible scripts in `benchmarks/` (deterministic by default, no
LLM needed):

| Script | What it measures |
|---|---|
| `attack_matrix.py` | Z-score drop per attack: structural, dilute (3 intensities), unicode spam, word shuffle |
| `attack_matrix_v2.py` | Blackbox v2: N real EuroLLM generations + post-hoc KGW mark (γ=0.25), attack matrix with ΔZ, 100-token window analysis; cached in %TEMP%, reproducible without Ollama via `--skip-generation` |
| `synthid_sweep.py` | Detection curve: gamma × paraphrase-rate grid |
| `kgw_e2e_proof.py` | Full round-trip against a real local model |

Honest attack-matrix finding: style attacks (dilute, unicode spam,
rule-based structural rewrite) do **not** break the greenlist mark; word
permutation does (z drops to ~−1.4). The detection curve shows the mark
survives roughly 45–60% lexical churn depending on γ.

---

## 15. API server

```bash
ai-wm serve --port 8000
```

FastAPI app with 22 route modules: text processing (`/api/detect`, `/api/clean`,
`/api/dilute`, `/api/pipeline`, `/api/rewrite/run`), forensics (`/api/forensics/*`),
metadata (`/api/metadata/*`), documents, PDF, RAG, LLM, routing, prompts,
optimization, multi-agent, graph, community, export, cloud, queue/streams,
plus `/health` and `/ready` probes. Swagger UI at `/docs`.

---

## 16. MCP tools & Hermes skills

The repo bundles MCP tools and 5 Hermes skills
(`hermes/skills/text-watermark-studio-lab/`) with class-level vendor notes
for Claude, Gemini/SynthID and OpenAI — what each vendor's watermarking is
verifiably known to do vs. best-effort claims.

---

## 17. Security model & honest limitations

- **No rule-based detector defeats a vendor's sampling watermark applied at
  logit level by a model you don't control.** What this toolkit gives you is
  the measurement: if the mark is there, it's found, with a defensible
  Z-score.
- **Pixel-watermark removal is not a goal.** Attempts to remove visible or
  invisible image watermarks are out of scope by design.
- **"Pangram-safe" means:** no known markers/tropes/stego patterns remain.
  It is not a guarantee against unknown schemes.
- Everything runs locally; no telemetry. Verify: the code is MIT and short
  enough to read.

---

## 18. Troubleshooting

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: tiktoken` | `pip install text-watermark-studio[bpe]` |
| SynthID scoring unavailable | Checkpoint not set up — run `scripts/setup_synthid.sh --verify` |
| Rewrite gives structural result | LLM backend not configured — set `LOCAL_LLM_*` env vars (§12) |
| Embed reports missing secret | Key ID has no secret in `data/key_registry.json` |
| Metadata reports `unsupported` format | File type not in the metadata layer's supported set — expected, honest signal |

---

## 19. Development & testing

```bash
pip install -e ".[dev,bpe]"
pytest tests/          # deterministic, no network
python benchmarks/attack_matrix.py
```

CI runs on Windows and Linux. Tests use `tmp_path` isolation — no test
writes into tracked `data/` files.

---

## 20. Local corpus similarity

Use the Corpus Similarity action in the TUI (`ai-wm tui`), the Desktop GUI,
or `POST /api/forensics/similarity`:

MinHash fingerprint comparison of a text against **your own** document
corpus. Deterministic, offline, with fundstelle quotes as evidence.
Exit code `1` when findings exceed the threshold, `0` otherwise.

**Honest boundary (by design):** similarity measures literal overlap
(5-gram MinHash signatures), not paraphrased meaning. A heavily rewritten
copy scores low — the report says so. No web crawl, no hidden corpus, no
"plagiarism proof": similarity to *these* sources, nothing more. Binary or
unreadable corpus files are listed as skipped, not treated as errors.

---

License: MIT · Repository: <https://github.com/mrmixx-max/text-watermark-studio>
PyPI: <https://pypi.org/project/text-watermark-studio>
