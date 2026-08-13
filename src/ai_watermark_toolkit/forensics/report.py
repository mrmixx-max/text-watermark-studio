"""Forensic findings report: turn a detect run into a self-contained HTML
(optionally PDF) report — what was found, which key, Z-score, recommendation.

Pure stdlib: the HTML is generated from the detect results and styled inline.
PDF rendering is delegated to an external renderer (Edge headless on
Windows) when --pdf is requested and the binary exists; otherwise the HTML
is the deliverable.
"""

from __future__ import annotations

import html
import json
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .kgw import detect_kgw


def build_report(text: str, key: str, *, lang: str = "en",
                 unicode_findings: list | None = None,
                 marker_hits: int = 0,
                 include_text: bool = True,
                 key_label: str | None = None,
                 level: str = "word", context: int = 1) -> str:
    """Build a self-contained HTML findings report for one detect run.

    ``key`` is the secret used for KGW detection (never shown in the report).
    ``key_label`` is the display name (e.g. the registry key_id); when omitted
    it falls back to ``key`` for backward compatibility with direct callers.
    """
    label = key_label if key_label is not None else key
    r = detect_kgw(text, key, level=level, context=context)
    verdict = r["verdict"]
    z = r["z_score"]
    green_rate = r["green_rate"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    uni = len(unicode_findings or [])

    badge = {
        "watermark_detected": ("WASSERZEICHEN NACHGEWIESEN", "#b02a2a"),
        "redlist_detected": ("REDLIST-SIGNAL NACHGEWIESEN", "#b02a2a"),
        "weak_signal": ("SCHWACHES SIGNAL", "#d9a404"),
        "weak_redlist_signal": ("SCHWACHES REDLIST-SIGNAL", "#d9a404"),
        "no_signal": ("KEIN SIGNAL", "#0b7a3b"),
        "too_short": ("TEXT ZU KURZ", "#777777"),
    }.get(verdict, ("UNBEKANNT", "#777777"))

    z_cell = "—" if z is None else f"{z:.2f}"
    rate_cell = "—" if green_rate is None else f"{green_rate * 100:.1f}%"

    verdict_rows = "".join(
        f"<tr><td><code>{html.escape(f.get('char',''))}</code></td>"
        f"<td>U+{f.get('codepoint','')}</td><td>{html.escape(str(f.get('name','')))}</td></tr>"
        for f in (unicode_findings or [])[:30]
    )
    if not verdict_rows:
        verdict_rows = "<tr><td colspan=3><i>Keine unsichtbaren Zeichen gefunden.</i></td></tr>"

    text_block = ""
    if include_text:
        text_block = (
            f"<h2>Analysierter Text</h2><pre>{html.escape(text[:2000])}</pre>"
            if len(text) > 2000 else
            f"<h2>Analysierter Text</h2><pre>{html.escape(text)}</pre>"
        )

    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head><meta charset="utf-8"><title>Forensik-Befund — {html.escape(label)}</title>
<style>
body {{ font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; color:#1a1a2e;
       margin:24px auto; max-width:800px; padding:0 16px; font-size:13px; line-height:1.5; }}
h1 {{ color:#0b4f6c; font-size:22px; margin-bottom:2px; }}
h2 {{ color:#0b4f6c; border-bottom:2px solid #0b4f6c; padding-bottom:4px; margin-top:22px; }}
.badge {{ display:inline-block; padding:6px 14px; border-radius:4px; color:#fff;
          font-weight:700; background:{badge[1]}; margin:10px 0; }}
table {{ border-collapse:collapse; width:100%; margin:8px 0; }}
th,td {{ border:1px solid #c8d2da; padding:5px 8px; text-align:left; font-size:12px; }}
th {{ background:#eef3f7; }}
pre {{ background:#f4f6f8; padding:12px; border-radius:4px; white-space:pre-wrap;
      font-size:11px; }}
.meta {{ color:#777; font-size:11px; }}
.rec {{ background:#fdf6e3; border-left:4px solid #d9a404; padding:8px 12px; margin-top:12px; }}
</style></head>
<body>
<h1>Forensik-Befund</h1>
<div class="meta">Erstellt {now} · Schlüssel: <code>{html.escape(label)}</code></div>
<div class="badge">{badge[0]}</div>
<h2>KGW-Statistik</h2>
<table>
<tr><th>Metrik</th><th>Wert</th></tr>
<tr><td>Z-Score</td><td><b>{z_cell}</b></td></tr>
<tr><td>Green-Rate</td><td>{rate_cell}</td></tr>
<tr><td>Score-Tokens</td><td>{r.get('n_tokens', 0)}</td></tr>
<tr><td>Grüne Tokens</td><td>{r.get('green_count', 0)}</td></tr>
<tr><td>p-Wert (zweiseitig)</td><td>{r.get('p_value')}</td></tr>
</table>
<h2>Unsichtbare Zeichen ({uni} gefunden)</h2>
<table><tr><th>Zeichen</th><th>Codepoint</th><th>Name</th></tr>{verdict_rows}</table>
{text_block}
<div class="rec"><b>Empfehlung:</b>
{"Clean + Dilute + Rewrite — das statistische Signal ist signifikant (Z>=4); "
 "der Text trägt nachweisbar ein Greenlist-Wasserzeichen." if verdict == "watermark_detected"
 else "Redlist-Signal nachgewiesen (Z<=-4) — der Text meidet bewusst eine "
 "hash-abgeleitete Token-Menge (Redlist-Wasserzeichen). Clean + Dilute + Rewrite empfohlen."
 if verdict == "redlist_detected"
 else "Signal vorhanden aber unter der Signifikanzschwelle — Clean + Dilute als Vorsichtsmaßnahme."
 if verdict == "weak_signal"
 else "Schwaches Redlist-Signal (Z<=-2) — Hinweis auf eine bewusst vermiedene "
 "Hash-Menge, unter der Signifikanzschwelle. Clean + Dilute als Vorsichtsmaßnahme."
 if verdict == "weak_redlist_signal"
 else "Kein statistisches Signal mit diesem Schlüssel. Reguläre Cleanup-Kette ausreichend."
 if verdict == "no_signal"
 else "Text zu kurz für eine statistische Aussage (mindestens ~10 Score-Tokens nötig)."}
</div>
</body></html>"""


def render_pdf(html_path: Path) -> Path | None:
    """Render HTML to PDF via Edge headless (Windows). Returns PDF path or None."""
    edge = None
    for candidate in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                      r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"):
        if Path(candidate).exists():
            edge = candidate
            break
    if edge is None:
        return None
    out = html_path.with_suffix(".pdf")
    subprocess.run(
        [edge, "--headless", "--disable-gpu", "--no-sandbox",
         f"--print-to-pdf={out.resolve()}",
         "--no-pdf-header-footer",
         f"file:///{html_path.resolve().as_posix()}"],
        capture_output=True, timeout=120,
    )
    return out if out.exists() else None
