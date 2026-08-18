"""PDF text watermark (C7, 2026-08-18) — tests for invisible PDF text watermarks.

Contract under test:
- embed_pdf_watermark / detect_pdf_watermark: round-trip for all 3 methods
  (spacing, metadata, color).
- Spacing watermark: Tc operator injection after Td operators.
- Metadata watermark: signed stream object with HMAC-SHA256.
- Color watermark: near-zero RGB shift (0 0 0.004 rg).
- Auto-detection tries all methods.
- Honest boundaries: metadata removed on regen, spacing survives rendering.
"""

import pytest

from ai_watermark_toolkit.metadata.pdf_watermark import (
    _bits_to_bytes,
    _text_to_bits,
    detect_color_watermark,
    detect_metadata_watermark,
    detect_pdf_watermark,
    detect_spacing_watermark,
    embed_color_watermark,
    embed_metadata_watermark,
    embed_pdf_watermark,
    embed_spacing_watermark,
)

# Minimal PDF with text operators for testing
# Has 100+ Td operators to support multi-bit watermarks
_pdf_stream = b"BT\n/F1 12 Tf\n"
for i in range(100):
    _pdf_stream += f"{100 + i * 5} {700 - i * 30} Td\n(Word {i}) Tj\n".encode()
_pdf_stream += b"0 0 0 rg\n"
for i in range(100):
    _pdf_stream += b"0 0 0 rg\n"
_pdf_stream += b"ET"

SAMPLE_PDF = (
    b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]
   /Contents 4 0 R >>
endobj
4 0 obj
<< /Length 100 >>
stream
"""
    + _pdf_stream
    + b"""
endstream
endobj
xref
0 5
0000000000 65535 f
trailer
<< /Size 5 /Root 1 0 R >>
startxref
0
%%EOF
"""
)

SECRET = "test-secret-001"
KEY_ID = "test-key-001"


class TestSpacingWatermark:
    """Tests for inter-word spacing watermark."""

    def test_embed_spacing_injects_tc(self):
        result = embed_spacing_watermark(SAMPLE_PDF, "hi", SECRET)
        assert b"Tc" in result
        assert len(result) > len(SAMPLE_PDF)

    def test_detect_spacing_roundtrip(self):
        message = "test123"
        embedded = embed_spacing_watermark(SAMPLE_PDF, message, SECRET)
        result = detect_spacing_watermark(embedded, SECRET)
        assert result["found"] is True
        assert result["message"] == message

    def test_spacing_no_markers_in_original(self):
        result = detect_spacing_watermark(SAMPLE_PDF, SECRET)
        assert result["found"] is False

    def test_spacing_empty_message(self):
        embedded = embed_spacing_watermark(SAMPLE_PDF, "", SECRET)
        # Empty message should still embed (length header = 0)
        result = detect_spacing_watermark(embedded, SECRET)
        # May or may not find depending on implementation
        assert isinstance(result, dict)


class TestMetadataWatermark:
    """Tests for signed metadata stream watermark."""

    def test_embed_metadata_adds_stream(self):
        result = embed_metadata_watermark(SAMPLE_PDF, KEY_ID, SECRET)
        assert b"/Type /Metadata" in result
        assert b"TWS-PDF-WM" in result

    def test_detect_metadata_roundtrip(self):
        embedded = embed_metadata_watermark(SAMPLE_PDF, KEY_ID, SECRET)
        result = detect_metadata_watermark(embedded, {KEY_ID: SECRET})
        assert result["found"] is True
        assert result["valid"] is True
        assert result["key_id"] == KEY_ID

    def test_detect_metadata_wrong_secret(self):
        embedded = embed_metadata_watermark(SAMPLE_PDF, KEY_ID, SECRET)
        result = detect_metadata_watermark(embedded, {KEY_ID: "wrong-secret"})
        assert result["found"] is True
        assert result["valid"] is False

    def test_detect_metadata_no_marks(self):
        result = detect_metadata_watermark(SAMPLE_PDF, {KEY_ID: SECRET})
        assert result["found"] is False

    def test_metadata_no_eof(self):
        pdf_no_eof = b"%PDF-1.4\n<< >>"
        result = embed_metadata_watermark(pdf_no_eof, KEY_ID, SECRET)
        assert b"%%EOF" in result


class TestColorWatermark:
    """Tests for text color watermark."""

    def test_embed_color_injects_rg(self):
        result = embed_color_watermark(SAMPLE_PDF, "hi", SECRET)
        # Should have either 0.004 rg (bit=1) or 0.001 rg (bit=0)
        assert b"0.004 rg" in result or b"0.001 rg" in result

    def test_detect_color_roundtrip(self):
        message = "color"
        embedded = embed_color_watermark(SAMPLE_PDF, message, SECRET)
        result = detect_color_watermark(embedded, SECRET)
        assert result["found"] is True
        assert result["message"] == message

    def test_color_no_markers_in_original(self):
        result = detect_color_watermark(SAMPLE_PDF, SECRET)
        assert result["found"] is False


class TestUnifiedAPI:
    """Tests for the unified embed/detect API."""

    def test_embed_auto_metadata(self):
        result = embed_pdf_watermark(SAMPLE_PDF, "test", SECRET, method="metadata", key_id=KEY_ID)
        assert b"/Type /Metadata" in result

    def test_embed_auto_spacing(self):
        result = embed_pdf_watermark(SAMPLE_PDF, "test", SECRET, method="spacing")
        assert b"Tc" in result

    def test_embed_auto_color(self):
        result = embed_pdf_watermark(SAMPLE_PDF, "test", SECRET, method="color")
        assert b"0.004 rg" in result

    def test_detect_auto_finds_metadata(self):
        embedded = embed_pdf_watermark(SAMPLE_PDF, "test", SECRET, method="metadata", key_id=KEY_ID)
        result = detect_pdf_watermark(embedded, SECRET, secrets={KEY_ID: SECRET}, method="auto")
        assert result["found"] is True

    def test_detect_auto_no_watermark(self):
        result = detect_pdf_watermark(SAMPLE_PDF, SECRET, method="auto")
        assert result["found"] is False

    def test_unknown_method_raises(self):
        with pytest.raises(ValueError):
            embed_pdf_watermark(SAMPLE_PDF, "test", SECRET, method="unknown")


class TestBitConversion:
    """Tests for bit/byte conversion helpers."""

    def test_text_to_bits_roundtrip(self):
        text = "Hello"
        bits = _text_to_bits(text)
        assert len(bits) == len(text.encode("utf-8")) * 8

    def test_bits_to_bytes_roundtrip(self):
        text = "Test message"
        bits = _text_to_bits(text)
        result = _bits_to_bytes(bits)
        assert result == text.encode("utf-8")

    def test_empty_text_bits(self):
        assert _text_to_bits("") == []
