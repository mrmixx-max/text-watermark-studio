"""Shared fixtures for E2E integration tests."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# Path to the project root (tests/e2e/ -> project root)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

SAMPLE_TEXT = """The rapid advancement of artificial intelligence has brought significant
changes to many industries. Machine learning models can now process vast amounts
of data and find patterns that would be impossible for humans to detect. This
technology continues to evolve at a fast pace, creating new opportunities and
challenges for society. Researchers and developers work hard to improve these
systems and make them more reliable and safe for everyone."""

SAMPLE_TEXT_DE = """Die rasante Entwicklung der kuenstlichen Intelligenz hat zu wichtigen
Aenderungen in vielen Branchen gefuehrt. Maschinelle Lernmodelle koennen heute
grosse Datenmengen verarbeiten und Muster finden, die für Menschen unmoechlich
waeren zu erkennen. Diese Technologie entwickelt sich weiterhin in einem schnellen
Tempo und schafft neue Moeglichkeiten und Herausforderungen fuer die Gesellschaft."""

SAMPLE_MARKDOWN = """# AI Watermarking Test Document

This is a **test document** for the watermarking pipeline.

## Section 1: Overview

The system uses statistical methods to embed and detect watermarks.

- Point one: embedding modifies token distributions
- Point two: detection uses greenlist analysis
- Point three: cleaning removes unicode steganography

## Section 2: Code

```python
def hello():
    print("world")
```

## Section 3: Conclusion

Furthermore, this system is designed for research purposes."""

SAMPLE_HTML = """<!DOCTYPE html>
<html>
<head><title>Test Document</title></head>
<body>
<h1>AI Watermarking Test</h1>
<p>This is a <strong>test</strong> HTML document.</p>
<p>The system detects and removes hidden unicode markers.</p>
<p>Furthermore, it provides statistical watermark analysis.</p>
</body>
</html>"""


@pytest.fixture
def sample_text():
    return SAMPLE_TEXT


@pytest.fixture
def sample_text_de():
    return SAMPLE_TEXT_DE


@pytest.fixture
def sample_markdown():
    return SAMPLE_MARKDOWN


@pytest.fixture
def sample_html():
    return SAMPLE_HTML


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def tmp_key_registry(tmp_dir):
    """Create a temporary key registry with a known KGW key."""
    reg = tmp_dir / "key_registry.json"
    data = {
        "keys": [
            {
                "key_id": "e2e-test-key",
                "family": "kgw",
                "status": "active",
                "owner": "e2e-test",
                "trigger_phrase": "",
                "notes": "E2E test key",
                "secret": "e2e-test-secret-key-2026",
                "gamma": 0.25,
                "is_demo": True,
            }
        ]
    }
    reg.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return reg


@pytest.fixture
def cli_env(tmp_key_registry):
    """Environment for CLI subprocess with custom key registry."""
    env = os.environ.copy()
    env["AI_WM_KEY_REGISTRY"] = str(tmp_key_registry)
    return env


def run_cli(args: list[str], input_text: str | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    """Run ai-wm CLI as a subprocess and return the result."""
    cmd = [sys.executable, "-m", "ai_watermark_toolkit.cli", *args]
    return subprocess.run(
        cmd,
        input=input_text,
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        env=env,
    )
