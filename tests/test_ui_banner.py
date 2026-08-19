"""Tests for ui/banner.py"""
from ai_watermark_toolkit.ui import banner


def test_version():
    assert banner.__version__ == "2.4.3"


def test_render_banner_plain():
    result = banner.render_banner(color=False)
    assert "TEXT WATERMARK STUDIO" in result
    assert "2.4.3" in result


def test_render_banner_color():
    result = banner.render_banner(color=True)
    assert "TEXT WATERMARK STUDIO" in result
    assert "2.4.3" in result


def test_render_detect_report_clean():
    report = {
        "layers": {
            "markers": {"high": 0, "mid": 0, "low": 0},
            "unicode": {"count": 0, "items": []},
        }
    }
    result = banner.render_detect_report(report, color=False)
    assert "DETECT" in result
    assert "CLEAN" in result


def test_render_detect_report_signals():
    report = {
        "layers": {
            "markers": {"high": 2, "mid": 1, "low": 0},
            "unicode": {"count": 3, "items": [{"cp": "U+200B", "name": "ZERO WIDTH SPACE"}]},
        }
    }
    result = banner.render_detect_report(report, color=False)
    assert "DETECT" in result
    assert "WATERMARK SIGNALS FOUND" in result


def test_render_detect_report_color():
    report = {
        "layers": {
            "markers": {"high": 0, "mid": 0, "low": 0},
            "unicode": {"count": 0, "items": []},
        }
    }
    result = banner.render_detect_report(report, color=True)
    assert "DETECT" in result
