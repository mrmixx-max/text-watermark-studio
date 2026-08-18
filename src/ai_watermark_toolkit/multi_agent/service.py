from __future__ import annotations

from typing import Any


class MultiAgentService:
    def run(self, text: str) -> dict[str, Any]:
        drafts: list[dict[str, Any]] = [
            {"id": "g1", "draft": text.strip()},
            {"id": "g2", "draft": text.strip() + "\n\nRevised for clarity."},
        ]
        final = drafts[-1]["draft"] if drafts else text
        return {"agents": len(drafts), "drafts": drafts, "final": final}
