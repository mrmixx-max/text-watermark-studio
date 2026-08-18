from __future__ import annotations

from typing import Any


class TextChunker:
    def split_text(self, text: str, chunk_size: int = 600, overlap: int = 80, separators: list[str] | None = None):
        separators = separators or ["\n\n", "\n", ". ", " "]
        text = text or ""
        chunks = []
        start = 0
        n = len(text)
        while start < n:
            end = min(start + chunk_size, n)
            window = text[start:end]
            split_at = -1
            for sep in separators:
                idx = window.rfind(sep)
                if idx > max(0, chunk_size // 3):
                    split_at = start + idx + len(sep)
                    break
            if split_at == -1 or split_at <= start:
                split_at = end
            chunk = text[start:split_at].strip()
            if chunk:
                chunks.append(chunk)
            if split_at >= n:
                break
            start = max(split_at - overlap, start + 1)
        return chunks

    def split_with_metadata(self, text: str, chunk_size: int = 600, overlap: int = 80) -> list[dict[str, Any]]:
        chunks = self.split_text(text, chunk_size=chunk_size, overlap=overlap)
        return [
            {'chunk_id': f'chunk-{i+1}', 'text': chunk, 'chars': len(chunk)}
            for i, chunk in enumerate(chunks)
        ]
