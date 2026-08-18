"""Encoding detection (C7, 2026-08-18) — UTF-8/16/32, Latin-1, BOM, mixed.

Detects the encoding of byte strings with special attention to:

1. **BOM detection**: UTF-8 (EF BB BF), UTF-16 LE/BE, UTF-32 LE/BE.
2. **UTF-8 validation**: strict vs lenient, with confidence scoring.
3. **UTF-16 detection**: via surrogate pairs and null-byte patterns.
4. **Latin-1 fallback**: valid bytes 0x00-0xFF but not valid UTF-8.
5. **Mixed encoding detection**: bytes that switch between encodings mid-stream
   (an attack vector — hiding watermarks by encoding some parts differently).
6. **Encoding-conversion attacks**: data that appears as one encoding but
   contains byte sequences designed to exploit conversion to another.

This module is designed for forensic analysis — it goes beyond simple
chardet-style detection to identify deliberate encoding manipulation.

Honest boundaries:
- Latin-1 detection is inherently ambiguous — any byte sequence is valid
  Latin-1. The module uses heuristics (common byte patterns) but confidence
  is always lower than for UTF-8/16.
- Mixed encoding detection has false positives on multilingual text that
  legitimately mixes scripts. Context is needed.
- Encoding attacks are detected by signature patterns, not by solving the
  halting problem. Clever attacks may evade detection.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# BOM signatures
BOM_UTF8 = b"\xef\xbb\xbf"
BOM_UTF16_LE = b"\xff\xfe"
BOM_UTF16_BE = b"\xfe\xff"
BOM_UTF32_LE = b"\xff\xfe\x00\x00"
BOM_UTF32_BE = b"\x00\x00\xfe\xff"

BOM_MAP = {
    BOM_UTF32_LE: "utf-32-le",
    BOM_UTF32_BE: "utf-32-be",
    BOM_UTF8: "utf-8-sig",
    BOM_UTF16_LE: "utf-16-le",
    BOM_UTF16_BE: "utf-16-be",
}


# Encoding detection result
@dataclass
class EncodingResult:
    """Result of encoding detection."""

    encoding: str  # detected encoding
    confidence: float  # 0.0 to 1.0
    bom: str | None = None  # BOM type if present
    mixed: bool = False  # detected mixed encoding
    mixed_segments: list[dict] = field(default_factory=list)
    conversion_attack: bool = False  # suspected encoding-conversion attack
    attack_details: list[str] = field(default_factory=list)
    byte_order: str | None = None  # "little" or "big" for UTF-16/32

    def to_dict(self) -> dict:
        return {
            "encoding": self.encoding,
            "confidence": round(self.confidence, 4),
            "bom": self.bom,
            "mixed": self.mixed,
            "mixed_segments": self.mixed_segments,
            "conversion_attack": self.conversion_attack,
            "attack_details": self.attack_details,
            "byte_order": self.byte_order,
        }


def detect_bom(data: bytes) -> tuple[str | None, int]:
    """Detect BOM in data. Returns (encoding, bom_length)."""
    for bom, encoding in BOM_MAP.items():
        if data.startswith(bom):
            return encoding, len(bom)
    return None, 0


def is_valid_utf8(data: bytes, strict: bool = True) -> tuple[bool, float]:
    """Check if data is valid UTF-8. Returns (valid, confidence)."""
    try:
        data.decode("utf-8", errors="strict" if strict else "replace")
        # Confidence based on multi-byte sequence ratio
        # Pure ASCII = lower confidence (could be anything)
        # Rich multi-byte = higher confidence it's intentional UTF-8
        n_multibyte = sum(1 for b in data if b >= 0x80)
        if n_multibyte == 0:
            # All ASCII — valid UTF-8 but ambiguous
            return True, 0.6 if len(data) < 100 else 0.8
        # Has multi-byte chars — likely intentional UTF-8
        return True, 0.95
    except UnicodeDecodeError:
        return False, 0.0


def is_valid_utf16(data: bytes, byteorder: str = "little") -> tuple[bool, float]:
    """Check if data is valid UTF-16. Returns (valid, confidence)."""
    if len(data) % 2 != 0:
        return False, 0.0

    encoding = "utf-16-le" if byteorder == "little" else "utf-16-be"
    try:
        decoded = data.decode(encoding, errors="strict")
    except UnicodeDecodeError:
        return False, 0.0

    # Check character distribution to determine confidence
    # Pure ASCII encoded as UTF-16 has many null bytes — lower confidence
    null_chars = decoded.count("\x00")
    null_ratio = null_chars / max(len(decoded), 1)

    # High null ratio indicates ASCII misdetected as UTF-16
    if null_ratio > 0.4:
        confidence = 0.4  # Low confidence — likely ASCII
    # Private use area characters indicate random bytes
    elif sum(1 for c in decoded if 0xE000 <= ord(c) <= 0xF8FF) > len(decoded) * 0.3:
        confidence = 0.3  # Low confidence — likely random
    else:
        # Legitimate UTF-16 with real characters
        has_surrogates = any(0xD800 <= ord(c) <= 0xDFFF for c in decoded)
        confidence = 0.9 if has_surrogates else 0.75

    return True, confidence


def detect_encoding(data: bytes) -> EncodingResult:
    """Detect the encoding of byte data.

    Tries BOM first, then UTF-8, then UTF-16 variants, then Latin-1.
    Also detects mixed encodings and conversion attacks.
    """
    if not data:
        return EncodingResult(encoding="utf-8", confidence=1.0)

    # Step 1: Check for BOM
    bom_encoding, _bom_len = detect_bom(data)
    if bom_encoding:
        return EncodingResult(
            encoding=bom_encoding,
            confidence=1.0,
            bom=bom_encoding,
            byte_order="little" if "le" in bom_encoding else "big" if "be" in bom_encoding else None,
        )

    # Step 2: Try UTF-8 first (always preferred for valid UTF-8)
    valid_utf8, utf8_conf = is_valid_utf8(data)
    if valid_utf8:
        return EncodingResult(encoding="utf-8", confidence=utf8_conf)

    # Step 3: Try UTF-16 (only for non-UTF-8 data)
    # Only detect UTF-16 if there's a BOM or the decoded text contains
    # at least one character that can't be represented in Latin-1 (> 0xFF)
    # This avoids misdetecting Latin-1 or ASCII data as UTF-16.
    valid_utf16_le, utf16_le_conf = is_valid_utf16(data, "little")
    valid_utf16_be, utf16_be_conf = is_valid_utf16(data, "big")

    # Check if UTF-16 decoded text has characters > 0xFF (not representable in Latin-1)
    def _has_wide_chars(conf, byteorder):
        if not conf:
            return False
        try:
            enc = "utf-16-le" if byteorder == "little" else "utf-16-be"
            decoded = data.decode(enc, errors="strict")
            return any(ord(c) > 0xFF for c in decoded)
        except UnicodeDecodeError:
            return False

    has_wide_le = _has_wide_chars(valid_utf16_le, "little")
    has_wide_be = _has_wide_chars(valid_utf16_be, "big")

    # For non-BOM UTF-16, require at least 4 decoded characters
    # to avoid misdetecting short Latin-1 sequences as UTF-16
    min_utf16_chars = 4
    try:
        n_chars_le = len(data.decode("utf-16-le", errors="strict")) if valid_utf16_le else 0
    except UnicodeDecodeError:
        n_chars_le = 0
    try:
        n_chars_be = len(data.decode("utf-16-be", errors="strict")) if valid_utf16_be else 0
    except UnicodeDecodeError:
        n_chars_be = 0

    if valid_utf16_le and utf16_le_conf > utf16_be_conf and has_wide_le and n_chars_le >= min_utf16_chars:
        return EncodingResult(
            encoding="utf-16-le",
            confidence=utf16_le_conf,
            byte_order="little",
        )
    if valid_utf16_be and utf16_be_conf > 0.5 and has_wide_be and n_chars_be >= min_utf16_chars:
        return EncodingResult(
            encoding="utf-16-be",
            confidence=utf16_be_conf,
            byte_order="big",
        )

    # Step 5: Check for mixed encoding
    mixed = _detect_mixed_encoding(data)
    if mixed.mixed:
        return mixed

    # Step 6: Check for conversion attacks
    attack = _detect_conversion_attack(data)
    if attack.conversion_attack:
        return attack

    # Step 7: Fallback to Latin-1 (always valid for arbitrary bytes)
    latin1_conf = _latin1_confidence(data)
    return EncodingResult(
        encoding="latin-1",
        confidence=latin1_conf,
    )


def _detect_mixed_encoding(data: bytes, window_size: int = 64) -> EncodingResult:
    """Detect if data contains segments in different encodings.

    Uses a sliding window approach to detect encoding shifts.
    """
    result = EncodingResult(encoding="unknown", confidence=0.5)

    if len(data) < window_size:
        return result

    segments = []
    current_encoding = None
    current_start = 0

    for i in range(0, len(data) - window_size + 1, window_size // 2):
        window = data[i : i + window_size]
        window_enc = _quick_detect(window)

        if window_enc != current_encoding:
            if current_encoding is not None:
                segments.append(
                    {
                        "start": current_start,
                        "end": i,
                        "encoding": current_encoding,
                    }
                )
            current_encoding = window_enc
            current_start = i

    # Add final segment
    if current_encoding is not None:
        segments.append(
            {
                "start": current_start,
                "end": len(data),
                "encoding": current_encoding,
            }
        )

    # Filter: only "mixed" if we have segments with genuinely different encodings
    unique_encs = {s["encoding"] for s in segments}
    meaningful_diffs = unique_encs - {"ascii", "utf-8"}  # ascii is subset of utf-8

    if len(unique_encs) > 1 and (len(meaningful_diffs) > 1 or "utf-8" not in unique_encs):
        result.mixed = True
        result.mixed_segments = segments
        # Overall encoding is the most common one
        from collections import Counter

        enc_counts = Counter(s["encoding"] for s in segments)
        result.encoding = enc_counts.most_common(1)[0][0]
        result.confidence = 0.7

    return result


def _quick_detect(window: bytes) -> str:
    """Quick encoding detection for a small window."""
    # Check ASCII
    if all(b < 0x80 for b in window):
        return "ascii"

    # Check UTF-8
    try:
        window.decode("utf-8", errors="strict")
        return "utf-8"
    except UnicodeDecodeError:
        pass

    # Check if high bytes suggest Latin-1
    high_bytes = sum(1 for b in window if b >= 0x80)
    if high_bytes > 0:
        return "latin-1"

    return "unknown"


def _detect_conversion_attack(data: bytes) -> EncodingResult:
    """Detect encoding-conversion attacks.

    These are byte sequences that:
    1. Appear valid in one encoding but produce unexpected characters when
       converted to another (e.g., overlong UTF-8 sequences).
    2. Contain invalid UTF-8 sequences that are "just barely" invalid
       (designed to trigger fallback to a different encoding).
    3. Use homoglyphs (look-alike characters from different scripts).
    """
    result = EncodingResult(encoding="unknown", confidence=0.5)
    attacks = []

    # Check for overlong UTF-8 sequences
    overlong_pattern = re.compile(
        b"[\xc0\xc1]"  # 2-byte sequences for ASCII (overlong)
        b"|[\xe0\x80-\x9f]"  # 3-byte overlong
        b"|[\xf0\x80-\x8f]",  # 4-byte overlong
    )
    if overlong_pattern.search(data):
        attacks.append("overlong_utf8_sequences")

    # Check for invalid UTF-8 that would become valid in Latin-1
    # Bytes 0x80-0xBF without a leading byte = orphaned continuation bytes
    orphaned = re.compile(b"(?<![\xc0-\xfd])[\x80-\xbf]")
    if orphaned.search(data):
        attacks.append("orphaned_continuation_bytes")

    # Check for homoglyph substitution patterns
    # Common: Cyrillic 'а' (U+0430) replacing Latin 'a' (U+0061)
    # In UTF-8: Cyrillic 'а' = D0 B0
    cyrillic_homoglyphs = re.compile(
        b"[\xd0-\xd3][\x80-\xbf]"  # Cyrillic range in UTF-8
    )
    if cyrillic_homoglyphs.search(data):
        # Check if there's also Latin text (suspicious mix)
        latin_text = re.compile(b"[a-zA-Z]{4,}")
        if latin_text.search(data):
            attacks.append("cyrillic_latin_homoglyph_mix")

    # Check for BOM in the middle of the file (should only be at start)
    if len(data) > 4:
        middle_data = data[1:]  # skip first byte
        for bom in [BOM_UTF8, BOM_UTF16_LE, BOM_UTF16_BE]:
            if bom in middle_data:
                attacks.append(f"embedded_bom_{BOM_MAP.get(bom, 'unknown')}")
                break

    if attacks:
        result.conversion_attack = True
        result.attack_details = attacks
        # Try to determine the "real" underlying encoding
        try:
            data.decode("latin-1")
            result.encoding = "latin-1"
            result.confidence = 0.6
        except (UnicodeDecodeError, LookupError, AttributeError):
            result.encoding = "unknown"
            result.confidence = 0.3

    return result


def _latin1_confidence(data: bytes) -> float:
    """Estimate confidence that data is truly Latin-1 (not just fallback).

    High confidence: common Latin-1 accented chars (0xC0-0xFF range).
    Low confidence: control chars or random high bytes.
    """
    if not data:
        return 0.5

    n_high = sum(1 for b in data if b >= 0x80)
    if n_high == 0:
        return 0.5  # All ASCII — ambiguous

    # Common Latin-1 letters (accented Western European)
    common_latin1 = sum(1 for b in data if 0xC0 <= b <= 0xFF)
    n_control = sum(1 for b in data if 0x80 <= b <= 0x9F)

    # High common letters = likely Latin-1
    ratio = common_latin1 / n_high
    if ratio > 0.8 and n_control < n_high * 0.1:
        return 0.85
    if ratio > 0.5:
        return 0.65
    return 0.4


def detect_and_convert(data: bytes, target_encoding: str = "utf-8") -> tuple[bytes, EncodingResult]:
    """Detect encoding and convert to target encoding.

    Returns (converted_data, detection_result).
    Raises ValueError if conversion is not possible.
    """
    result = detect_encoding(data)

    # If already in target encoding, return as-is
    source_enc = result.encoding.replace("-sig", "")
    if source_enc == target_encoding:
        # Strip BOM if present and target is utf-8
        if result.bom and target_encoding == "utf-8":
            _, bom_len = detect_bom(data)
            return data[bom_len:], result
        return data, result

    # Decode from source, encode to target
    try:
        text = data.decode(source_enc, errors="replace")
        converted = text.encode(target_encoding, errors="replace")
        return converted, result
    except (UnicodeDecodeError, LookupError) as e:
        raise ValueError(f"cannot convert from {result.encoding} to {target_encoding}: {e}")


def strip_bom(data: bytes) -> tuple[bytes, str | None]:
    """Strip BOM from data. Returns (data_without_bom, bom_encoding_or_none)."""
    encoding, bom_len = detect_bom(data)
    if encoding:
        return data[bom_len:], encoding
    return data, None
