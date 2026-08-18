# Contributing to Text Watermark Studio

First off — thank you for considering contributing. This document will get you set up and explain how to work with us effectively.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [How to Contribute](#how-to-contribute)
- [What to Work On](#what-to-work-on)
- [Style Guide](#style-guide)
- [Testing](#testing)
- [Pull Request Process](#pull-request-process)
- [Release Process](#release-process)
- [Getting Help](#getting-help)

---

## Code of Conduct

Be respectful, constructive, and honest. This project serves researchers, journalists, and legal professionals — accuracy and integrity are non-negotiable.

---

## Development Setup

### Prerequisites

- Python 3.10+ (3.11 recommended)
- Git
- (Optional) Ollama for local LLM integration
- (Optional) Docker for containerized development

### Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/mrmixx-max/text-watermark-studio.git
cd text-watermark-studio

# 2. Create a virtual environment
python -m venv .venv

# 3. Activate it
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 4. Install in editable mode with dev dependencies
pip install -e ".[dev,bpe]"

# 5. Verify everything works
pytest -q
ai-wm --help
```

### Optional Extras

```bash
# Terminal UI support
pip install -e ".[tui]"

# Quantum-safe signatures (ML-DSA FIPS 204)
pip install cryptography>=50

# All optional dependencies at once
pip install -e ".[dev,bpe,tui]"
```

---

## Project Structure

```
text-watermark-studio/
├── src/ai_watermark_toolkit/     # Main package
│   ├── api/                       # FastAPI server (22 route modules)
│   ├── core/                      # Config + logging
│   ├── forensics/                 # KGW detector, e-process, delta-z, finding
│   ├── generation/                # KGW sampler (experimental)
│   ├── transform/                 # Clean, dilute, rewrite strategies
│   ├── metadata/                  # File provenance (HMAC), SynthID adapter
│   ├── ui/                        # TUI (textual) + Desktop (PySide6)
│   ├── lab/                       # Watermark family plugins
│   ├── plugins/                   # Plugin registry + base class
│   ├── cli.py                     # CLI entry point
│   └── ...
├── tests/                         # pytest test suite
├── docs/                          # Documentation
├── hermes/skills/                 # Hermes skill bundles
├── mcp/tools.json                 # MCP tool manifest (65+ tools)
└── scripts/                       # Setup + utility scripts
```

### Key Modules for Contributors

| Module | What it does | Good for |
|---|---|---|
| `forensics/kgw.py` | KGW statistical detector | Detection algorithm improvements |
| `forensics/e_process.py` | E-process anytime-valid testing | Statistical method work |
| `transform/` | Clean, dilute, rewrite strategies | New text transforms |
| `lab/` | Watermark family plugins | Adding new watermark families |
| `api/routes/` | FastAPI route modules | New API endpoints |
| `ui/` | TUI + Desktop UI | UI/UX improvements |

---

## How to Contribute

### 1. Find an Issue

- Check [GitHub Issues](https://github.com/mrmixx-max/text-watermark-studio/issues) for `good first issue` or `help wanted` labels.
- Or propose your own improvement by opening an issue first.

### 2. Create a Branch

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/issue-description
```

Branch naming:
- `feature/` — new features
- `fix/` — bug fixes
- `docs/` — documentation improvements
- `refactor/` — code restructuring

### 3. Make Your Changes

- Keep the stdlib-first approach where practical.
- Prefer small, testable modules.
- Document capability limits honestly (this is a forensics tool — overclaiming is worse than underclaiming).

### 4. Add or Update Tests

Every new feature or bugfix needs tests. Place them in `tests/` with the `test_*.py` naming convention.

### 5. Run the Full Check

```bash
# Run tests
pytest -q

# Run with coverage
pytest --cov=src --cov-report=term-missing

# Lint
ruff check src tests

# Security scan
bandit -r src
```

### 6. Open a Pull Request

Push your branch and open a PR with:
- A clear summary of what changed and why
- Reference to any related issues
- Test results (CI will run automatically)

---

## What to Work On

### High-Priority Areas

1. **New watermark families** — Add implementations under `lab/` for new watermark schemes
2. **Detection accuracy** — Improve KGW, e-process, or phrasing detection
3. **Language support** — Extend non-English detection (currently EN/DE focus)
4. **Performance** — Speed up batch processing and large-file handling
5. **Documentation** — User guides, API docs, tutorials
6. **Test coverage** — Bring coverage above 80%

### Plugin Architecture

The lab uses a plugin registry (`plugins/`). To add a new watermark family:

```python
# 1. Create a new plugin class in lab/
from ai_watermark_toolkit.plugins import WatermarkPlugin

class MyWatermarkPlugin(WatermarkPlugin):
    name = "my-watermark"
    family = "statistical"

    def embed(self, text: str, key: str) -> str:
        # Your embedding logic
        ...

    def detect(self, text: str, key: str) -> dict:
        # Your detection logic
        ...

# 2. Register it in plugins/registry.py
# 3. Add tests in tests/
```

---

## Style Guide

- **Language:** Python 3.10+
- **Linter:** ruff (configuration in `pyproject.toml`)
- **Formatter:** ruff format (or black-compatible)
- **Type hints:** Use them everywhere. Run `mypy src` if you have it.
- **Line length:** 120 characters
- **Naming:** `snake_case` for functions/variables, `PascalCase` for classes
- **Imports:** stdlib → third-party → local (enforced by ruff `I` rules)

### Documentation Style

- Docstrings for all public functions and classes
- Honest about limitations — if a detector is experimental, say so
- Include examples in docstrings where helpful

---

## Testing

```bash
# Run all tests
pytest -q

# Run a specific test file
pytest tests/test_kgw.py -v

# Run with coverage
pytest --cov=src --cov-report=html

# Run tests matching a keyword
pytest -k "delta_z"

# Skip slow tests
pytest -m "not slow"
```

### Writing Good Tests

```python
def test_kgw_detect_watermarked_text():
    """KGW detector should return Z > 4 for text embedded with matching key."""
    from ai_watermark_toolkit.forensics.kgw import embed_kgw, detect_kgw

    original = "The quick brown fox jumps over the lazy dog. " * 20
    key = "test-key"

    watermarked = embed_kgw(original, key=key)
    result = detect_kgw(watermarked, key=key)

    assert result["z_score"] > 4.0
    assert result["green_rate"] > 0.5
```

---

## Pull Request Process

1. **Before submitting:** Ensure `pytest -q` passes, linting is clean, and your branch is up to date with `main`.
2. **Template:** PRs should include:
   - Description of the change
   - Motivation / problem solved
   - Testing approach
   - Screenshots (if UI-related)
3. **Review:** At least one maintainer review is required.
4. **CI:** All GitHub Actions checks must pass (tests, lint, security).
5. **Merge:** Squash merge to `main` with a clean commit message.

---

## Release Process

Releases are handled by maintainers:

1. Version is bumped in `pyproject.toml`
2. `CHANGELOG.md` is updated
3. Git tag `vX.Y.Z` is created
4. GitHub Actions builds and publishes to PyPI
5. GitHub Release is created with release notes

---

## Getting Help

- **Issues:** [GitHub Issues](https://github.com/mrmixx-max/text-watermark-studio/issues)
- **Documentation:** `docs/USER-GUIDE.md`, `docs/DEVELOPER-GUIDE.md`, `docs/API.md`
- **Security:** Report vulnerabilities privately to the maintainers

---

*Thanks for helping make AI text forensics more honest, more accessible, and more verifiable.*
