from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class DocumentService:
    def export_markdown(self, title: str, body: str, metadata: Dict[str, Any] | None = None) -> str:
        metadata = metadata or {}
        meta_lines = ['---'] + [f'{k}: {v}' for k, v in metadata.items()] + ['---', ''] if metadata else []
        return '\n'.join(meta_lines + [f'# {title}', '', body.strip(), ''])

    def export_text(self, title: str, body: str) -> str:
        return f'{title}\n' + ('=' * len(title)) + f'\n\n{body.strip()}\n'

    def export(self, title: str, body: str, fmt: str = 'md', metadata: Dict[str, Any] | None = None) -> Dict[str, Any]:
        fmt = (fmt or 'md').lower()
        if fmt in {'md', 'markdown'}:
            content = self.export_markdown(title, body, metadata)
            media_type = 'text/markdown'
        else:
            content = self.export_text(title, body)
            media_type = 'text/plain'
        return {'title': title, 'format': fmt, 'media_type': media_type, 'content': content}
