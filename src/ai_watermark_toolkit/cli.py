from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .ingest import read_text
from .pipeline import detect_text, run_pipeline
from .report import write_json
from .transform.clean import clean_text
from .transform.dilute import dilute_text
from .batch import process_batch


def _read(args) -> str:
    if args.stdin:
        return read_text(stdin_text=sys.stdin.read()).text
    return read_text(path=args.input).text


def main() -> int:
    p = argparse.ArgumentParser(prog="ai-wm")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("detect")
    d.add_argument("input", nargs="?")
    d.add_argument("--stdin", action="store_true")
    d.add_argument("--lang", default="auto", choices=["auto", "de", "en"])
    d.add_argument("--json", action="store_true")
    d.add_argument("-o", "--output")

    c = sub.add_parser("clean")
    c.add_argument("input", nargs="?")
    c.add_argument("--stdin", action="store_true")
    c.add_argument("--nfkc", action="store_true")
    c.add_argument("--fold-confusables", action="store_true")
    c.add_argument("-o", "--output")
    c.add_argument("--report")

    dl = sub.add_parser("dilute")
    dl.add_argument("input", nargs="?")
    dl.add_argument("--stdin", action="store_true")
    dl.add_argument("--intensity", default="standard", choices=["light", "standard", "aggressive"])
    dl.add_argument("-o", "--output")

    pl = sub.add_parser("pipeline")
    pl.add_argument("input", nargs="?")
    pl.add_argument("--stdin", action="store_true")
    pl.add_argument("--lang", default="auto", choices=["auto", "de", "en"])
    pl.add_argument("--nfkc", action="store_true")
    pl.add_argument("--fold-confusables", action="store_true")
    pl.add_argument("--intensity", default="standard", choices=["light", "standard", "aggressive"])
    pl.add_argument("-o", "--output")
    pl.add_argument("--report")

    bt = sub.add_parser("batch")
    bt.add_argument("input_dir")
    bt.add_argument("output_dir")
    bt.add_argument("--mode", default="pipeline", choices=["detect", "clean", "dilute", "pipeline"])
    bt.add_argument("--lang", default="auto", choices=["auto", "de", "en"])
    bt.add_argument("--intensity", default="standard", choices=["light", "standard", "aggressive"])
    bt.add_argument("--report")

    sv = sub.add_parser("serve")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8080)

    args = p.parse_args()

    if args.cmd == "detect":
        text = _read(args)
        result = detect_text(text, lang=args.lang)
        rendered = json.dumps(result, ensure_ascii=False, indent=2) if args.json or args.output else json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).write_text(rendered, encoding="utf-8")
        else:
            print(rendered)
        high = result["layers"]["markers"]["high"]
        uni = result["layers"]["unicode"]["count"]
        return 1 if high or uni else 0

    if args.cmd == "clean":
        text = _read(args)
        result = clean_text(text, nfkc=args.nfkc, fold_confusables=args.fold_confusables)
        if args.output:
            Path(args.output).write_text(result.text, encoding="utf-8")
        else:
            print(result.text)
        if args.report:
            write_json(args.report, result.to_dict())
        return 0

    if args.cmd == "dilute":
        text = _read(args)
        result = dilute_text(text, intensity=args.intensity)
        if args.output:
            Path(args.output).write_text(result.text, encoding="utf-8")
        else:
            print(result.text)
        return 0

    if args.cmd == "pipeline":
        text = _read(args)
        out, report = run_pipeline(
            text,
            lang=args.lang,
            nfkc=args.nfkc,
            fold_confusables=args.fold_confusables,
            intensity=args.intensity,
        )
        if args.output:
            Path(args.output).write_text(out, encoding="utf-8")
        else:
            print(out)
        if args.report:
            write_json(args.report, report)
        return 0

    if args.cmd == "batch":
        report = process_batch(args.input_dir, args.output_dir, mode=args.mode, intensity=args.intensity, lang=args.lang)
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        if args.report:
            write_json(args.report, report)
        print(rendered)
        return 0

    if args.cmd == "serve":
        from uvicorn import run
        run("ai_watermark_toolkit.api.fastapi_app:app", host=args.host, port=args.port, reload=False)
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
