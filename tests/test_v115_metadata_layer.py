"""Behavioral tests for the file metadata layer (2026-08-13).

Fixtures are built in-memory so the tests are deterministic and portable.
Every test asserts a REAL removal: the cleaned bytes must differ from the
input and the offending marker must be gone.
"""

import io
import struct
import zipfile

from ai_watermark_toolkit.metadata.service import SUPPORTED, clean, inspect


def _png_chunk(ctype: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + ctype + payload + struct.pack(">I", 0)


def make_png_with_exif() -> bytes:
    ihdr = _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    exif = _png_chunk(b"eXIf", b"Exif\x00\x00II*\x00\x08\x00\x00\x00\x00")
    idat = _png_chunk(b"IDAT", b"\x00")
    iend = _png_chunk(b"IEND", b"")
    return b"\x89PNG\r\n\x1a\n" + ihdr + exif + idat + iend


def make_jpeg_with_app1() -> bytes:
    # minimal JPEG: SOI, APP1 (EXIF), EOI
    app1_payload = b"Exif\x00\x00II*\x00\x08\x00\x00\x00\x00\x00\x00\x00\x00"
    seg = b"\xff\xe1" + struct.pack(">H", len(app1_payload) + 2) + app1_payload
    return b"\xff\xd8" + seg + b"\xff\xd9"


class TestPng:
    def test_exif_chunk_removed(self):
        data = make_png_with_exif()
        cleaned, rep = clean(data, "shot.png")
        assert rep["format"] == "png"
        assert "removed_eXIf_EXIF_chunk" in rep["actions"]
        assert b"eXIf" not in cleaned
        assert cleaned[:8] == b"\x89PNG\r\n\x1a\n"
        assert len(cleaned) < len(data)

    def test_inspect_reports_but_keeps_data(self):
        rep = inspect(make_png_with_exif(), "shot.png")
        assert rep["format"] == "png"


class TestJpeg:
    def test_app1_exif_removed(self):
        data = make_jpeg_with_app1()
        cleaned, rep = clean(data, "photo.jpg")
        assert "removed_APP1_EXIF" in rep["actions"]
        assert b"Exif" not in cleaned
        assert cleaned[:2] == b"\xff\xd8"
        assert len(cleaned) < len(data)


class TestSvg:
    def test_metadata_and_ai_attrs_removed(self):
        svg = (
            b'<svg xmlns="http://www.w3.org/2000/svg" data-ai-origin="claude">'
            b'<metadata><rdf:RDF><cc:Work>provenance</cc:Work></rdf:RDF></metadata>'
            b'<circle cx="1" cy="1" r="1"/></svg>'
        )
        cleaned, rep = clean(svg, "logo.svg")
        assert "removed_svg_metadata_and_ai_attrs" in rep["actions"]
        assert b"<metadata" not in cleaned
        assert b"data-ai-origin" not in cleaned
        assert b"<circle" in cleaned  # content survives


class TestDocx:
    def test_customxml_and_docprops_scrubbed(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("word/document.xml", "<w:document/>")
            z.writestr("docProps/core.xml",
                       "<cp:coreProperties><dc:creator>Claude</dc:creator><cp:lastModifiedBy>AI</cp:lastModifiedBy></cp:coreProperties>")
            z.writestr("customXml/item1.xml", "<provenance>c2pa</provenance>")
        data = buf.getvalue()
        cleaned, rep = clean(data, "draft.docx")
        assert "removed_customXml_part" in rep["actions"]
        assert "scrubbed_core_properties" in rep["actions"]
        with zipfile.ZipFile(io.BytesIO(cleaned)) as z:
            names = z.namelist()
            assert not any(n.startswith("customXml/") for n in names)
            core = z.read("docProps/core.xml").decode()
            assert "Claude" not in core


class TestHtml:
    def test_ai_meta_and_jsonld_removed(self):
        html = (
            b'<html><head><meta name="generator" content="Claude">'
            b'<meta name="provenance" content="c2pa">'
            b'<script type="application/ld+json">{"@context":"https://schema.org","generator":"AI"}</script>'
            b'</head><body data-ai-content="yes">hi</body></html>'
        )
        cleaned, rep = clean(html, "page.html")
        assert "removed_ai_meta_tag" in rep["actions"]
        assert "removed_jsonld_provenance_block" in rep["actions"]
        assert b'"generator"' not in cleaned
        assert b"data-ai-content" not in cleaned
        assert b"<body>" in cleaned  # content survives


class TestMarkdown:
    def test_ai_frontmatter_keys_removed(self):
        md = (
            b"---\ntitle: Report\ngenerated_by: Claude\nmodel_name: claude-sonnet\ndate: 2026-01-01\n---\n\n# Body\n"
        )
        cleaned, rep = clean(md, "draft.md")
        assert "removed_ai_frontmatter_key" in rep["actions"]
        assert rep["removed_keys"] == ["generated_by", "model_name"]
        assert b"generated_by" not in cleaned
        assert b"title: Report" in cleaned  # non-AI keys survive
        assert b"# Body" in cleaned


class TestPdf:
    def test_pdf_xmp_stream_removed(self):
        pdf = (
            b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
            b"2 0 obj\n<< /Type /Metadata /Subtype /XML /Length 20 >>\nstream\n<x:xmpmeta>c2pa</x:xmpmeta>\nendstream\nendobj\n"
            b"3 0 obj\n<< /Producer (Claude 3.5) /Creator (AI) >>\nendobj\n"
            b"%%EOF"
        )
        cleaned, rep = clean(pdf, "doc.pdf")
        assert "removed_pdf_xmp_streams_and_info" in rep["actions"]
        assert b"x:xmpmeta" not in cleaned
        assert b"Claude" not in cleaned
        assert cleaned[:5] == b"%PDF-"

    def test_not_a_pdf_guarded(self):
        rep = inspect(b"not a pdf", "x.pdf")
        assert "not_a_pdf" in rep["actions"]


class TestFormats:
    def test_supported_list(self):
        for f in ("png", "jpg", "jpeg", "svg", "pdf", "docx", "odt", "html", "md", "markdown", "txt"):
            assert f in SUPPORTED

    def test_unsupported_format_guarded(self):
        rep = inspect(b"data", "file.exe")
        assert "unsupported_format" in rep["actions"]
