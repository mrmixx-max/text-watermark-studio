from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path

EXPORT_DIR = Path(__file__).resolve().parents[3] / "output"


class ExportService:
    def __init__(self, export_dir: Path | None = None):
        self.export_dir = export_dir or EXPORT_DIR
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def _style_block(self, style: str) -> str:
        styles = {
            "clean": "body{font-family:Inter,Arial,sans-serif;line-height:1.6;margin:40px;color:#1f2937}h1,h2{color:#111827}.box{border:1px solid #d1d5db;border-radius:12px;padding:16px;background:#f9fafb}",
            "report": "body{font-family:Georgia,serif;line-height:1.7;margin:48px;color:#1f1f1f}h1,h2{letter-spacing:.01em}.box{border-left:4px solid #374151;padding:16px 20px;background:#fafafa}",
            "terminal": "body{font-family:ui-monospace,monospace;line-height:1.6;margin:32px;background:#0b1020;color:#d1fae5}a{color:#93c5fd}.box{border:1px solid #134e4a;border-radius:10px;padding:16px;background:#111827}",
        }
        return styles.get(style, styles["clean"])

    def _render_markdown(self, title: str, text: str, metadata: dict) -> str:
        lines = [f"# {title}", ""]
        if metadata:
            lines.append("## Metadata")
            lines.append("")
            for k, v in metadata.items():
                lines.append(f"- **{k}**: {v}")
            lines.append("")
        lines.append("## Content")
        lines.append("")
        lines.append(text)
        lines.append("")
        return "\n".join(lines)

    def _render_html(self, title: str, text: str, metadata: dict, style: str) -> str:
        meta_html = "".join(
            f"<li><strong>{html.escape(str(k))}</strong>: {html.escape(str(v))}</li>" for k, v in metadata.items()
        )
        body = html.escape(text).replace("\n", "<br>")
        return (
            '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" '
            'content="width=device-width,initial-scale=1"><title>' + html.escape(title) + "</title>"
            "<style>" + self._style_block(style) + "</style></head><body>"
            "<h1>" + html.escape(title) + "</h1>"
            '<div class="box"><h2>Metadata</h2><ul>' + meta_html + "</ul></div>"
            '<div class="box" style="margin-top:16px"><h2>Content</h2><p>' + body + "</p></div>"
            "</body></html>"
        )

    def _render_json(self, title: str, text: str, metadata: dict) -> str:
        return json.dumps({"title": title, "metadata": metadata, "content": text}, ensure_ascii=False, indent=2)

    def _render_csv(self, title: str, text: str, metadata: dict) -> str:
        rows = [["field", "value"], ["title", title], ["content", text]] + [
            [str(k), str(v)] for k, v in metadata.items()
        ]
        out = []
        for row in rows:
            escaped = ['"' + c.replace('"', '""') + '"' for c in row]
            out.append(",".join(escaped))
        return "\n".join(out)

    def export(self, title: str, text: str, format: str = "md", style: str = "clean", metadata: dict | None = None):
        metadata = metadata or {}
        stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        ext = {"md": "md", "html": "html", "json": "json", "csv": "csv", "txt": "txt"}.get(format, "md")
        path = self.export_dir / f"export-{stamp}.{ext}"
        if format == "html":
            content = self._render_html(title, text, metadata, style)
        elif format == "json":
            content = self._render_json(title, text, metadata)
        elif format == "csv":
            content = self._render_csv(title, text, metadata)
        elif format == "txt":
            content = text
        else:
            content = self._render_markdown(title, text, metadata)
        path.write_text(content, encoding="utf-8")
        return {
            "path": str(path),
            "format": format,
            "style": style,
            "bytes": path.stat().st_size,
            "metadata_keys": list(metadata.keys()),
        }
