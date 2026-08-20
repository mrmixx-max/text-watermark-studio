"""Video watermark detector — C2PA / MP4 metadata-based detection.

C2PA (Coalition for Content Provenance and Authenticity) embeds content
credentials in video containers (MP4, MOV, WebM). This plugin detects the
METADATA LAYER: C2PA manifests, XMP provenance, and AI-generation markers
in video file containers.

Detects:
  - C2PA JUMBF boxes in ISOBMFF containers (MP4/MOV)
  - XMP metadata with provenance hints (uuid boxes)
  - WebM C2PA/EXIF chunks
  - Manifest signatures (c2pa.signature)
  - AI generator attribution in video metadata

Honest limits:
  - Detects metadata presence, not pixel-domain watermarks.
  - C2PA soft-binding (remote manifest links) is partially detected.
  - Hard-bound C2PA removal is OUT OF SCOPE — we report, not strip.
  - For full C2PA manifest parsing, use a dedicated C2PA toolchain.
"""

from __future__ import annotations

import re
from pathlib import Path

from .base import DetectorPlugin

# C2PA box types in ISOBMFF
_C2PA_BOX_TYPES = (b"jumb", b"c2pa", b"c2ma", b"c2cs")

# XMP UUID for ISOBMFF uuid boxes
_XMP_UUID = b"\xbe\x7a\xcf\xcb\x97\xa9\x42\xe8\x9c\x71\x99\x94\x91\xe3\xaf\xac"

# AI provenance hints in metadata
_AI_PROVENANCE_HINTS = re.compile(
    r"(c2pa|content[-_ ]?credentials|provenance|ai[-_ ]?generated|"
    r"ai[-_ ]?video|generator|created[-_ ]?by|authoring[-_ ]?tool|"
    r"sora|runway|pika|kling|synthesia|deepfake|stable[-_ ]?video|"
    r"produce?d[-_ ]?by|made[-_ ]?with)",
    re.IGNORECASE,
)

# Bytes version for raw binary scanning
_AI_PROVENANCE_HINTS_BYTES = re.compile(
    rb"(c2pa|content[-_ ]?credentials|provenance|ai[-_ ]?generated|"
    rb"ai[-_ ]?video|generator|created[-_ ]?by|authoring[-_ ]?tool|"
    rb"sora|runway|pika|kling|synthesia|deepfake|stable[-_ ]?video|"
    rb"produce?d[-_ ]?by|made[-_ ]?with)",
    re.IGNORECASE,
)

# Manifest signature markers
_C2PA_MANIFEST_SIG = re.compile(rb"c2pa\.manifest|c2pa\.signature|c2pa\.assertion", re.IGNORECASE)


class VideoWatermarkPlugin(DetectorPlugin):
    """Detect C2PA / content-credentials metadata in video containers.

    Works on raw bytes (file content) passed as key_meta['raw_bytes'],
    or on text descriptions passed as the `text` argument.
    """

    name = "video_watermark"

    def detect(self, text: str, key_meta: dict) -> dict:
        """Detect C2PA / provenance metadata in video files.

        key_meta keys used:
          - raw_bytes: bytes of the video file (preferred path)
          - filename: str, used to pick container parser
          - format: optional override ("mp4", "mov", "webm", "mkv", "avi")
        """
        raw = key_meta.get("raw_bytes")
        filename = key_meta.get("filename", "")
        fmt = key_meta.get("format", Path(filename).suffix.lower().lstrip("."))

        if raw is None and not text:
            return {"score": 0.0, "plugin": self.name, "notes": ["no_input"]}

        notes: list[str] = []
        score = 0.0
        details: dict = {"format": fmt, "checks": [], "c2pa_boxes": [], "xmp_found": False}

        if raw:
            if fmt in ("mp4", "m4v", "m4a", "f4v"):
                s, n, d = self._check_isobmff(raw)
                score = max(score, s)
                notes.extend(n)
                details["checks"].append("isobmff")
                details["c2pa_boxes"] = d.get("c2pa_boxes", [])
                details["xmp_found"] = d.get("xmp_found", False)
            elif fmt in ("mov", "qt"):
                s, n, d = self._check_isobmff(raw)
                score = max(score, s)
                notes.extend(n)
                details["checks"].append("isobmff_mov")
                details["c2pa_boxes"] = d.get("c2pa_boxes", [])
                details["xmp_found"] = d.get("xmp_found", False)
            elif fmt in ("webm",):
                s, n, d = self._check_webm(raw)
                score = max(score, s)
                notes.extend(n)
                details["checks"].append("webm")
                details["c2pa_boxes"] = d.get("c2pa_boxes", [])
            elif fmt in ("mkv", "mka"):
                s, n, d = self._check_matroska(raw)
                score = max(score, s)
                notes.extend(n)
                details["checks"].append("matroska")
                details["c2pa_boxes"] = d.get("c2pa_boxes", [])
            else:
                # Generic scan for C2PA markers
                s, n = self._check_generic_c2pa(raw)
                score = max(score, s)
                notes.extend(n)
                details["checks"].append("generic")

        # Also scan the text argument
        if text:
            text_score, text_notes = self._check_text(text)
            if text_score > score:
                score = text_score
                notes.extend(text_notes)
                details["checks"].append("text_scan")

        if score >= 0.7:
            notes.append("c2pa_metadata_confirmed")
        elif score >= 0.4:
            notes.append("c2pa_metadata_suspected")
        elif score >= 0.1:
            notes.append("weak_metadata_signal")
        else:
            notes.append("no_c2pa_metadata")

        details["manifest_count"] = len(details["c2pa_boxes"])
        return {
            "score": round(score, 4),
            "plugin": self.name,
            "notes": notes,
            "details": details,
        }

    def _iter_isobmff_boxes(self, data: bytes, start: int = 0, end: int | None = None):
        """Yield (fourcc, payload, header_size) for ISOBMFF boxes."""
        i = start
        n = end or len(data)
        while i + 8 <= n:
            size = int.from_bytes(data[i : i + 4], "big")
            fourcc = data[i + 4 : i + 8]
            header = 8
            if size == 1:
                if i + 16 > n:
                    break
                size = int.from_bytes(data[i + 8 : i + 16], "big")
                header = 16
            elif size == 0:
                size = n - i
            if size < header or i + size > n:
                break
            yield fourcc, data[i + header : i + size], header
            i += size

    def _check_isobmff(self, data: bytes) -> tuple[float, list[str], dict]:
        """Check ISOBMFF (MP4/MOV) for C2PA boxes and XMP provenance."""
        notes: list[str] = []
        score = 0.0
        c2pa_boxes: list[str] = []
        xmp_found = False

        # Check ftyp
        boxes = list(self._iter_isobmff_boxes(data))
        if not boxes or boxes[0][0] != b"ftyp":
            return 0.0, ["not_isobmff"], {"c2pa_boxes": [], "xmp_found": False}

        # Recursively scan all boxes (including nested containers)
        score, notes, c2pa_boxes, xmp_found = self._scan_boxes_recursive(boxes, score, notes, c2pa_boxes, xmp_found)

        return score, notes, {"c2pa_boxes": c2pa_boxes, "xmp_found": xmp_found}

    def _scan_boxes_recursive(
        self,
        boxes: list[tuple[bytes, bytes, int]],
        score: float,
        notes: list[str],
        c2pa_boxes: list[str],
        xmp_found: bool,
    ) -> tuple[float, list[str], list[str], bool]:
        """Recursively scan ISOBMFF boxes for C2PA/XMP markers."""
        for fourcc, payload, _header in boxes:
            name = fourcc.decode("latin1", "replace")

            # C2PA JUMBF boxes
            if fourcc in _C2PA_BOX_TYPES or name.lower().startswith("c2"):
                c2pa_boxes.append(name)
                score = 0.9
                notes.append(f"c2pa_box_{name}_found")

            # uuid boxes with XMP
            if fourcc == b"uuid":
                if payload.startswith(_XMP_UUID):
                    xmp_found = True
                    xmp_data = payload[16:]
                    if _AI_PROVENANCE_HINTS_BYTES.search(xmp_data):
                        score = max(score, 0.85)
                        notes.append("xmp_provenance_confirmed")
                    else:
                        score = max(score, 0.3)
                        notes.append("xmp_uuid_present")
                elif _AI_PROVENANCE_HINTS_BYTES.search(payload[:512]):
                    score = max(score, 0.5)
                    notes.append("uuid_provenance_hint")

            # Check for manifest signature strings in any box
            if _C2PA_MANIFEST_SIG.search(payload) and name not in [b"c2pa", b"jumb"]:
                c2pa_boxes.append(f"sig_in_{name}")
                score = max(score, 0.7)
                notes.append(f"manifest_signature_in_{name}")

            # Recurse into container boxes
            if fourcc in (b"moov", b"trak", b"mdia", b"minf", b"stbl", b"dinf", b"edts", b"udta", b"meta"):
                try:
                    sub_start = 4 if fourcc == b"meta" else 0  # meta has version/flags
                    sub_boxes = list(self._iter_isobmff_boxes(payload, start=sub_start))
                    if sub_boxes:
                        score, notes, c2pa_boxes, xmp_found = self._scan_boxes_recursive(
                            sub_boxes,
                            score,
                            notes,
                            c2pa_boxes,
                            xmp_found,
                        )
                except (ValueError, TypeError, AttributeError):
                    pass

        return score, notes, c2pa_boxes, xmp_found

    def _check_webm(self, data: bytes) -> tuple[float, list[str], dict]:
        """Check WebM for C2PA and XMP metadata chunks."""
        notes: list[str] = []
        score = 0.0
        c2pa_boxes: list[str] = []

        # WebM uses EBML — simplified scan for known chunk IDs
        # C2PA in WebM uses the same ISOBMFF-style boxes embedded in EBML
        if data[:4] != b"\x1a\x45\xdf\xa3":
            return 0.0, ["not_webm"], {"c2pa_boxes": []}

        # Scan for C2PA box signatures anywhere in the file
        # (EBML doesn't use fixed offsets, so we scan)
        lower = data.lower()
        if b"c2pa" in lower or b"jumbf" in lower:
            score = 0.85
            notes.append("webm_c2pa_marker_found")
            c2pa_boxes.append("c2pa_via_ebml")
        if b"xmp" in lower:
            score = max(score, 0.4)
            notes.append("webm_xmp_marker")
        if b"provenance" in lower:
            score = max(score, 0.5)
            notes.append("webm_provenance_marker")

        return score, notes, {"c2pa_boxes": c2pa_boxes}

    def _check_matroska(self, data: bytes) -> tuple[float, list[str], dict]:
        """Check Matroska (MKV) for C2PA/XMP tags."""
        notes: list[str] = []
        score = 0.0
        c2pa_boxes: list[str] = []

        if data[:4] != b"\x1a\x45\xdf\xa3":
            return 0.0, ["not_matroska"], {"c2pa_boxes": []}

        lower = data.lower()
        if b"c2pa" in lower:
            score = 0.85
            notes.append("mkv_c2pa_marker")
            c2pa_boxes.append("c2pa_via_ebml")
        if b"xmp" in lower or b"provenance" in lower:
            score = max(score, 0.4)
            notes.append("mkv_provenance_marker")

        return score, notes, {"c2pa_boxes": c2pa_boxes}

    def _check_generic_c2pa(self, data: bytes) -> tuple[float, list[str]]:
        """Generic byte scan for C2PA markers (fallback)."""
        notes: list[str] = []
        score = 0.0
        lower = data.lower()

        if b"c2pa" in lower:
            score = 0.8
            notes.append("generic_c2pa_string")
        if b"jumbf" in lower:
            score = max(score, 0.7)
            notes.append("generic_jumbf_string")
        if b"contentcredentials" in lower.replace(b" ", b""):
            score = max(score, 0.75)
            notes.append("generic_content_credentials")
        if b"manifest" in lower and b"signature" in lower:
            score = max(score, 0.5)
            notes.append("generic_manifest_signature")

        return score, notes

    def _check_text(self, text: str) -> tuple[float, list[str]]:
        """Scan text for C2PA provenance descriptions."""
        notes: list[str] = []
        score = 0.0
        lower = text.lower()

        if "c2pa" in lower or "content credentials" in lower:
            score = 0.8
            notes.append("text_c2pa_mention")
        if "provenance" in lower and ("video" in lower or "ai" in lower):
            score = max(score, 0.5)
            notes.append("text_provenance_video")
        if "ai-generated video" in lower or "ai generated video" in lower:
            score = max(score, 0.6)
            notes.append("text_ai_generated_video")

        return score, notes

    def clean(self, raw: bytes, filename: str = "") -> bytes:
        """Remove C2PA metadata boxes from video file bytes.

        Delegates to the metadata service for container-specific cleaning.
        Note: hard-bound C2PA may not be fully removable by byte-level ops.
        """
        from ai_watermark_toolkit.metadata.service import clean as meta_clean

        cleaned, _ = meta_clean(raw, filename)
        return cleaned

    def embed(self, raw: bytes, watermark: str) -> bytes:
        """Not applicable — we detect video watermarks, we don't generate them."""
        raise NotImplementedError("embed not supported by video_watermark plugin")
