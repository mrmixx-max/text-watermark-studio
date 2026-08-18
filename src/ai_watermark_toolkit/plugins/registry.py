from __future__ import annotations

from .audio_watermark import AudioWatermarkPlugin
from .base import DetectorPlugin
from .code_watermark import CodeWatermarkPlugin
from .video_watermark import VideoWatermarkPlugin


class SimpleHeuristicPlugin(DetectorPlugin):
    name = "simple_heuristic"

    def detect(self, text: str, key_meta: dict) -> dict:
        trigger = key_meta.get("trigger_phrase", "")
        score = 0.7 if trigger and trigger.lower() in text.lower() else 0.1
        return {"score": score, "plugin": self.name, "notes": ["heuristic_only"]}


def get_plugins() -> list[DetectorPlugin]:
    return [
        SimpleHeuristicPlugin(),
        CodeWatermarkPlugin(),
        AudioWatermarkPlugin(),
        VideoWatermarkPlugin(),
    ]


def get_plugin(name: str) -> DetectorPlugin | None:
    """Get a plugin by name."""
    for plugin in get_plugins():
        if plugin.name == name:
            return plugin
    return None
