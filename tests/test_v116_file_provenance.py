"""Behavioral tests for keyed file provenance + SynthID adapter (2026-08-13).

Roundtrip contract: embed with a key -> detect with the SAME key validates
(HMAC). Tampering with the content breaks the signature. Unknown key ->
found but invalid.
"""

import io
import struct
import zipfile

from ai_watermark_toolkit.metadata.provenance import (
    detect_provenance,
    embed_provenance,
)
from ai_watermark_toolkit.metadata.synthid import score_synthid, synthid_available

KEY = "roundtrip-key-1"
SECRET = "roundtrip-secret-abc"
OTHER_SECRET = "other-secret-xyz"


def _png_chunk(ctype: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + ctype + payload + struct.pack(">I", 0)


def make_png() -> bytes:
    ihdr = _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    idat = _png_chunk(b"IDAT", b"\x00")
    iend = _png_chunk(b"IEND", b"")
    return b"\x89PNG\r\n\x1a\n" + ihdr + idat + iend


def make_jpeg() -> bytes:
    return b"\xff\xd8" + b"\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00" + b"\xff\xd9"


def make_docx() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", "<w:document>hello</w:document>")
    return buf.getvalue()


class TestFileRoundtrip:
    def test_png_roundtrip(self):
        data = make_png()
        emb = embed_provenance(data, "a.png", KEY, SECRET)
        assert emb.embedded
        res = detect_provenance(emb.data, "a.png", {KEY: SECRET})
        assert res.found and res.valid and res.key_id == KEY, res.to_dict()

    def test_jpeg_roundtrip(self):
        data = make_jpeg()
        emb = embed_provenance(data, "b.jpg", KEY, SECRET)
        assert emb.embedded
        res = detect_provenance(emb.data, "b.jpg", {KEY: SECRET})
        assert res.found and res.valid, res.to_dict()

    def test_svg_roundtrip(self):
        data = b'<svg xmlns="http://www.w3.org/2000/svg"><circle/></svg>'
        emb = embed_provenance(data, "c.svg", KEY, SECRET)
        res = detect_provenance(emb.data, "c.svg", {KEY: SECRET})
        assert res.found and res.valid, res.to_dict()

    def test_html_roundtrip(self):
        data = b"<html><body>hi</body></html>"
        emb = embed_provenance(data, "d.html", KEY, SECRET)
        res = detect_provenance(emb.data, "d.html", {KEY: SECRET})
        assert res.found and res.valid, res.to_dict()

    def test_markdown_roundtrip(self):
        data = b"# Title\n\nBody text here.\n"
        emb = embed_provenance(data, "e.md", KEY, SECRET)
        res = detect_provenance(emb.data, "e.md", {KEY: SECRET})
        assert res.found and res.valid, res.to_dict()

    def test_docx_roundtrip_content_bound(self):
        data = make_docx()
        emb = embed_provenance(data, "f.docx", KEY, SECRET)
        assert emb.embedded
        res = detect_provenance(emb.data, "f.docx", {KEY: SECRET})
        assert res.found and res.valid, res.to_dict()

    def test_pdf_roundtrip(self):
        data = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF"
        emb = embed_provenance(data, "g.pdf", KEY, SECRET)
        res = detect_provenance(emb.data, "g.pdf", {KEY: SECRET})
        assert res.found and res.valid, res.to_dict()


class TestTamperProtection:
    def test_tampered_content_invalidates(self):
        data = make_png()
        emb = embed_provenance(data, "a.png", KEY, SECRET)
        # flip a byte in the CONTENT area (after the mark chunk), not inside the mark
        tampered = emb.data[:-20] + b"\xff" + emb.data[-19:]
        res = detect_provenance(tampered, "a.png", {KEY: SECRET})
        assert res.found and not res.valid, res.to_dict()
        assert "hmac" in res.reason

    def test_unknown_key_found_but_invalid(self):
        data = make_png()
        emb = embed_provenance(data, "a.png", KEY, SECRET)
        res = detect_provenance(emb.data, "a.png", {KEY: OTHER_SECRET})
        assert res.found and not res.valid
        assert "unknown_key" in res.reason

    def test_clean_file_has_no_mark(self):
        res = detect_provenance(make_png(), "a.png", {KEY: SECRET})
        assert not res.found

    def test_unsupported_format(self):
        res = detect_provenance(b"data", "x.exe", {KEY: SECRET})
        assert not res.found and res.reason == "unsupported_format"


class TestSynthidAdapter:
    def test_unavailable_without_checkout(self, tmp_path, monkeypatch):
        monkeypatch.setenv("REVERSE_SYNTHID_DIR", str(tmp_path / "nope"))
        r = score_synthid(str(tmp_path / "missing.png"))
        assert r["available"] is False
        assert "checkout_not_found" in r["reason"]

    def test_available_detection(self, tmp_path):
        d = tmp_path / "checkout"
        assert synthid_available(str(d)) is False
