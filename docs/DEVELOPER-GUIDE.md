# Text Watermark Studio — Developer Guide

Version 2.0.0 · MIT · 100% local, zero telemetry

This guide covers the architecture, how to extend the toolkit, and how to run the test suite.

---

## Architecture

```
text-watermark-studio/
├── src/ai_watermark_toolkit/     # Main package
│   ├── api/                       # FastAPI server
│   │   ├── fastapi_app.py         # App factory + middleware
│   │   ├── middleware/            # Auth, rate limit, request ID, Prometheus
│   │   └── routes/               # 22 route modules (one per domain)
│   ├── core/                      # Config + logging
│   ├── forensics/                 # KGW detector, e-process, delta-z, finding
│   ├── generation/                # KGW sampler (experimental)
│   ├── transform/                 # Clean, dilute, rewrite strategies
│   ├── metadata/                  # File provenance (HMAC), SynthID adapter
│   ├── ui/                        # TUI (textual) + Desktop (PySide6)
│   ├── lab/                       # Watermark family plugins
│   ├── plugins/                   # Plugin registry + base class
│   ├── services/                  # Text, job services
│   ├── workers/                   # Background workers
│   ├── queue/                     # Redis queue adapter
│   ├── streams/                   # Redis Streams adapter
│   ├── observability/             # Metrics
│   ├── cli.py                     # CLI entry point (argparse)
│   ├── batch.py                  # Batch processing
│   ├── pipeline.py               # Detection pipeline
│   └── report.py                 # JSON report writer
├── hermes/skills/                 # Hermes skill bundles
├── mcp/tools.json                 # MCP tool manifest (65+ tools)
├── tests/                         # pytest test suite
├── benchmarks/                    # Reproducible benchmarks
├── docs/                          # Documentation
└── scripts/                       # Setup + utility scripts
```

### Layers

1. **Core** (`core/`) — config (pydantic settings), logging setup
2. **Forensics** (`forensics/`) — KGW detector, e-process, delta-z, finding report
3. **Transform** (`transform/`) — clean, dilute, rewrite strategies
4. **Metadata** (`metadata/`) — file provenance, SynthID adapter
5. **API** (`api/`) — FastAPI server with 22 route modules
6. **UI** (`ui/`) — TUI (textual), Desktop (PySide6)
7. **Lab** (`lab/`) — watermark family plugins

---

## Project structure

### Route modules

Each domain has its own route module under `api/routes/`:

| Module | Prefix | Description |
|---|---|---|
| `text.py` | `/api/*` | Detect, clean, dilute |
| `forensics.py` | `/api/forensics/*` | Keys, detect, embed, delta-z, finding |
| `metadata.py` | `/api/metadata/*` | File provenance, SynthID |
| `documents.py` | `/api/documents/*` | Load, export |
| `pdf.py` | `/api/pdf/*` | Extract window, strategy |
| `rag.py` | `/api/rag/*` | Chunking strategies |
| `llm.py` | `/api/llm/*` | Local backend status/configure |
| `routing.py` | `/api/routing/*` | Model fallback routing |
| `prompts.py` | `/api/prompts/*` | Template registry |
| `optimization.py` | `/api/optimization/*` | Prompt optimizer |
| `multi_agent.py` | `/api/multi-agent/*` | Feedback loop |
| `graph.py` | `/api/graph/*` | Knowledge graph |
| `community.py` | `/api/community/*` | Graph communities |
| `rewrite.py` | `/api/rewrite/*` | Rewrite engine |
| `exporting.py` | `/api/export/*` | Multi-format export |
| `cloud.py` | `/api/cloud/*` | Direct upload |
| `lab.py` | `/api/lab/*` | Family demos |
| `queue.py` | `/api/queue/*` | Redis queue |
| `streams.py` | `/api/streams/*` | Redis Streams |
| `jobs.py` | `/api/jobs/*` | Batch jobs |
| `studio.py` | `/api/studio/*` | Diff, export zip |
| `ops.py` | `/api/ops/*` | Status, metrics, DLQ |

### Lab families

Watermark families are plugins under `lab/families/`:

- `unicode_zero_width.py` — bidi + zero-width
- `lexical_choice.py` — lexical patterns
- `syntactic_pattern.py` — syntactic structures
- `format_layout.py` — format/layout
- `sampling_bias.py` — post-hoc KGW + generation-time sampler
- `semantic_structure.py` — semantic/structure
- `localized_provenance.py` — provenance
- `training_time.py` — training-time ownership

---

## Setup

```bash
python -m venv .venv
# Windows: .\.venv\Scripts\activate | macOS/Linux: source .venv/bin/activate
pip install -e ".[dev,bpe]"
```

### Extras

| Extra | Installs | Use |
|---|---|---|
| `[dev]` | pytest, ruff, bandit, mypy | Development |
| `[bpe]` | tiktoken | BPE token-level detection |
| `[tui]` | textual | Terminal UI |

---

## Testing

```bash
pytest tests/          # full suite (~540 tests, deterministic, no network)
pytest -q              # quiet mode
pytest -x              # stop on first failure
pytest -k "kgw"        # filter by keyword
```

### Test organization

| File pattern | Coverage |
|---|---|
| `test_v11*` | KGW detector, multi-key, BPE |
| `test_v12*` | File provenance (HMAC) |
| `test_v13*` | CLI, batch, TUI |
| `test_v14*` | Signed reports, ML-DSA |
| `test_v15*` | E-process, delta-z, finding |
| `test_v16*` | Metadata, SynthID |
| `test_v17*` | API routes |
| `test_v18*` | Graph, community, optimization |

### Test principles

- **Deterministic by default** — no network, no LLM needed for core tests
- **`tmp_path` isolation** — no test writes into tracked `data/` files
- **CI runs on Windows and Linux**

---

## Adding a watermark family

1. Create a new module under `src/ai_watermark_toolkit/lab/families/`:

```python
from ..base import WatermarkFamily

class MyFamily(WatermarkFamily):
    name = "my_family"
    description = "What this family detects/embeds"

    def detect(self, text: str) -> dict:
        """Return findings dict with score, matches, verdict."""
        ...

    def embed(self, text: str, key: str) -> str:
        """Return text with the mark embedded."""
        ...
```

2. Register it in `lab/families/__init__.py`:

```python
from .my_family import MyFamily
```

3. Add API routes in a new `api/routes/my_family.py` if needed.

4. Add tests in `tests/test_v1XX_my_family.py`.

5. Update `mcp/tools.json` if exposing new MCP tools.

---

## Adding an API endpoint

1. Create or edit a route module under `api/routes/`:

```python
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix='/api/my_feature', tags=['my_feature'])

class MyRequest(BaseModel):
    text: str

@router.post('/run')
async def run_feature(req: MyRequest):
    return {"result": process(req.text)}
```

2. Register in `api/fastapi_app.py`:

```python
from .routes.my_feature import router as my_feature_router
app.include_router(my_feature_router)
```

3. Add tests under `tests/`.

---

## Adding an MCP tool

Edit `mcp/tools.json` and add an entry:

```json
{
  "name": "my_tool",
  "method": "POST",
  "path": "/api/my_feature/run",
  "description": "What the tool does",
  "body_schema": {
    "text": "string"
  }
}
```

Tools map 1:1 to API endpoints. The `optional: true` flag marks tools that require runtime subsystems.

---

## Code style

- **Python 3.10+** — use `X | Y` union syntax, `match` where appropriate
- **stdlib-first** — minimize dependencies; optional extras for heavy features
- **Type hints** — all public functions annotated
- **Docstrings** — Google-style for public APIs
- **Honest boundaries** — every detector documents what it cannot do

---

## Key patterns

### Key resolution

The `--key` argument accepts either a `key_id` (resolved from `data/key_registry.json`) or a raw secret. Raw secrets are masked in output (`secret:<sha256-prefix>`):

```python
from ai_watermark_toolkit.forensics.key_registry import KeyRegistry, mask_secret_key_id
```

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Clean / success (no findings) |
| 1 | Findings detected / processing result |
| 2 | Usage/input error |

### Batch processing

```python
from ai_watermark_toolkit.batch import process_batch

report = process_batch("./input", "./output", mode="embed",
                        key_id="my-key", verify=True)
# report = {count, items: [{input_path, output_path, mode, changed, verified, z_score}]}
```

### Signed reports

```python
from ai_watermark_toolkit.forensics.signed_report import sign_report, verify_report

signed = sign_report({"finding": "watermark_detected"}, secret="my-secret")
valid = verify_report(signed, secret="my-secret")
```

---

## Benchmarks

Reproducible scripts in `benchmarks/`:

| Script | What it measures |
|---|---|
| `attack_matrix.py` | Z-score drop per attack |
| `attack_matrix_v2.py` | Blackbox v2: N real generations + post-hoc mark |
| `synthid_sweep.py` | Detection curve (gamma × paraphrase-rate) |
| `kgw_e2e_proof.py` | Full round-trip against a real local model |
| `tui_burnin.py` | Drives all 25 TUI actions headlessly |

```bash
python benchmarks/attack_matrix.py
python benchmarks/kgw_e2e_proof.py
```

---

## Debugging

```bash
# Verbose logging
ai-wm --quiet detect file.txt    # machine-readable only
ai-wm detect file.txt --json    # structured output

# API debug mode
AI_WM_ENV=development ai-wm serve --port 8080
```

---

## Release checklist

1. Update version in `pyproject.toml`
2. Update `CHANGELOG.md`
3. Run full test suite: `pytest -q`
4. Run benchmarks: `python benchmarks/attack_matrix.py`
5. Run TUI burn-in: `python benchmarks/tui_burnin.py`
6. Run security scan: `bandit -r src/`
7. Build: `python -m build`
8. Tag: `git tag vX.Y.Z`

---

## Contributing

See [CONTRIBUTING.md](../../CONTRIBUTING.md) and [CODE_OF_CONDUCT.md](../../CODE_OF_CONDUCT.md).

---

## License

MIT · Repository: <https://github.com/mrmixx-max/text-watermark-studio>
