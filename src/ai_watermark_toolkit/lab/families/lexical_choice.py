from __future__ import annotations

from .base import LabFamily


class FamilyPlugin(LabFamily):
    slug = "lexical_choice"

    def capability(self) -> dict:
        return {"embed": True, "detect": True, "explain": True, "demo": True}

    def detect(self, text: str, options: dict | None = None) -> dict:
        hits = text.lower().count("furthermore") + text.lower().count("moreover")
        return {
            "family": self.slug,
            "supported": True,
            "score": min(0.9, hits * 0.25),
            "notes": ["lexical_pattern_demo"],
        }

    def embed(self, text: str, options: dict | None = None) -> dict:
        return {"family": self.slug, "supported": True, "text": "Furthermore, " + text, "notes": ["demo_lexical_embed"]}
