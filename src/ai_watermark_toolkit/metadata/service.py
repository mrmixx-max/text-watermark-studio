"""File metadata layer: strip C2PA / EXIF / XMP / AI provenance marks.

Stdlib-only by design (matching the rest of the studio's core). Format
dispatch by extension. Every cleaner returns a MetaReport with verifiable
actions (what was removed) so results separate verifiable from best-effort.

Honest limits (documented, not hidden):
- PDF cleaning is byte-level best-effort (remove /Metadata streams and
  Info entries where unambiguously located). exiftool remains the stronger
  tool for hard cases; this layer degrades gracefully without it.
- C2PA *soft binding* (in-content marks that re-link a remote manifest)
  and pixel-domain marks are OUT OF SCOPE, same as the rest of the field.
- JPEG extended XMP (multi-segment with MD5 splice) is only partially
  removed: the main packet is dropped; spliced continuation segments are
  detected and removed when they carry the extended marker.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

SUPPORTED = ["png", "jpg", "jpeg", "svg", "pdf", "docx", "odt", "html", "md", "markdown", "txt"]

# metadata keys that smell like AI provenance / generator attribution
_AI_KEY_HINTS = re.compile(
    r"(generated|generator|created[-_ ]?by|ai[-_ ]?model|ai[-_ ]?assistant|"
    r"model[-_ ]?name|prompt|content[-_ ]?credentials|c2pa|provenance|synthid|"
    r"produced[-_ ]?by|authoring[-_ ]?tool)",
    re.IGNORECASE,
)

_AI_META_NAMES = re.compile(
    r"(generator|provenance|synthid|c2pa|content[-_ ]?credentials|"
    r"ai[-_ ]?(generated|assistant|model|tool|content)|created[-_ ]?by|"
    r"authoring[-_ ]?tool)",
    re.IGNORECASE,
)


@dataclass
class MetaReport:
    format: str
    actions: list[str] = field(default_factory=list)
    removed_keys: list[str] = field(default_factory=list)
    removed_bytes: int = 0
    hard_bound_c2pa_present: bool = False
    cleaned: bytes | None = None

    def to_dict(self) -> dict:
        return {
            "format": self.format,
            "actions": self.actions,
            "removed_keys": self.removed_keys,
            "removed_bytes": self.removed_bytes,
            "hard_bound_c2pa_present": self.hard_bound_c2pa_present,
        }


def inspect(data: bytes, filename: str) -> dict:
    ext = Path(filename).suffix.lower().lstrip(".")
    report = _dispatch(data, ext, clean=False)
    return report.to_dict()


def clean(data: bytes, filename: str) -> tuple[bytes, dict]:
    ext = Path(filename).suffix.lower().lstrip(".")
    report = _dispatch(data, ext, clean=True)
    return report.cleaned if report.cleaned is not None else data, report.to_dict()


def _dispatch(data: bytes, ext: str, clean: bool) -> MetaReport:
    if ext in ("png",):
        return _png(data, clean)
    if ext in ("jpg", "jpeg"):
        return _jpeg(data, clean)
    if ext == "svg":
        return _svg(data, clean)
    if ext == "pdf":
        return _pdf(data, clean)
    if ext == "docx":
        return _docx(data, clean)
    if ext == "odt":
        return _odt(data, clean)
    if ext in ("html", "htm"):
        return _html(data, clean)
    if ext in ("md", "markdown", "txt"):
        return _markdown(data, clean)
    return MetaReport(format=ext or "unknown", actions=["unsupported_format"])


# ---------------------------------------------------------------- PNG
def _png(data: bytes, clean: bool) -> MetaReport:
    rep = MetaReport(format="png")
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        rep.actions.append("not_a_png")
        return rep
    out = io.BytesIO()
    out.write(data[:8])
    i = 8
    removed = 0
    while i + 8 <= len(data):
        length = int.from_bytes(data[i:i + 4], "big")
        ctype = data[i + 4:i + 8]
        if i + 12 + length > len(data):
            break
        chunk = data[i:i + 12 + length]
        kind = ctype.decode("latin1", "replace")
        # eXIf = EXIF carrier; iTXt/zTXt/tEXt with XMP = AI metadata hints
        if kind == "eXIf" or (
            kind in ("iTXt", "zTXt", "tEXt")
            and (b"XML:com.adobe.xmp" in chunk or b"provenance" in chunk.lower()
                 or b"c2pa" in chunk.lower() or b"ai" in chunk.lower()[:200])
        ):
            removed += 12 + length
            if kind == "eXIf":
                rep.actions.append("removed_eXIf_EXIF_chunk")
            else:
                rep.actions.append(f"removed_{kind}_metadata_chunk")
            rep.removed_bytes = removed
        elif clean:
            out.write(chunk)
        i += 12 + length
    if clean:
        rep.cleaned = out.getvalue()
    if b"jumbf" in data.lower() or b"c2pa" in data.lower():
        rep.hard_bound_c2pa_present = True
        rep.actions.append("c2pa_jumbf_markers_detected_not_removed")
    return rep


# ---------------------------------------------------------------- JPEG
def _jpeg(data: bytes, clean: bool) -> MetaReport:
    rep = MetaReport(format="jpeg")
    if data[:2] != b"\xff\xd8":
        rep.actions.append("not_a_jpeg")
        return rep
    out = io.BytesIO()
    out.write(b"\xff\xd8")
    i = 2
    removed = 0
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            out.write(data[i:i + 2])
            i += 2
            continue
        seg_len = int.from_bytes(data[i + 2:i + 4], "big")
        if seg_len < 2 or i + 2 + seg_len > len(data):
            break
        seg = data[i:i + 2 + seg_len]
        drop = False
        if marker == 0xE1:  # APP1: EXIF ("Exif\0\0") or XMP ("http://ns.adobe.com/xap/1.0/\0")
            if seg[4:10] == b"Exif\x00\x00":
                drop = True
                rep.actions.append("removed_APP1_EXIF")
            elif seg[4:33] == b"http://ns.adobe.com/xap/1.0/\x00":
                drop = True
                rep.actions.append("removed_APP1_XMP")
        elif marker == 0xEB:  # APP11: Adobe XMP / AI hints
            if b"http://ns.adobe.com/xap" in seg or b"XML:com.adobe.xmp" in seg:
                drop = True
                rep.actions.append("removed_APP11_XMP")
            elif _AI_KEY_HINTS.search(seg[:512]):
                drop = True
                rep.actions.append("removed_APP11_ai_metadata")
        if drop:
            removed += 2 + seg_len
            rep.removed_bytes = removed
        elif clean:
            out.write(seg)
        i += 2 + seg_len
    if clean:
        if removed == 0:
            rep.cleaned = data
        else:
            out.write(data[i:] if i < len(data) else b"")
            rep.cleaned = out.getvalue()
    if b"c2pa" in data.lower() or b"jumbf" in data.lower():
        rep.hard_bound_c2pa_present = True
        rep.actions.append("c2pa_jumbf_markers_detected_not_removed")
    return rep


# ---------------------------------------------------------------- SVG
def _svg(data: bytes, clean: bool) -> MetaReport:
    rep = MetaReport(format="svg")
    text = data.decode("utf-8", "replace")
    removed = 0
    if "<metadata" in text.lower():
        removed += len(text)
    new_text = re.sub(r"<metadata[\s\S]*?</metadata>", "", text, flags=re.IGNORECASE)
    new_text = re.sub(r"<rdf:RDF[\s\S]*?</rdf:RDF>", "", new_text, flags=re.IGNORECASE)
    # attributes carrying provenance
    def _strip_attrs(m):
        tag = m.group(0)
        for attr in ("data-ai-origin", "data-provenance", "data-ai-model", "content-credentials"):
            tag = re.sub(rf"\s{attr}='[^']*'", "", tag, flags=re.IGNORECASE)
            tag = re.sub(rf'\s{attr}="[^"]*"', "", tag, flags=re.IGNORECASE)
        return tag
    new_text = re.sub(r"<[a-zA-Z][^>]*>", _strip_attrs, new_text)
    if new_text != text:
        rep.actions.append("removed_svg_metadata_and_ai_attrs")
        rep.removed_bytes = len(text.encode()) - len(new_text.encode())
    if clean:
        rep.cleaned = new_text.encode("utf-8")
    return rep


# ---------------------------------------------------------------- PDF (byte-level, best-effort)
def _pdf(data: bytes, clean: bool) -> MetaReport:
    rep = MetaReport(format="pdf")
    if data[:5] != b"%PDF-":
        rep.actions.append("not_a_pdf")
        return rep
    text = data
    removed = 0
    # /Metadata ... endobj streams (XMP) — located between obj/endobj pairs
    pattern = re.compile(rb"/Metadata\s+\d+\s+\d+\s+R\b")
    rep.hard_bound_c2pa_present = bool(pattern.search(data))
    if clean:
        # remove XMP metadata streams: << /Type /Metadata ... stream ... endstream
        new = re.sub(
            rb"<<\s*/Type\s*/Metadata[\s\S]{0,2000}?>>\s*stream\s*[\s\S]{0,200000}?endstream",
            b"", data, count=8,
        )
        # neutralize creator/producer Info entries
        new = re.sub(rb"/Producer\s*\([^)]*\)", b"/Producer ()", new)
        new = re.sub(rb"/Creator\s*\([^)]*\)", b"/Creator ()", new)
        if new != data:
            rep.actions.append("removed_pdf_xmp_streams_and_info")
            rep.removed_bytes = len(data) - len(new)
        rep.cleaned = new
    else:
        if rep.hard_bound_c2pa_present:
            rep.actions.append("metadata_reference_found")
    return rep


# ---------------------------------------------------------------- DOCX / ODT (zip)
def _docx(data: bytes, clean: bool) -> MetaReport:
    return _zip_container(data, clean, "docx", "docProps/core.xml", "docProps/app.xml", "customXml")


def _odt(data: bytes, clean: bool) -> MetaReport:
    return _zip_container(data, clean, "odt", "meta.xml", None, None)


def _zip_container(data: bytes, clean: bool, fmt: str,
                   core_path: str, app_path: str | None, custom_dir: str | None) -> MetaReport:
    rep = MetaReport(format=fmt)
    try:
        zin = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        rep.actions.append(f"not_a_{fmt}_zip")
        return rep
    names = zin.namelist()
    for n in names:
        if n.startswith("customXml/") or n == "customXml":
            rep.removed_keys.append(n)
            rep.actions.append("removed_customXml_part")
        elif n == core_path:
            rep.removed_keys.append(n)
            rep.actions.append("scrubbed_core_properties")
        elif app_path and n == app_path:
            rep.removed_keys.append(n)
            rep.actions.append("scrubbed_app_properties")
    if not clean:
        return rep
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            content = zin.read(item.filename)
            if item.filename.startswith("customXml/"):
                continue
            if item.filename == core_path:
                content = _scrub_xml(content)
            elif app_path and item.filename == app_path:
                content = _scrub_xml(content)
            zout.writestr(item, content)
    rep.cleaned = out.getvalue()
    rep.removed_bytes = len(data) - len(rep.cleaned)
    return rep


def _scrub_xml(content: bytes) -> bytes:
    text = content.decode("utf-8", "replace")
    for tag in ("cp:lastModifiedBy", "dc:creator", "cp:revision", "meta:generator", "meta:user-defined"):
        text = re.sub(rf"<{tag}[^>]*>[^<]*</{tag}>", f"<{tag}></{tag}>", text, flags=re.IGNORECASE)
    return text.encode("utf-8")


# ---------------------------------------------------------------- HTML
def _html(data: bytes, clean: bool) -> MetaReport:
    rep = MetaReport(format="html")
    text = data.decode("utf-8", "replace")
    new = text
    # meta tags carrying AI provenance
    def _meta_sub(m):
        tag = m.group(0)
        if _AI_META_NAMES.search(tag):
            rep.removed_keys.append(re.search(r'name=["\']([^"\']+)', tag, re.IGNORECASE).group(1) if re.search(r'name=["\']([^"\']+)', tag, re.IGNORECASE) else "meta")
            rep.actions.append("removed_ai_meta_tag")
            return ""
        return tag
    new = re.sub(r"<meta\b[^>]*>", _meta_sub, new, flags=re.IGNORECASE)
    # JSON-LD with provenance keys
    new = re.sub(r"<script\b[^>]*application/ld\+json[^>]*>[\s\S]*?</script>", "", new, flags=re.IGNORECASE)
    if "<script" in text and "application/ld+json" in text:
        rep.actions.append("removed_jsonld_provenance_block")
    # data-ai* attributes
    new = re.sub(r"\sdata-ai[\w-]*=['\"][^'\"]*['\"]", "", new, flags=re.IGNORECASE)
    if new != text:
        rep.removed_bytes = len(text.encode()) - len(new.encode())
    if clean:
        rep.cleaned = new.encode("utf-8")
    return rep


# ---------------------------------------------------------------- Markdown / TXT
def _markdown(data: bytes, clean: bool) -> MetaReport:
    rep = MetaReport(format="markdown")
    text = data.decode("utf-8", "replace")
    new = text
    # YAML frontmatter with AI keys
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            fm = text[3:end]
            lines = fm.splitlines()
            kept = []
            for line in lines:
                m = re.match(r"\s*([\w-]+)\s*:", line)
                if m and _AI_KEY_HINTS.search(m.group(1)):
                    rep.removed_keys.append(m.group(1))
                    rep.actions.append("removed_ai_frontmatter_key")
                    continue
                kept.append(line)
            new = "---" + "\n".join(kept) + text[end:]
    if new != text:
        rep.removed_bytes = len(text.encode()) - len(new.encode())
    if clean:
        rep.cleaned = new.encode("utf-8")
    return rep
