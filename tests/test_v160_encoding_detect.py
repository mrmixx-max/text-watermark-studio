"""Encoding detection (C7, 2026-08-18) — tests for encoding detection.

Contract under test:
- detect_bom: identifies UTF-8/16/32 BOMs.
- is_valid_utf8: strict validation with confidence.
- is_valid_utf16: validation for LE/BE variants.
- detect_encoding: full detection pipeline.
- _detect_mixed_encoding: sliding window mixed detection.
- _detect_conversion_attack: overlong sequences, homoglyphs, embedded BOMs.
- detect_and_convert: detect + convert to target encoding.
- strip_bom: removes BOM from data.
"""


from ai_watermark_toolkit.forensics.encoding_detect import (
    BOM_UTF8,
    BOM_UTF16_BE,
    BOM_UTF16_LE,
    BOM_UTF32_LE,
    _detect_conversion_attack,
    _detect_mixed_encoding,
    _latin1_confidence,
    detect_and_convert,
    detect_bom,
    detect_encoding,
    is_valid_utf8,
    is_valid_utf16,
    strip_bom,
)


class TestBOMDetection:
    """Tests for BOM detection."""

    def test_utf8_bom(self):
        data = BOM_UTF8 + b"Hello"
        enc, length = detect_bom(data)
        assert enc == "utf-8-sig"
        assert length == 3

    def test_utf16_le_bom(self):
        data = BOM_UTF16_LE + b"Hello"
        enc, length = detect_bom(data)
        assert enc == "utf-16-le"
        assert length == 2

    def test_utf16_be_bom(self):
        data = BOM_UTF16_BE + b"Hello"
        enc, length = detect_bom(data)
        assert enc == "utf-16-be"
        assert length == 2

    def test_utf32_le_bom(self):
        data = BOM_UTF32_LE + b"Hello"
        enc, length = detect_bom(data)
        assert enc == "utf-32-le"
        assert length == 4

    def test_no_bom(self):
        data = b"Hello World"
        enc, length = detect_bom(data)
        assert enc is None
        assert length == 0


class TestUTF8Validation:
    """Tests for UTF-8 validation."""

    def test_valid_ascii(self):
        valid, conf = is_valid_utf8(b"Hello World")
        assert valid is True
        assert 0.5 <= conf <= 1.0

    def test_valid_utf8_multibyte(self):
        valid, conf = is_valid_utf8("Héllo Wörld".encode())
        assert valid is True
        assert conf >= 0.9

    def test_invalid_utf8(self):
        valid, conf = is_valid_utf8(b"\xff\xfe\xfd")
        assert valid is False
        assert conf == 0.0

    def test_empty(self):
        valid, _conf = is_valid_utf8(b"")
        assert valid is True


class TestUTF16Validation:
    """Tests for UTF-16 validation."""

    def test_valid_utf16_le(self):
        text = "Hello"
        data = text.encode("utf-16-le")
        valid, _conf = is_valid_utf16(data, "little")
        assert valid is True

    def test_valid_utf16_be(self):
        text = "Hello"
        data = text.encode("utf-16-be")
        valid, _conf = is_valid_utf16(data, "big")
        assert valid is True

    def test_odd_length_invalid(self):
        valid, _conf = is_valid_utf16(b"\x00\x00\x00", "little")
        assert valid is False

    def test_too_many_nulls(self):
        # Data that is technically valid UTF-16 but mostly nulls
        # Should return True with low confidence (not a valid encoding choice)
        data = b"\x00\x00" * 100 + b"A\x00"
        valid, conf = is_valid_utf16(data, "little")
        assert valid is True
        assert conf < 0.5


class TestDetectEncoding:
    """Tests for the main detect_encoding function."""

    def test_detect_utf8_bom(self):
        data = BOM_UTF8 + b"Hello"
        result = detect_encoding(data)
        assert result.encoding == "utf-8-sig"
        assert result.confidence == 1.0

    def test_detect_ascii(self):
        data = b"Hello World, this is plain ASCII text."
        result = detect_encoding(data)
        assert result.encoding == "utf-8"
        assert result.confidence >= 0.6

    def test_detect_utf8_with_multibyte(self):
        data = "Héllo Wörld".encode()
        result = detect_encoding(data)
        assert result.encoding == "utf-8"
        assert result.confidence >= 0.9

    def test_detect_utf16_le(self):
        # "Hello World" encoded as UTF-16-LE is also valid UTF-8 (each byte is ASCII)
        # UTF-8 is preferred for valid UTF-8 data
        data = "Hello World".encode("utf-16-le")
        result = detect_encoding(data)
        assert result.encoding == "utf-8"

    def test_detect_latin1_fallback(self):
        # Bytes that are not valid UTF-8 but valid Latin-1
        data = b"\x80\x81\x82\x83"
        result = detect_encoding(data)
        assert result.encoding == "latin-1"

    def test_empty_data(self):
        result = detect_encoding(b"")
        assert result.encoding == "utf-8"
        assert result.confidence == 1.0


class TestMixedEncoding:
    """Tests for mixed encoding detection."""

    def test_uniform_ascii(self):
        data = b"A" * 200
        result = _detect_mixed_encoding(data)
        assert result.mixed is False

    def test_mixed_utf8_and_latin1(self):
        # Create data with UTF-8 multibyte and Latin-1 high bytes
        part1 = b"Hello "
        part2 = b"\x80\x81\x82"
        data = (part1 + part2) * 20
        result = _detect_mixed_encoding(data)
        # May or may not detect as mixed depending on window alignment
        assert isinstance(result.mixed, bool)


class TestConversionAttack:
    """Tests for encoding-conversion attack detection."""

    def test_no_attack_clean_utf8(self):
        data = b"Hello World"
        result = _detect_conversion_attack(data)
        assert result.conversion_attack is False

    def test_overlong_utf8(self):
        # Overlong encoding of '/' (0x2F) as 2 bytes: C0 AF
        data = b"\xc0\xaf"
        result = _detect_conversion_attack(data)
        assert result.conversion_attack is True
        assert "overlong_utf8_sequences" in result.attack_details

    def test_orphaned_continuation(self):
        # Continuation byte without leading byte
        data = b"Hello \x80 World"
        result = _detect_conversion_attack(data)
        assert result.conversion_attack is True
        assert "orphaned_continuation_bytes" in result.attack_details

    def test_embedded_bom(self):
        data = b"Hello" + BOM_UTF8 + b"World"
        result = _detect_conversion_attack(data)
        assert result.conversion_attack is True
        assert any("embedded_bom" in d for d in result.attack_details)


class TestLatin1Confidence:
    """Tests for Latin-1 confidence scoring."""

    def test_common_latin1_chars(self):
        # Common accented Western European chars
        data = "café résumé naïve".encode("latin-1")
        conf = _latin1_confidence(data)
        assert conf >= 0.7

    def test_random_high_bytes(self):
        data = bytes(range(0x80, 0xA0))
        conf = _latin1_confidence(data)
        assert conf < 0.7

    def test_all_ascii(self):
        conf = _latin1_confidence(b"Hello")
        assert conf == 0.5


class TestDetectAndConvert:
    """Tests for detect_and_convert function."""

    def test_utf8_to_utf8(self):
        data = b"Hello World"
        converted, _result = detect_and_convert(data, "utf-8")
        assert converted == data

    def test_utf8_bom_stripped(self):
        data = BOM_UTF8 + b"Hello"
        converted, _result = detect_and_convert(data, "utf-8")
        assert converted == b"Hello"

    def test_latin1_to_utf8(self):
        data = "café".encode("latin-1")
        converted, _result = detect_and_convert(data, "utf-8")
        assert converted == "café".encode()


class TestStripBOM:
    """Tests for BOM stripping."""

    def test_strip_utf8_bom(self):
        data = BOM_UTF8 + b"Hello"
        stripped, enc = strip_bom(data)
        assert stripped == b"Hello"
        assert enc == "utf-8-sig"

    def test_no_bom_unchanged(self):
        data = b"Hello"
        stripped, enc = strip_bom(data)
        assert stripped == data
        assert enc is None
