from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

from .pipeline import detect_text, run_pipeline
from .transform.clean import clean_text
from .transform.dilute import dilute_text


TEXT_EXTS = {".txt", ".md", ".html", ".htm", ".rst"}


@dataclass
class BatchItemResult:
    input_path: str
    output_path: str
    mode: str
    changed: bool

    def to_dict(self) -> dict:
        return asdict(self)


def iter_text_files(root: str) -> Iterable[Path]:
    base = Path(root)
    for p in base.rglob('*'):
        if p.is_file() and p.suffix.lower() in TEXT_EXTS:
            yield p


def process_batch(input_dir: str, output_dir: str, *, mode: str = 'pipeline', intensity: str = 'standard', lang: str = 'auto') -> dict:
    in_base = Path(input_dir)
    out_base = Path(output_dir)
    out_base.mkdir(parents=True, exist_ok=True)
    items = []
    for src in iter_text_files(input_dir):
        rel = src.relative_to(in_base)
        dst = out_base / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        text = src.read_text(encoding='utf-8')
        if mode == 'detect':
            result = detect_text(text, lang=lang)
            dst = dst.with_suffix(dst.suffix + '.json')
            dst.write_text(__import__('json').dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            changed = False
        elif mode == 'clean':
            result = clean_text(text)
            dst.write_text(result.text, encoding='utf-8')
            changed = result.text != text
        elif mode == 'dilute':
            result = dilute_text(text, intensity=intensity)
            dst.write_text(result.text, encoding='utf-8')
            changed = result.text != text
        else:
            out, report = run_pipeline(text, lang=lang, intensity=intensity)
            dst.write_text(out, encoding='utf-8')
            report_path = dst.with_suffix(dst.suffix + '.report.json')
            report_path.write_text(__import__('json').dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            changed = out != text
        items.append(BatchItemResult(str(src), str(dst), mode, changed).to_dict())
    return {"count": len(items), "items": items, "mode": mode}
