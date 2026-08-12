from ai_watermark_toolkit.sanitize_unicode import analyze, sanitize
from ai_watermark_toolkit.markers.scanner import scan_markers
from ai_watermark_toolkit.transform.clean import clean_text
from ai_watermark_toolkit.transform.dilute import dilute_text
from ai_watermark_toolkit.pipeline import detect_text, run_pipeline


def test_unicode_detect_and_clean():
    raw = "Hello\u200bWorld\u202e"
    findings = analyze(raw)
    assert len(findings) >= 2
    cleaned = sanitize(raw)
    assert "\u200b" not in cleaned.text
    assert "\u202e" not in cleaned.text


def test_marker_scan_de():
    text = "In der heutigen digitalen Welt ist es wichtig zu betonen, dass das hilft."
    hits = scan_markers(text, lang="de")
    assert any(h.severity >= 3 for h in hits)


def test_clean_idempotent():
    text = "Hello\u200bWorld"
    once = clean_text(text)
    twice = clean_text(once.text)
    assert once.text == twice.text


def test_dilute_preserves_codeblock():
    text = "Text davor. ```bash\necho test\n``` Darüber hinaus ist es wichtig zu betonen, dass es klappt."
    out = dilute_text(text, intensity="standard")
    assert "```bash\necho test\n```" in out.text


def test_detect_report_shape():
    report = detect_text("Furthermore, this is a test.", lang="en")
    assert "layers" in report
    assert "markers" in report["layers"]


def test_pipeline_changes_text():
    text = "In today's digital world, it is important to note that tools leverage automation."
    out, report = run_pipeline(text, lang="en", intensity="standard")
    assert out
    assert "before" in report and "after" in report
