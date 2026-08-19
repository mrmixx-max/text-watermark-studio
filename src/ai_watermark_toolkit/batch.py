from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

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
    verified: bool | None = None
    z_score: float | None = None
    green_rate: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def iter_text_files(root: str) -> Iterable[Path]:
    base = Path(root)
    for p in base.rglob("*"):
        if p.is_file() and p.suffix.lower() in TEXT_EXTS:
            yield p


def process_batch(
    input_dir: str,
    output_dir: str,
    *,
    mode: str = "pipeline",
    intensity: str = "standard",
    lang: str = "auto",
    key_id: str | None = None,
    level: str = "word",
    context: int = 1,
    gamma: float | None = None,
    seed: int | None = None,
    verify: bool = False,
) -> dict:
    in_base = Path(input_dir)
    out_base = Path(output_dir)
    out_base.mkdir(parents=True, exist_ok=True)
    items = []

    # Resolve embed key once if mode == 'embed'
    embed_key = None
    if mode == "embed":
        if not key_id:
            raise ValueError("batch mode 'embed' requires --key (a registered key_id with secret)")
        from .forensics.key_registry import KeyRegistry
        from .forensics.kgw import DEFAULT_GAMMA

        registry = KeyRegistry("data/key_registry.json")
        key = next((k for k in registry.list_keys() if k.get("key_id") == key_id), None)
        if key is None:
            raise ValueError(f"key not found: {key_id}")
        if not key.get("secret"):
            raise ValueError(f"key {key_id} has no secret — cannot embed")
        embed_key = key

    for src in iter_text_files(input_dir):
        rel = src.relative_to(in_base)
        dst = out_base / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            text = src.read_text(encoding="utf-8")
            if mode == "detect":
                result = detect_text(text, lang=lang)
                dst = dst.with_suffix(dst.suffix + ".json")
                dst.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                changed = False
            elif mode == "clean":
                result = clean_text(text)
                dst.write_text(result.text, encoding="utf-8")
                changed = result.text != text
            elif mode == "dilute":
                result = dilute_text(text, intensity=intensity)
                dst.write_text(result.text, encoding="utf-8")
                changed = result.text != text
            elif mode == "embed":
                from .forensics.kgw import DEFAULT_GAMMA, mark_greenlist

                effective_gamma = gamma if gamma is not None else (embed_key.get("gamma") or DEFAULT_GAMMA)
                result = mark_greenlist(
                    text, embed_key["secret"], gamma=effective_gamma, level=level, context=context, seed=seed,
                )
                dst.write_text(result["text"], encoding="utf-8")
                changed = result["text"] != text
                # --verify: run detection after embedding to confirm the
                # watermark is detectable (README promise: "garantiert
                # detektierbar, Z>4"). Only meaningful for embed mode.
                verified = None
                z_score = None
                green_rate = None
                if verify:
                    from .forensics.kgw import detect_kgw

                    det = detect_kgw(
                        result["text"], embed_key["secret"], gamma=effective_gamma, level=level, context=context,
                    )
                    z_score = det.get("z_score")
                    green_rate = det.get("green_rate")
                    verified = det.get("verdict") in ("watermark_detected", "redlist_detected")
            else:
                out, report = run_pipeline(text, lang=lang, intensity=intensity)
                dst.write_text(out, encoding="utf-8")
                report_path = dst.with_suffix(dst.suffix + ".report.json")
                report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                changed = out != text
            items.append(
                BatchItemResult(
                    str(src),
                    str(dst),
                    mode,
                    changed,
                    verified=verified if mode == "embed" and verify else None,
                    z_score=z_score if mode == "embed" and verify else None,
                    green_rate=green_rate if mode == "embed" and verify else None,
                ).to_dict(),
            )
        except UnicodeDecodeError:
            items.append(BatchItemResult(str(src), str(dst), mode, False).to_dict())
            # Log error to stderr but continue processing remaining files
        except Exception:
            items.append(BatchItemResult(str(src), str(dst), mode, False).to_dict())
    return {"count": len(items), "items": items, "mode": mode}
