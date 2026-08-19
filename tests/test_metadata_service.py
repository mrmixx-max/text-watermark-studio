"""Tests for metadata/service.py"""

import struct


from ai_watermark_toolkit.metadata import service


class TestInspect:
    def test_inspect_unsupported_format(self):
        result = service.inspect(b"data", "test.xyz")
        assert result["format"] == "xyz"
        assert "unsupported_format" in result["actions"]


class TestClean:
    def test_clean_unsupported_format(self):
        data = b"some data"
        cleaned, report = service.clean(data, "test.xyz")
        assert cleaned == data
        assert report["format"] == "xyz"


class TestVerifyClean:
    def test_verify_unsupported_format(self):
        result = service.verify_clean(b"data", "test.xyz")
        assert result["verification"] == "unsupported_format"


class TestPngClean:
    def test_png_inspect_valid(self):
        # Minimal PNG: 8-byte signature + IHDR chunk
        data = b"\x89PNG\r\n\x1a\n"
        data += struct.pack(">I", 13)  # length
        data += b"IHDR"  # type
        data += b"\x00" * 13  # data
        data += struct.pack(">I", 0)  # CRC (invalid but parsed)
        result = service.inspect(data, "test.png")
        assert result["format"] == "png"

    def test_png_clean_strips_text(self):
        # PNG with tEXt chunk
        data = b"\x89PNG\r\n\x1a\n"
        text_data = b"generator\x00AI Model"
        data += struct.pack(">I", len(text_data))
        data += b"tEXt"
        data += text_data
        data += struct.pack(">I", 0)
        cleaned, report = service.clean(data, "test.png")
        assert report["format"] == "png"


class TestJpegClean:
    def test_jpeg_inspect_valid(self):
        data = b"\xff\xd8"
        result = service.inspect(data, "test.jpg")
        assert result["format"] in ("jpg", "jpeg")

    def test_jpeg_clean_strips_app1(self):
        data = b"\xff\xd8"
        data += b"\xff\xe1"
        data += struct.pack(">H", 10)
        data += b"\x00" * 8
        cleaned, report = service.clean(data, "test.jpg")
        assert report["format"] in ("jpg", "jpeg")


class TestSvgClean:
    def test_svg_clean_strips_metadata(self):
        svg = b"<svg><metadata>test</metadata><rect/></svg>"
        cleaned, report = service.clean(svg, "test.svg")
        assert b"metadata" not in cleaned

    def test_svg_clean_no_metadata(self):
        svg = b"<svg><rect/></svg>"
        cleaned, report = service.clean(svg, "test.svg")
        assert cleaned == svg


class TestMarkdownClean:
    def test_markdown_clean_strips_generator(self):
        md = b"---\ntitle: test\ngenerator: AI Bot\n---\n\nHello\n"
        cleaned, report = service.clean(md, "test.md")
        assert b"generator" not in cleaned
        assert b"title: test" in cleaned


class TestHtmlClean:
    def test_html_clean_strips_ai_meta(self):
        html = b'<meta name="generator" content="AI"><p>Hello</p>'
        cleaned, report = service.clean(html, "test.html")
        assert b"generator" not in cleaned
        assert b"Hello" in cleaned


class TestPdfClean:
    def test_pdf_clean_best_effort(self):
        pdf = b"%PDF-1.4\n%%EOF"
        cleaned, report = service.clean(pdf, "test.pdf")
        assert report["format"] == "pdf"


class TestDocxClean:
    def test_docx_unsupported(self):
        data = b"PK\x03\x04" + b"\x00" * 26
        cleaned, report = service.clean(data, "test.docx")
        assert report["format"] == "docx"


class TestOdtClean:
    def test_odt_unsupported(self):
        data = b"PK\x03\x04" + b"\x00" * 26
        cleaned, report = service.clean(data, "test.odt")
        assert report["format"] == "odt"


class TestMarkdownFrontmatter:
    def test_markdown_clean_preserves_normal_keys(self):
        md = b"---\ntitle: test\nauthor: someone\n---\n\nContent\n"
        cleaned, report = service.clean(md, "test.md")
        assert b"title: test" in cleaned
        assert b"author: someone" in cleaned


class TestHtmlJsonLd:
    def test_html_clean_strips_jsonld_ai(self):
        html = b'<script type="application/ld+json">{"AI": true}</script><p>Hi</p>'
        cleaned, report = service.clean(html, "test.html")
        assert b"Hi" in cleaned


class TestSvgRdf:
    def test_svg_clean_strips_rdf(self):
        svg = b"<svg><rdf:RDF>c2pa</rdf:RDF><rect/></svg>"
        cleaned, report = service.clean(svg, "test.svg")
        assert b"rdf" not in cleaned
