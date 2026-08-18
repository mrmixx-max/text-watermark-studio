"""Menu-driven Textual TUI for Text Watermark Studio.

Dark studio theme matching the repo's hero infographic: neon cyan/green on
near-black. Menu on the left, output on the right, an input line for file
paths, and keyboard bindings for every action. All actions call the toolkit
services directly (no subprocesses).

Run: ai-wm tui   (requires `pip install text-watermark-studio[tui]`)
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Input, Label, ListItem, ListView, RichLog, Static

from .. import __version__  # noqa: F401  (available for banner use)

# Menu structure: (label, action_id)
MENU: list[tuple[str, str]] = [
    ("1  Detect invisible + markers", "detect"),
    ("2  Clean unicode layer", "clean"),
    ("3  Dilute AI phrasing", "dilute"),
    ("4  Embed greenlist mark", "embed"),
    ("5  Pipeline (detect→clean→dilute→rewrite)", "pipeline"),
    ("6  Findings report (KGW)", "report"),
    ("7  Rewrite (structural/backtranslate)", "rewrite"),
    ("8  File inspect metadata", "file-inspect"),
    ("9  File clean metadata", "file-clean"),
    ("10 File embed provenance", "file-embed"),
    ("11 File detect provenance", "file-detect"),
    ("12 Image score (SynthID)", "image-score"),
    ("13 Watch directory (--once)", "watch-once"),
    ("14 Attack matrix (benchmark)", "attack-matrix"),
    ("15 SynthID sweep (benchmark)", "synthid-sweep"),
    ("16 System state", "splash"),
    ("17 Update studio (check + upgrade)", "update"),
    ("18 Install local model (Ollama pull)", "llm-install"),
    ("19 Prompt optimizer (locked evals)", "optimizer"),
    ("20 Corpus similarity (local MinHash)", "similarity"),
    ("21 ΔZ check (before --after after)", "delta-z"),
    ("22 Findings report (Evidenzklassen A-D)", "finding"),
    ("23 Sign findings JSON (report-sign)", "report-sign"),
    ("24 Verify signed findings JSON", "report-verify"),
    ("25 Generate ML-DSA keypair (report-keygen)", "report-keygen"),
]

SHORT_HELP: dict[str, str] = {
    "detect": "scan a text file for unicode + AI markers (--e-value/--signature-filter opt-in)",
    "clean": "strip the invisible-character layer",
    "dilute": "rewrite marker-heavy phrasing",
    "embed": "impose a greenlist mark (keyed)",
    "pipeline": "full chain detect→clean→dilute→rewrite→detect",
    "report": "HTML/PDF forensics report for a KGW key",
    "rewrite": "structural or backtranslate rewrite",
    "file-inspect": "inspect C2PA/EXIF/XMP metadata",
    "file-clean": "strip metadata from a file",
    "file-embed": "HMAC-sign a file",
    "file-detect": "verify a file signature",
    "image-score": "SynthID pixel scoring (needs checkpoint)",
    "watch-once": "one scan pass over a directory",
    "attack-matrix": "run the attack matrix benchmark",
    "synthid-sweep": "run the gamma×paraphrase sweep",
    "splash": "studio banner + system state",
    "update": "check PyPI for a newer release, then upgrade",
    "llm-install": "pull a local model via the Ollama API (name in Path field)",
    "optimizer": "run the prompt-optimizer evaluator loop against the locked evals",
    "similarity": "compare a text against your own corpus (Path: file --corpus dir)",
    "delta-z": "ΔZ check: Path: before.txt --after after.txt (--key <id> optional)",
    "finding": "KI-Erklärungs-Befund A-D: Path: file.txt (--e-value, --delta-z <after>, --key <id>)",
    "report-sign": "sign a findings JSON: Path: finding.json (--key <id>) — Secret bleibt in der Registry",
    "report-verify": "verify a signed findings JSON: Path: signed.json (--key <id>)",
    "report-keygen": "generate an ML-DSA keypair: Path: target base path (--algorithm mldsa-44|65|87)",
}


class StudioTUI(App):
    """Menu-driven studio interface."""

    TITLE = "Text Watermark Studio"
    SUB_TITLE = "detect · remove · prove · protect"

    CSS = """
    Screen { background: #0a0e14; }
    #menu { width: 42; border: solid #1c2834; background: #0d1219; }
    #menu ListView { background: #0d1219; }
    #menu ListItem { color: #9fb3c0; padding: 0 1; }
    #menu ListItem.--highlight { background: #12222e; color: #2ad4c8; }
    #right { padding: 0 1; }
    #out { border: solid #1c2834; background: #10161f; height: 1fr; }
    #out Label { padding: 1 1; }
    #help { height: 3; color: #55616e; padding: 0 1; }
    #pathline Label { color: #2ad4c8; width: 8; }
    #path Input { background: #121a24; color: #eef6fa; border: solid #2a3a4a; }
    Header { background: #0d1219; color: #2ad4c8; }
    Footer { background: #0d1219; }
    RichLog { background: #10161f; color: #d7e3ea; border: none; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("up", "menu_up", "Menu up", show=True, priority=True),
        Binding("down", "menu_down", "Menu down", show=True, priority=True),
        Binding("enter", "run_selected", "Run", show=False, priority=True),
        Binding("d", "menu_detect", "Detect"),
        Binding("c", "menu_clean", "Clean"),
        Binding("e", "menu_embed", "Embed"),
        Binding("p", "menu_pipeline", "Pipeline"),
        Binding("r", "menu_report", "Report"),
        Binding("s", "menu_splash", "Splash"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            with Vertical(id="menu"):
                yield ListView(*[ListItem(Label(label)) for label, _ in MENU],
                               id="menu-list")
                yield Static("\n↑↓ select · Enter run\nq quit · letters = shortcuts",
                             id="help")
            with Vertical(id="right"):
                yield RichLog(id="out", highlight=True, markup=True)
                with Horizontal(id="pathline"):
                    yield Label("Path:")
                    yield Input(placeholder="file or directory path, then Enter",
                                id="path")
        yield Footer()

    def on_mount(self) -> None:
        # header title carries the author credit — guaranteed visible
        self.title = "Text Watermark Studio 2.0.0 — by Erik Gieske"
        self.query_one("#out", RichLog).write(
            "[cyan]Text Watermark Studio 2.0.0[/] — menu-driven local forensics")
        self.query_one("#out", RichLog).write(
            "↑/↓ navigate · Enter runs the selected action · q quits")

    # ---- helpers ----------------------------------------------------------

    def _out(self, text: str) -> None:
        self.query_one("#out", RichLog).write(text)

    def _read_path(self) -> str:
        return self.query_one("#path", Input).value.strip()

    def _report(self, data: dict) -> None:
        self._out(json.dumps(data, ensure_ascii=False, indent=2, default=str))

    def _need_path(self) -> str | None:
        p = self._read_path()
        if not p:
            self._out("[yellow]No path given — type one into the Path field.[/]")
            return None
        return p

    def _kgw_key(self) -> dict | None:
        """Resolve the first registered KGW key with a secret.

        No silent demo-key fallback: if the registry has no usable KGW key
        the action must fail loudly instead of embedding under a hardcoded
        secret the user never chose.
        """
        keys = self._kgw_keys()
        return keys[0] if keys else None

    def _kgw_keys(self) -> list[dict]:
        """All registered KGW keys that carry a secret (keyed-detect path)."""
        from ..forensics.key_registry import KeyRegistry
        registry = KeyRegistry('data/key_registry.json')
        return [k for k in registry.list_keys()
                if k.get('family') == 'kgw' and k.get('secret')]

    def _provenance_secrets(self) -> dict[str, str]:
        """key_id -> secret for every registered key with a secret.

        Used by file-detect so a mark signed under ANY registered key
        verifies — the previous hardcoded demo secret reported real user
        keys as hmac_invalid (F5).
        """
        from ..forensics.key_registry import KeyRegistry
        registry = KeyRegistry('data/key_registry.json')
        return {k.get('key_id'): k.get('secret')
                for k in registry.list_keys() if k.get('secret')}

    @staticmethod
    def _parse_level_context(raw: str) -> tuple[str, int]:
        """Parse optional `--level word|bpe` and `--context <n>` from the
        Path field (defaults: word / 1 — identical to CLI and API defaults).

        The remaining text is the plain path; unknown tokens are ignored so
        existing Path-field formats keep working.
        """
        import re as _re
        level = "word"
        context = 1
        m = _re.search(r"--level\s+(\w+)", raw)
        if m and m.group(1) in ("word", "bpe"):
            level = m.group(1)
        m = _re.search(r"--context\s+(\d+)", raw)
        if m:
            context = max(1, int(m.group(1)))
        return level, context

    @staticmethod
    def _parse_tui_flags(raw: str) -> dict:
        """Parse the Runde-3 opt-in flag tokens from the Path field.

        Supported: ``--key <id>``, ``--e-value``, ``--signature-filter``,
        ``--after <file>``, ``--delta-z <file>``, ``--algorithm <name>``.
        ``path`` ist der verbleibende Token (der erste, der keine Flag ist).
        Defaults sind CLI-parität (alles opt-in, ``--key`` None = erster
        registrierter KGW-Key).
        """
        import re as _re
        # Path = everything up to the first flag token (trimmed), so paths
        # containing spaces survive; quoted flag values are handled below.
        m_path = _re.match(r"^(.*?)(?=\s+--|$)", raw, _re.S)
        path = m_path.group(1).strip() if m_path else raw.strip()
        flags = {
            "path": path or raw.strip(),
            "key": None,
            "e_value": False,
            "signature_filter": False,
            "after": None,
            "delta_z": None,
            "algorithm": "mldsa-44",
        }

        def _val(name: str) -> str | None:
            # --name "quoted value" | --name 'quoted value' | --name value
            m = _re.search(
                rf"--{name}\s+(?:\"([^\"]+)\"|'([^']+)'|(\S+))", raw)
            if not m:
                return None
            return m.group(1) or m.group(2) or m.group(3)

        flags["key"] = _val("key")
        flags["after"] = _val("after")
        flags["delta_z"] = _val("delta-z")
        flags["algorithm"] = _val("algorithm") or "mldsa-44"
        flags["e_value"] = "--e-value" in raw.split()
        flags["signature_filter"] = "--signature-filter" in raw.split()
        return flags

    # ---- actions ----------------------------------------------------------

    def action_detect(self) -> None:
        from ..pipeline import detect_text
        p = self._need_path()
        if not p:
            return
        try:
            text = open(p, encoding="utf-8").read()
        except OSError as e:
            self._out(f"[red]{e}[/]")
            return
        # Keyed verification first: if KGW keys with secrets are registered,
        # run the real multi-key detection (redlist sign + Bonferroni).
        keys = self._kgw_keys()
        if keys:
            from ..forensics.kgw import detect_multi_key, DEFAULT_GAMMA
            flags = self._parse_tui_flags(p)
            if flags["key"]:
                keys = [k for k in keys if k["key_id"] == flags["key"]] or keys
            level, context = self._parse_level_context(p)
            # Runde-3 opt-in-Umschalter (CLI-Parität, Default aus):
            # --signature-filter (FPR-Kontrolle) und --e-value (E-Wert-Befund).
            r = detect_multi_key(text, keys, level=level, context=context,
                                 signature_filter=flags["signature_filter"])
            best = r.get("best", {})
            self._out(f"[green]Keyed detect ({r.get('tested_keys', 0)} keys).[/] "
                      f"best={best.get('key_id')} z={best.get('z_score')} "
                      f"verdict={best.get('verdict')}")
            if flags["signature_filter"]:
                sf = best.get("signature_filtered")
                if sf:
                    self._out(f"[cyan]Signature filter:[/] "
                              f"{sf.get('removed_types')} removed "
                              f"({sf.get('before_n')} -> {sf.get('after_n')} tokens)")
            if flags["e_value"]:
                from ..forensics.e_value import e_detect
                best_id = best.get("key_id")
                secret = next((k["secret"] for k in keys
                               if k.get("key_id") == best_id), keys[0]["secret"])
                gamma = next((k.get("gamma") for k in keys
                              if k.get("key_id") == best_id), None) or DEFAULT_GAMMA
                ev = e_detect(text, secret, gamma=gamma,
                              level=level, context=context)
                self._out(f"[cyan]E-Wert:[/] e={ev.get('e_value'):.3g} "
                          f"detected={ev.get('detected')}")
            self._report(detect_text(text))
            return
        self._report(detect_text(text))

    def action_delta_z(self) -> None:
        """ΔZ check (E2): Path = before.txt --after after.txt --key <id>."""
        from ..forensics.delta_z import delta_z
        from ..forensics.key_registry import KeyRegistry
        p = self._need_path()
        if not p:
            return
        flags = self._parse_tui_flags(p)
        if not flags["after"]:
            self._out("[yellow]ΔZ needs two files: Path: before.txt --after after.txt[/]")
            return
        try:
            text_before = open(flags["path"], encoding="utf-8").read()
            text_after = open(flags["after"], encoding="utf-8").read()
        except OSError as e:
            self._out(f"[red]{e}[/]")
            return
        keys = self._kgw_keys()
        if not keys:
            self._out("[red]No KGW key with secret registered — add one via CLI `ai-wm key add`.[/]")
            return
        key = flags["key"]
        if key and key not in [k["key_id"] for k in keys]:
            self._out(f"[red]Key {key} not found in registry.[/]")
            return
        key_arg = key or keys[0]["key_id"]
        level, context = self._parse_level_context(flags["path"])
        result = delta_z(text_before, text_after, key_arg,
                         level=level, context=context,
                         registry=KeyRegistry('data/key_registry.json'))
        self._report(result)

    def action_finding(self) -> None:
        """KI-Erklärungs-Befund A-D (E2): Path: file.txt --key <id>
        --e-value --delta-z <after> --institutional-rule <t> --origin-history <t>."""
        from ..forensics.finding import build_finding_report
        from ..forensics.kgw import detect_multi_key, DEFAULT_GAMMA
        from ..forensics.key_registry import KeyRegistry
        from ..forensics.e_value import e_detect
        from ..forensics.delta_z import delta_z
        import re as _re
        p = self._need_path()
        if not p:
            return
        flags = self._parse_tui_flags(p)
        try:
            text = open(flags["path"], encoding="utf-8").read()
        except OSError as e:
            self._out(f"[red]{e}[/]")
            return
        keys = self._kgw_keys()
        if not keys:
            self._out("[red]No KGW key with secret registered — add one via CLI `ai-wm key add`.[/]")
            return
        key_id = flags["key"] or keys[0]["key_id"]
        key = next((k for k in keys if k["key_id"] == key_id), None)
        if key is None:
            self._out(f"[red]Key {key_id} not found in registry.[/]")
            return
        gamma = key.get("gamma") or DEFAULT_GAMMA
        level, context = self._parse_level_context(flags["path"])
        results = {"detect": detect_multi_key(
            text, [key], gamma=gamma, level=level, context=context)}
        if flags["e_value"]:
            results["e_value"] = e_detect(
                text, key["secret"], gamma=gamma, level=level, context=context)
        if flags["delta_z"]:
            try:
                after_text = open(flags["delta_z"], encoding="utf-8").read()
            except OSError as e:
                self._out(f"[red]{e}[/]")
                return
            results["delta_z"] = delta_z(
                text, after_text, key_id, level=level, context=context,
                registry=KeyRegistry('data/key_registry.json'))
        ctx = None
        m = _re.search(r"--institutional-rule\s+(.+?)(?:\s+--|\s*$)", p)
        m2 = _re.search(r"--origin-history\s+(.+?)(?:\s+--|\s*$)", p)
        if m or m2:
            ctx = {}
            if m:
                ctx["institutional_rule"] = m.group(1).strip()
            if m2:
                ctx["origin_history"] = m2.group(1).strip()
        report = build_finding_report(results, key_id=key_id, context=ctx)
        self._report(report)

    def action_report_sign(self) -> None:
        """Sign a findings JSON (E2): Path: finding.json --key <id>.
        Secret comes from the registry — never shown."""
        from ..forensics.signed_report import sign_report
        p = self._need_path()
        if not p:
            return
        flags = self._parse_tui_flags(p)
        try:
            payload = json.loads(open(flags["path"], encoding="utf-8").read())
        except (OSError, json.JSONDecodeError) as e:
            self._out(f"[red]{e}[/]")
            return
        if not isinstance(payload, dict):
            self._out("[red]Payload must be a JSON object.[/]")
            return
        secrets = self._provenance_secrets()
        key_id = flags["key"] or next(iter(secrets), None)
        if not key_id or key_id not in secrets:
            self._out("[red]No registry secret for --key — sign via CLI with --secret-file.[/]")
            return
        signed = sign_report(payload, secrets[key_id], key_id=key_id,
                             algorithm="hmac-sha256")
        out = Path(flags["path"]).with_suffix(".signed.json")
        out.write_text(json.dumps(signed, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        self._out(f"[green]Signed[/] {out} (HMAC-SHA256, key_id={key_id}) — "
                  f"Secret bleibt in der Registry, nie im Report.")

    def action_report_verify(self) -> None:
        """Verify a signed findings JSON (E2): Path: signed.json --key <id>."""
        from ..forensics.signed_report import verify_report
        p = self._need_path()
        if not p:
            return
        flags = self._parse_tui_flags(p)
        try:
            signed = json.loads(open(flags["path"], encoding="utf-8").read())
        except (OSError, json.JSONDecodeError) as e:
            self._out(f"[red]{e}[/]")
            return
        algorithm = (signed.get("signature") or {}).get("algorithm") if isinstance(signed, dict) else None
        secret = None
        if algorithm == "hmac-sha256":
            secrets = self._provenance_secrets()
            key_id = flags["key"] or next(iter(secrets), None)
            if key_id and key_id in secrets:
                secret = secrets[key_id]
            elif key_id:
                self._out(f"[red]No registry secret for --key {key_id}.[/]")
                return
        result = verify_report(signed, secret or "", public_key_pem=None)
        self._report(result)

    def action_report_keygen(self) -> None:
        """Generate an ML-DSA keypair (E2): Path: target dir
        (e.g. keys) --algorithm mldsa-44|65|87."""
        from ..forensics.signed_report import generate_mldsa_keypair, mldsa_status
        p = self._need_path()
        if not p:
            return
        flags = self._parse_tui_flags(p)
        status = mldsa_status()
        if not status["available"]:
            self._out(f"[red]{status['hint']}[/]")
            return
        try:
            pair = generate_mldsa_keypair(flags["algorithm"])
        except ValueError as e:
            self._out(f"[red]{e}[/]")
            return
        out_dir = Path(flags["path"])
        out_dir.mkdir(parents=True, exist_ok=True)
        prefix = "mldsa"
        priv = out_dir / f"{prefix}_private.pem"
        pub = out_dir / f"{prefix}_public.pem"
        priv.write_text(pair["private_key_pem"], encoding="utf-8")
        pub.write_text(pair["public_key_pem"], encoding="utf-8")
        self._out(f"[green]ML-DSA keypair ({pair['algorithm']})[/] -> {priv} / {pub}")

    def action_clean(self) -> None:
        from ..transform.clean import clean_text
        p = self._need_path()
        if not p:
            return
        try:
            text = open(p, encoding="utf-8").read()
        except OSError as e:
            self._out(f"[red]{e}[/]")
            return
        cleaned = clean_text(text)
        self._out(f"[green]Cleaned.[/] {cleaned.unicode_removed} unicode removed, "
                    f"{cleaned.confusable_folds} confusable folds.")
        self._out(cleaned.text[:2000])

    def action_dilute(self) -> None:
        from ..transform.dilute import dilute_text
        p = self._need_path()
        if not p:
            return
        try:
            text = open(p, encoding="utf-8").read()
        except OSError as e:
            self._out(f"[red]{e}[/]")
            return
        out = dilute_text(text, intensity="standard")
        self._out(f"[green]Diluted.[/] {out.changed} phrases rewritten "
                  f"({out.intensity}, {out.frozen_blocks} frozen).")
        self._out(out.text[:2000])

    def action_embed(self) -> None:
        from ..forensics.kgw import mark_greenlist, DEFAULT_GAMMA
        p = self._need_path()
        if not p:
            return
        key = self._kgw_key()
        if key is None:
            self._out("[red]No KGW key with a secret registered — add one via the "
                      "API/CLI first, then retry.[/]")
            return
        try:
            text = open(p, encoding="utf-8").read()
        except OSError as e:
            self._out(f"[red]{e}[/]")
            return
        level, context = self._parse_level_context(p)
        emb = mark_greenlist(text, key['secret'],
                             gamma=key.get('gamma') or DEFAULT_GAMMA,
                             level=level, context=context)
        self._out(f"[green]Embedded (key {key['key_id']}, level={level}, "
                  f"context={context}).[/] "
                  f"{emb.get('replacements', 0)} replacements, "
                  f"green_rate {emb.get('green_rate_after')}.")
        self._out(emb["text"][:2000])

    def action_pipeline(self) -> None:
        from ..pipeline import run_pipeline
        p = self._need_path()
        if not p:
            return
        try:
            text = open(p, encoding="utf-8").read()
        except OSError as e:
            self._out(f"[red]{e}[/]")
            return
        out, report = run_pipeline(text, rewrite_mode="structural")
        self._out("[green]Pipeline done.[/]")
        self._out(json.dumps(report, ensure_ascii=False, indent=2, default=str))

    def action_report(self) -> None:
        from ..forensics.report import build_report
        p = self._need_path()
        if not p:
            return
        key = self._kgw_key()
        if key is None:
            self._out("[red]No KGW key with a secret registered — add one via the "
                      "API/CLI first, then retry.[/]")
            return
        try:
            text = open(p, encoding="utf-8").read()
        except OSError as e:
            self._out(f"[red]{e}[/]")
            return
        level, context = self._parse_level_context(p)
        html_out = build_report(text, key['secret'],
                                key_label=key['key_id'],
                                level=level, context=context)
        out_path = "tws-report-tui.html"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html_out)
        self._out(f"[green]Report written:[/] {out_path} (key {key['key_id']})")

    def action_rewrite(self) -> None:
        from ..rewrite.service import RewriteService
        p = self._need_path()
        if not p:
            return
        try:
            text = open(p, encoding="utf-8").read()
        except OSError as e:
            self._out(f"[red]{e}[/]")
            return
        svc = RewriteService()
        result = svc.rewrite(text, mode="structural")
        self._out("[green]Rewritten (structural).[/]")
        self._out(result.get("rewritten", "")[:2000])

    def action_file_inspect(self) -> None:
        from pathlib import Path as P
        from ..metadata.service import inspect
        p = self._need_path()
        if not p:
            return
        data = P(p).read_bytes()
        try:
            report = inspect(data, P(p).name)
            self._report(report)
        except ValueError:
            self._out("[yellow]Format not supported by the metadata layer.[/]")

    def action_file_clean(self) -> None:
        from pathlib import Path as P
        from ..metadata.service import clean
        p = self._need_path()
        if not p:
            return
        src = P(p)
        data = src.read_bytes()
        try:
            cleaned, report = clean(data, src.name)
            out = src.with_name(src.stem + "-clean" + src.suffix)
            out.write_bytes(cleaned)
            self._out(f"[green]Cleaned file written:[/] {out}")
            self._out(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        except ValueError:
            self._out("[yellow]Format not supported by the metadata layer.[/]")

    def action_file_embed(self) -> None:
        from pathlib import Path as P
        from ..metadata.provenance import embed_provenance
        p = self._need_path()
        if not p:
            return
        key = self._kgw_key()
        if key is None:
            self._out("[red]No KGW key with a secret registered — add one via the "
                      "API/CLI first, then retry.[/]")
            return
        src = P(p)
        data = src.read_bytes()
        try:
            emb = embed_provenance(data, src.name, key["key_id"], key["secret"])
            out = src.with_name(src.stem + "-signed" + src.suffix)
            out.write_bytes(emb.data)
            self._out(f"[green]Signed file written:[/] {out} "
                        f"(mark {emb.mark_size} bytes, format {emb.format}, "
                        f"key {key['key_id']}).")
        except Exception as e:
            self._out(f"[red]{type(e).__name__}: {e}[/]")

    def action_file_detect(self) -> None:
        from pathlib import Path as P
        from ..metadata.provenance import detect_provenance
        p = self._need_path()
        if not p:
            return
        secrets = self._provenance_secrets()
        if not secrets:
            self._out("[red]No provenance keys with secrets registered — a "
                      "signed file can't be verified without them.[/]")
            return
        src = P(p)
        data = src.read_bytes()
        det = detect_provenance(data, src.name, secrets=secrets)
        self._report({"found": getattr(det, "found", None),
                      "valid": getattr(det, "valid", None),
                      "key_id": getattr(det, "key_id", None)})

    def action_image_score(self) -> None:
        from ..metadata.synthid import score_synthid
        p = self._need_path()
        if not p:
            return
        r = score_synthid(p)
        self._report(r)

    def action_watch_once(self) -> None:
        from ..forensics.watcher import watch_dir
        p = self._need_path()
        if not p:
            return
        lines: list[str] = []
        try:
            n = watch_dir(p, once=True, out=lines.append)
            for l in lines:
                self._out(l)
            self._out(f"[green]{n} file(s) reported.[/]")
        except NotADirectoryError:
            self._out("[red]Not a directory.[/]")

    def action_attack_matrix(self) -> None:
        import subprocess  # nosec B404 — list args, no shell=True
        import sys
        from pathlib import Path as P
        script = P(__file__).resolve().parents[2] / "benchmarks" / "attack_matrix.py"
        if not script.exists():
            self._out("[red]benchmarks/attack_matrix.py not found (repo install).[/]")
            return
        try:
            r = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired:
            self._out("[red]Attack matrix timed out after 300s.[/]")
            return
        self._out(r.stdout[-3000:] or r.stderr[-2000:])

    def action_synthid_sweep(self) -> None:
        import subprocess  # nosec B404 — list args, no shell=True
        import sys
        from pathlib import Path as P
        script = P(__file__).resolve().parents[2] / "benchmarks" / "synthid_sweep.py"
        if not script.exists():
            self._out("[red]benchmarks/synthid_sweep.py not found (repo install).[/]")
            return
        try:
            r = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired:
            self._out("[red]SynthID sweep timed out after 300s.[/]")
            return
        self._out(r.stdout[-3000:] or r.stderr[-2000:])

    def action_update(self) -> None:
        """Check the installed version against PyPI; upgrade if newer exists."""
        import subprocess  # nosec B404 — list args, no shell=True
        import sys
        import urllib.request
        try:
            from importlib.metadata import version as _pkg_version
            installed = _pkg_version("text-watermark-studio")
        except Exception:
            installed = "unknown"
        self._out(f"[cyan]Installed:[/] {installed}")
        try:
            with urllib.request.urlopen(  # nosec B310  # hardcoded HTTPS URL to PyPI
                "https://pypi.org/pypi/text-watermark-studio/json", timeout=15
            ) as r:
                import json as _json
                latest = _json.loads(r.read().decode())["info"]["version"]
        except Exception as e:
            self._out(f"[red]Could not reach PyPI: {e}[/]")
            return
        self._out(f"[cyan]Latest on PyPI:[/] {latest}")
        if installed == latest:
            self._out("[green]Up to date.[/]")
            return
        self._out(f"[yellow]Upgrade available ({installed} -> {latest}).[/]")
        self._out("Running pip install --upgrade text-watermark-studio ...")
        proc = subprocess.run(  # nosec B603 — list args, no shell=True, hardcoded package name
            [sys.executable, "-m", "pip", "install", "--upgrade", "text-watermark-studio"],
            capture_output=True, text=True, timeout=600,
        )
        if proc.returncode == 0:
            self._out(f"[green]Upgraded.[/] {proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ''}")
            self._out("[yellow]Restart the TUI to use the new version.[/]")
        else:
            self._out(f"[red]Upgrade failed (exit {proc.returncode}).[/]")
            self._out(proc.stderr[-1500:])

    def action_llm_install(self) -> None:
        """Pull a model via the Ollama API; model name comes from the Path
        field (e.g. `hf.co/bartowski/EuroLLM-9B-Instruct-GGUF:Q4_K_M`)."""
        from ..llm.service import LocalLLMService
        model = self._read_path()
        if not model:
            self._out("[yellow]No model name — type one into the Path field "
                      "(e.g. llama3.2:3b).[/]")
            return
        svc = LocalLLMService()

        def progress(line: str) -> None:
            self._out(f"[cyan]{line}[/]")

        self._out(f"Pulling {model} via Ollama API ...")
        try:
            result = svc.install_model(model, progress=progress)
        except RuntimeError as e:
            self._out(f"[red]{e}[/]")
            return
        self._out(f"[green]Installed and selected:[/] {result['model']}")

    def action_optimizer(self) -> None:
        """Run the prompt-optimizer evaluator loop against the locked eval
        set and show baseline, ranking and winner (read-only; promotion
        happens through the API/CLI to keep the registry safe)."""
        from ..optimization.service import PromptOptimizationService
        base = ("Rewrite the given text so it no longer reads like AI output. "
                "Keep all facts, numbers and names exactly as they are.")
        self._out("[cyan]Prompt-Optimizer-Loop (locked evals, read-only):[/]")
        try:
            r = PromptOptimizationService().optimize(base)
        except Exception as e:
            self._out(f"[red]{e}[/]")
            return
        self._out(f"Backend: {r['backend']} · Evals: {r['eval_count']} · "
                  f"Baseline: {r['baseline_score']} ({r['baseline_hash'][:8]})")
        for row in r["ranking"]:
            g = "OK" if row["guardrail_passed"] else "VERLETZT"
            self._out(f"  {row['variant']:<20} {row['avg_score']:<6} "
                      f"guardrail={g}")
        w = r["winner"]
        self._out(f"[green]Gewinner:[/] {w['candidate']['variant']} "
                  f"({w['avg_score']}) — {w['candidate']['changed_variable']}")

    def action_similarity(self) -> None:
        """Compare a text against a user-owned corpus. Path field format:
        `document.txt --corpus ./archiv` (threshold optional via --threshold)."""
        from ..forensics.similarity import check_similarity
        from pathlib import Path as _P
        raw = self._read_path()
        parts = [p.strip() for p in raw.split("--corpus")] if "--corpus" in raw else [raw]
        target = parts[0]
        corpus = parts[1] if len(parts) > 1 else ""
        if not target or not corpus:
            self._out("[yellow]Format: <datei.txt> --corpus <ordner> "
                      "(Threshold optional: --threshold 0.4)[/]")
            return
        if not os.path.exists(target) or not os.path.isdir(corpus):
            self._out("[yellow]Datei oder Corpus-Ordner nicht gefunden.[/]")
            return
        try:
            text = _P(target).read_text(encoding="utf-8", errors="replace")
            r = check_similarity(text, [corpus])
        except Exception as e:
            self._out(f"[red]{e}[/]")
            return
        self._out(f"[cyan]Similarity gegen {os.path.basename(corpus)}:[/]")
        if r["findings"]:
            top = r["findings"][0]
            self._out(f"Top: {top['similarity']:.2f} ({os.path.basename(top['path'])})")
            for f in r["findings"][:5]:
                zit = f["fundstellen"][0] if f["fundstellen"] else ""
                self._out(f"  {f['similarity']:.2f}  {os.path.basename(f['path'])}"
                          f"  ~ {zit[:60]}")
        else:
            self._out(f"Keine Treffer über Schwelle "
                      f"({r['input']['threshold']}). Top: {r['top_similarity']:.2f}")

    def action_splash(self) -> None:
        from ..ui.banner import render_banner
        banner = render_banner() if callable(render_banner) else "Text Watermark Studio 2.0.0"
        self._out(banner)
        self._out("[dim]MIT · 100% local, zero telemetry[/]")

    # ---- menu navigation ---------------------------------------------------

    def _selected_action(self) -> str:
        lv = self.query_one("#menu-list", ListView)
        if lv.index is None:
            return ""
        return MENU[lv.index][1]

    def action_run_selected(self) -> None:
        action = self._selected_action()
        if action == "watch-once":
            self.action_watch_once()
        elif action:
            getattr(self, "action_" + action.replace("-", "_"), lambda: None)()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        idx = MENU[event.list_view.index][1] if event.list_view.index is not None else ""
        help_text = SHORT_HELP.get(idx, "")
        if idx:
            self._out(f"[cyan]{idx}[/] — {help_text}")
            getattr(self, "action_" + idx.replace("-", "_"), lambda: None)()

    # ---- keyboard shortcuts ------------------------------------------------

    def _menu_list(self) -> ListView:
        return self.query_one("#menu-list", ListView)

    def action_menu_up(self) -> None:
        """Cursor up: move the menu selection up (works from any focus)."""
        lv = self._menu_list()
        idx = lv.index if lv.index is not None else 0
        lv.index = max(0, idx - 1)

    def action_menu_down(self) -> None:
        """Cursor down: move the menu selection down (works from any focus)."""
        lv = self._menu_list()
        idx = lv.index if lv.index is not None else 0
        lv.index = min(len(MENU) - 1, idx + 1)

    def action_menu_detect(self):
        self._menu_list().index = 0

    def action_menu_clean(self):
        self._menu_list().index = 1

    def action_menu_embed(self):
        self._menu_list().index = 3

    def action_menu_pipeline(self):
        self._menu_list().index = 4

    def action_menu_report(self):
        self._menu_list().index = 5

    def action_menu_splash(self):
        self._menu_list().index = 15


def main(argv: list[str] | None = None) -> int:
    StudioTUI().run()
    return 0
