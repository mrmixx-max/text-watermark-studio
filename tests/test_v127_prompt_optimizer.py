"""Tests for the real evaluator-loop prompt optimizer (2026-08-13).

Contract: locked evals, one changed variable per candidate, deterministic
scoring, hard guardrail, promotion only on improvement, immutable versioning
with rollback. Everything writes to tmp_path — never into tracked data/.
"""

import json

import pytest

from ai_watermark_toolkit.optimization.service import PromptOptimizationService
from ai_watermark_toolkit.prompts.service import PromptRegistryService

SYSTEM = (
    "Rewrite the given text so it no longer reads like AI output. "
    "Keep all facts, numbers and names exactly as they are."
)


@pytest.fixture()
def optimizer(tmp_path):
    # tmp registry (empty template list)
    reg_path = tmp_path / "registry.json"
    reg_path.write_text(json.dumps({"templates": []}), encoding="utf-8")
    registry = PromptRegistryService(path=reg_path)
    # tmp eval set with two deterministic cases
    eval_path = tmp_path / "evals.json"
    eval_path.write_text(
        json.dumps(
            {
                "locked": True,
                "evals": [
                    {
                        "id": "e1",
                        "text": "The quarterly report shows revenue growth of 12.4 percent in 2026.",
                        "protected_terms": ["12.4", "2026"],
                    },
                    {
                        "id": "e2",
                        "text": "Our comprehensive suite empowers teams to leverage robust security standards.",
                        "protected_terms": ["security"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return PromptOptimizationService(registry=registry, eval_path=eval_path)


class TestEvalSet:
    def test_locked(self, optimizer):
        assert len(optimizer.eval_cases()) == 2

    def test_unlocked_rejected(self, optimizer, tmp_path):
        p = tmp_path / "unlocked.json"
        p.write_text(json.dumps({"locked": False, "evals": []}), encoding="utf-8")
        svc = PromptOptimizationService(registry=optimizer.registry, eval_path=p)
        with pytest.raises(ValueError):
            svc.eval_cases()


class TestCandidates:
    def test_base_plus_one_variable_each(self, optimizer):
        cands = optimizer.variants(SYSTEM)
        assert cands[0]["variant"] == "baseline"
        assert cands[0]["changed_variable"] is None
        for c in cands[1:]:
            assert c["changed_variable"] is not None
            # every candidate changes exactly one variable -> unique names
        changed = [c["changed_variable"] for c in cands[1:]]
        assert len(set(changed)) == len(changed)

    def test_baseline_hash_stable(self, optimizer):
        assert optimizer.baseline_hash(SYSTEM) == optimizer.baseline_hash(SYSTEM)
        assert optimizer.baseline_hash(SYSTEM + " ") != optimizer.baseline_hash(SYSTEM)


class TestScoring:
    def test_deterministic_scores(self, optimizer):
        r1 = optimizer.optimize(SYSTEM)
        r2 = optimizer.optimize(SYSTEM)
        assert r1["baseline_score"] == r2["baseline_score"]
        assert [x["avg_score"] for x in r1["ranking"]] == [x["avg_score"] for x in r2["ranking"]]

    def test_guardrail_blocks_term_dropping_candidate(self):
        """A prompt that explicitly tells the rewrite to drop numbers must
        never pass the guardrail on the 12.4/2026 case."""

        from ai_watermark_toolkit.optimization.metrics import composite

        evil = composite(
            "Revenue growth of 12.4 percent in 2026.",
            "Revenue growth was strong last year.",
            ["12.4", "2026"],
        )
        assert evil["guardrail_passed"] is False
        assert evil["score"] == 0.0


class TestPromote:
    def test_promote_writes_new_version(self, optimizer):
        # seed the registry with a base template
        optimizer.registry.create_version(
            {
                "id": "rewrite-default",
                "version": "1.0.0",
                "channel": "stable",
                "system_prompt": "Rewrite plainly.",
                "user_template": "{{text}}",
                "provider": None,
                "model": None,
                "parameters": {},
            }
        )
        record = optimizer.promote(SYSTEM, "rewrite-default")
        assert record["version"] != "1.0.0"
        assert record["optimization"]["baseline_hash"] == optimizer.baseline_hash(SYSTEM)
        assert record["optimization"]["winner_score"] > record["optimization"]["baseline_score"]

    def test_promote_rejects_no_improvement(self, optimizer):
        optimizer.registry.create_version(
            {
                "id": "rewrite-default",
                "version": "1.0.0",
                "channel": "stable",
                "system_prompt": "x",
                "user_template": "{{text}}",
                "provider": None,
                "model": None,
                "parameters": {},
            }
        )
        # baseline = identical to candidates' behaviour when system is empty-ish:
        # no candidate beats it -> no_improvement
        with pytest.raises(ValueError, match="no_improvement|guardrail"):
            optimizer.promote("Rewrite the text.", "rewrite-default", candidate_variant="baseline")

    def test_history_lists_all_versions(self, optimizer):
        optimizer.registry.create_version(
            {
                "id": "t",
                "version": "1.0.0",
                "channel": "stable",
                "system_prompt": "a",
                "user_template": "{{text}}",
                "provider": None,
                "model": None,
                "parameters": {},
            }
        )
        optimizer.promote(SYSTEM, "t")
        assert len(optimizer.history("t")) >= 2


class TestRollback:
    def test_rollback_restores_as_new_stable(self, optimizer):
        optimizer.registry.create_version(
            {
                "id": "t",
                "version": "1.0.0",
                "channel": "stable",
                "system_prompt": "original prompt",
                "user_template": "{{text}}",
                "provider": None,
                "model": None,
                "parameters": {},
            }
        )
        optimizer.promote(SYSTEM, "t")  # now 1.0.1 is stable
        restored = optimizer.rollback("t", "1.0.0")
        assert restored["channel"] == "stable"
        assert restored["version"] not in ("1.0.0",)
        assert restored["system_prompt"] == "original prompt"
        current = optimizer.registry.get_template("t")
        assert current["version"] == restored["version"]
