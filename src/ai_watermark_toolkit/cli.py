from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

from .ingest import read_text
from .pipeline import detect_text, run_pipeline
from .report import write_json
from .transform.clean import clean_text
from .transform.dilute import dilute_text
from .batch import process_batch
from .forensics.key_registry import mask_secret_key_id


def _resolve_key_arg(args: argparse.Namespace) -> str | None:
    """Resolve the effective signing key from CLI arguments.

    ``--key-file`` content wins over ``--key``, letting callers pass a raw
    secret without it appearing in shell history.

    Args:
        args: Parsed command-line arguments.

    Returns:
        The resolved secret string, or ``None`` if neither source was
        provided.
    """
    key_file = getattr(args, "key_file", None)
    if key_file:
        return Path(key_file).read_text(encoding="utf-8").strip()
    return getattr(args, "key", None)


def _resolve_secret_arg(args: argparse.Namespace) -> str | None:
    """Resolve the effective HMAC / signing secret from CLI arguments.

    ``--secret-file`` content wins over ``--secret``, keeping the secret out
    of shell history.

    Args:
        args: Parsed command-line arguments.

    Returns:
        The resolved secret string, or ``None``.
    """
    secret_file = getattr(args, "secret_file", None)
    if secret_file:
        return Path(secret_file).read_text(encoding="utf-8").strip()
    return getattr(args, "secret", None)


def _resolve_key(
    registry: object,
    key_arg: str,
) -> tuple[dict, bool]:
    """Resolve a ``--key`` argument (key_id OR raw secret) to a key dict.

    A matching ``key_id`` in the registry returns that entry (including its
    secret).  Anything else is treated as a raw secret; its reported key_id
    is masked (``secret:<sha256-prefix>``) so the secret never appears in
    detect / finding / report output.

    Args:
        registry: A ``KeyRegistry`` instance with ``list_keys()``.
        key_arg: The string from ``--key`` or ``--key-file``.

    Returns:
        A ``(key_dict, from_registry)`` pair.  ``from_registry`` is
        ``True`` when the key was found in the registry; ``False`` when
        it was treated as a raw secret.
    """
    key = next((k for k in registry.list_keys() if k.get('key_id') == key_arg), None)
    if key is not None:
        return key, True
    return {"key_id": mask_secret_key_id(key_arg), "family": "kgw",
            "secret": key_arg, "gamma": None, "key_source": "raw_secret"}, False


def _read(args: argparse.Namespace) -> str:
    """Read input text from a file or stdin.

    Args:
        args: Parsed CLI arguments; expects ``.stdin`` (bool) and
            ``.input`` (optional str) attributes.

    Returns:
        The full text read from the file or stdin.
    """
    if args.stdin:
        return read_text(stdin_text=sys.stdin.read()).text
    return read_text(path=args.input).text


def main() -> int:
    """CLI entry point: parse arguments and dispatch to the matching command.

    Builds an ``argparse`` subcommand tree for all ``ai-wm`` operations —
    ``detect``, ``clean``, ``dilute``, ``embed``, ``pipeline``, ``batch``,
    ``report`` / ``report-sign`` / ``report-verify`` / ``report-keygen``,
    ``delta-z``, ``trace``, ``finding``, ``payload``, ``evade``,
    ``file-{inspect,clean,embed,detect}``, ``image-score``, ``watch``,
    ``rewrite``, ``similarity``, ``llm``, ``kgw-sample``, ``tui``,
    ``serve``, ``splash`` — and runs the handler.

    Returns:
        | ``0`` — success / no findings.
        | ``1`` — findings detected (markers, unicode, watermark).
        | ``2`` — usage or input error.
    """
    p = argparse.ArgumentParser(prog="ai-wm")
    p.add_argument("--quiet", "-q", action="store_true", help="suppress status messages on stderr (machine-readable output only)")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("detect")
    d.add_argument("input", nargs="?")
    d.add_argument("--stdin", action="store_true")
    d.add_argument("--lang", default="auto", choices=["auto", "de", "en"])
    d.add_argument("--json", action="store_true")
    d.add_argument("--pretty", action="store_true")
    d.add_argument("--aggressive", action="store_true", help="also flag script fillers (Braille blank, Hangul, ...)")
    d.add_argument("-o", "--output")
    d.add_argument("--key", default=None, help="key_id / secret for the keyed KGW test (enables real Z-score detection)")
    d.add_argument("--key-file", default=None, help="read the raw secret from a file (keeps it out of shell history); overrides --key")
    d.add_argument("--level", default="word", choices=["word", "bpe"], help="token level for KGW detection (default word)")
    d.add_argument("--context", type=int, default=1, help="greenlist context window c (default 1)")
    d.add_argument("--e-value", action="store_true",
                   help="also run anytime-valid e-process detection (E >= 1/alpha, log-space, Bonferroni in multi-key runs); requires --key")
    d.add_argument("--signature-filter", action="store_true",
                   help="opt-in signature-token pre-filter: drop token types with share >= 0.25 AND |z_contribution| >= 3 before the green count — FPR control for texts dominated by one repetitive token (arXiv 2606.18430v2), NOT a TPR gain; requires --key")

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
    em.add_argument("--key", help="key_id from data/key_registry.json (must carry a secret) or a raw secret")
    em.add_argument("--key-file", default=None, help="read the raw secret from a file (keeps it out of shell history); overrides --key")
    em.add_argument("--gamma", type=float, default=None)
    em.add_argument("--level", default="word", choices=["word", "bpe"], help="token level for greenlist marking (default word)")
    em.add_argument("--context", type=int, default=1, help="greenlist context window c (default 1)")
    em.add_argument("--seed", type=int, default=None, help="RNG seed for deterministic marking")
    em.add_argument("-o", "--output")

    fi = sub.add_parser("file-inspect")
    fi.add_argument("input", help="file to inspect (png/jpg/svg/pdf/docx/odt/html/md)")
    fi.add_argument("--json", action="store_true")

    fc = sub.add_parser("file-clean")
    fc.add_argument("input")
    fc.add_argument("-o", "--output", required=True)
    fc.add_argument("--verify", action="store_true",
                    help="re-inspect the cleaned file and report C2PA before/after (verified_clear | residual_hard_bound | no_c2pa_present)")
    fc.add_argument("--json", action="store_true")

    fe = sub.add_parser("file-embed")
    fe.add_argument("input", help="file to watermark")
    fe.add_argument("--key", required=True, help="key_id (must carry a secret)")
    fe.add_argument("-o", "--output", required=True)

    fd = sub.add_parser("file-detect")
    fd.add_argument("input", help="file to verify")
    fd.add_argument("--json", action="store_true")

    rp = sub.add_parser("report")
    rp.add_argument("input", nargs="?")
    rp.add_argument("--stdin", action="store_true")
    rp.add_argument("--key", help="key_id / secret for the KGW test")
    rp.add_argument("--key-file", default=None, help="read the raw secret from a file (keeps it out of shell history); overrides --key")
    rp.add_argument("--lang", default="de", choices=["en", "de"])
    rp.add_argument("--level", default="word", choices=["word", "bpe"], help="token level for KGW detection (default word)")
    rp.add_argument("--context", type=int, default=1, help="greenlist context window c (default 1)")
    rp.add_argument("--pdf", action="store_true", help="render to PDF via Edge headless (Windows)")
    rp.add_argument("-o", "--output", default=None, help="output path (default: tws-report-<ts>.html)")

    rs = sub.add_parser("report-sign", help="sign a forensic findings payload into an auditable JSON document (HMAC-SHA256 stdlib or ML-DSA FIPS 204 optional)")
    rs.add_argument("input", nargs="?", default="-", help="payload JSON file (or - for stdin)")
    rs.add_argument("--secret", default=None, help="HMAC secret")
    rs.add_argument("--secret-file", default=None, help="read the HMAC secret from a file (keeps it out of shell history); overrides --secret")
    rs.add_argument("--key-id", default=None, help="key identifier recorded in the signature (default: default)")
    rs.add_argument("--algorithm", default="hmac-sha256", choices=["hmac-sha256", "mldsa-44", "mldsa-65", "mldsa-87"])
    rs.add_argument("--private-key", default=None, help="PEM private key for --algorithm mldsa-44|65|87 (generate with ai-wm report-keygen)")
    rs.add_argument("-o", "--output", default="report-signed.json", help="output path (default report-signed.json)")

    rv = sub.add_parser("report-verify", help="verify a signed forensic findings document (exit 0 valid / 1 invalid / 2 usage)")
    rv.add_argument("input", help="signed JSON file")
    rv.add_argument("--secret", default=None, help="HMAC secret")
    rv.add_argument("--secret-file", default=None, help="read the HMAC secret from a file; overrides --secret")
    rv.add_argument("--public-key", default=None, help="PEM public key for ML-DSA (mldsa-44/65/87) signatures (default: embedded in the signature)")
    rv.add_argument("--json", action="store_true", help="machine-readable output (JSON is the default)")

    rk = sub.add_parser("report-keygen", help="generate an ML-DSA keypair for signing forensic findings (FIPS 204, needs cryptography)")
    rk.add_argument("--algorithm", default="mldsa-44", choices=["mldsa-44", "mldsa-65", "mldsa-87"])
    rk.add_argument("--output-dir", default=".", help="directory for the PEM files (default: current directory)")
    rk.add_argument("--prefix", default="mldsa", help="file name prefix (default mldsa -> mldsa_private.pem / mldsa_public.pem)")

    wc = sub.add_parser("watch")
    wc.add_argument("directory")
    wc.add_argument("--once", action="store_true", help="single scan pass, then exit")
    wc.add_argument("--interval", type=float, default=5.0, help="poll seconds (default 5)")
    wc.add_argument("--kgw", action="store_true",
                    help="also run KGW text detection on text files (requires registered KGW keys with secrets)")

    tui = sub.add_parser("tui", help="launch the menu-driven terminal UI (needs textual)")

    sim = sub.add_parser("similarity", help="compare a text against YOUR OWN corpus (local MinHash, honest boundary)")
    sim.add_argument("input", help="text file to check")
    sim.add_argument("--corpus", action="append", required=True,
                     help="corpus file or directory (repeatable)")
    sim.add_argument("--threshold", type=float, default=0.4,
                     help="similarity threshold for findings (default 0.4)")
    sim.add_argument("--top", type=int, default=5, help="max findings shown (default 5)")
    sim.add_argument("--json", action="store_true", help="machine-readable output")

    llm = sub.add_parser("llm", help="manage the local model backend (Ollama)")
    llm_sub = llm.add_subparsers(dest="llm_action", required=True)
    llm_install = llm_sub.add_parser("install", help="pull a model via the Ollama API and select it")
    llm_install.add_argument("model")
    llm_sub.add_parser("list", help="list models known to the local Ollama instance")
    llm_use = llm_sub.add_parser("use", help="switch to an already-installed model")
    llm_use.add_argument("model")
    llm_sub.add_parser("status", help="show the current backend configuration")

    rw = sub.add_parser("rewrite")
    rw.add_argument("input", nargs="?")
    rw.add_argument("--stdin", action="store_true")
    rw.add_argument("--mode", default="clarity", choices=["clarity", "concise", "plain", "formal", "structural", "backtranslate"])
    rw.add_argument("--use-llm", action="store_true", help="force the local LLM backend")
    rw.add_argument("--no-preserve", action="store_true", help="disable protected-token preservation")
    rw.add_argument("--json", action="store_true")
    rw.add_argument("-o", "--output")

    ims = sub.add_parser("image-score")
    ims.add_argument("input", help="image to score for SynthID pixel marks")
    ims.add_argument("--synthid-dir", default=None, help="reverse-SynthID checkout path")
    ims.add_argument("--json", action="store_true")

    pl = sub.add_parser("pipeline")
    pl.add_argument("input", nargs="?")
    pl.add_argument("--stdin", action="store_true")
    pl.add_argument("--lang", default="auto", choices=["auto", "de", "en"])
    pl.add_argument("--nfkc", action="store_true")
    pl.add_argument("--fold-confusables", action="store_true")
    pl.add_argument("--intensity", default="standard", choices=["light", "standard", "aggressive"])
    pl.add_argument("--rewrite-mode", default=None, choices=["clarity", "concise", "plain", "formal", "structural", "backtranslate"], help="optional rewrite phase after dilute")
    pl.add_argument("--aggressive", action="store_true", help="aggressive unicode scanning")
    pl.add_argument("-o", "--output")
    pl.add_argument("--report")

    rm = sub.add_parser("remove", help="best-effort watermark removal: clean unicode + dilute + structural rewrite (the README's honest removal path)")
    rm.add_argument("input", nargs="?")
    rm.add_argument("--stdin", action="store_true")
    rm.add_argument("--lang", default="auto", choices=["auto", "de", "en"])
    rm.add_argument("--intensity", default="standard", choices=["light", "standard", "aggressive"], help="dilute intensity (default standard)")
    rm.add_argument("--rewrite-mode", default="structural", choices=["clarity", "concise", "plain", "formal", "structural", "backtranslate"], help="rewrite mode (default structural — reorders while keeping facts)")
    rm.add_argument("--use-llm", action="store_true", help="force the local LLM backend for rewriting")
    rm.add_argument("--no-preserve", action="store_true", help="disable protected-token preservation")
    rm.add_argument("--aggressive", action="store_true", help="aggressive unicode scanning")
    rm.add_argument("--json", action="store_true", help="machine-readable output")
    rm.add_argument("-o", "--output")

    bt = sub.add_parser("batch")
    bt.add_argument("input_dir")
    bt.add_argument("output_dir")
    bt.add_argument("--mode", default="pipeline", choices=["detect", "clean", "dilute", "pipeline", "embed"])
    bt.add_argument("--lang", default="auto", choices=["auto", "de", "en"])
    bt.add_argument("--intensity", default="standard", choices=["light", "standard", "aggressive"])
    bt.add_argument("--key", default=None, help="key_id for --mode embed (must carry a secret)")
    bt.add_argument("--level", default="word", choices=["word", "bpe"], help="token level for --mode embed (default word)")
    bt.add_argument("--context", type=int, default=1, help="greenlist context window c for --mode embed (default 1)")
    bt.add_argument("--gamma", type=float, default=None, help="greenlist fraction for --mode embed (default: key's gamma or 0.25)")
    bt.add_argument("--seed", type=int, default=None, help="RNG seed for deterministic --mode embed")
    bt.add_argument("--verify", action="store_true", help="for --mode embed: run detection after embedding to confirm the watermark is detectable (Z>4)")
    bt.add_argument("--report")

    ks = sub.add_parser("kgw-sample", help="generate synthetic KGW-bias text and detect it (experimental generation-time bias demo)")
    ks.add_argument("--key", default="demo-sampling-bias-key", help="secret key (default: demo key)")
    ks.add_argument("--gamma", type=float, default=0.5, help="greenlist fraction (default 0.5)")
    ks.add_argument("--bias", type=float, default=2.0, help="additive logit bias on greenlist tokens (default 2.0)")
    ks.add_argument("--n-tokens", type=int, default=200, help="tokens to generate (default 200)")
    ks.add_argument("--seed", type=int, default=0)
    ks.add_argument("--context", type=int, default=1, help="greenlist context window c (default 1)")
    ks.add_argument("--prefix", default="", help="optional prefix text as context")
    ks.add_argument("--json", action="store_true", help="machine-readable output")

    sv = sub.add_parser("serve")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8080)

    dz = sub.add_parser("delta-z", help="ΔZ check: measure KGW watermark strength before vs after (removal with receipt)")
    dz.add_argument("before", nargs="?", help="file with the text BEFORE cleaning/attack (single file when --transform is used)")
    dz.add_argument("after", nargs="?", help="file with the text AFTER cleaning/attack (omitted with --transform)")
    dz.add_argument("--stdin", action="store_true")
    dz.add_argument("--key", default=None, help="key_id from data/key_registry.json (must carry a secret) or a raw secret")
    dz.add_argument("--key-file", default=None, help="read the raw secret from a file (keeps it out of shell history); overrides --key")
    dz.add_argument("--level", default="word", choices=["word", "bpe"], help="token level for KGW detection (default word)")
    dz.add_argument("--context", type=int, default=1, help="greenlist context window c (default 1)")
    dz.add_argument("--transform", default=None, choices=["clean", "truncate", "shuffle", "reformat", "rewrite"],
                    help="apply a transform to the single input file and measure its ΔZ (no second file)")
    dz.add_argument("--truncate-fraction", type=float, default=0.6, help="fraction of leading tokens kept by --transform truncate (default 0.6)")
    dz.add_argument("--rewrite-mode", default="structural", choices=["clarity", "concise", "plain", "formal", "structural", "backtranslate"],
                    help="RewriteService mode for --transform rewrite (default structural — rule-based, no LLM)")
    dz.add_argument("--use-llm", action="store_true",
                    help="with --transform rewrite: call the local Ollama backend instead of the rule-based path")
    dz.add_argument("--seed", type=int, default=42, help="RNG seed for --transform shuffle (default 42)")
    dz.add_argument("--sign", default=None, help="HMAC secret: sign the ΔZ result (signed_report) for an auditable document")
    dz.add_argument("--sign-file", default=None, help="read the HMAC signing secret from a file; overrides --sign")
    dz.add_argument("-o", "--output", default=None, help="write the JSON result to a file instead of stdout")

    fi = sub.add_parser("finding", help="KI-Erklärungs-Befund (C5): Evidenzklassen A-D, Prüfpriorität 0-5, ehrlicher verdict_text — nie 'KI-generiert' als Feststellung")
    fi.add_argument("input", nargs="?")
    fi.add_argument("--stdin", action="store_true")
    fi.add_argument("--key", default=None, help="key_id from data/key_registry.json (must carry a secret) or a raw secret")
    fi.add_argument("--key-file", default=None, help="read the raw secret from a file (keeps it out of shell history); overrides --key")
    fi.add_argument("--level", default="word", choices=["word", "bpe"], help="token level for KGW detection (default word)")
    fi.add_argument("--context", type=int, default=1, help="greenlist context window c (default 1)")
    fi.add_argument("--e-value", action="store_true", help="also run the anytime-valid e-process (E-Wert-Befund, Klasse C)")
    fi.add_argument("--delta-z", metavar="FILE_AFTER", default=None, help="also run the ΔZ comparison against FILE_AFTER (Vergleichsbefund, Klasse B)")
    fi.add_argument("--institutional-rule", default=None, help="institutionelle KI-Regel (Evidenzklasse D): Regeltext, gegen den der Befund gehalten wird — setzt context_missing:false")
    fi.add_argument("--origin-history", default=None, help="Entstehungshistorie (Evidenzklasse D): Entwürfe, Versionen, Betreuungsfeedback, Abgabedatum — setzt context_missing:false")
    fi.add_argument("--frs", action="store_true", help="Forensic-Readiness-Score (12 Kriterien, 3 Gates, ehrliches Selbst-Assessment) in den Befund aufnehmen")
    fi.add_argument("--lang", default="de", choices=["de", "en"], help="report language: de (default) or en")
    fi.add_argument("--sign", default=None, help="HMAC secret: sign the finding report (signed_report)")
    fi.add_argument("--sign-file", default=None, help="read the HMAC signing secret from a file; overrides --sign")
    fi.add_argument("-o", "--output", default=None, help="write the JSON report to a file instead of stdout")

    tr = sub.add_parser("trace", help="KGW Z-score trajectory: sliding-window detection over a long document (find WHERE the watermark is, not just IF)")
    tr.add_argument("input", nargs="?")
    tr.add_argument("--stdin", action="store_true")
    tr.add_argument("--key", default=None, help="key_id from data/key_registry.json (must carry a secret) or a raw secret")
    tr.add_argument("--key-file", default=None, help="read the raw secret from a file (keeps it out of shell history); overrides --key")
    tr.add_argument("--level", default="word", choices=["word", "bpe"], help="token level for KGW detection (default word)")
    tr.add_argument("--context", type=int, default=1, help="greenlist context window c (default 1)")
    tr.add_argument("--window", type=int, default=500, help="sliding window size in words (default 500)")
    tr.add_argument("--step", type=int, default=0, help="step between windows in words (default = window, i.e. non-overlapping)")
    tr.add_argument("--threshold", type=float, default=4.0, help="Z threshold for a finding window (default 4.0)")
    tr.add_argument("--json", action="store_true", help="emit the full JSON trajectory instead of the human report")
    tr.add_argument("-o", "--output", default=None, help="write the JSON result to a file instead of stdout")

    mb = sub.add_parser("payload", help="multi-bit invariant-feature watermarking: embed/extract a text payload (user id, timestamp, run id) into a text")
    mb_sub = mb.add_subparsers(dest="payload_action", required=True)
    mb_emb = mb_sub.add_parser("embed", help="embed a payload into a text file (codebook: 1 bit per mask position)")
    mb_emb.add_argument("input", nargs="?", help="original text file")
    mb_emb.add_argument("--stdin", action="store_true")
    mb_emb.add_argument("--payload", required=True, help="the text payload to embed (e.g. user-42, run-2026-08-16)")
    mb_emb.add_argument("--max-masks", type=int, default=None, help="cap mask positions (payload capacity); default = all usable positions")
    mb_emb.add_argument("-o", "--output", required=True, help="write the watermarked text here")
    mb_ext = mb_sub.add_parser("extract", help="recover the payload from a watermarked text (needs the ORIGINAL text as reference state)")
    mb_ext.add_argument("input", nargs="?", help="watermarked text file")
    mb_ext.add_argument("--stdin", action="store_true")
    mb_ext.add_argument("--reference", required=True, help="the ORIGINAL text file (both parties share the invariant anchor state)")
    mb_ext.add_argument("--reference-stdin", action="store_true", help="read the original text from stdin instead of a file")
    mb_ext.add_argument("--json", action="store_true", help="emit the full JSON extraction result")
    mb_ext.add_argument("-o", "--output", default=None, help="write the JSON result to a file instead of stdout")

    ev = sub.add_parser("evade", help="adversarial evaluation (white-box, own scheme): push the KGW Z-score below a threshold with minimal edits — stress test, not a laundering tool")
    ev.add_argument("input", nargs="?")
    ev.add_argument("--stdin", action="store_true")
    ev.add_argument("--key", default=None, help="key_id from data/key_registry.json (must carry a secret) or a raw secret")
    ev.add_argument("--key-file", default=None, help="read the raw secret from a file (keeps it out of shell history); overrides --key")
    ev.add_argument("--level", default="word", choices=["word", "bpe"], help="token level for KGW detection (default word)")
    ev.add_argument("--context", type=int, default=1, help="greenlist context window c (default 1)")
    ev.add_argument("--target-z", type=float, default=3.9, help="Z threshold to get below (default 3.9)")
    ev.add_argument("--max-changes", type=int, default=None, help="cap the edit budget (default: unlimited until target)")
    ev.add_argument("--ollama-model", default=None, help="optional local Ollama model for natural candidates per position")
    ev.add_argument("--seed", type=int, default=0, help="RNG seed for green-position order (default 0)")
    ev.add_argument("--json", action="store_true", help="emit the full JSON measurement instead of the human report")
    ev.add_argument("-o", "--output", default=None, help="write the evaded text (or JSON with --json) to a file")

    args = p.parse_args()

    # Guard: output path same as input path would destroy the source file.
    # Check before any processing so we fail fast instead of after a
    # potentially expensive operation.
    input_path = getattr(args, "input", None)
    output_path = getattr(args, "output", None)
    if input_path and output_path:
        try:
            if Path(input_path).resolve() == Path(output_path).resolve():
                print(f"ai-wm: error: output path is the same as input path ({input_path}) — refusing to overwrite the source", file=sys.stderr)
                return 2
        except OSError:
            pass  # If we can't resolve paths, let the command handle it

    # --quiet: suppress stderr status messages for scripted use. Errors
    # printed via print(..., file=sys.stderr) are silenced; stdout JSON is
    # untouched so pipelines keep working.
    if getattr(args, "quiet", False):
        import io
        sys.stderr = io.StringIO()

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
            logger.debug("key registry unavailable for splash display", exc_info=True)
        try:
            import json as _json
            llm = _json.loads(open('data/local_llm.json', encoding='utf-8').read())
            print(f"  local llm       : {llm.get('model_variant', llm.get('model_family', 'unconfigured'))} @ {llm.get('server_base_url', 'unconfigured')}")
        except Exception:
            print("  local llm       : unconfigured")
        return 0

    if args.cmd == "detect":
        text = _read(args)
        key_arg = _resolve_key_arg(args)
        if getattr(args, "e_value", False) and not key_arg:
            print("ai-wm: error: --e-value requires --key (e-process detection is keyed)", file=sys.stderr)
            return 2
        if getattr(args, "signature_filter", False) and not key_arg:
            print("ai-wm: error: --signature-filter requires --key (the filter only applies to the keyed KGW Z-test)", file=sys.stderr)
            return 2
        if key_arg:
            # Keyed KGW detection path (real Z-score test, sign-preserving).
            from .forensics.key_registry import KeyRegistry
            from .forensics.kgw import detect_multi_key, DEFAULT_GAMMA
            registry = KeyRegistry('data/key_registry.json')
            key = next((k for k in registry.list_keys() if k.get('key_id') == key_arg), None)
            if key is None:
                # allow a raw secret to be passed directly as --key; the
                # reported key_id is masked so the secret never leaks into
                # the JSON output (the detection uses the real secret)
                key = {"key_id": mask_secret_key_id(key_arg), "family": "kgw",
                       "secret": key_arg, "gamma": None, "key_source": "raw_secret"}
            if not key.get('secret'):
                print(f"ai-wm: error: key {key_arg} has no secret", file=sys.stderr)
                return 2
            result = detect_multi_key(text, [key],
                                      gamma=key.get('gamma') or DEFAULT_GAMMA,
                                      level=getattr(args, "level", "word"),
                                      context=getattr(args, "context", 1),
                                      signature_filter=getattr(args, "signature_filter", False))
            best = result.get('best') or {}
            out = {
                "verdict": best.get("verdict", "no_signal"),
                "signal": best.get("signal"),
                "z_score": best.get("z_score"),
                "p_value": best.get("p_value"),
                "green_rate": best.get("green_rate"),
                "key_id": best.get("key_id"),
                "best_p_adjusted": result.get("best_p_adjusted"),
                "tested_keys": result.get("tested_keys"),
                "kgw": result,
            }
            if getattr(args, "signature_filter", False):
                # Opt-in signature pre-filter: surface the per-key filter
                # report at top level (removed types, before/after sizes).
                out["signature_filtered"] = best.get("signature_filtered")
            e_value_result = None
            if getattr(args, "e_value", False):
                # Anytime-valid e-process detection on the SAME key, same
                # tokenization and same green_token PRF as the Z-score path.
                from .forensics.e_value import e_detect
                e_value_result = e_detect(
                    text, key["secret"],
                    gamma=key.get('gamma') or DEFAULT_GAMMA,
                    level=getattr(args, "level", "word"),
                    context=getattr(args, "context", 1),
                )
                out["e_value"] = e_value_result
            rendered = json.dumps(out, ensure_ascii=False, indent=2)
            if args.output:
                Path(args.output).write_text(rendered, encoding="utf-8")
            else:
                print(rendered)
            e_detected = bool(e_value_result and e_value_result.get("detected"))
            return 1 if (best.get("verdict") in ("watermark_detected", "redlist_detected") or e_detected) else 0
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
        from .forensics.kgw import mark_greenlist, DEFAULT_GAMMA
        text = _read(args)
        registry = KeyRegistry('data/key_registry.json')
        key = next((k for k in registry.list_keys() if k.get('key_id') == args.key), None)
        if key is None:
            print(f"ai-wm: error: key not found: {args.key}", file=sys.stderr)
            return 2
        if not key.get('secret'):
            print(f"ai-wm: error: key {args.key} has no secret", file=sys.stderr)
            return 2
        result = mark_greenlist(text, key['secret'],
                                gamma=args.gamma or key.get('gamma') or DEFAULT_GAMMA,
                                level=args.level, context=args.context, seed=args.seed)
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
        from .metadata.service import clean, verify_clean
        data = Path(args.input).read_bytes()
        cleaned, report = clean(data, args.input)
        Path(args.output).write_bytes(cleaned)
        if args.verify:
            verification = verify_clean(data, args.input)
            report["verification"] = verification
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
        from .rewrite.service import RewriteService
        text = _read(args)
        svc = RewriteService(llm_backend=bool(os.getenv('LOCAL_LLM_ENABLED', '0') == '1'))
        use_llm = True if getattr(args, 'use_llm', False) else None
        result = svc.rewrite(text, mode=args.mode, preserve=not getattr(args, 'no_preserve', False), use_llm=use_llm)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(result['rewritten'])
        if args.output:
            Path(args.output).write_text(result['rewritten'], encoding='utf-8')
        return 0

    if args.cmd == "image-score":
        from .metadata.synthid import score_synthid
        result = score_synthid(args.input, synthid_dir=getattr(args, "synthid_dir", None))
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            if not result.get("available"):
                print(f"synthid: unavailable — {result.get('reason', 'unknown')}")
                print(f"hint: {result.get('hint', 'run scripts/setup_synthid.sh')}")
                return 1
            if "error" in result:
                print(f"synthid: {result['error']}")
                return 1
            print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("available") and "error" not in result else 1

    if args.cmd == "report":
        import time as _time
        from .forensics.report import build_report, render_pdf
        from .sanitize_unicode import analyze as _uni_analyze
        from .pipeline import detect_text as _detect_text
        from .forensics.key_registry import KeyRegistry
        text = _read(args)
        uni = _uni_analyze(text)
        # marker hits from the detect pipeline (unicode excluded — those are uni above)
        d = _detect_text(text, lang=args.lang)
        marker_hits = d.get("layers", {}).get("lexical", {}).get("score", 0) if isinstance(d, dict) else 0
        # Resolve key_id -> secret (or accept a raw secret), like detect does.
        # The secret itself is never shown in the report; key_id is the label
        # (a raw secret's label is masked so it cannot leak into the HTML).
        effective_key = _resolve_key_arg(args)
        key_secret = effective_key
        key_label = mask_secret_key_id(effective_key) if effective_key else None
        if effective_key:
            try:
                reg = KeyRegistry()
                resolved, from_registry = _resolve_key(reg, effective_key)
                if from_registry:
                    key_secret = resolved.get("secret") or effective_key
                    key_label = resolved.get("key_id", effective_key)
            except Exception:
                logger.debug("registry unavailable -> masked raw argument stays the label", exc_info=True)
        html_out = build_report(text, key_secret, lang=args.lang,
                                unicode_findings=[asdict(x) for x in uni],
                                marker_hits=marker_hits,
                                key_label=key_label,
                                level=getattr(args, "level", "word"),
                                context=getattr(args, "context", 1))
        out_path = args.output or f"tws-report-{int(_time.time())}.html"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html_out)
        print(f"Befund geschrieben: {out_path}")
        if args.pdf:
            pdf = render_pdf(Path(out_path).resolve())
            if pdf:
                print(f"PDF gerendert: {pdf}")
            else:
                print("PDF-Rendering übersprungen (Edge nicht gefunden) — HTML liegt vor.")
        return

    if args.cmd == "report-sign":
        from .forensics.signed_report import sign_report, mldsa_status
        raw = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"ai-wm: error: input is not valid JSON: {e}", file=sys.stderr)
            return 2
        if not isinstance(payload, dict):
            print("ai-wm: error: payload must be a JSON object", file=sys.stderr)
            return 2
        secret = _resolve_secret_arg(args)
        if args.algorithm == "hmac-sha256" and not secret:
            print("ai-wm: error: --secret or --secret-file is required for hmac-sha256", file=sys.stderr)
            return 2
        private_key_pem = None
        if args.algorithm.startswith("mldsa"):
            status = mldsa_status()
            if not status["available"]:
                print(f"ai-wm: error: {args.algorithm} unavailable — {status['hint']}", file=sys.stderr)
                return 1
            if not args.private_key:
                print(f"ai-wm: error: --private-key <pem> is required for {args.algorithm} (generate with ai-wm report-keygen)", file=sys.stderr)
                return 2
            private_key_pem = Path(args.private_key).read_text(encoding="utf-8")
        signed = sign_report(payload, secret or "", key_id=args.key_id,
                             algorithm=args.algorithm, private_key_pem=private_key_pem)
        Path(args.output).write_text(
            json.dumps(signed, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"ok": True, "output": args.output,
                          "algorithm": args.algorithm,
                          "key_id": signed["signature"]["key_id"],
                          "signature_date": signed["signature"]["signature_date"]},
                         ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "report-verify":
        from .forensics.signed_report import verify_report, mldsa_status
        try:
            signed = json.loads(Path(args.input).read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"ai-wm: error: not valid JSON: {e}", file=sys.stderr)
            return 2
        secret = _resolve_secret_arg(args)
        algorithm = (signed.get("signature") or {}).get("algorithm") if isinstance(signed, dict) else None
        if algorithm == "hmac-sha256" and not secret:
            print("ai-wm: error: --secret or --secret-file is required for hmac-sha256", file=sys.stderr)
            return 2
        if algorithm and algorithm.startswith("mldsa") and not mldsa_status()["available"]:
            print(f"ai-wm: error: {algorithm} unavailable — {mldsa_status()['hint']}", file=sys.stderr)
            return 1
        public_key_pem = (Path(args.public_key).read_text(encoding="utf-8")
                          if args.public_key else None)
        result = verify_report(signed, secret, public_key_pem=public_key_pem)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["valid"] else 1

    if args.cmd == "report-keygen":
        from .forensics.signed_report import generate_mldsa_keypair, mldsa_status
        status = mldsa_status()
        if not status["available"]:
            print(f"ai-wm: error: {args.algorithm} unavailable — {status['hint']}", file=sys.stderr)
            return 1
        pair = generate_mldsa_keypair(args.algorithm)
        out_dir = Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        priv = out_dir / f"{args.prefix}_private.pem"
        pub = out_dir / f"{args.prefix}_public.pem"
        priv.write_text(pair["private_key_pem"], encoding="utf-8")
        pub.write_text(pair["public_key_pem"], encoding="utf-8")
        # P0-6: PrivKey nie weltweit lesbar (Unix 0644 wäre ein Review-Stopper)
        if os.name != "nt":
            os.chmod(priv, 0o600)
            os.chmod(pub, 0o644)
        print(json.dumps({"ok": True, "algorithm": pair["algorithm"],
                          "private_key": str(priv), "public_key": str(pub)},
                         ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "similarity":
        from pathlib import Path as _P
        from .forensics.similarity import check_similarity, render_text, render_json
        inp = _P(args.input)
        if not inp.is_file():
            print(f"error: input file not found: {args.input}", file=sys.stderr)
            return 2
        corpus = [_P(c) for c in args.corpus]
        if not any(c.exists() for c in corpus):
            print("error: no corpus path exists", file=sys.stderr)
            return 2
        report = check_similarity(inp.read_text(encoding="utf-8", errors="replace"),
                                  corpus, threshold=args.threshold, top=args.top)
        if args.json:
            print(render_json(report))
        else:
            print(render_text(report))
        return 1 if report["findings"] else 0

    if args.cmd == "llm":
        from .llm.service import LocalLLMService
        svc = LocalLLMService()
        if args.llm_action == "list":
            try:
                models = svc.list_models()
            except RuntimeError as e:
                print(f"error: {e}", file=sys.stderr)
                return 1
            if not models:
                print("no models")
                return 0
            for m in models:
                size_gb = m.get("size", 0) / 1e9
                print(f"{m.get('name', '?')}  ({size_gb:.1f} GB)")
            return 0
        if args.llm_action == "status":
            print(json.dumps(svc.status(), ensure_ascii=False, indent=2, default=str))
            return 0
        if args.llm_action == "use":
            try:
                cfg = svc.use_model(args.model)
            except (ValueError, RuntimeError) as e:
                print(f"error: {e}", file=sys.stderr)
                return 1
            print(f"active model: {cfg['model_variant']}")
            return 0
        if args.llm_action == "install":
            def progress(line):
                print(line, flush=True)
            try:
                result = svc.install_model(args.model, progress=progress)
            except RuntimeError as e:
                print(f"error: {e}", file=sys.stderr)
                return 1
            print(f"installed and selected: {result['model']}")
            return 0
        return 2

    if args.cmd == "tui":
        try:
            from .ui.tui import main as _tui_main
        except ImportError as e:
            print(f"error: textual not installed — pip install text-watermark-studio[tui] ({e})",
                  file=sys.stderr)
            return 2
        return _tui_main()

    if args.cmd == "watch":
        from .forensics.watcher import watch_dir
        if args.interval <= 0:
            print("ai-wm: error: --interval must be > 0", file=sys.stderr)
            return 2
        try:
            n = watch_dir(args.directory, once=args.once, interval=args.interval, kgw=getattr(args, "kgw", False))
        except NotADirectoryError as e:
            print(f"error: not a directory: {e}", file=sys.stderr)
            return 2
        if args.once:
            print(f"watch --once: {n} Datei(en) gemeldet.")
        return 0

    if args.cmd == "pipeline":
        text = _read(args)
        out, report = run_pipeline(
            text,
            lang=args.lang,
            nfkc=args.nfkc,
            fold_confusables=args.fold_confusables,
            intensity=args.intensity,
            rewrite_mode=getattr(args, "rewrite_mode", None),
            aggressive=getattr(args, "aggressive", False),
        )
        if args.output:
            Path(args.output).write_text(out, encoding="utf-8")
        else:
            print(out)
        if args.report:
            write_json(args.report, report)
        return 0

    if args.cmd == "remove":
        # Best-effort watermark removal: the README is honest that statistical
        # marks live in the wording itself — removal means rewording, not
        # restructuring. This command chains clean → dilute → rewrite to
        # degrade the signal as far as possible without an LLM. With
        # --use-llm it forces the local LLM backend for a stronger rewrite.
        # NOTE: clean_text and dilute_text are intentionally NOT re-imported
        # here — they would shadow the module-level imports (same names) and
        # Python's function scoping would make the clean/dilute handlers raise
        # UnboundLocalError. Use the module-level imports directly.
        import os as _os
        from .rewrite.service import RewriteService
        text = _read(args)
        cleaned = clean_text(text, nfkc=True, fold_confusables=True)
        diluted = dilute_text(cleaned.text, intensity=args.intensity)
        svc = RewriteService(llm_backend=bool(_os.getenv('LOCAL_LLM_ENABLED', '0') == '1'))
        use_llm = True if getattr(args, 'use_llm', False) else None
        rewritten = svc.rewrite(diluted.text, mode=args.rewrite_mode,
                                preserve=not getattr(args, 'no_preserve', False),
                                use_llm=use_llm)
        out = rewritten['rewritten']
        if args.json:
            report = {
                "original_length": len(text),
                "cleaned_length": len(cleaned.text),
                "diluted_length": len(diluted.text),
                "removed_length": len(out),
                "unicode_removed": cleaned.unicode_removed,
                "confusable_folds": cleaned.confusable_folds,
                "phrases_rewritten": diluted.changed,
                "rewrite_mode": args.rewrite_mode,
                "rewritten": out,
            }
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(out)
        if args.output:
            Path(args.output).write_text(out, encoding="utf-8")
        return 0

    if args.cmd == "batch":
        if args.context < 1:
            print("ai-wm: error: --context must be >= 1", file=sys.stderr)
            return 2
        if args.gamma is not None and not (0 < args.gamma <= 0.5):
            print("ai-wm: error: --gamma must be in (0, 0.5]", file=sys.stderr)
            return 2
        if not Path(args.input_dir).is_dir():
            print(f"ai-wm: error: input directory not found: {args.input_dir}", file=sys.stderr)
            return 2
        report = process_batch(args.input_dir, args.output_dir, mode=args.mode, intensity=args.intensity, lang=args.lang,
                               key_id=getattr(args, "key", None), level=getattr(args, "level", "word"),
                               context=getattr(args, "context", 1), gamma=getattr(args, "gamma", None),
                               seed=getattr(args, "seed", None), verify=getattr(args, "verify", False))
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        if args.report:
            write_json(args.report, report)
        print(rendered)
        return 0

    if args.cmd == "kgw-sample":
        from .generation.kgw_sampler import generate_marked_text
        from .forensics.kgw import detect_kgw
        gen = generate_marked_text(prefix=args.prefix, vocab=None, key=args.key,
                                   gamma=args.gamma, bias_strength=args.bias,
                                   n_tokens=args.n_tokens, seed=args.seed, context=args.context)
        det = detect_kgw(gen["text"], args.key, args.gamma, context=args.context)
        if args.json:
            print(json.dumps({"generated": gen, "detected": det}, ensure_ascii=False, indent=2))
        else:
            print(gen["text"])
            print(f"# green_rate {gen['green_rate']}  z={det['z_score']}  verdict={det['verdict']}  "
                  f"bias={args.bias} gamma={args.gamma} context={args.context} seed={args.seed}",
                  file=sys.stderr)
        return 0

    if args.cmd == "delta-z":
        # ΔZ check: measurement IS the product — exit 0 on any successful
        # measurement (even removed:true; removed is a FINDING, not an
        # error). Exit 2 for usage/input errors. Unlike `detect`, exit 1 is
        # not used for findings.
        from .forensics.delta_z import delta_z, delta_z_report, delta_z_transform
        from .forensics.key_registry import KeyRegistry
        key_arg = _resolve_key_arg(args)
        if not key_arg:
            print("ai-wm: error: delta-z requires --key (key_id or raw secret)", file=sys.stderr)
            return 2
        if args.transform:
            if args.after is not None:
                print("ai-wm: error: --transform measures ONE file — do not pass <after>", file=sys.stderr)
                return 2
            if args.stdin:
                text = read_text(stdin_text=sys.stdin.read()).text
            elif args.before:
                text = read_text(path=args.before).text
            else:
                print("ai-wm: error: delta-z --transform requires an input file (or --stdin)", file=sys.stderr)
                return 2
            result = delta_z_transform(
                text, key_arg, method=args.transform,
                level=args.level, context=args.context,
                registry=KeyRegistry('data/key_registry.json'),
                seed=args.seed, truncate_fraction=args.truncate_fraction,
                rewrite_mode=args.rewrite_mode, use_llm=args.use_llm,
            )
        else:
            if args.stdin or not (args.before and args.after):
                print("ai-wm: error: delta-z requires <before> and <after> files (or --transform with one file)", file=sys.stderr)
                return 2
            result = delta_z(
                read_text(path=args.before).text,
                read_text(path=args.after).text,
                key_arg, level=args.level, context=args.context,
                registry=KeyRegistry('data/key_registry.json'),
            )
        sign_secret = None
        if args.sign_file:
            sign_secret = Path(args.sign_file).read_text(encoding="utf-8").strip()
        elif args.sign:
            sign_secret = args.sign
        if sign_secret:
            result = delta_z_report(result, sign_secret, key_id=result.get("key_id"))
        rendered = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).write_text(rendered, encoding="utf-8")
        else:
            print(rendered)
        return 0

    if args.cmd == "finding":
        # KI-Erklärungs-Befund (C5): der Befund IST das Ergebnis — Exit 0 bei
        # jeder erfolgreichen Erstellung (auch bei priority 5; priority ist
        # Prüfbedarf, kein Fehler). Exit 2 = Input-/Usage-Fehler.
        from .forensics.finding import build_finding_report
        from .forensics.key_registry import KeyRegistry
        from .forensics.kgw import detect_multi_key, DEFAULT_GAMMA
        from .forensics.e_value import e_detect
        from .forensics.delta_z import delta_z
        if args.stdin:
            text = read_text(stdin_text=sys.stdin.read()).text
        elif args.input:
            text = read_text(path=args.input).text
        else:
            print("ai-wm: error: finding requires an input file (or --stdin)", file=sys.stderr)
            return 2
        key_arg = _resolve_key_arg(args)
        if not key_arg:
            print("ai-wm: error: finding requires --key (key_id or raw secret)", file=sys.stderr)
            return 2
        registry = KeyRegistry('data/key_registry.json')
        key = next((k for k in registry.list_keys() if k.get('key_id') == key_arg), None)
        if key is None:
            # raw secret: masked key_id keeps the secret out of the finding
            # report and its signature block (detection uses the real secret)
            key = {"key_id": mask_secret_key_id(key_arg), "family": "kgw",
                   "secret": key_arg, "gamma": None, "key_source": "raw_secret"}
        if not key.get('secret'):
            print(f"ai-wm: error: key {key_arg} has no secret", file=sys.stderr)
            return 2
        gamma = key.get('gamma') or DEFAULT_GAMMA
        results = {}
        results["detect"] = detect_multi_key(
            text, [key], gamma=gamma,
            level=args.level, context=args.context,
        )
        if args.e_value:
            results["e_value"] = e_detect(
                text, key["secret"], gamma=gamma,
                level=args.level, context=args.context,
            )
        if args.delta_z:
            results["delta_z"] = delta_z(
                text, read_text(path=args.delta_z).text, key_arg,
                level=args.level, context=args.context, registry=registry,
            )
        sign_secret = None
        if args.sign_file:
            sign_secret = Path(args.sign_file).read_text(encoding="utf-8").strip()
        elif args.sign:
            sign_secret = args.sign
        # Evidenzklasse D (Runde-3-Lücke E1): institutionelle Regel und
        # Entstehungshistorie sind über eindeutige Flags übergebbar — sie
        # kollidieren nicht mit --context (KGW-Fenster, int).
        context = None
        if args.institutional_rule or args.origin_history:
            context = {}
            if args.institutional_rule:
                context["institutional_rule"] = args.institutional_rule
            if args.origin_history:
                context["origin_history"] = args.origin_history
        frs_block = None
        if getattr(args, "frs", False):
            from .forensics.frs import compute_frs
            frs_block = compute_frs()
        report = build_finding_report(
            results, key_id=key.get("key_id", key_arg),
            context=context,
            sign_secret=sign_secret,
            frs=frs_block,
            lang=args.lang,
        )
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).write_text(rendered, encoding="utf-8")
        else:
            print(rendered)
        return 0

    if args.cmd == "trace":
        # Z-score trajectory: sliding-window detection over a long document.
        # The trajectory IS the result — exit 0 on any successful measurement
        # (findings are findings, not errors). Exit 2 for usage/input errors.
        from .forensics.trace import trace_kgw, format_trace
        from .forensics.key_registry import KeyRegistry
        from .forensics.kgw import DEFAULT_GAMMA
        if args.stdin:
            text = read_text(stdin_text=sys.stdin.read()).text
        elif args.input:
            text = read_text(path=args.input).text
        else:
            print("ai-wm: error: trace requires an input file (or --stdin)", file=sys.stderr)
            return 2
        key_arg = _resolve_key_arg(args)
        if not key_arg:
            print("ai-wm: error: trace requires --key (key_id or raw secret)", file=sys.stderr)
            return 2
        registry = KeyRegistry('data/key_registry.json')
        key = next((k for k in registry.list_keys() if k.get('key_id') == key_arg), None)
        if key is None:
            key = {"key_id": mask_secret_key_id(key_arg), "family": "kgw",
                   "secret": key_arg, "gamma": None}
        if not key.get('secret'):
            print(f"ai-wm: error: key {key_arg} has no secret", file=sys.stderr)
            return 2
        gamma = key.get('gamma') or DEFAULT_GAMMA
        result = trace_kgw(
            text, key['secret'], gamma=gamma,
            level=args.level, context=args.context,
            window=args.window, step=args.step or None,
            threshold=args.threshold,
        )
        if args.json or args.output:
            rendered = json.dumps(result, ensure_ascii=False, indent=2, default=str)
            if args.output:
                Path(args.output).write_text(rendered, encoding="utf-8")
            else:
                print(rendered)
        else:
            print(format_trace(result, text=text))
        return 0

    if args.cmd == "payload":
        # Multi-bit invariant-feature watermarking: embed/extract a payload.
        from .forensics.invariant import embed_payload, extract_payload
        if args.payload_action == "embed":
            if args.stdin:
                text = read_text(stdin_text=sys.stdin.read()).text
            elif args.input:
                text = read_text(path=args.input).text
            else:
                print("ai-wm: error: payload embed requires an input file (or --stdin)", file=sys.stderr)
                return 2
            opts = {}
            if args.max_masks is not None:
                opts["max_masks"] = args.max_masks
            result = embed_payload(text, args.payload, opts)
            Path(args.output).write_text(result["text"], encoding="utf-8")
            print(f"embedded {result['bits_embedded']} bits"
                  f" (payload '{args.payload}': {len(result['payload_bits'])} bits requested)"
                  f" -> {args.output}")
            if result["bits_embedded"] < len(result["payload_bits"]):
                print(f"warning: text capacity is too small for the full payload"
                      f" — {len(result['payload_bits']) - result['bits_embedded']} bits dropped",
                      file=sys.stderr)
                return 1
            return 0
        elif args.payload_action == "extract":
            if args.stdin:
                text = read_text(stdin_text=sys.stdin.read()).text
            elif args.input:
                text = read_text(path=args.input).text
            else:
                print("ai-wm: error: payload extract requires an input file (or --stdin)", file=sys.stderr)
                return 2
            if args.reference_stdin:
                reference = sys.stdin.read()
            else:
                reference = read_text(path=args.reference).text
            result = extract_payload(text, reference)
            if args.json or args.output:
                rendered = json.dumps(result, ensure_ascii=False, indent=2, default=str)
                if args.output:
                    Path(args.output).write_text(rendered, encoding="utf-8")
                else:
                    print(rendered)
            else:
                payload = result.get("payload", "")
                if result.get("payload_valid"):
                    print(f"payload: {payload!r}")
                else:
                    print(f"payload: {payload!r} (NOT trusted — {result.get('payload_reason')})")
                print(f"confidence: {result.get('confidence')}  masks: {result.get('masks_used')}")
            return 0
        return 2

    if args.cmd == "evade":
        # Adversarial evaluation (white-box, own scheme): stress test, not a
        # laundering tool. Exit 0 on any successful measurement.
        from .forensics.evader import evade, format_evade_report
        from .forensics.key_registry import KeyRegistry
        from .forensics.kgw import DEFAULT_GAMMA
        if args.stdin:
            text = read_text(stdin_text=sys.stdin.read()).text
        elif args.input:
            text = read_text(path=args.input).text
        else:
            print("ai-wm: error: evade requires an input file (or --stdin)", file=sys.stderr)
            return 2
        key_arg = _resolve_key_arg(args)
        if not key_arg:
            print("ai-wm: error: evade requires --key (key_id or raw secret)", file=sys.stderr)
            return 2
        registry = KeyRegistry('data/key_registry.json')
        key = next((k for k in registry.list_keys() if k.get('key_id') == key_arg), None)
        if key is None:
            key = {"key_id": mask_secret_key_id(key_arg), "family": "kgw",
                   "secret": key_arg, "gamma": None}
        if not key.get('secret'):
            print(f"ai-wm: error: key {key_arg} has no secret", file=sys.stderr)
            return 2
        gamma = key.get('gamma') or DEFAULT_GAMMA
        result = evade(
            text, key['secret'], gamma=gamma,
            level=args.level, context=args.context,
            target_z=args.target_z, max_changes=args.max_changes,
            ollama_model=args.ollama_model, seed=args.seed,
        )
        if args.json:
            rendered = json.dumps(
                {k: v for k, v in result.items() if k != "text"},
                ensure_ascii=False, indent=2, default=str,
            )
            if args.output:
                Path(args.output).write_text(rendered, encoding="utf-8")
            else:
                print(rendered)
        else:
            print(format_evade_report(result))
            if args.output:
                Path(args.output).write_text(result["text"], encoding="utf-8")
        return 0

    if args.cmd == "serve":
        from uvicorn import run
        run("ai_watermark_toolkit.api.fastapi_app:app", host=args.host, port=args.port, reload=False)
        return 0

    return 2


def main_entry() -> int:
    """CLI wrapper that catches unexpected errors for clean stderr output.

    Raw Python tracebacks on the CLI are unprofessional and confuse scripts
    that parse stderr.  This wrapper catches known error families and prints
    a clean ``ai-wm: error: ...`` message instead.

    Returns:
        | ``0`` — success / no findings.
        | ``1`` — findings / processing result.
        | ``2`` — usage or input error.
    """
    # Save original stderr so --quiet (which replaces sys.stderr with a
    # StringIO inside main()) cannot silence our error messages. Errors
    # must always reach the real stderr.
    original_stderr = sys.stderr
    try:
        return main()
    except FileNotFoundError as e:
        print(f"ai-wm: error: file not found: {e.filename or e}", file=original_stderr)
        return 2
    except IsADirectoryError as e:
        print(f"ai-wm: error: expected a file, got a directory: {e.filename}", file=original_stderr)
        return 2
    except PermissionError as e:
        print(f"ai-wm: error: permission denied: {e.filename or e}", file=original_stderr)
        return 2
    except ValueError as e:
        print(f"ai-wm: error: {e}", file=original_stderr)
        return 2
    except UnicodeDecodeError as e:
        print(f"ai-wm: error: cannot decode file as UTF-8: {e.object if hasattr(e, 'object') else e}", file=original_stderr)
        return 2
    except OSError as e:
        print(f"ai-wm: error: {e.strerror or e}", file=original_stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main_entry())
