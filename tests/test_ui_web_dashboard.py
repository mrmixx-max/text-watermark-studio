"""Tests for ui/web/dashboard.py"""
import asyncio
import time
from datetime import datetime, timezone

import pytest

from ai_watermark_toolkit.ui.web import dashboard


class TestBumpStat:
    def setup_method(self):
        dashboard._stats["detections_total"] = 0
        dashboard._stats["embeds_total"] = 0
        dashboard._stats["cleans_total"] = 0
        dashboard._stats["reports_total"] = 0
        dashboard._stats["recent_detections"] = []

    def test_bump_detection(self):
        dashboard.bump_stat("detections", verdict="watermark_detected")
        assert dashboard._stats["detections_total"] == 1
        assert dashboard._stats["recent_detections"][0]["verdict"] == "watermark_detected"

    def test_bump_embed(self):
        dashboard.bump_stat("embeds")
        assert dashboard._stats["embeds_total"] == 1

    def test_bump_clean(self):
        dashboard.bump_stat("cleans")
        assert dashboard._stats["cleans_total"] == 1

    def test_bump_report(self):
        dashboard.bump_stat("reports")
        assert dashboard._stats["reports_total"] == 1

    def test_recent_detections_capped(self):
        for _ in range(25):
            dashboard.bump_stat("detections")
        assert len(dashboard._stats["recent_detections"]) == 20


class TestGetStats:
    def setup_method(self):
        dashboard._stats["detections_total"] = 0
        dashboard._stats["embeds_total"] = 0
        dashboard._stats["cleans_total"] = 0
        dashboard._stats["reports_total"] = 0
        dashboard._stats["recent_detections"] = []
        dashboard._stats["start_ts"] = time.time()

    def test_get_stats_structure(self):
        stats = dashboard.get_stats()
        assert "detections_total" in stats
        assert "detections_last_minute" in stats
        assert "uptime_seconds" in stats
        assert "version" in stats
        assert "recent_detections" in stats

    def test_get_stats_counts(self):
        dashboard._stats["detections_total"] = 5
        stats = dashboard.get_stats()
        assert stats["detections_total"] == 5


class TestIsoToTs:
    def test_valid_iso(self):
        ts = dashboard._iso_to_ts("2024-01-01T00:00:00+00:00")
        assert ts > 0

    def test_invalid_iso(self):
        ts = dashboard._iso_to_ts("not-a-date")
        assert ts == 0.0

    def test_none_iso(self):
        ts = dashboard._iso_to_ts(None)
        assert ts == 0.0


@pytest.mark.anyio
async def test_stats_event_generator():
    gen = dashboard.stats_event_generator()
    event = await gen.__anext__()
    assert "event: stats" in event
    assert "data:" in event
    await gen.aclose()
