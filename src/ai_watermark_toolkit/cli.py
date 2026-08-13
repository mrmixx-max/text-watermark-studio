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
    d.add_argument("--pretty", action="store_true")
    d.add_argument("--aggressive", action="store_true", help="also flag script fillers (Braille blank, Hangul, ...)")
    d.add_argument("-o", "--output")

    sp = sub.add_parser("splash", help="Show the studio banner and system state")
    sp.add_argument("--plain", action="store_true", help="no ANSI colors")

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

    em = sub.add_parser("embed")
    em.add_argument("input", nargs="?")
    em.add_argument("--stdin", action="store_true")
    em.add_argument("--key", required=True, help="key_id from data/key_registry.json (must carry a secret)")
    em.add_argument("--gamma", type=float, default=None)
    em.add_argument("-o", "--output")

    fi = sub.add_parser("file-inspect")
    fi.add_argument("input", help="file to inspect (png/jpg/svg/pdf/docx/odt/html/md)")
    fi.add_argument("--json", action="store_true")

    fc = sub.add_parser("file-clean")
    fc.add_argument("input", help="file to clean")
    fc.add_argument("-o", "--output", required=True, help="output path for cleaned file")
    fc.add_argument("--json", action="store_true")

    fe = sub.add_parser("file-embed")
    fe.add_argument("input", help="file to watermark")
    fe.add_argument("--key", required=True, help="key_id (must carry a secret)")
    fe.add_argument("-o", "--output", required=True)

    fd = sub.add_parser("file-detect")
    fd.add_argument("input", help="file to verify")
    fd.add_argument("--json", action="store_true")

    rw = sub.add_parser("rewrite")
    rw.add_argument("input", nargs="?")
    rw.add_argument("--stdin", action="store_true")
    rw.add_argument("--mode", default="clarity", choices=["clarity", "concise", "plain", "formal", "structural", "backtranslate"])
    rw.add_argument("--use-llm", action="store_true", help="force the local LLM backend")
    rw.add_argument("--no-preserve", action="store_true", help="disable protected-token preservation")
    rw.add_argument("--json", action="store_true")
    rw.add_argument("-o", "--output")

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

    if args.cmd == "splash":
        from .ui import render_banner
        print(render_banner(color=not args.plain))
        try:
            from .forensics.key_registry import KeyRegistry
            registry = KeyRegistry('data/key_registry.json')
            keys = registry.list_keys()
            kgw = [k for k in keys if k.get('family') == 'kgw' and k.get('secret')]
            print(f"  keys registered : {len(keys)} ({len(kgw)} KGW)")
        except Exception:
            pass
        try:
            import json as _json
            llm = _json.loads(open('data/local_llm.json', encoding='utf-8').read())
            print(f"  local llm       : {llm.get('model_variant', llm.get('model_family', 'unconfigured'))} @ {llm.get('server_base_url', 'unconfigured')}")
        except Exception:
            print("  local llm       : unconfigured")
        return 0

    if args.cmd == "detect":
        text = _read(args)
        result = detect_text(text, lang=args.lang, aggressive=getattr(args, "aggressive", False))
        rendered = json.dumps(result, ensure_ascii=False, indent=2) if args.json or args.output else json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).write_text(rendered, encoding="utf-8")
        elif args.pretty:
            from .ui import render_detect_report
            print(render_detect_report(result, color=True))
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

    if args.cmd == "embed":
        from .forensics.key_registry import KeyRegistry
        from .forensics.kgw import embed_kgw, DEFAULT_GAMMA
        text = _read(args)
        registry = KeyRegistry('data/key_registry.json')
        key = next((k for k in registry.list_keys() if k.get('key_id') == args.key), None)
        if key is None:
            print(f"ai-wm: error: key not found: {args.key}", file=sys.stderr)
            return 2
        if not key.get('secret'):
            print(f"ai-wm: error: key {args.key} has no secret", file=sys.stderr)
            return 2
        result = embed_kgw(text, key['secret'], gamma=args.gamma or key.get('gamma') or DEFAULT_GAMMA)
        out = result['text']
        if args.output:
            Path(args.output).write_text(out, encoding="utf-8")
        else:
            print(out)
        print(f"# embedded: {result['replacements']} replacements, green_rate {result['green_rate_after']}", file=sys.stderr)
        return 0

    if args.cmd == "file-inspect":
        from .metadata.service import inspect
        data = Path(args.input).read_bytes()
        report = inspect(data, args.input)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            for k, v in report.items():
                print(f"{k}: {v}")
        return 0

    if args.cmd == "file-clean":
        from .metadata.service import clean
        data = Path(args.input).read_bytes()
        cleaned, report = clean(data, args.input)
        Path(args.output).write_bytes(cleaned)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            for k, v in report.items():
                print(f"{k}: {v}")
        print(f"# cleaned -> {args.output}", file=sys.stderr)
        return 0

    if args.cmd == "file-embed":
        from .forensics.key_registry import KeyRegistry
        from .metadata.provenance import embed_provenance
        registry = KeyRegistry('data/key_registry.json')
        key = next((k for k in registry.list_keys() if k.get('key_id') == args.key), None)
        if key is None:
            print(f"ai-wm: error: key not found: {args.key}", file=sys.stderr)
            return 2
        if not key.get('secret'):
            print(f"ai-wm: error: key {args.key} has no secret", file=sys.stderr)
            return 2
        data = Path(args.input).read_bytes()
        result = embed_provenance(data, args.input, args.key, key['secret'])
        if not result.embedded:
            print(f"ai-wm: error: unsupported format: {result.format}", file=sys.stderr)
            return 2
        Path(args.output).write_bytes(result.data)
        print(f"# embedded {args.key} mark ({result.mark_size} bytes) -> {args.output}", file=sys.stderr)
        return 0

    if args.cmd == "file-detect":
        from .forensics.key_registry import KeyRegistry
        from .metadata.provenance import detect_provenance
        registry = KeyRegistry('data/key_registry.json')
        secrets = {k.get('key_id'): k.get('secret') for k in registry.list_keys() if k.get('secret')}
        data = Path(args.input).read_bytes()
        result = detect_provenance(data, args.input, secrets)
        if args.json:
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        else:
            print(f"format: {result.format} | found: {result.found} | key_id: {result.key_id} | valid: {result.valid} | reason: {result.reason}")
        return 0 if (result.found and result.valid) else 1

    if args.cmd == "rewrite":
        import os as _os
        from .rewrite.service import RewriteService
        text = _read(args)
        svc = RewriteService(llm_backend=bool(_os.getenv('LOCAL_LLM_ENABLED', '0') == '1'))
        use_llm = True if getattr(args, 'use_llm', False) else None
        result = svc.rewrite(text, mode=args.mode, preserve=not getattr(args, 'no_preserve', False), use_llm=use_llm)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(result['rewritten'])
        if args.output:
            Path(args.output).write_text(result['rewritten'], encoding='utf-8')
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


def main_entry() -> int:
    """Wrapper that turns unexpected errors into clean stderr messages.

    Raw Python tracebacks on the CLI are unprofessional and confuse
    scripts that parse stderr. Exit codes stay meaningful: 0 = ok,
    1 = findings/processing result, 2 = usage/input error.
    """
    try:
        return main()
    except FileNotFoundError as e:
        print(f"ai-wm: error: file not found: {e.filename or e}", file=sys.stderr)
        return 2
    except IsADirectoryError as e:
        print(f"ai-wm: error: expected a file, got a directory: {e.filename}", file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"ai-wm: error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main_entry())
