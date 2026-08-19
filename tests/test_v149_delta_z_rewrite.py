"""ΔZ rewrite transform (2026-08-16) — paraphrase in the forensics core.

Contract under test:
- TRANSFORM_METHODS now includes 'rewrite': the paraphrase path via
  RewriteService is a first-class ΔZ transform, no longer "open/documented
  as not part of the product path".
- delta_z_transform(method='rewrite') runs the rule-based structural path by
  default (no LLM call, CI-safe). The transform meta records mode, backend
  ('rule-based'), and similarity ratio so the measurement is reproducible.
- Honest measurement: rule-based structural editing changes the token surface
  slightly and weakens the mark a little (delta_z > 0 possible) but does NOT
  provably remove it (removed:false) — no fake removal receipt from light
  editing. The LLM path (--use-llm) is NOT exercised in CI (needs a local
  Ollama backend); it is covered by the existing rewrite-service tests
  (test_v118/test_v119) and manual smoke runs.
- CLI: `ai-wm delta-z --transform rewrite --key <secret> <file>` exits 0 with
  JSON output carrying method=rewrite and transform_meta.

No data/ writes: raw secrets + tmp registries only (same as test_v145).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ai_watermark_toolkit.forensics.delta_z import (
    TRANSFORM_METHODS,
    delta_z_transform,
)
from ai_watermark_toolkit.forensics.frequent_vocab import FREQUENT_VOCAB
from ai_watermark_toolkit.forensics.kgw import mark_greenlist

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"

KEY = "demo-kgw-secret-0001"
GAMMA = 0.25

TEXT = (
    "Local AI models are crucial for maintaining user privacy and ensuring "
    "secure interactions with data processing. This reduces the amount of "
    "personal information shared with third parties. On-device processing "
    "keeps sensitive details under your control. The result is a lower risk "
    "of breaches and stronger protection. People gain more confidence when "
    "their data stays local and private systems keep everything on device "
    "without sending anything to remote servers or external infrastructure."
)

MARK_SEED = 0  # mark_greenlist seed -> z_before 12.1592 (stable, same as test_v145)


@pytest.fixture(scope="module")
def marked():
    emb = mark_greenlist(TEXT, KEY, vocab=FREQUENT_VOCAB, seed=MARK_SEED)
    return emb["text"]


def run_cli(args, stdin=None, cwd=None):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC)
    base = [sys.executable, "-m", "ai_watermark_toolkit.cli"]
    return subprocess.run(base + args, capture_output=True, text=True, input=stdin, env=env, cwd=cwd or REPO)


class TestRewriteInCore:
    def test_rewrite_is_a_transform_method(self):
        assert "rewrite" in TRANSFORM_METHODS
        # order is documented in the module header: stdlib transforms first,
        # then the paraphrase path
        assert TRANSFORM_METHODS[-1] == "rewrite"

    def test_structural_rewrite_rule_based_no_llm(self, marked):
        """Default rewrite transform is rule-based structural — no Ollama call."""
        r = delta_z_transform(marked, KEY, method="rewrite", rewrite_mode="structural", use_llm=False)
        assert r["method"] == "rewrite"
        meta = r["transform_meta"]
        assert meta["mode"] == "structural"
        assert meta["backend"] == "rule-based"
        assert meta["similarity_ratio"] is not None
        assert 0.0 < meta["similarity_ratio"] < 1.0
        # the rewrite changed the text
        assert r["transformed_text"] != marked

    def test_structural_rewrite_honest_no_false_removal(self, marked):
        """Light rule-based editing weakens but does not provably remove."""
        r = delta_z_transform(marked, KEY, method="rewrite", rewrite_mode="structural", use_llm=False)
        assert r["verdict_before"] == "watermark_detected"
        assert r["z_before"] == pytest.approx(12.1592, abs=1e-3)
        # honest boundary: no removal receipt from light paraphrase
        assert r["removed"] is False, r
        # delta_z is tiny (mark mostly survives), NOT the shuffle collapse
        assert r["delta_z"] < 2.0, r

    def test_protected_tokens_survive(self):
        """Numbers/URLs/quotes are protected across the rewrite (preserve=True).

        The rewrite transform calls RewriteService with preserve=True; the
        protection layer must survive the ΔZ path. Direct service test because
        mark_greenlist GENERATES new text (the tokens below would not appear
        in the generated output by construction).
        """
        from ai_watermark_toolkit.rewrite.service import RewriteService

        svc = RewriteService()
        res = svc.rewrite(
            "The price is 42.99 euros per unit. Visit https://example.com/docs "
            'for details. "Stay focused" was the motto. The year is 2026 '
            "and the policy number is 7341.",
            mode="structural",
            preserve=True,
            use_llm=False,
        )
        out = res["rewritten"]
        assert "42.99" in out
        assert "https://example.com/docs" in out
        assert "7341" in out
        assert "__PROTECTED_" not in out  # tokens restored, no leaks

    def test_unknown_mode_rejected(self, marked):
        with pytest.raises(ValueError):
            delta_z_transform(marked, KEY, method="rewrite", rewrite_mode="nonsense-mode", use_llm=False)


class TestCliRewriteTransform:
    def test_cli_transform_rewrite_exit_0(self, tmp_path, marked):
        src = tmp_path / "marked.txt"
        src.write_text(marked, encoding="utf-8")
        p = run_cli(["delta-z", str(src), "--transform", "rewrite", "--key", KEY])
        assert p.returncode == 0, p.stderr
        r = json.loads(p.stdout)
        assert r["method"] == "rewrite"
        assert r["transform_meta"]["backend"] == "rule-based"
        assert r["removed"] is False

    def test_cli_transform_rewrite_mode_flag(self, tmp_path, marked):
        src = tmp_path / "marked.txt"
        src.write_text(marked, encoding="utf-8")
        p = run_cli(["delta-z", str(src), "--transform", "rewrite", "--rewrite-mode", "plain", "--key", KEY])
        assert p.returncode == 0, p.stderr
        r = json.loads(p.stdout)
        assert r["transform_meta"]["mode"] == "plain"

    def test_cli_transform_rewrite_json_output_file(self, tmp_path, marked):
        src = tmp_path / "marked.txt"
        out = tmp_path / "result.json"
        src.write_text(marked, encoding="utf-8")
        p = run_cli(["delta-z", str(src), "--transform", "rewrite", "--key", KEY, "-o", str(out)])
        assert p.returncode == 0, p.stderr
        assert out.exists()
        r = json.loads(out.read_text(encoding="utf-8"))
        assert r["method"] == "rewrite"
        assert "transformed_text" in r
