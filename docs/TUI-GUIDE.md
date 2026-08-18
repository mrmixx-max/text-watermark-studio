# Text Watermark Studio — TUI Guide

Version 2.0.0 · 25-action menu-driven terminal UI

The TUI (Text User Interface) gives you the full power of the toolkit through a keyboard-driven menu. No memorizing commands — just navigate and run.

```bash
ai-wm tui
```

Requires: `pip install text-watermark-studio[tui]` (installs `textual`).

---

## Layout

```
┌─────────────────────────────────────────────────────────┐
│  Text Watermark Studio 2.0.0 — by Erik Gieske    12:34  │
├──────────────────┬──────────────────────────────────────┤
│ 1  Detect        │                                      │
│ 2  Clean         │  [Output panel]                      │
│ 3  Dilute        │  Rich text results appear here       │
│ 4  Embed         │                                      │
│ ...              │                                      │
│ 25 Report-keygen │                                      │
│                  │                                      │
│ ↑↓ select       ├──────────────────────────────────────┤
│ Enter run        │  Path: [________________________]    │
│ q quit           │                                      │
├──────────────────┴──────────────────────────────────────┤
│  q:quit  ↑:up  ↓:down  d:detect  c:clean  ...          │
└─────────────────────────────────────────────────────────┘
```

- **Menu** (left): 25 actions, navigable with cursor keys
- **Output** (right): RichLog panel showing results
- **Path** (bottom): Input field for file/directory paths + flags
- **Footer**: Keyboard shortcuts

---

## Navigation

| Key | Action |
|---|---|
| `↑` / `↓` | Move through the menu (works from any focused element) |
| `Enter` | Run the selected action |
| `q` | Quit |
| `d` | Jump to Detect |
| `c` | Jump to Clean |
| `e` | Jump to Embed |
| `p` | Jump to Pipeline |
| `r` | Jump to Report |
| `s` | Jump to System state (splash) |

---

## The Path field

Most actions read a file or directory path from the bottom input field. Type the path and press `Enter` (or select the action from the menu).

**Flag syntax:** Many actions support additional flags typed after the path:

```
article.txt --key my-key --e-value --signature-filter
```

The TUI parses these flags and passes them to the underlying service, matching CLI behavior exactly.

---

## All 25 actions

### 1. Detect invisible + markers
**Path:** `file.txt` (optional flags: `--key <id>`, `--e-value`, `--signature-filter`, `--level word|bpe`, `--context <n>`)

Scans for unicode stego + AI phrasing markers. If KGW keys are registered, runs the real keyed multi-key detection with Z-score. With `--e-value`, adds anytime-valid e-process detection. With `--signature-filter`, enables FPR control for repetitive-token texts.

### 2. Clean unicode layer
**Path:** `file.txt`

Strips invisible characters (bidi controls, zero-width, etc.). Writes cleaned text to output.

### 3. Dilute AI phrasing
**Path:** `file.txt`

Rewrites marker-heavy phrasing. Three intensities available via `--intensity light|standard|aggressive`.

### 4. Embed greenlist mark
**Path:** `file.txt` (flag: `--key <id>`)

Imposes a KGW greenlist mark using a registered key. The output replaces the input text (Z > 4 guaranteed with a registered key carrying a secret).

### 5. Pipeline (detect→clean→dilute→rewrite)
**Path:** `file.txt`

Runs the full chain. Detects, cleans, dilutes, optionally rewrites, and re-detects. Results shown in output panel.

### 6. Findings report (KGW)
**Path:** `file.txt` (flag: `--key <id>`)

Generates an HTML forensics report with Z-score, green rate, p-value, invisible-character table, and recommendation. With `--pdf`, renders to PDF via Edge headless (Windows).

### 7. Rewrite (structural/backtranslate)
**Path:** `file.txt` (flags: `--mode clarity|concise|plain|formal|structural|backtranslate`)

Rewrites text. `structural` is rule-based (deterministic). `backtranslate` needs a local LLM backend.

### 8. File inspect metadata
**Path:** `file.png|pdf|docx|...`

Inspects a file for C2PA/EXIF/XMP metadata. Shows what provenance marks are present.

### 9. File clean metadata
**Path:** `file.png|pdf|docx|...`

Strips AI provenance metadata from a file. Reports what was removed per format.

### 10. File embed provenance
**Path:** `file.png|pdf|docx|...` (flag: `--key <id>`)

Embeds an HMAC-SHA256 provenance mark into the file. Content-bound: tampering breaks the signature.

### 11. File detect provenance
**Path:** `file.png|pdf|docx|...`

Detects and verifies studio provenance marks. Reports `found`/`valid` status.

### 12. Image score (SynthID)
**Path:** `image.png`

Scores an image for SynthID pixel marks. Requires the external checkpoint (see §11 of the user guide). Without it, reports `available: false` honestly.

### 13. Watch directory (--once)
**Path:** `./directory`

Polls a directory once and reports metadata + provenance findings per file as JSON lines.

### 14. Attack matrix (benchmark)

Runs the attack matrix benchmark: structural, dilute (3 intensities), unicode spam, and word shuffle against a marked text. Measures Z-score drop per attack.

### 15. SynthID sweep (benchmark)

Runs the gamma × paraphrase-rate grid producing the detection curve (Z vs. rewording strength).

### 16. System state

Shows the studio banner, registered key count, and local LLM backend status.

### 17. Update studio (check + upgrade)

Checks PyPI for a newer release. If one exists, runs `pip install --upgrade text-watermark-studio`.

### 18. Install local model (Ollama pull)
**Path:** `model-name` (e.g., `llama3.2:3b`)

Pulls a model via the Ollama API, streams progress, verifies it landed, and selects it as the active backend. Any Ollama-compatible model works.

### 19. Prompt optimizer (locked evals)

Runs the prompt optimizer against the locked eval set. Generates candidates, scores them, promotes the winner if it improves over the baseline.

### 20. Corpus similarity (local MinHash)
**Path:** `file.txt` (flag: `--corpus ./archiv`)

Compares a text against your own document corpus using MinHash fingerprinting. Reports literal overlap findings with fundstelle quotes. Honest boundary: literal overlap only, not paraphrased meaning.

### 21. ΔZ check (before — after)
**Path:** `before.txt --after after.txt` (flag: `--key <id>`)

Measures KGW watermark strength before and after. Shows the ΔZ (Z-score drop) and whether the mark was removed.

### 22. Findings report (Evidenzklassen A-D)
**Path:** `file.txt` (flags: `--key <id>`, `--e-value`, `--delta-z <after_file>`)

Produces a KI-Erklärungs-Befund (C5) with evidence classes A-D, priority 0-5, and an honest verdict text. Optional signing.

### 23. Sign findings JSON (report-sign)
**Path:** `finding.json` (flag: `--key <id>`)

Signs a findings payload. HMAC-SHA256 by default (secret from registry). The secret never leaves the machine.

### 24. Verify signed findings JSON
**Path:** `signed.json` (flag: `--key <id>`)

Verifies a signed findings document. Reports `valid`/`invalid` with reason.

### 25. Generate ML-DSA keypair (report-keygen)
**Path:** `output-base-path` (flag: `--algorithm mldsa-44|65|87`)

Generates an ML-DSA keypair (FIPS 204, quantum-safe). Private key written with 0600 permissions on Unix.

---

## Flag reference

| Flag | Description | Used by |
|---|---|---|
| `--key <id>` | Key ID for keyed operations | detect, embed, report, delta-z, finding, report-sign, report-verify |
| `--e-value` | Anytime-valid e-process detection | detect, finding |
| `--signature-filter` | FPR control for repetitive tokens | detect |
| `--level word\|bpe` | Token level for KGW | detect, embed, report |
| `--context <n>` | Greenlist context window | detect, embed, report |
| `--after <file>` | After-file for ΔZ comparison | delta-z |
| `--delta-z <file>` | After-file for finding | finding |
| `--algorithm <name>` | ML-DSA algorithm variant | report-keygen |
| `--intensity <level>` | Dilute intensity | dilute, remove, pipeline |
| `--corpus <path>` | Corpus for similarity | similarity |

---

## Keyboard shortcut summary

| Key | Action |
|---|---|
| `↑` | Menu up |
| `↓` | Menu down |
| `Enter` | Run selected action |
| `d` | Jump to Detect |
| `c` | Jump to Clean |
| `e` | Jump to Embed |
| `p` | Jump to Pipeline |
| `r` | Jump to Report |
| `s` | Jump to System state |
| `q` | Quit |

---

## Burn-in test

The pre-release gate for the UI is `benchmarks/tui_burnin.py`. It drives all 25 actions through a real sample file headlessly and fails loudly on any exception.

```bash
python benchmarks/tui_burnin.py
```

---

## Tips

- **No path needed** for benchmarks, splash, and optimizer — just select and they run.
- **Flag order doesn't matter** — `file.txt --key k --e-value` is the same as `--e-value file.txt --key k`.
- **Output is scrollable** — use mouse wheel or Page Up/Down in the output panel.
- **JSON results** are pretty-printed in the output panel.
- **Errors** show in yellow in the output panel with a clear message.
