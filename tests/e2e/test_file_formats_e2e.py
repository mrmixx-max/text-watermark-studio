"""E2E tests for real file formats: .txt, .md, .html, .docx, .pdf.

Tests the metadata service (inspect/clean) and document service (load/export)
with actual file content for each supported format.
"""
from __future__ import annotations

from pathlib import Path

from ai_watermark_toolkit.documents.service import DocumentService
from ai_watermark_toolkit.metadata.service import clean, inspect


class TestTxtFormat:
    """Plain text file format support."""

    def test_inspect_txt(self, tmp_dir, sample_text):
        """Inspect a .txt file should succeed."""
        f = tmp_dir / "sample.txt"
        f.write_text(sample_text, encoding="utf-8")
        report = inspect(f.read_bytes(), "sample.txt")
        # .txt is dispatched through the markdown path in metadata service
        assert report["format"] in ("txt", "markdown")
        assert "unsupported_format" not in report["actions"]

    def test_clean_txt(self, tmp_dir, sample_text):
        """Clean a .txt file should return cleaned bytes."""
        f = tmp_dir / "sample.txt"
        f.write_text(sample_text, encoding="utf-8")
        cleaned, report = clean(f.read_bytes(), "sample.txt")
        assert isinstance(cleaned, bytes)
        assert report["format"] in ("txt", "markdown")

    def test_load_txt_document(self, sample_text):
        """DocumentService should load .txt files."""
        svc = DocumentService()
        doc = svc.load_text("test.txt", sample_text)
        assert doc.format == "txt"
        assert doc.normalized == sample_text.strip()
        assert doc.metadata["chars"] == len(sample_text)


class TestMarkdownFormat:
    """Markdown file format support."""

    def test_inspect_markdown(self, tmp_dir, sample_markdown):
        """Inspect a .md file should succeed."""
        f = tmp_dir / "sample.md"
        f.write_text(sample_markdown, encoding="utf-8")
        report = inspect(f.read_bytes(), "sample.md")
        assert report["format"] in ("md", "markdown")
        assert "unsupported_format" not in report["actions"]

    def test_clean_markdown(self, tmp_dir, sample_markdown):
        """Clean a .md file should return cleaned bytes."""
        f = tmp_dir / "sample.md"
        f.write_text(sample_markdown, encoding="utf-8")
        cleaned, _report = clean(f.read_bytes(), "sample.md")
        assert isinstance(cleaned, bytes)
        # Content should still be readable
        text = cleaned.decode("utf-8")
        assert "AI Watermarking" in text or "watermarking" in text.lower()

    def test_load_markdown_document(self, sample_markdown):
        """DocumentService should load .md files."""
        svc = DocumentService()
        doc = svc.load_text("test.md", sample_markdown)
        assert doc.format in ("md", "markdown")
        assert doc.normalized == sample_markdown.strip()

    def test_export_markdown(self):
        """DocumentService should export to markdown format."""
        svc = DocumentService()
        result = svc.export("Test Title", "Test body content", fmt="md",
                            metadata={"author": "E2E Test"})
        assert result["format"] == "md"
        assert result["media_type"] == "text/markdown"
        assert "Test Title" in result["content"]
        assert "Test body content" in result["content"]
        assert "author: E2E Test" in result["content"]


class TestHtmlFormat:
    """HTML file format support."""

    def test_inspect_html(self, tmp_dir, sample_html):
        """Inspect an .html file should succeed."""
        f = tmp_dir / "sample.html"
        f.write_text(sample_html, encoding="utf-8")
        report = inspect(f.read_bytes(), "sample.html")
        assert report["format"] in ("html", "htm")
        assert "unsupported_format" not in report["actions"]

    def test_clean_html_removes_ai_meta(self, tmp_dir):
        """Clean an .html file should remove AI generator meta tags."""
        html = b"""<!DOCTYPE html>
<html><head>
<meta name="generator" content="ChatGPT">
<meta name="provenance" content="AI-generated">
<title>Test</title></head><body><p>Hello</p></body></html>"""
        f = tmp_dir / "test.html"
        f.write_bytes(html)
        cleaned, _report = clean(f.read_bytes(), "test.html")
        assert isinstance(cleaned, bytes)
        text = cleaned.decode("utf-8")
        # Generator meta should be removed
        assert "generator" not in text.lower() or "ChatGPT" not in text

    def test_load_html_document(self, sample_html):
        """DocumentService should handle .html (falls back to txt)."""
        svc = DocumentService()
        doc = svc.load_text("test.html", sample_html)
        # html is not in SUPPORTED_FORMATS, so it falls back to txt
        assert doc.format == "txt"


class TestDocxFormat:
    """DOCX file format support (byte-level metadata cleaning)."""

    def _make_docx(self, tmp_dir: Path, filename: str = "test.docx") -> Path:
        """Create a minimal valid .docx file (ZIP with XML inside)."""
        import zipfile
        f = tmp_dir / filename
        with zipfile.ZipFile(f, "w") as zf:
            # [Content_Types].xml
            zf.writestr("[Content_Types].xml", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/odpackage/2006/content-types">
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
</Types>""")
            # docProps/core.xml with AI generator metadata
            zf.writestr("docProps/core.xml", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
  xmlns:dc="http://purl.org/dc/elements/1.1/">
  <dc:title>Test Doc</dc:title>
  <dc:creator>E2E Test</dc:creator>
  <cp:generator>ChatGPT</cp:generator>
  <cp:description>AI-generated content</cp:description>
</cp:coreProperties>""")
            # word/document.xml
            zf.writestr("word/document.xml", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body><w:p><w:r><w:t>Hello World</w:t></w:r></w:p></w:body>
</w:document>""")
            # _rels/.rels
            zf.writestr("_rels/.rels", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>""")
        return f

    def test_inspect_docx(self, tmp_dir):
        """Inspect a .docx file should succeed."""
        f = self._make_docx(tmp_dir)
        report = inspect(f.read_bytes(), "test.docx")
        assert report["format"] == "docx"
        assert "unsupported_format" not in report["actions"]

    def test_clean_docx(self, tmp_dir):
        """Clean a .docx file should remove AI metadata."""
        f = self._make_docx(tmp_dir)
        cleaned, report = clean(f.read_bytes(), "test.docx")
        assert isinstance(cleaned, bytes)
        assert report["format"] == "docx"

    def test_clean_docx_scrubs_core_properties(self, tmp_dir):
        """Clean docx should report scrubbing core properties."""
        f = self._make_docx(tmp_dir)
        _cleaned, report = clean(f.read_bytes(), "test.docx")
        # The cleaner should report the scrubbing action
        assert report["format"] == "docx"
        assert len(report["actions"]) > 0
        assert "scrubbed_core_properties" in report["actions"]


class TestPdfFormat:
    """PDF file format support (byte-level metadata cleaning)."""

    def _make_pdf(self, tmp_dir: Path, filename: str = "test.pdf") -> Path:
        """Create a minimal valid .pdf file with metadata."""
        f = tmp_dir / filename
        content = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>
endobj
4 0 obj
<< /Title (Test Document) /Author (E2E Test) /Creator (ChatGPT) /Producer (AI Model) >>
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000266 00000 n
trailer
<< /Size 5 /Root 1 0 R /Info 4 0 R >>
startxref
374
%%EOF"""
        f.write_bytes(content)
        return f

    def test_inspect_pdf(self, tmp_dir):
        """Inspect a .pdf file should succeed."""
        f = self._make_pdf(tmp_dir)
        report = inspect(f.read_bytes(), "test.pdf")
        assert report["format"] == "pdf"
        assert "unsupported_format" not in report["actions"]

    def test_clean_pdf(self, tmp_dir):
        """Clean a .pdf file should return cleaned bytes."""
        f = self._make_pdf(tmp_dir)
        cleaned, report = clean(f.read_bytes(), "test.pdf")
        assert isinstance(cleaned, bytes)
        assert report["format"] == "pdf"

    def test_clean_pdf_removes_creator(self, tmp_dir):
        """Clean pdf should strip Creator/Producer fields."""
        f = self._make_pdf(tmp_dir)
        cleaned, _report = clean(f.read_bytes(), "test.pdf")
        text = cleaned.decode("latin-1", errors="replace")
        # Creator and Producer should be removed or blanked
        assert "/Creator" not in text or "ChatGPT" not in text
        assert "/Producer" not in text or "AI Model" not in text


class TestDocumentServiceFormats:
    """DocumentService load/export for supported text formats."""

    def test_supported_formats(self):
        """DocumentService should list supported formats."""
        svc = DocumentService()
        formats = svc.supported()
        assert "txt" in formats
        assert "md" in formats

    def test_export_text_format(self):
        """Export as plain text should produce simple format."""
        svc = DocumentService()
        result = svc.export("My Title", "Body text here", fmt="txt")
        assert result["format"] == "txt"
        assert result["media_type"] == "text/plain"
        assert "My Title" in result["content"]
        assert "Body text here" in result["content"]

    def test_export_markdown_with_metadata(self):
        """Export as markdown with metadata should include YAML frontmatter."""
        svc = DocumentService()
        result = svc.export("Title", "Body", fmt="md",
                            metadata={"version": "1.0"})
        assert "version: 1.0" in result["content"]
        assert "# Title" in result["content"]

    def test_export_default_is_markdown(self):
        """Default export format should be markdown."""
        svc = DocumentService()
        result = svc.export("T", "B")
        assert result["format"] == "md"
