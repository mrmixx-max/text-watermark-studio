"""Keyed file provenance: embed your own signed watermark marks into files
and detect them again — the file-level sibling of the KGW text detector.

Embed: insert a studio mark (XMP-style packet) carrying key_id + an HMAC
signature. Detect: extract the mark, verify the HMAC against registered
secrets, report key_id + validity.

Honest limits (documented, not hidden):
- The signature binds CONTENT for stream formats (png/jpeg/svg/html/md),
  where the mark can be removed byte-exactly to restore the original.
  For container formats (docx/odt/pdf) the signature binds the main
  content part only — metadata edits outside that part do not invalidate.
- This is provenance YOU set and verify. It does not prove anything
  about third-party watermarks.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import re
import struct
import zipfile
from dataclasses import dataclass, field

MARK_NAME = "ai-wm-studio"

_AIWM_META_RE = re.compile(
    rb"<meta\s+name=[\"']ai-wm-studio[\"']\s+content=[\"']([^\"']*)[\"']\s*/?>",
    re.IGNORECASE,
)


@dataclass
class EmbedResult:
    format: str
    key_id: str
    embedded: bool
    mark_size: int = 0
    data: bytes | None = None

    def to_dict(self) -> dict:
        return {"format": self.format, "key_id": self.key_id, "embedded": self.embedded, "mark_size": self.mark_size}


@dataclass
class DetectResult:
    format: str
    found: bool
    key_id: str | None = None
    valid: bool = False
    reason: str = ""
    marks: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "format": self.format,
            "found": self.found,
            "key_id": self.key_id,
            "valid": self.valid,
            "reason": self.reason,
            "marks": self.marks,
        }


def _sign(secret: str, payload: bytes) -> str:
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def _packet(key_id: str, sig: str) -> bytes:
    return json.dumps({"name": MARK_NAME, "key_id": key_id, "sig": sig, "v": 1}, separators=(",", ":")).encode()


def _packet_dict(packet: bytes) -> dict:
    try:
        return json.loads(packet.decode("utf-8"))
    except Exception:
        return {}


# ---------------------------------------------------------------- PNG
def _embed_png(data: bytes, key_id: str, secret: str) -> bytes:
    sig = _sign(secret, data)
    payload = _packet(key_id, sig)
    ctype = b"iTXt"
    content = b"XML:com.adobe.xmp\x00" + payload
    chunk = struct.pack(">I", len(content)) + ctype + content + struct.pack(">I", 0)
    return data[:8] + chunk + data[8:]


def _detect_png(data: bytes, secrets: dict[str, str]) -> DetectResult:
    res = DetectResult(format="png", found=False)
    i = 8
    while i + 12 <= len(data):
        length = int.from_bytes(data[i : i + 4], "big")
        ctype = data[i + 4 : i + 8]
        if i + 12 + length > len(data):
            break
        payload = data[i + 8 : i + 8 + length]
        if ctype == b"iTXt" and payload.startswith(b"XML:com.adobe.xmp\x00"):
            packet = _packet_dict(payload.split(b"\x00", 1)[1])
            if packet.get("name") == MARK_NAME:
                res.found = True
                res.marks.append(packet)
                restored = data[:i] + data[i + 12 + length :]
                sig_ok = packet.get("sig") and packet["sig"] == _sign(secrets.get(packet.get("key_id"), ""), restored)
                if sig_ok:
                    res.valid, res.key_id = True, packet.get("key_id")
                    res.reason = "hmac_valid"
                else:
                    res.reason = "hmac_invalid_or_unknown_key"
        i += 12 + length
    return res


# ---------------------------------------------------------------- JPEG
def _embed_jpeg(data: bytes, key_id: str, secret: str) -> bytes:
    sig = _sign(secret, data)
    payload = _packet(key_id, sig)
    xmp = b"http://ns.adobe.com/xap/1.0/\x00" + payload
    seg = b"\xff\xe1" + struct.pack(">H", len(xmp) + 2) + xmp
    return data[:2] + seg + data[2:]


def _detect_jpeg(data: bytes, secrets: dict[str, str]) -> DetectResult:
    res = DetectResult(format="jpeg", found=False)
    i = 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        seg_len = int.from_bytes(data[i + 2 : i + 4], "big")
        if seg_len < 2 or i + 2 + seg_len > len(data):
            break
        seg = data[i : i + 2 + seg_len]
        if marker == 0xE1 and seg[4:33] == b"http://ns.adobe.com/xap/1.0/\x00":
            packet = _packet_dict(seg[33:])
            if packet.get("name") == MARK_NAME:
                res.found = True
                res.marks.append(packet)
                restored = data[:i] + data[i + 2 + seg_len :]
                sig_ok = packet.get("sig") and packet["sig"] == _sign(secrets.get(packet.get("key_id"), ""), restored)
                if sig_ok:
                    res.valid, res.key_id = True, packet.get("key_id")
                    res.reason = "hmac_valid"
                else:
                    res.reason = "hmac_invalid_or_unknown_key"
        i += 2 + seg_len
    return res


# ---------------------------------------------------------------- text-ish (svg/html/md)
def _embed_text(data: bytes, key_id: str, secret: str, fmt: str) -> bytes:
    sig = _sign(secret, data)
    packet = _packet(key_id, sig).decode()
    if fmt == "svg":
        mark = f"<metadata><!-- {packet} --></metadata>".encode()
        return mark + data
    if fmt == "html":
        import html as _html_mod

        escaped = _html_mod.escape(packet, quote=True)
        mark = f'<meta name="{MARK_NAME}" content="{escaped}" />'.encode()
        return mark + data
    if fmt in ("md", "markdown", "txt"):
        mark = f"---\nai_wm_studio: {packet}\n---\n".encode()
        return mark + data
    return data


def _detect_text(data: bytes, secrets: dict[str, str], fmt: str) -> DetectResult:
    res = DetectResult(format=fmt, found=False)
    text = data
    if fmt == "svg":
        m = re.match(rb"<metadata><!-- (\{[^<]*\}) --></metadata>", text)
        if m:
            packet = _packet_dict(m.group(1))
            if packet.get("name") == MARK_NAME:
                res.found = True
                res.marks.append(packet)
                restored = text[m.end() :]
                if packet.get("sig") and packet["sig"] == _sign(secrets.get(packet.get("key_id"), ""), restored):
                    res.valid, res.key_id = True, packet.get("key_id")
                    res.reason = "hmac_valid"
                else:
                    res.reason = "hmac_invalid_or_unknown_key"
    elif fmt == "html":
        m = _AIWM_META_RE.search(text)
        if m:
            import html as _html_mod

            packet = _packet_dict(_html_mod.unescape(m.group(1).decode()).encode())
            if packet.get("name") == MARK_NAME:
                res.found = True
                res.marks.append(packet)
                restored = text[: m.start()] + text[m.end() :]
                if packet.get("sig") and packet["sig"] == _sign(secrets.get(packet.get("key_id"), ""), restored):
                    res.valid, res.key_id = True, packet.get("key_id")
                    res.reason = "hmac_valid"
                else:
                    res.reason = "hmac_invalid_or_unknown_key"
    else:  # markdown/txt frontmatter
        m = re.match(rb"---\nai_wm_studio: (\{[^\n]*\})\n---\n", text)
        if m:
            packet = _packet_dict(m.group(1))
            if packet.get("name") == MARK_NAME:
                res.found = True
                res.marks.append(packet)
                restored = text[m.end() :]
                if packet.get("sig") and packet["sig"] == _sign(secrets.get(packet.get("key_id"), ""), restored):
                    res.valid, res.key_id = True, packet.get("key_id")
                    res.reason = "hmac_valid"
                else:
                    res.reason = "hmac_invalid_or_unknown_key"
    return res


# ---------------------------------------------------------------- zip containers (docx/odt)
def _embed_docx(data: bytes, key_id: str, secret: str, fmt: str) -> bytes:
    try:
        zin = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return data
    main_part = "word/document.xml" if fmt == "docx" else "content.xml"
    main_bytes = zin.read(main_part) if main_part in zin.namelist() else data
    sig = _sign(secret, main_bytes)
    packet = _packet(key_id, sig)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            zout.writestr(item, zin.read(item.filename))
        mark_name = "customXml/wm.xml" if fmt == "docx" else "meta-wm.xml"
        if mark_name not in zin.namelist():
            zout.writestr(mark_name, packet)
    return out.getvalue()


def _detect_docx(data: bytes, secrets: dict[str, str], fmt: str) -> DetectResult:
    res = DetectResult(format=fmt, found=False)
    try:
        zin = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        res.reason = "not_a_zip"
        return res
    mark_name = "customXml/wm.xml" if fmt == "docx" else "meta-wm.xml"
    main_part = "word/document.xml" if fmt == "docx" else "content.xml"
    if mark_name in zin.namelist():
        packet = _packet_dict(zin.read(mark_name))
        if packet.get("name") == MARK_NAME:
            res.found = True
            res.marks.append(packet)
            main_bytes = zin.read(main_part) if main_part in zin.namelist() else b""
            if packet.get("sig") and packet["sig"] == _sign(secrets.get(packet.get("key_id"), ""), main_bytes):
                res.valid, res.key_id = True, packet.get("key_id")
                res.reason = "hmac_valid_content_bound"
            else:
                res.reason = "hmac_invalid_or_unknown_key"
    return res


# ---------------------------------------------------------------- pdf
def _embed_pdf(data: bytes, key_id: str, secret: str) -> bytes:
    sig = _sign(secret, data)
    packet = _packet(key_id, sig)
    stream = (
        b"<< /Type /Metadata /Subtype /XML /Length "
        + str(len(packet)).encode()
        + b" >>\nstream\n"
        + packet
        + b"\nendstream"
    )
    return data + stream


def _detect_pdf(data: bytes, secrets: dict[str, str]) -> DetectResult:
    res = DetectResult(format="pdf", found=False)
    m = re.search(
        rb"<<\s*/Type\s*/Metadata\s*/Subtype\s*/XML\s*/Length\s+\d+\s*>>\s*stream\s*([\s\S]*?)endstream", data,
    )
    if m:
        packet = _packet_dict(m.group(1).strip())
        if packet.get("name") == MARK_NAME:
            res.found = True
            res.marks.append(packet)
            restored = data[: m.start()] + data[m.end() :]
            if packet.get("sig") and packet["sig"] == _sign(secrets.get(packet.get("key_id"), ""), restored):
                res.valid, res.key_id = True, packet.get("key_id")
                res.reason = "hmac_valid"
            else:
                res.reason = "hmac_invalid_or_unknown_key"
    return res


# ---------------------------------------------------------------- dispatch
def embed_provenance(data: bytes, filename: str, key_id: str, secret: str) -> EmbedResult:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    try:
        if ext == "png":
            out = _embed_png(data, key_id, secret)
        elif ext in ("jpg", "jpeg"):
            out = _embed_jpeg(data, key_id, secret)
        elif ext == "svg":
            out = _embed_text(data, key_id, secret, "svg")
        elif ext in ("html", "htm"):
            out = _embed_text(data, key_id, secret, "html")
        elif ext in ("md", "markdown", "txt"):
            out = _embed_text(data, key_id, secret, "md")
        elif ext == "docx":
            out = _embed_docx(data, key_id, secret, "docx")
        elif ext == "odt":
            out = _embed_docx(data, key_id, secret, "odt")
        elif ext == "pdf":
            out = _embed_pdf(data, key_id, secret)
        else:
            return EmbedResult(format=ext, key_id=key_id, embedded=False)
    except Exception:
        return EmbedResult(format=ext, key_id=key_id, embedded=False)
    return EmbedResult(format=ext, key_id=key_id, embedded=True, mark_size=len(out) - len(data), data=out)


def detect_provenance(data: bytes, filename: str, secrets: dict[str, str]) -> DetectResult:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "png":
        return _detect_png(data, secrets)
    if ext in ("jpg", "jpeg"):
        return _detect_jpeg(data, secrets)
    if ext == "svg":
        return _detect_text(data, secrets, "svg")
    if ext in ("html", "htm"):
        return _detect_text(data, secrets, "html")
    if ext in ("md", "markdown", "txt"):
        return _detect_text(data, secrets, "md")
    if ext == "docx":
        return _detect_docx(data, secrets, "docx")
    if ext == "odt":
        return _detect_docx(data, secrets, "odt")
    if ext == "pdf":
        return _detect_pdf(data, secrets)
    return DetectResult(format=ext, found=False, reason="unsupported_format")
