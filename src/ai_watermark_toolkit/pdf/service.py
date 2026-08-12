from __future__ import annotations

from typing import Dict, Any


class PDFService:
    def summarize_text(self, text: str) -> Dict[str, Any]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        excerpt = "\n".join(lines[:10])
        return {
            'pages_estimated': max(1, len(text) // 2500 + 1),
            'line_count': len(lines),
            'excerpt': excerpt,
        }

    def extract_text(self, text: str) -> Dict[str, Any]:
        return {
            'text': text,
            'summary': self.summarize_text(text),
        }
