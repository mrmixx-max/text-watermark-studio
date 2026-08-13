"""Menu-driven Textual TUI for Text Watermark Studio.

Dark studio theme matching the repo's hero infographic: neon cyan/green on
near-black. Menu on the left, output on the right, an input line for file
paths, and keyboard bindings for every action. All actions call the toolkit
services directly (no subprocesses).

Run: ai-wm tui   (requires `pip install text-watermark-studio[tui]`)
"""

from __future__ import annotations

import json

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
]

SHORT_HELP: dict[str, str] = {
    "detect": "scan a text file for unicode + AI markers",
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
        Binding("d", "menu_detect", "Detect"),
        Binding("c", "menu_clean", "Clean"),
        Binding("e", "menu_embed", "Embed"),
        Binding("p", "menu_pipeline", "Pipeline"),
        Binding("r", "menu_report", "Report"),
        Binding("s", "menu_splash", "Splash"),
        Binding("enter", "run_selected", "Run", show=False),
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
        self._report(detect_text(text))

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
        from ..forensics.kgw import embed_kgw
        p = self._need_path()
        if not p:
            return
        try:
            text = open(p, encoding="utf-8").read()
        except OSError as e:
            self._out(f"[red]{e}[/]")
            return
        emb = embed_kgw(text, "demo-kgw-1")
        self._out(f"[green]Embedded (demo key).[/] {emb.get('replacements', 0)} replacements.")
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
        try:
            text = open(p, encoding="utf-8").read()
        except OSError as e:
            self._out(f"[red]{e}[/]")
            return
        html_out = build_report(text, "demo-kgw-1")
        out_path = "tws-report-tui.html"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html_out)
        self._out(f"[green]Report written:[/] {out_path}")

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
        src = P(p)
        data = src.read_bytes()
        try:
            emb = embed_provenance(data, src.name, "demo-kgw-1", "demo-kgw-secret-0001")
            out = src.with_name(src.stem + "-signed" + src.suffix)
            out.write_bytes(emb.data)
            self._out(f"[green]Signed file written:[/] {out} "
                        f"(mark {emb.mark_size} bytes, format {emb.format}).")
        except Exception as e:
            self._out(f"[red]{type(e).__name__}: {e}[/]")

    def action_file_detect(self) -> None:
        from pathlib import Path as P
        from ..metadata.provenance import detect_provenance
        p = self._need_path()
        if not p:
            return
        src = P(p)
        data = src.read_bytes()
        det = detect_provenance(data, src.name, secrets={"demo-kgw-1": "demo-kgw-secret-0001"})
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
        import subprocess
        import sys
        from pathlib import Path as P
        script = P(__file__).resolve().parents[2] / "benchmarks" / "attack_matrix.py"
        if not script.exists():
            self._out("[red]benchmarks/attack_matrix.py not found (repo install).[/]")
            return
        r = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=300)
        self._out(r.stdout[-3000:] or r.stderr[-2000:])

    def action_synthid_sweep(self) -> None:
        import subprocess
        import sys
        from pathlib import Path as P
        script = P(__file__).resolve().parents[2] / "benchmarks" / "synthid_sweep.py"
        if not script.exists():
            self._out("[red]benchmarks/synthid_sweep.py not found (repo install).[/]")
            return
        r = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=300)
        self._out(r.stdout[-3000:] or r.stderr[-2000:])

    def action_update(self) -> None:
        """Check the installed version against PyPI; upgrade if newer exists."""
        import subprocess
        import sys
        import urllib.request
        try:
            from importlib.metadata import version as _pkg_version
            installed = _pkg_version("text-watermark-studio")
        except Exception:
            installed = "unknown"
        self._out(f"[cyan]Installed:[/] {installed}")
        try:
            with urllib.request.urlopen(
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
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "text-watermark-studio"],
            capture_output=True, text=True, timeout=600,
        )
        if proc.returncode == 0:
            self._out(f"[green]Upgraded.[/] {proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ''}")
            self._out("[yellow]Restart the TUI to use the new version.[/]")
        else:
            self._out(f"[red]Upgrade failed (exit {proc.returncode}).[/]")
            self._out(proc.stderr[-1500:])

    def action_splash(self) -> None:
        from ..ui.banner import render_banner
        banner = render_banner() if callable(render_banner) else "Text Watermark Studio 2.0.0"
        self._out(str(banner))

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

    def action_menu_detect(self):
        self.query_one("#menu-list", ListView).index = 0

    def action_menu_clean(self):
        self.query_one("#menu-list", ListView).index = 1

    def action_menu_embed(self):
        self.query_one("#menu-list", ListView).index = 3

    def action_menu_pipeline(self):
        self.query_one("#menu-list", ListView).index = 4

    def action_menu_report(self):
        self.query_one("#menu-list", ListView).index = 5

    def action_menu_splash(self):
        self.query_one("#menu-list", ListView).index = 15


def main(argv: list[str] | None = None) -> int:
    StudioTUI().run()
    return 0
