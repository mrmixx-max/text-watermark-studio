"""DOCX repair (C7, 2026-08-18) — tests for corrupted DOCX file repair.

Contract under test:
- validate_docx: detects missing parts, invalid XML, orphaned rels.
- repair_docx: rebuilds content types, rels, removes corrupt parts.
- rebuild_document_rels: rebuilds only document relationships.
- RepairReport: accurate reporting of what was fixed.
"""

import io
import zipfile

from ai_watermark_toolkit.metadata.docx_repair import (
    _build_content_types_xml,
    _build_rels_xml,
    _guess_content_type,
    _is_valid_xml,
    _parse_rels_xml,
    rebuild_document_rels,
    repair_docx,
    validate_docx,
)


def _make_minimal_docx() -> bytes:
    """Create a minimal valid DOCX in memory."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        # [Content_Types].xml
        zf.writestr("[Content_Types].xml", b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>""")
        # _rels/.rels
        zf.writestr("_rels/.rels", b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>""")
        # word/document.xml
        zf.writestr("word/document.xml", b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body><w:p><w:r><w:t>Hello World</w:t></w:r></w:p></w:body>
</w:document>""")
        # word/_rels/document.xml.rels
        zf.writestr("word/_rels/document.xml.rels", b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
</Relationships>""")
    return out.getvalue()


def _make_broken_docx() -> bytes:
    """Create a DOCX with structural issues."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        # Missing [Content_Types].xml
        # Missing _rels/.rels
        zf.writestr("word/document.xml", b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body><w:p><w:r><w:t>Hello</w:t></w:r></w:p></w:body>
</w:document>""")
    return out.getvalue()


def _make_invalid_xml_docx() -> bytes:
    """Create a DOCX with invalid XML in a part."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", b"NOT XML")
        zf.writestr("word/document.xml", b"<invalid>xml<")
    return out.getvalue()


class TestValidateDocx:
    """Tests for DOCX validation."""

    def test_valid_docx(self):
        data = _make_minimal_docx()
        report = validate_docx(data)
        assert report.was_valid is True
        assert len(report.errors) == 0

    def test_missing_content_types(self):
        data = _make_broken_docx()
        report = validate_docx(data)
        assert report.was_valid is False
        assert any("content_types" in e for e in report.errors)

    def test_missing_required_part(self):
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", b"<Types/>")
        report = validate_docx(out.getvalue())
        assert any("document.xml" in e for e in report.errors)

    def test_not_a_zip(self):
        report = validate_docx(b"not a zip file")
        assert report.was_valid is False
        assert len(report.errors) > 0


class TestRepairDocx:
    """Tests for DOCX repair."""

    def test_repair_broken_docx(self):
        data = _make_broken_docx()
        report = repair_docx(data)
        assert report.data is not None
        # Verify repaired is valid
        validation = validate_docx(report.data)
        assert validation.was_valid is True

    def test_repair_adds_content_types(self):
        data = _make_broken_docx()
        report = repair_docx(data)
        zf = zipfile.ZipFile(io.BytesIO(report.data))
        assert "[Content_Types].xml" in zf.namelist()

    def test_repair_adds_rels(self):
        data = _make_broken_docx()
        report = repair_docx(data)
        zf = zipfile.ZipFile(io.BytesIO(report.data))
        assert "_rels/.rels" in zf.namelist()

    def test_repair_preserves_document(self):
        data = _make_broken_docx()
        report = repair_docx(data)
        zf = zipfile.ZipFile(io.BytesIO(report.data))
        assert "word/document.xml" in zf.namelist()

    def test_repair_already_valid(self):
        data = _make_minimal_docx()
        report = repair_docx(data)
        assert report.was_valid is True
        assert report.data == data

    def test_repair_report_tracks_changes(self):
        data = _make_broken_docx()
        report = repair_docx(data)
        assert len(report.repairs) > 0


class TestRebuildDocumentRels:
    """Tests for document relationship rebuilding."""

    def test_rebuild_preserves_parts(self):
        data = _make_minimal_docx()
        result = rebuild_document_rels(data)
        zf = zipfile.ZipFile(io.BytesIO(result))
        assert "word/document.xml" in zf.namelist()
        assert "word/_rels/document.xml.rels" in zf.namelist()

    def test_rebuild_without_document(self):
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("other.txt", b"content")
        result = rebuild_document_rels(out.getvalue())
        # Should return unchanged
        assert result == out.getvalue()


class TestHelpers:
    """Tests for helper functions."""

    def test_is_valid_xml_true(self):
        assert _is_valid_xml(b"<root><child/></root>") is True

    def test_is_valid_xml_false(self):
        assert _is_valid_xml(b"<root><invalid>") is False

    def test_guess_content_type_document(self):
        ct = _guess_content_type("word/document.xml")
        assert "wordprocessingml" in ct

    def test_guess_content_type_image(self):
        ct = _guess_content_type("word/media/image1.png")
        assert ct == "image/png"

    def test_build_content_types_xml(self):
        parts = ["word/document.xml", "word/styles.xml"]
        xml = _build_content_types_xml(parts)
        assert b"Types" in xml
        assert b"document.xml" in xml

    def test_build_rels_xml(self):
        rels = [{"Id": "rId1", "Type": "test", "Target": "target.xml"}]
        xml = _build_rels_xml(rels)
        assert b"Relationships" in xml
        assert b"rId1" in xml

    def test_parse_rels_xml(self):
        xml = b"""<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
            <Relationship Id="rId1" Type="test" Target="target.xml"/>
        </Relationships>"""
        rels = _parse_rels_xml(xml)
        assert len(rels) == 1
        assert rels[0]["Id"] == "rId1"
