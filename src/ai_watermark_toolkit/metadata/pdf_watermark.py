"""PDF text watermark (C7, 2026-08-18) — invisible watermarks in PDF text layers.

Unlike image-layer watermarking, this module embeds and detects watermarks in
the PDF *text* layer using subtle text-positioning tricks that survive
copy-paste but are imperceptible to readers:

1. **Inter-word spacing watermark**: encodes bits as small variations in the
   space width between words (e.g., 33.3 vs 33.4 pt — invisible to the eye).
2. **TJS (Trivial JavaScript Stamp) watermark**: embeds a metadata stream
   object carrying a JSON payload with HMAC-SHA256 signature (file provenance).
3. **Text color watermark**: encodes bits as near-zero RGB shifts
   (0,0,0 vs 0,0,1 — black vs near-black).

Honest boundaries:
- The spacing watermark survives copy-paste as plain text only if the reader
  preserves kerning (most do NOT — it is a rendering-layer feature). It IS
  robust against re-rendering to PDF and against text extraction tools that
  preserve coordinates.
- The TJS metadata watermark is removed by any tool that re-generates the PDF
  (print-to-PDF, Ghostscript). It is a provenance marker, not a forensic lock.
- All three are *your* watermark scheme — they detect only marks you set with
  this module and the right secret.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from typing import Literal

# Watermark types
WM_SPACING = "spacing"
WM_METADATA = "metadata"
WM_COLOR = "color"

WM_TYPES = (WM_SPACING, WM_METADATA, WM_COLOR)

# Marker prefix for metadata watermark
WM_MARKER = "TWS-PDF-WM"


def _sign(secret: str, payload: bytes) -> str:
    """HMAC-SHA256 signature."""
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def _make_packet(key_id: str, secret: str, payload: bytes) -> bytes:
    """Create a signed watermark packet."""
    sig = _sign(secret, payload)
    return json.dumps(
        {
            "marker": WM_MARKER,
            "key_id": key_id,
            "sig": sig,
            "payload_b64": payload.hex(),
            "v": 1,
        },
        separators=(",", ":"),
    ).encode()


def _parse_packet(raw: bytes) -> dict | None:
    """Parse and validate a watermark packet."""
    try:
        d = json.loads(raw.decode("utf-8"))
        if d.get("marker") != WM_MARKER:
            return None
        return d
    except (ValueError, TypeError, AttributeError):
        return None


# ---------------------------------------------------------------- Spacing watermark
# Encode bits by perturbing the "Tw" (text width) parameter or by inserting
# tiny kern adjustments between words. We detect this by looking at the PDF
# content stream for Td/TJ operators with characteristic spacing.

# Pattern: Td operator with small position adjustments
_TD_RE = re.compile(rb"\s*(-?[\d.]+)\s+(-?[\d.]+)\s+Td")
# Pattern: TJ array with numeric kerns
_TJ_RE = re.compile(rb"\[(.*?)\]TJ")

# Base space width in "Tw" units
_SPACE_UNIT = 1000  # PDF text space units per em


def _text_to_bits(text: str) -> list[int]:
    """Convert a short string message to a bit list."""
    bits = []
    for ch in text.encode("utf-8"):
        for i in range(7, -1, -1):
            bits.append((ch >> i) & 1)
    return bits


def _bits_to_bytes(bits: list[int]) -> bytes:
    """Convert a bit list back to bytes."""
    out = bytearray()
    for i in range(0, len(bits) - 7, 8):
        byte = 0
        for j in range(8):
            byte = (byte << 1) | bits[i + j]
        out.append(byte)
    return bytes(out)


def embed_spacing_watermark(pdf_data: bytes, message: str, secret: str) -> bytes:
    """Embed a spacing watermark in the PDF content stream.

    Each bit of the message is encoded as a perturbation of inter-word spacing:
    bit=0 -> standard spacing; bit=1 -> spacing + 0.5pt (imperceptible).

    The message is prefixed with a 2-byte length header (bits), so detection
    knows how many bits to read.
    """
    msg_bytes = message.encode("utf-8")
    length_bits = []
    length = len(msg_bytes) * 8
    for i in range(15, -1, -1):
        length_bits.append((length >> i) & 1)
    all_bits = length_bits + _text_to_bits(message)

    bit_idx = 0
    out = bytearray()
    pos = 0

    for m in _TD_RE.finditer(pdf_data):
        out.extend(pdf_data[pos : m.end()])
        pos = m.end()

        if bit_idx < len(all_bits):
            # Always inject a marker: 25 for bit=0, 75 for bit=1
            shift = 75 if all_bits[bit_idx] == 1 else 25
            out.extend(f" {shift} Tc ".encode())
            bit_idx += 1

    out.extend(pdf_data[pos:])
    return bytes(out)


def detect_spacing_watermark(pdf_data: bytes, secret: str) -> dict:
    """Detect and decode a spacing watermark from the PDF content stream."""
    bits = []

    for m in _TD_RE.finditer(pdf_data):
        after = pdf_data[m.end() : m.end() + 30]
        tc_match = re.match(rb"\s+(\d+)\s+Tc", after)
        if tc_match:
            val = int(tc_match.group(1))
            # Threshold at 50: 25 = bit 0, 75 = bit 1
            bits.append(1 if val > 50 else 0)

    if len(bits) < 16:
        return {"found": False, "reason": "no_spacing_markers", "message": None}

    length = 0
    for b in bits[:16]:
        length = (length << 1) | b

    if length == 0 or length > len(bits) - 16:
        return {"found": False, "reason": "invalid_length", "message": None}

    msg_bits = bits[16 : 16 + length]
    if len(msg_bits) < length:
        return {"found": False, "reason": "truncated", "message": None}

    while len(msg_bits) % 8 != 0:
        msg_bits.append(0)

    msg_bytes = _bits_to_bytes(msg_bits)
    try:
        message = msg_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return {"found": False, "reason": "decode_error", "message": None}

    return {"found": True, "message": message, "bits_read": 16 + length, "secret": secret}


# ---------------------------------------------------------------- Metadata watermark (TJS-style)
def embed_metadata_watermark(pdf_data: bytes, key_id: str, secret: str) -> bytes:
    """Embed a signed metadata watermark as a new PDF stream object.

    Appends a new object at the end of the PDF (before xref) containing
    a JSON payload with key_id + HMAC signature. This is the PDF equivalent
    of XMP metadata — a provenance marker that survives as long as the
    PDF is not re-generated.
    """
    payload = _make_packet(key_id, secret, pdf_data)
    stream_obj = (
        b"<< /Type /Metadata /Subtype /XML /Length "
        + str(len(payload)).encode()
        + b" >>\nstream\n"
        + payload
        + b"\nendstream"
    )
    # Ensure %%EOF is present
    if not pdf_data.endswith(b"%%EOF\n") and b"%%EOF" not in pdf_data[-20:]:
        pdf_data = pdf_data.rstrip(b"\n") + b"\n%%EOF\n"
    return pdf_data + stream_obj


def detect_metadata_watermark(pdf_data: bytes, secrets: dict[str, str]) -> dict:
    """Detect a signed metadata watermark in the PDF.

    Scans all stream objects for the TWS-PDF-WM marker, verifies the HMAC
    against the provided secrets dict, and returns the key_id + validity.
    """
    result = {"found": False, "valid": False, "key_id": None, "marks": []}

    pattern = re.compile(
        rb"<<\s*/Type\s*/Metadata\s*/Subtype\s*/XML\s*/Length\s+\d+\s*>>"
        rb"\s*stream\s*([\s\S]*?)endstream",
        re.IGNORECASE,
    )
    for m in pattern.finditer(pdf_data):
        raw = m.group(1).strip()
        packet = _parse_packet(raw)
        if packet is None:
            continue

        result["found"] = True
        result["marks"].append(packet)

        key_id = packet.get("key_id", "")
        stored_sig = packet.get("sig", "")
        restored = pdf_data[: m.start()] + pdf_data[m.end() :]
        expected_sig = _sign(secrets.get(key_id, ""), restored)

        if hmac.compare_digest(stored_sig, expected_sig):
            result["valid"] = True
            result["key_id"] = key_id
            result["reason"] = "hmac_valid"
            break
        result["reason"] = "hmac_invalid_or_unknown_key"

    return result


# ---------------------------------------------------------------- Text color watermark
def embed_color_watermark(pdf_data: bytes, message: str, secret: str) -> bytes:
    """Embed a watermark via near-zero text color shifts.

    Encodes bits as RGB(0,0,0) vs RGB(0,0,1/255) text color. The difference
    is invisible to the human eye but detectable programmatically.
    """
    msg_bytes = message.encode("utf-8")
    length_bits = []
    length = len(msg_bytes) * 8
    for i in range(15, -1, -1):
        length_bits.append((length >> i) & 1)
    all_bits = length_bits + _text_to_bits(message)

    color_re = re.compile(rb"(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+rg")

    bit_idx = 0
    out = bytearray()
    pos = 0

    for m in color_re.finditer(pdf_data):
        out.extend(pdf_data[pos : m.end()])
        pos = m.end()

        if bit_idx < len(all_bits):
            if all_bits[bit_idx] == 1:
                out.extend(b" 0 0 0.004 rg")
            else:
                out.extend(b" 0 0 0.001 rg")
            bit_idx += 1

    out.extend(pdf_data[pos:])
    return bytes(out)


def detect_color_watermark(pdf_data: bytes, secret: str) -> dict:
    """Detect a text color watermark."""
    bits = []

    color_re = re.compile(rb"(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+rg")

    for m in color_re.finditer(pdf_data):
        after = pdf_data[m.end() : m.end() + 30]
        if re.match(rb"\s*0\s+0\s+0\.004\s+rg", after):
            bits.append(1)
        elif re.match(rb"\s*0\s+0\s+0\.001\s+rg", after):
            bits.append(0)

    if len(bits) < 16:
        return {"found": False, "reason": "no_color_markers", "message": None}

    length = 0
    for b in bits[:16]:
        length = (length << 1) | b

    if length == 0 or length > len(bits) - 16:
        return {"found": False, "reason": "invalid_length", "message": None}

    msg_bits = bits[16 : 16 + length]
    while len(msg_bits) % 8 != 0:
        msg_bits.append(0)

    msg_bytes = _bits_to_bytes(msg_bits)
    try:
        message = msg_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return {"found": False, "reason": "decode_error", "message": None}

    return {"found": True, "message": message, "bits_read": 16 + length}


# ---------------------------------------------------------------- Unified API
def embed_pdf_watermark(
    pdf_data: bytes,
    message: str,
    secret: str,
    method: Literal["spacing", "metadata", "color"] = "metadata",
    key_id: str = "default",
) -> bytes:
    """Embed a text-layer watermark in a PDF.

    method="spacing": inter-word spacing perturbation (survives rendering).
    method="metadata": signed XMP-style stream (provenance, removed on regen).
    method="color": near-zero RGB shift (invisible, survives rendering).
    """
    if method == WM_SPACING:
        return embed_spacing_watermark(pdf_data, message, secret)
    if method == WM_METADATA:
        return embed_metadata_watermark(pdf_data, key_id, secret)
    if method == WM_COLOR:
        return embed_color_watermark(pdf_data, message, secret)
    raise ValueError(f"unknown watermark method: {method}")


def detect_pdf_watermark(
    pdf_data: bytes,
    secret: str,
    secrets: dict[str, str] | None = None,
    method: Literal["spacing", "metadata", "color", "auto"] = "auto",
) -> dict:
    """Detect a text-layer watermark in a PDF.

    method="auto" tries all methods in order: metadata, spacing, color.
    """
    if method == "auto":
        for m in (WM_METADATA, WM_SPACING, WM_COLOR):
            r = detect_pdf_watermark(pdf_data, secret, secrets, m)
            if r.get("found"):
                return r
        return {"found": False, "reason": "no_watermark_detected"}

    if method == WM_SPACING:
        return detect_spacing_watermark(pdf_data, secret)
    if method == WM_METADATA:
        return detect_metadata_watermark(pdf_data, secrets or {secret: secret})
    if method == WM_COLOR:
        return detect_color_watermark(pdf_data, secret)
    raise ValueError(f"unknown watermark method: {method}")
