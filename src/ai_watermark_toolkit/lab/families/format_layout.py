from __future__ import annotations

from .base import LabFamily


class FamilyPlugin(LabFamily):
    slug = "format_layout"

    def capability(self) -> dict:
        return {"embed": True, "detect": True, "explain": True, "demo": True}

    def detect(self, text: str, options: dict | None = None) -> dict:
        return {
            "family": self.slug,
            "supported": True,
            "score": 0.75 if "  " in text or "\t" in text else 0.1,
            "notes": ["layout_spacing_demo"],
        }

    def embed(self, text: str, options: dict | None = None) -> dict:
        return {
            "family": self.slug,
            "supported": True,
            "text": text.replace(" ", "  ", 1) if " " in text else text,
            "notes": ["demo_layout_embed"],
        }
