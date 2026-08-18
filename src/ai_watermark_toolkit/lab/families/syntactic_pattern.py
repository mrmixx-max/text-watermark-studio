from __future__ import annotations

from .base import LabFamily


class FamilyPlugin(LabFamily):
    slug = "syntactic_pattern"

    def capability(self) -> dict:
        return {"embed": True, "detect": True, "explain": True, "demo": True}

    def detect(self, text: str, options: dict | None = None) -> dict:
        hits = text.count(";") + text.count(":")
        return {
            "family": self.slug,
            "supported": True,
            "score": min(0.85, hits * 0.15),
            "notes": ["syntactic_pattern_demo"],
        }

    def embed(self, text: str, options: dict | None = None) -> dict:
        return {
            "family": self.slug,
            "supported": True,
            "text": text.replace(".", "; therefore.") if "." in text else text + "; therefore.",
            "notes": ["demo_syntactic_embed"],
        }
