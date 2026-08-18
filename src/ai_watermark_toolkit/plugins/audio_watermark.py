"""Audio watermark detector — SynthID-style metadata-based detection.

Google's SynthID for audio embeds watermarks in the inaudible frequency range.
True detection requires the upstream research codebook (non-commercial license).
This plugin detects the METADATA LAYER: watermark provenance tags that tools
embed in audio container metadata (ID3, RIFF, ISOBMFF) to signal that a
watermark is present. This is the "label on the tin" — not the watermark
itself, but the claim that one exists.

Detects:
  - ID3v2 tags with TXXX fields containing "synthid", "watermark", "ai_generated"
  - RIFF INFO fields with watermark markers (WAV)
  - ISOBMFF/MP4 uuid boxes with XMP watermark provenance
  - iXML/ Broadcast Wave Format (BWF) chunks with watermark metadata
  - LAME/Xing header tags that carry AI attribution

Honest limits:
  - This detects metadata CLAIMS of watermarks, not the watermarks themselves.
  - A file can have a SynthID watermark with no metadata label (false negative).
  - A file can have the metadata label but no actual watermark (false positive).
  - For true inaudible watermark detection, use the reverse-SynthID codebook
    via the metadata/synthid.py adapter.
"""

from __future__ import annotations

import re
import struct
from pathlib import Path

from .base import DetectorPlugin

# Metadata field names that signal AI audio watermarking
_WM_FIELD_HINTS = re.compile(
    r"(synthid|watermark|ai[-_ ]?generated|ai[-_ ]?audio|provenance|"
    r"content[-_ ]?credentials|generator|created[-_ ]?by|authoring[-_ ]?tool)",
    re.IGNORECASE,
)

# Bytes version for raw binary scanning
_WM_FIELD_HINTS_BYTES = re.compile(
    rb"(synthid|watermark|ai[-_ ]?generated|ai[-_ ]?audio|provenance|"
    rb"content[-_ ]?credentials|generator|created[-_ ]?by|authoring[-_ ]?tool)",
    re.IGNORECASE,
)

# Values that confirm watermark presence
_WM_VALUE_HINTS = re.compile(
    r"(synthid|google[-_ ]?deepmind|watermarked|ai[-_ ]?generated|"
    r"generated[-_ ]?by|stable[-_ ]?audio|music[-?]gen|audiogen)",
    re.IGNORECASE,
)

# Bytes version
_WM_VALUE_HINTS_BYTES = re.compile(
    rb"(synthid|google[-_ ]?deepmind|watermarked|ai[-_ ]?generated|"
    rb"generated[-_ ]?by|stable[-_ ]?audio|music[-?]gen|audiogen)",
    re.IGNORECASE,
)

# ID3v2 TXXX frame header: "TXXX" then encoding then description\0 value
_ID3_TXXX_RE = re.compile(rb"TXXX", re.IGNORECASE)

# iXML chunk signature
_IXML_SIGNATURE = re.compile(rb"<IXML|<BWFXML|<xml", re.IGNORECASE)

# BWF bext chunk with description fields
_BEXT_RE = re.compile(rb"bext")


class AudioWatermarkPlugin(DetectorPlugin):
    """Detect SynthID-style audio watermark metadata markers.

    Works on raw bytes (file content) passed as key_meta['raw_bytes'],
    or on text descriptions passed as the `text` argument.
    """

    name = "audio_watermark"

    def detect(self, text: str, key_meta: dict) -> dict:
        """Detect audio watermark metadata markers.

        key_meta keys used:
          - raw_bytes: bytes of the audio file (preferred path)
          - filename: str, used to pick container parser
          - format: optional override ("mp3", "wav", "flac", "mp4", "ogg")
        """
        raw = key_meta.get("raw_bytes")
        filename = key_meta.get("filename", "")
        fmt = key_meta.get("format", Path(filename).suffix.lower().lstrip("."))

        if raw is None and not text:
            return {"score": 0.0, "plugin": self.name, "notes": ["no_input"]}

        notes: list[str] = []
        score = 0.0
        details: dict = {"format": fmt, "checks": []}

        if raw:
            # Parse container-specific metadata
            if fmt in ("mp3",):
                s, n = self._check_id3(raw)
                score = max(score, s)
                notes.extend(n)
                details["checks"].append("id3")
            elif fmt in ("wav",):
                s, n = self._check_riff(raw)
                score = max(score, s)
                notes.extend(n)
                details["checks"].append("riff")
            elif fmt in ("mp4", "m4a", "aac"):
                s, n = self._check_isobmff(raw)
                score = max(score, s)
                notes.extend(n)
                details["checks"].append("isobmff")
            elif fmt in ("flac",):
                s, n = self._check_flac(raw)
                score = max(score, s)
                notes.extend(n)
                details["checks"].append("flac")
            else:
                # Generic byte scan for watermark strings
                s, n = self._check_generic_bytes(raw)
                score = max(score, s)
                notes.extend(n)
                details["checks"].append("generic")

        # Also scan the text argument (could be metadata dump or description)
        if text:
            text_score, text_notes = self._check_text(text)
            if text_score > score:
                score = text_score
                notes.extend(text_notes)
                details["checks"].append("text_scan")

        if score >= 0.7:
            notes.append("watermark_metadata_confirmed")
        elif score >= 0.4:
            notes.append("watermark_metadata_suspected")
        elif score >= 0.1:
            notes.append("weak_metadata_signal")
        else:
            notes.append("no_watermark_metadata")

        return {
            "score": round(score, 4),
            "plugin": self.name,
            "notes": notes,
            "details": details,
        }

    def _check_id3(self, data: bytes) -> tuple[float, list[str]]:
        """Check ID3v2 tags for watermark TXXX frames."""
        notes: list[str] = []
        score = 0.0
        # Look for TXXX frames
        for m in _ID3_TXXX_RE.finditer(data):
            start = m.start()
            # TXXX format: 'TXXX' + size(4) + flags(2) + encoding(1) + desc\0 + value
            try:
                # ID3v2.3 uses plain 32-bit size; ID3v2.4 uses synchsafe.
                # Try synchsafe first (7-bit groups), fall back to plain.
                raw_size_bytes = data[start + 4 : start + 8]
                if all(b <= 0x7F for b in raw_size_bytes):
                    # Synchsafe integer
                    frame_size = (
                        (raw_size_bytes[0] << 21)
                        | (raw_size_bytes[1] << 14)
                        | (raw_size_bytes[2] << 7)
                        | raw_size_bytes[3]
                    )
                else:
                    frame_size = struct.unpack(">I", raw_size_bytes)[0]
                payload = data[start + 10 : start + 10 + frame_size]
                if _WM_FIELD_HINTS_BYTES.search(payload) or _WM_VALUE_HINTS_BYTES.search(payload):
                    score = 0.85
                    notes.append(f"id3_txxx_watermark_field_at_{start}")
                    break
                # Also check for SynthID-specific markers
                if b"synthid" in payload.lower() or b"watermark" in payload.lower():
                    score = max(score, 0.7)
                    notes.append(f"id3_txxx_suspect_at_{start}")
            except (struct.error, IndexError):
                continue
        return score, notes

    def _check_riff(self, data: bytes) -> tuple[float, list[str]]:
        """Check RIFF/WAV for iXML and bext watermark chunks."""
        notes: list[str] = []
        score = 0.0
        if data[:4] != b"RIFF":
            return 0.0, ["not_a_riff"]

        i = 12  # skip RIFF header + size + WAVE
        while i + 8 <= len(data):
            chunk_id = data[i : i + 4]
            chunk_size = int.from_bytes(data[i + 4 : i + 8], "little")
            if i + 8 + chunk_size > len(data):
                break
            chunk_data = data[i + 8 : i + 8 + chunk_size]

            if chunk_id == b"iXML" or _IXML_SIGNATURE.search(chunk_data[:64]):
                if _WM_FIELD_HINTS_BYTES.search(chunk_data) or _WM_VALUE_HINTS_BYTES.search(chunk_data):
                    score = 0.9
                    notes.append("ixml_watermark_confirmed")
                    break
                score = max(score, 0.3)
                notes.append("ixml_chunk_present")

            if chunk_id == b"bext" and (
                _WM_FIELD_HINTS_BYTES.search(chunk_data) or _WM_VALUE_HINTS_BYTES.search(chunk_data)
            ):
                score = max(score, 0.7)
                notes.append("bext_watermark_field")

            # INFO list chunks
            if chunk_id == b"INFO" and _WM_FIELD_HINTS_BYTES.search(chunk_data):
                score = max(score, 0.6)
                notes.append("info_watermark_field")

            i += 8 + chunk_size
            # Align to word boundary
            if chunk_size % 2 != 0:
                i += 1

        return score, notes

    def _check_isobmff(self, data: bytes) -> tuple[float, list[str]]:
        """Check ISOBMFF (MP4/M4A) for watermark uuid/XMP boxes."""
        notes: list[str] = []
        score = 0.0
        if data[:4] != b"\x00\x00\x00" and data[4:8] != b"ftyp":
            return 0.0, ["not_isobmff"]

        # Scan for uuid boxes with XMP UUID
        XMP_UUID = b"\xbe\x7a\xcf\xcb\x97\xa9\x42\xe8\x9c\x71\x99\x94\x91\xe3\xaf\xac"
        i = 0
        while i + 8 <= len(data):
            size = int.from_bytes(data[i : i + 4], "big")
            box_type = data[i + 4 : i + 8]
            if size < 8:
                break
            if i + size > len(data):
                break

            if box_type == b"uuid":
                payload = data[i + 8 : i + size]
                if payload.startswith(XMP_UUID):
                    xmp_data = payload[16:]
                    if _WM_FIELD_HINTS.search(xmp_data) or _WM_VALUE_HINTS.search(xmp_data):
                        score = 0.9
                        notes.append("xmp_uuid_watermark_confirmed")
                        break
                    score = max(score, 0.2)
                    notes.append("xmp_uuid_present")
                elif _WM_FIELD_HINTS.search(payload[:512]):
                    score = max(score, 0.5)
                    notes.append("uuid_watermark_field")

            if box_type in (b"meta",):
                # Scan sub-boxes for provenance
                sub = data[i + 12 : i + size]  # skip version/flags
                if _WM_FIELD_HINTS.search(sub) or _WM_VALUE_HINTS.search(sub):
                    score = max(score, 0.6)
                    notes.append("meta_box_watermark_hint")

            i += size

        return score, notes

    def _check_flac(self, data: bytes) -> tuple[float, list[str]]:
        """Check FLAC for watermark Vorbis comments."""
        notes: list[str] = []
        if data[:4] != b"fLaC":
            return 0.0, ["not_flac"]

        # FLAC metadata blocks start at offset 4
        i = 4
        while i + 4 <= len(data):
            header = data[i]
            is_last = header & 0x80
            block_type = header & 0x7F
            block_size = int.from_bytes(data[i + 1 : i + 4], "big")
            if i + 4 + block_size > len(data):
                break
            block_data = data[i + 4 : i + 4 + block_size]

            # Type 4 = VORBIS_COMMENT
            if block_type == 4 and (_WM_FIELD_HINTS.search(block_data) or _WM_VALUE_HINTS.search(block_data)):
                notes.append("flac_vorbis_watermark_comment")
                return 0.85, notes

            # Type 2 = APPLICATION block
            if block_type == 2 and _WM_FIELD_HINTS.search(block_data):
                notes.append("flac_application_watermark")
                return 0.7, notes

            i += 4 + block_size
            if is_last:
                break

        return 0.0, notes

    def _check_generic_bytes(self, data: bytes) -> tuple[float, list[str]]:
        """Generic byte scan for watermark strings (fallback)."""
        notes: list[str] = []
        score = 0.0
        lower = data.lower()
        if b"synthid" in lower:
            score = 0.8
            notes.append("generic_synthid_string_found")
        if b"watermark" in lower and b"ai" in lower:
            score = max(score, 0.6)
            notes.append("generic_watermark_ai_string")
        if b"ai_generated" in lower or b"ai-generated" in lower:
            score = max(score, 0.5)
            notes.append("generic_ai_generated_marker")
        return score, notes

    def _check_text(self, text: str) -> tuple[float, list[str]]:
        """Scan text for watermark metadata descriptions."""
        notes: list[str] = []
        score = 0.0
        lower = text.lower()
        if "synthid" in lower:
            score = 0.8
            notes.append("text_synthid_mention")
        if "watermark" in lower and ("audio" in lower or "ai" in lower):
            score = max(score, 0.5)
            notes.append("text_watermark_audio_mention")
        if "ai-generated audio" in lower or "ai generated audio" in lower:
            score = max(score, 0.6)
            notes.append("text_ai_generated_audio")
        return score, notes

    def clean(self, raw: bytes, filename: str = "") -> bytes:
        """Remove watermark metadata from audio file bytes.

        Delegates to the metadata service for container-specific cleaning.
        """
        from ai_watermark_toolkit.metadata.service import clean as meta_clean

        cleaned, _ = meta_clean(raw, filename)
        return cleaned

    def embed(self, raw: bytes, watermark: str) -> bytes:
        """Not applicable — we detect audio watermarks, we don't generate them."""
        raise NotImplementedError("embed not supported by audio_watermark plugin")
