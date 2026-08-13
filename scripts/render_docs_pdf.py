"""Render docs/*.md into print-ready PDFs (Downloads) via markdown + Edge headless."""
import sys
from pathlib import Path

import markdown

CSS = """
@page { size: A4 portrait; margin: 16mm 15mm; }
* { box-sizing: border-box; }
body { font-family: -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
       color: #1a1a2e; font-size: 9.6pt; line-height: 1.5; }
h1 { color: #0b4f6c; font-size: 20pt; border-bottom: 3px solid #0b4f6c; padding-bottom: 6pt; }
h2 { color: #0b4f6c; font-size: 13.5pt; border-bottom: 1.5px solid #9fb3c0;
     padding-bottom: 3pt; margin-top: 18pt; page-break-after: avoid; }
h3 { color: #133; font-size: 11pt; page-break-after: avoid; }
p { margin: 5pt 0; }
code { background: #eef3f7; padding: 1pt 4pt; border-radius: 3px;
       font-family: Consolas, 'Courier New', monospace; font-size: 8.6pt; }
pre { background: #f4f6f8; border: 1px solid #d5dee5; border-radius: 4px;
      padding: 8pt 10pt; page-break-inside: avoid; }
pre code { background: none; padding: 0; font-size: 8.4pt; line-height: 1.4; }
table { border-collapse: collapse; width: 100%; margin: 8pt 0; page-break-inside: avoid; }
th, td { border: 1px solid #c8d2da; padding: 4pt 7pt; text-align: left; font-size: 8.6pt; }
th { background: #eef3f7; color: #0b4f6c; }
ul, ol { margin: 4pt 0 4pt 16pt; padding: 0; }
li { margin: 2.5pt 0; }
strong { color: #0b3a4a; }
hr { border: none; border-top: 1px solid #c8d2da; margin: 14pt 0; }
a { color: #0b6f9c; text-decoration: none; }
"""


def md_to_html(md_path: Path, out_html: Path):
    text = md_path.read_text(encoding="utf-8")
    body = markdown.markdown(text, extensions=["tables", "fenced_code"])
    html_doc = f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8">
<title>{md_path.stem}</title><style>{CSS}</style></head>
<body>{body}</body></html>"""
    out_html.write_text(html_doc, encoding="utf-8")
    return out_html


def main():
    repo = Path(__file__).resolve().parent.parent
    docs = repo / "docs"
    downloads = Path.home() / "Downloads"
    edge = None
    for c in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"):
        if Path(c).exists():
            edge = c
            break
    if edge is None:
        print("Edge nicht gefunden.")
        return 1

    import subprocess

    def render(md_name: str, out_name: str) -> bool:
        """Render one doc; returns True when the PDF was written."""
        md = docs / md_name
        html = downloads / f"{out_name}.html"
        pdf = downloads / f"{out_name}.pdf"
        md_to_html(md, html)
        proc = subprocess.run(
            [edge, "--headless", "--disable-gpu", "--no-sandbox",
             f"--print-to-pdf={pdf.resolve()}",
             "--no-pdf-header-footer",
             f"file:///{html.resolve().as_posix()}"],
            capture_output=True, text=True, timeout=180,
        )
        stderr = (proc.stderr or "") + (proc.stdout or "")
        # Edge exits 0 even when the write failed (e.g. Windows file lock) —
        # the stderr message is the only signal.
        if proc.returncode != 0 or "Failed to write file" in stderr:
            print(f"{md_name} -> FEHLER: {pdf.name} ist von einem anderen "
                  f"Prozess belegt (Viewer offen?).")
            html.unlink(missing_ok=True)
            return False
        print(f"{md_name} -> {pdf.name} ({pdf.stat().st_size} bytes)")
        html.unlink(missing_ok=True)
        return True

    pairs = [("USER-GUIDE.md", "tws-user-guide-en"),
             ("BENUTZERHANDBUCH.md", "tws-benutzerhandbuch-de")]
    for md_name, out_name in pairs:
        ok = render(md_name, out_name)
        if not ok:
            print(f"  -> Fallback: {out_name}-neu.pdf")
            render(md_name, f"{out_name}-neu")
    return 0


if __name__ == "__main__":
    sys.exit(main())
