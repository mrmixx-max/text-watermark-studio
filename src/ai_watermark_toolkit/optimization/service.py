"""Evaluator-driven prompt optimizer.

The loop follows production guidance, minus the marketing:

  1. locked eval set (never mutated by optimization runs)
  2. candidates that change exactly ONE variable each
  3. deterministic scoring against real rewrite output + metrics
  4. promote ONLY if score improves over a hashed baseline AND the
     protected-term guardrail holds on every eval case
  5. promotion writes an immutable new version into the prompt registry;
     rollback restores any previous version

Deterministic backend: candidates map to rewrite modes/constraints, the
rewrite service applies them, metrics score the result — reproducible and
offline. With LOCAL_LLM_ENABLED, the same loop scores real LLM rewrites.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .metrics import composite

EVAL_PATH = Path(__file__).resolve().parents[3] / 'data' / 'optimization_evals.json'

# one changed variable per candidate (vs. the base prompt)
_VARIABLES: List[Dict[str, Any]] = [
    {"variant": "output_format", "changed_variable": "output format instruction",
     "append": " Return only the rewritten text with no preamble."},
    {"variant": "style_rule", "changed_variable": "style constraint",
     "append": " Use short, concrete sentences. Prefer active voice."},
    {"variant": "constraint_negative", "changed_variable": "negative constraints",
     "append": " Do not add new facts, opinions, or transitions."},
    {"variant": "order_restructured", "changed_variable": "instruction order",
     "prepend": "Preserve every number, name and quotation exactly. "},
]


class PromptOptimizationService:
    """Optimizer with locked evals, baseline hash, guardrail + versioning."""

    def __init__(self, registry=None, eval_path: Path | None = None,
                 backend: str = "deterministic"):
        from ..prompts.service import PromptRegistryService
        self.registry = registry or PromptRegistryService()
        self.eval_path = Path(eval_path or EVAL_PATH)
        self.backend = backend

    # ---- eval set ----------------------------------------------------------

    def eval_cases(self) -> List[Dict[str, Any]]:
        data = json.loads(self.eval_path.read_text(encoding="utf-8"))
        cases = data.get("evals", [])
        if data.get("locked") is not True:
            raise ValueError("eval_set_not_locked")
        return cases

    def baseline_hash(self, system: str) -> str:
        return hashlib.sha256(system.encode("utf-8")).hexdigest()[:16]

    # ---- candidates --------------------------------------------------------

    def variants(self, system: str) -> List[Dict[str, Any]]:
        """Base + candidates, each changing exactly one variable."""
        base = system.strip()
        out = [{"variant": "baseline", "changed_variable": None,
                "system_prompt": base}]
        for v in _VARIABLES:
            if v.get("prepend"):
                prompt = v["prepend"] + base
            else:
                prompt = base + v["append"]
            out.append({"variant": v["variant"],
                        "changed_variable": v["changed_variable"],
                        "system_prompt": prompt})
        return out

    # ---- applying a candidate (deterministic or LLM) -----------------------

    def _apply(self, system_prompt: str, text: str) -> str:
        """Apply the prompt to a text. Deterministic backend interprets the
        prompt's constraints as concrete paraphrase rules; LLM backend uses
        the real local model."""
        if self.backend == "ollama" and _llm_enabled():
            return _apply_llm(system_prompt, text)
        from .deterministic_rewrite import apply_constraints
        return apply_constraints(system_prompt, text)

    # ---- scoring -----------------------------------------------------------

    def score_candidate(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        """Average composite score over all locked eval cases."""
        cases = self.eval_cases()
        per_case = []
        for case in cases:
            rewritten = self._apply(candidate["system_prompt"], case["text"])
            r = composite(case["text"], rewritten, case.get("protected_terms", []))
            per_case.append({"eval_id": case["id"], **r})
        avg = sum(c["score"] for c in per_case) / len(per_case) if per_case else 0.0
        guard = all(c["guardrail_passed"] for c in per_case)
        return {"candidate": candidate, "per_case": per_case,
                "avg_score": round(avg, 4), "guardrail_passed": guard}

    def optimize(self, system: str) -> Dict[str, Any]:
        """Run the loop: baseline -> candidates -> scores -> winner
        (evaluation only; nothing is promoted)."""
        cases = self.eval_cases()
        base_hash = self.baseline_hash(system)
        results = []
        for cand in self.variants(system):
            results.append(self.score_candidate(cand))
        baseline = next(r for r in results if r["candidate"]["variant"] == "baseline")
        ranked = sorted(results, key=lambda r: r["avg_score"], reverse=True)
        winner = ranked[0] if ranked else None
        return {
            "eval_count": len(cases),
            "backend": self.backend,
            "baseline_hash": base_hash,
            "baseline_score": baseline["avg_score"],
            "winner": winner,
            "ranking": [{"variant": r["candidate"]["variant"],
                         "avg_score": r["avg_score"],
                         "guardrail_passed": r["guardrail_passed"]}
                        for r in ranked],
        }

    # ---- promotion / versioning --------------------------------------------

    def promote(self, system: str, template_id: str,
                candidate_variant: str | None = None,
                version: str | None = None) -> Dict[str, Any]:
        """Promote the best (or a named) candidate into the registry as an
        immutable new version — only if it beats the baseline AND passes the
        guardrail. Returns the new template record."""
        report = self.optimize(system)
        winner = report["winner"]
        if candidate_variant:
            cand = next(c for c in self.variants(system)
                        if c["variant"] == candidate_variant)
            winner = self.score_candidate(cand)
        if winner is None:
            raise ValueError("no_candidate")
        if not winner["guardrail_passed"]:
            raise ValueError("guardrail_violation")
        if winner["avg_score"] <= report["baseline_score"]:
            raise ValueError("no_improvement")

        from ..prompts.service import PromptRegistryService
        if not isinstance(self.registry, PromptRegistryService):
            from ..prompts.service import PromptRegistryService as PRS
            self.registry = PRS(self.registry.path if hasattr(self.registry, "path") else None)

        now = datetime.now(timezone.utc).isoformat()
        if version is None:
            try:
                existing = self.registry.get_template(template_id)
                base_ver = existing.get("version", "1.0.0")
                parts = base_ver.split(".")
                new_parts = [int(p) for p in parts[:3]] if parts[0].isdigit() else [1, 0, 0]
                new_parts[2] = new_parts[2] + 1 if len(new_parts) > 2 else 1
                version = ".".join(str(p) for p in new_parts)
            except ValueError:
                version = "1.0.1"

        record = {
            "id": template_id,
            "version": version,
            "channel": "stable",
            "system_prompt": winner["candidate"]["system_prompt"],
            "user_template": "{{text}}",
            "provider": None,
            "model": None,
            "parameters": {},
            "optimization": {
                "baseline_hash": report["baseline_hash"],
                "baseline_score": report["baseline_score"],
                "winner_score": winner["avg_score"],
                "changed_variable": winner["candidate"]["changed_variable"],
                "eval_count": report["eval_count"],
                "backend": self.backend,
                "created_at": now,
            },
        }
        self.registry.create_version(record)
        return record

    def history(self, template_id: str) -> List[Dict[str, Any]]:
        return [t for t in self.registry.list_templates() if t.get("id") == template_id]

    def rollback(self, template_id: str, version: str) -> Dict[str, Any]:
        """Restore a previous version as the new stable one (immutable
        history, rollback-ready)."""
        target = self.registry.get_template(template_id, version=version)
        current = self.registry.get_template(template_id)
        from ..prompts.service import PromptRegistryService
        if not isinstance(self.registry, PromptRegistryService):
            from ..prompts.service import PromptRegistryService as PRS
            self.registry = PRS(self.registry.path)
        # bump current stable's patch number for the restored copy
        cur_parts = [int(p) for p in current["version"].split(".")[:3]]
        new_version = f"{cur_parts[0]}.{cur_parts[1]}.{cur_parts[2] + 1}"
        record = {**target, "version": new_version, "channel": "stable",
                  "optimization": {**(target.get("optimization") or {}),
                                   "rolled_back_from": current["version"]}}
        self.registry.create_version(record)
        return record


def _llm_enabled() -> bool:
    import os
    return os.environ.get("LOCAL_LLM_ENABLED", "").lower() in ("1", "true", "yes")


def _apply_llm(system_prompt: str, text: str) -> str:
    """Real LLM rewrite through the local backend (Ollama/OpenAI-compatible).
    Raises RuntimeError when the backend cannot produce output."""
    import os
    import urllib.request

    base = os.environ.get("LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434/v1")
    model = os.environ.get("LOCAL_LLM_MODEL", "eurollm-9b")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ],
        "temperature": 0.2,
    }
    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        out = data["choices"][0]["message"]["content"]
    except Exception as e:
        raise RuntimeError(f"llm_backend_failed: {e}") from e
    if not out.strip():
        raise RuntimeError("llm_backend_returned_empty")
    return out.strip()
