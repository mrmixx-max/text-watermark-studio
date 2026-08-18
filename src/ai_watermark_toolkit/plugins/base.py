from __future__ import annotations


class DetectorPlugin:
    name = "base"

    def detect(self, text: str, key_meta: dict) -> dict:
        return {"score": 0.0, "plugin": self.name, "notes": ["not_implemented"]}
