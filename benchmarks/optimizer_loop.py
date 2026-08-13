"""Full evaluator-loop check for the prompt optimizer (burn-in stage 5).

optimize -> promote -> history -> rollback against a TEMP registry, so the
real data/ registry is never touched. Prints one JSON line; exit 0 when the
whole loop behaves, 1 otherwise.
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ai_watermark_toolkit.optimization.service import PromptOptimizationService
from ai_watermark_toolkit.prompts.service import PromptRegistryService

BASE = ("Rewrite the given text so it no longer reads like AI output. "
        "Keep all facts, numbers and names exactly as they are.")


def main() -> int:
    tmp = Path(tempfile.mkdtemp())
    (tmp / "r.json").write_text(json.dumps({"templates": []}), encoding="utf-8")
    svc = PromptOptimizationService(registry=PromptRegistryService(path=tmp / "r.json"))

    # seed the base template so promote creates 1.0.1 on top of 1.0.0
    svc.registry.create_version({
        "id": "dewatermark-system", "version": "1.0.0", "channel": "stable",
        "system_prompt": BASE, "user_template": "{{text}}",
    })

    r = svc.optimize(BASE)
    w = r["winner"]
    svc.promote(BASE, "dewatermark-system")
    hist = svc.registry.list_templates()
    rolled = svc.rollback("dewatermark-system", hist[-2]["version"])

    ok = (w["avg_score"] > r["baseline_score"]
          and w["guardrail_passed"]
          and len(hist) >= 2
          and rolled["channel"] == "stable")
    print(json.dumps({
        "baseline": r["baseline_score"], "winner": w["candidate"]["variant"],
        "winner_score": w["avg_score"], "guardrail": w["guardrail_passed"],
        "versions": len(hist), "rollback": rolled["channel"], "ok": ok,
    }))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
