from __future__ import annotations

from .base import LabFamily


class FamilyPlugin(LabFamily):
    slug = "training_time"

    def capability(self) -> dict:
        return {"embed": True, "detect": True, "explain": True, "demo": True}

    def detect(self, text: str, options: dict | None = None) -> dict:
        return {"family": self.slug, "supported": False, "score": 0.0, "notes": ["requires_model_or_training_access"]}

    def embed(self, text: str, options: dict | None = None) -> dict:
        return {
            "family": self.slug,
            "supported": False,
            "text": text,
            "notes": ["training_time_embed_not_available_in_text_only_lab"],
        }
