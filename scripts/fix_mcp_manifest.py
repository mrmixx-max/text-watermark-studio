"""Fix mcp/tools.json to match the real API routes (agent audit 2026-08-13)."""
import json
from pathlib import Path

p = Path("mcp/tools.json")
data = json.loads(p.read_text(encoding="utf-8"))
tools = data["tools"]

# route fixes: manifest path/body -> real API contract
fixes = {
    "lab_pipeline": {"path": "/api/pipeline", "body": ["text", "lang", "intensity"]},
    "llm_rewrite": {"path": "/api/rewrite/run", "body": ["text", "mode", "preserve"]},
    "opt_baseline": {"path": "/api/optimization/evals", "body": []},
    "opt_candidates": {"body": ["system"]},
    "opt_optimize": {"body": ["system"]},
    "opt_promote": {"body": ["system", "template_id"]},
    "ma_run": {"body": ["text"]},
    "ma_promote": {"body": ["text"]},
}
# tools that have NO real route -> remove (do not ship dead interface)
drop = {"llm_providers", "llm_rewrite_from_template", "opt_score"}

kept = []
removed = []
for t in tools:
    name = t.get("name")
    if name in drop:
        removed.append(name)
        continue
    if name in fixes:
        fix = fixes[name]
        t.update({k: v for k, v in fix.items() if v is not None})
        # rebuild body_schema if we changed it
        if "body" in fix:
            t["body_schema"] = {f: {"type": "string"} for f in fix["body"]}
    kept.append(t)

data["tools"] = kept
p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"Tools: {len(tools)} -> {len(kept)} (entfernt: {removed})")
print("Gefixt:", sorted(fixes.keys()))
