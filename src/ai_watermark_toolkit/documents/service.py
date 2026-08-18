from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

SUPPORTED_FORMATS = ['md', 'markdown', 'txt', 'text']


@dataclass
class LoadedDocument:
    filename: str
    content: str
    normalized: str
    format: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DocumentService:
    def supported(self) -> list[str]:
        return SUPPORTED_FORMATS

    def load_text(self, filename: str, content: str) -> LoadedDocument:
        fmt = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'txt'
        if fmt not in SUPPORTED_FORMATS:
            fmt = 'txt'
        return LoadedDocument(
            filename=filename,
            content=content,
            normalized=content.strip(),
            format=fmt,
            metadata={'chars': len(content)},
        )

    def export_markdown(self, title: str, body: str, metadata: dict[str, Any] | None = None) -> str:
        metadata = metadata or {}
        meta_lines = ['---'] + [f'{k}: {v}' for k, v in metadata.items()] + ['---', ''] if metadata else []
        return '\n'.join([*meta_lines, f'# {title}', '', body.strip(), ''])

    def export_text(self, title: str, body: str) -> str:
        return f'{title}\n' + ('=' * len(title)) + f'\n\n{body.strip()}\n'

    def export(self, title: str, body: str, fmt: str = 'md', metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        fmt = (fmt or 'md').lower()
        if fmt in {'md', 'markdown'}:
            content = self.export_markdown(title, body, metadata)
            media_type = 'text/markdown'
        else:
            content = self.export_text(title, body)
            media_type = 'text/plain'
        return {'title': title, 'format': fmt, 'media_type': media_type, 'content': content}
