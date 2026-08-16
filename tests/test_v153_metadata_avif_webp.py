"""AVIF/HEIC (ISOBMFF) + WebP (RIFF) metadata stripping (2026-08-16).

Contract under test:
- _isobmff: drops top-level `jumb`/`c2pa` boxes (C2PA/JUMBF), `uuid` boxes
  carrying the XMP UUID, and AI-hint `uuid` boxes; recursively cleans the
  `meta` FullBox (C2PA sub-boxes, XMP uuid sub-boxes, AI xml/bxml sub-boxes)
  while PRESERVING innocent sub-boxes (hdlr, pitt, ...). Cleaned output must
  be re-parseable and the offending markers gone. 64-bit largesize boxes
  (size==1) are handled.
- _webp: drops EXIF / "XMP " / C2PA chunks and AI-hint ICCP profiles while
  preserving VP8/VP8L image chunks.
- clean()/inspect() dispatch by extension (avif, heic, webp).
- Honest boundary: no claim of pixel-level removal — only container
  metadata. hard-bound C2PA *content* watermarks are NOT removed (same as
  the rest of the layer); the report names what was verifiably removed.

Fixtures are built in-memory (deterministic, portable, no data/ writes).
"""

import struct

from ai_watermark_toolkit.metadata.service import (
    XMP_UUID,
    clean,
    inspect,
    verify_clean,
    SUPPORTED,
)


def _box(fourcc: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload) + 8) + fourcc + payload


def _full_box(fourcc: bytes, version: int, flags: int, payload: bytes) -> bytes:
    vf = struct.pack(">I", (version << 24) | (flags & 0xFFFFFF))
    return _box(fourcc, vf + payload)


def _minimal_avif_with_c2pa_and_xmp() -> bytes:
    ftyp = _box(b"ftyp", b"avif\x00\x00\x00\x00avifmif1")
    jumb_sub = _box(b"jumb", b"c2pa.manifest.store.v1")
    xmp_uuid_sub = _box(
        b"uuid",
        XMP_UUID
        + b"<?xpacket begin='' id='W5M0MpCehiHzreSzNTczkc9d'?>"
        b"<x:xmpmeta xmlns:x='adobe:ns:meta/'><rdf:RDF "
        b"xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#'>"
        b"<rdf:Description rdf:about='' xmlns:ai='http://ns.adobe.com/ai/'>"
        b"<ai:GeneratedBy>Midjourney</ai:GeneratedBy></rdf:Description>"
        b"</rdf:RDF></x:xmpmeta>",
    )
    hdlr = _full_box(
        b"hdlr", 0, 0,
        b"\x00\x00\x00\x00pict\x00\x00\x00\x00\x00\x00\x00\x00"
        b"\x00\x00\x00\x00PictureHandler\x00",
    )
    meta = _full_box(b"meta", 0, 0, hdlr + jumb_sub + xmp_uuid_sub)
    top_jumb = _box(b"jumb", b"c2pa.claim.v1 contentcredentials")
    mdat = _box(b"mdat", b"\x00\x01\x02\x03\x04\x05image_pixel_data")
    return ftyp + meta + top_jumb + mdat


def _minimal_heic_plain() -> bytes:
    ftyp = _box(b"ftyp", b"heic\x00\x00\x00\x00mif1heic")
    meta = _full_box(
        b"meta", 0, 0,
        _full_box(b"hdlr", 0, 0,
                  b"\x00\x00\x00\x00pict\x00\x00\x00\x00\x00\x00\x00\x00"
                  b"\x00\x00\x00\x00PictureHandler\x00"),
    )
    mdat = _box(b"mdat", b"\x0a\x0b\x0c")
    return ftyp + meta + mdat


def _avif_with_largesize_jumb() -> bytes:
    """jumb box encoded with the 64-bit largesize escape (size field = 1)."""
    ftyp = _box(b"ftyp", b"avif\x00\x00\x00\x00avifmif1")
    payload = b"c2pa.manifest.store.v1"
    jumb = struct.pack(">I", 1) + b"jumb" + struct.pack(">Q", 16 + len(payload)) + payload
    mdat = _box(b"mdat", b"\x01\x02")
    return ftyp + jumb + mdat


def _minimal_webp_with_meta() -> bytes:
    vp8 = b"VP8 " + struct.pack("<I", 4) + b"\x00\x01\x02\x03"
    exif = b"EXIF" + struct.pack("<I", 4) + b"Exif"
    xmp_payload = b"<x:xmpmeta><ai:GeneratedBy>x</ai:GeneratedBy></x:xmpmeta>"
    xmp = b"XMP " + struct.pack("<I", len(xmp_payload)) + xmp_payload
    c2pa = b"C2PA" + struct.pack("<I", 8) + b"c2pa.claim"
    body = vp8 + exif + xmp + c2pa
    return b"RIFF" + struct.pack("<I", len(body) + 4) + b"WEBP" + body


def _minimal_webp_plain() -> bytes:
    vp8 = b"VP8 " + struct.pack("<I", 4) + b"\x00\x01\x02\x03"
    body = vp8
    return b"RIFF" + struct.pack("<I", len(body) + 4) + b"WEBP" + body


class TestIsobmffAvif:
    def test_drops_c2pa_and_xmp(self):
        data = _minimal_avif_with_c2pa_and_xmp()
        cleaned, rep = clean(data, "shot.avif")
        assert rep["format"] == "avif"
        assert "removed_top_level_jumb_c2pa_box" in rep["actions"]
        assert "removed_meta_subbox_jumb_c2pa" in rep["actions"]
        assert "removed_meta_subbox_uuid_xmp" in rep["actions"]
        assert b"jumb" not in cleaned
        assert XMP_UUID not in cleaned
        assert b"c2pa" not in cleaned.lower()
        # ftyp + mdat survive
        assert cleaned[:8] == struct.pack(">I", len(b"avif\x00\x00\x00\x00avifmif1") + 8) + b"ftyp"
        assert b"mdat" in cleaned
        assert len(cleaned) < len(data)

    def test_inspect_reports_but_keeps_data(self):
        data = _minimal_avif_with_c2pa_and_xmp()
        rep = inspect(data, "shot.avif")
        assert rep["format"] == "avif"
        assert len(rep["actions"]) > 0
        # inspect must not mutate: no cleaned field in dict
        assert "cleaned" not in rep

    def test_plain_avif_untouched(self):
        data = _minimal_heic_plain()  # avif-compatible structure (ftyp/meta/mdat)
        cleaned, rep = clean(data, "plain.avif")
        assert rep["format"] == "avif"
        assert cleaned == data

    def test_largesize_jumb_removed(self):
        data = _avif_with_largesize_jumb()
        cleaned, rep = clean(data, "big.avif")
        assert "removed_top_level_jumb_c2pa_box" in rep["actions"]
        assert b"jumb" not in cleaned


class TestIsobmffHeic:
    def test_heic_dispatch(self):
        data = _minimal_avif_with_c2pa_and_xmp()
        cleaned, rep = clean(data, "photo.heic")
        assert rep["format"] == "heic"
        assert "removed_meta_subbox_jumb_c2pa" in rep["actions"]
        assert b"jumb" not in cleaned


class TestWebp:
    def test_drops_exif_xmp_c2pa_chunks(self):
        data = _minimal_webp_with_meta()
        cleaned, rep = clean(data, "img.webp")
        assert rep["format"] == "webp"
        assert "removed_EXIF_chunk" in rep["actions"]
        assert "removed_XMP _chunk" in rep["actions"]  # FourCC "XMP " keeps its trailing space
        assert "removed_C2PA_chunk" in rep["actions"]
        assert b"EXIF" not in cleaned
        assert b"XMP " not in cleaned
        assert b"C2PA" not in cleaned
        # image data survives
        assert b"VP8 " in cleaned
        assert cleaned[:4] == b"RIFF"
        assert len(cleaned) < len(data)

    def test_plain_webp_untouched(self):
        data = _minimal_webp_plain()
        cleaned, rep = clean(data, "img.webp")
        assert rep["format"] == "webp"
        assert cleaned == data

    def test_not_a_webp(self):
        cleaned, rep = clean(b"NOTRIFF....", "fake.webp")
        assert "not_a_webp" in rep["actions"]


class TestVerifyClean:
    def test_avif_verified_clear(self):
        data = _minimal_avif_with_c2pa_and_xmp()
        v = verify_clean(data, "shot.avif")
        assert v["c2pa_before"] is True
        assert v["c2pa_after"] is False
        assert v["c2pa_cleared"] is True
        assert v["c2pa_residual"] is False
        assert v["verification"] == "verified_clear"

    def test_webp_verified_clear(self):
        data = _minimal_webp_with_meta()
        v = verify_clean(data, "img.webp")
        assert v["verification"] == "verified_clear"
        assert v["c2pa_cleared"] is True

    def test_plain_avif_no_c2pa(self):
        data = _minimal_heic_plain()
        v = verify_clean(data, "plain.avif")
        assert v["verification"] == "no_c2pa_present"
        assert v["c2pa_cleared"] is False

    def test_unsupported_format(self):
        v = verify_clean(b"data", "file.xyz")
        assert v["verification"] == "unsupported_format"


class TestDispatch:
    def test_supported_formats_extended(self):
        assert "avif" in SUPPORTED
        assert "heic" in SUPPORTED
        assert "webp" in SUPPORTED

    def test_unsupported_still_unsupported(self):
        cleaned, rep = clean(b"data", "file.xyz")
        assert "unsupported_format" in rep["actions"]
