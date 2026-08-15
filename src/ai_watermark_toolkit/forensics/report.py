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

# ---------------------------------------------------------------- i18n
_RTEXTS: dict[str, dict[str, str]] = {
    "de": {
        "badge_detected": "WASSERZEICHEN NACHGEWIESEN",
        "badge_redlist": "REDLIST-SIGNAL NACHGEWIESEN",
        "badge_weak": "SCHWACHES SIGNAL",
        "badge_weak_redlist": "SCHWACHES REDLIST-SIGNAL",
        "badge_none": "KEIN SIGNAL",
        "badge_short": "TEXT ZU KURZ",
        "badge_unknown": "UNBEKANNT",
        "title": "Forensik-Befund",
        "meta": "Erstellt {now} · Schlüssel: {label}",
        "h2_stats": "KGW-Statistik",
        "th_metric": "Metrik",
        "th_value": "Wert",
        "td_zscore": "Z-Score",
        "td_green_rate": "Green-Rate",
        "td_score_tokens": "Score-Tokens",
        "td_green_tokens": "Grüne Tokens",
        "td_p_value": "p-Wert (zweiseitig)",
        "h2_unicode": "Unsichtbare Zeichen ({uni} gefunden)",
        "th_char": "Zeichen",
        "th_codepoint": "Codepoint",
        "th_name": "Name",
        "no_unicode": "Keine unsichtbaren Zeichen gefunden.",
        "h2_text": "Analysierter Text",
        "rec_label": "Empfehlung:",
        "rec_detected": ("Clean + Dilute + Rewrite — das statistische Signal ist "
                         "signifikant (Z>=4); der Text trägt nachweisbar ein "
                         "Greenlist-Wasserzeichen."),
        "rec_redlist": ("Redlist-Signal nachgewiesen (Z<=-4) — der Text meidet "
                        "bewusst eine hash-abgeleitete Token-Menge (Redlist-"
                        "Wasserzeichen). Clean + Dilute + Rewrite empfohlen."),
        "rec_weak": ("Signal vorhanden aber unter der Signifikanzschwelle — "
                     "Clean + Dilute als Vorsichtsmaßnahme."),
        "rec_weak_redlist": ("Schwaches Redlist-Signal (Z<=-2) — Hinweis auf "
                             "eine bewusst vermiedene Hash-Menge, unter der "
                             "Signifikanzschwelle. Clean + Dilute als "
                             "Vorsichtsmaßnahme."),
        "rec_none": ("Kein statistisches Signal mit diesem Schlüssel. Reguläre "
                     "Cleanup-Kette ausreichend."),
        "rec_short": ("Text zu kurz für eine statistische Aussage (mindestens "
                      "~10 Score-Tokens nötig)."),
    },
    "en": {
        "badge_detected": "WATERMARK DETECTED",
        "badge_redlist": "REDLIST SIGNAL DETECTED",
        "badge_weak": "WEAK SIGNAL",
        "badge_weak_redlist": "WEAK REDLIST SIGNAL",
        "badge_none": "NO SIGNAL",
        "badge_short": "TEXT TOO SHORT",
        "badge_unknown": "UNKNOWN",
        "title": "Forensic Finding",
        "meta": "Created {now} · Key: {label}",
        "h2_stats": "KGW Statistics",
        "th_metric": "Metric",
        "th_value": "Value",
        "td_zscore": "Z-Score",
        "td_green_rate": "Green rate",
        "td_score_tokens": "Score tokens",
        "td_green_tokens": "Green tokens",
        "td_p_value": "p-value (two-sided)",
        "h2_unicode": "Invisible characters ({uni} found)",
        "th_char": "Character",
        "th_codepoint": "Codepoint",
        "th_name": "Name",
        "no_unicode": "No invisible characters found.",
        "h2_text": "Analyzed text",
        "rec_label": "Recommendation:",
        "rec_detected": ("Clean + Dilute + Rewrite — the statistical signal is "
                         "significant (Z>=4); the text verifiably carries a "
                         "greenlist watermark."),
        "rec_redlist": ("Redlist signal detected (Z<=-4) — the text "
                        "deliberately avoids a hash-derived token set (redlist "
                        "watermark). Clean + Dilute + Rewrite recommended."),
        "rec_weak": ("Signal present but below the significance threshold — "
                     "Clean + Dilute as a precaution."),
        "rec_weak_redlist": ("Weak redlist signal (Z<=-2) — hint of a "
                             "deliberately avoided hash set, below the "
                             "significance threshold. Clean + Dilute as a "
                             "precaution."),
        "rec_none": ("No statistical signal with this key. Regular cleanup "
                     "chain is sufficient."),
        "rec_short": ("Text too short for a statistical statement (at least "
                      "~10 score tokens required)."),
    },
}


def _rt(lang: str, key: str) -> str:
    table = _RTEXTS.get(lang, _RTEXTS["de"])
    return table.get(key, _RTEXTS["de"].get(key, key))


def build_report(text: str, key: str, *, lang: str = "de",
                 unicode_findings: list | None = None,
                 marker_hits: int = 0,
                 include_text: bool = True,
                 key_label: str | None = None,
                 level: str = "word", context: int = 1) -> str:
    """Build a self-contained HTML findings report for one detect run.

    ``key`` is the secret used for KGW detection (never shown in the report).
    ``key_label`` is the display name (e.g. the registry key_id); when omitted
    it falls back to ``key`` for backward compatibility with direct callers.
    ``lang`` selects the report language (``"de"`` default, ``"en"``
    available); every human-readable string is localized.
    """
    label = key_label if key_label is not None else key
    r = detect_kgw(text, key, level=level, context=context)
    verdict = r["verdict"]
    z = r["z_score"]
    green_rate = r["green_rate"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    uni = len(unicode_findings or [])

    badge = {
        "watermark_detected": (_rt(lang, "badge_detected"), "#b02a2a"),
        "redlist_detected": (_rt(lang, "badge_redlist"), "#b02a2a"),
        "weak_signal": (_rt(lang, "badge_weak"), "#d9a404"),
        "weak_redlist_signal": (_rt(lang, "badge_weak_redlist"), "#d9a404"),
        "no_signal": (_rt(lang, "badge_none"), "#0b7a3b"),
        "too_short": (_rt(lang, "badge_short"), "#777777"),
    }.get(verdict, (_rt(lang, "badge_unknown"), "#777777"))

    z_cell = "—" if z is None else f"{z:.2f}"
    rate_cell = "—" if green_rate is None else f"{green_rate * 100:.1f}%"

    verdict_rows = "".join(
        f"<tr><td><code>{html.escape(f.get('char',''))}</code></td>"
        f"<td>U+{f.get('codepoint','')}</td><td>{html.escape(str(f.get('name','')))}</td></tr>"
        for f in (unicode_findings or [])[:30]
    )
    if not verdict_rows:
        verdict_rows = (f"<tr><td colspan=3><i>"
                        f"{html.escape(_rt(lang, 'no_unicode'))}</i></td></tr>")

    text_block = ""
    if include_text:
        text_block = (
            f"<h2>{html.escape(_rt(lang, 'h2_text'))}</h2>"
            f"<pre>{html.escape(text[:2000])}</pre>"
            if len(text) > 2000 else
            f"<h2>{html.escape(_rt(lang, 'h2_text'))}</h2>"
            f"<pre>{html.escape(text)}</pre>"
        )

    if verdict == "watermark_detected":
        rec = _rt(lang, "rec_detected")
    elif verdict == "redlist_detected":
        rec = _rt(lang, "rec_redlist")
    elif verdict == "weak_signal":
        rec = _rt(lang, "rec_weak")
    elif verdict == "weak_redlist_signal":
        rec = _rt(lang, "rec_weak_redlist")
    elif verdict == "no_signal":
        rec = _rt(lang, "rec_none")
    else:
        rec = _rt(lang, "rec_short")

    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head><meta charset="utf-8"><title>{html.escape(_rt(lang, 'title'))} — {html.escape(label)}</title>
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
<h1>{html.escape(_rt(lang, 'title'))}</h1>
<div class="meta">{html.escape(_rt(lang, 'meta').format(now=now, label=label))}</div>
<div class="badge">{badge[0]}</div>
<h2>{html.escape(_rt(lang, 'h2_stats'))}</h2>
<table>
<tr><th>{html.escape(_rt(lang, 'th_metric'))}</th><th>{html.escape(_rt(lang, 'th_value'))}</th></tr>
<tr><td>{html.escape(_rt(lang, 'td_zscore'))}</td><td><b>{z_cell}</b></td></tr>
<tr><td>{html.escape(_rt(lang, 'td_green_rate'))}</td><td>{rate_cell}</td></tr>
<tr><td>{html.escape(_rt(lang, 'td_score_tokens'))}</td><td>{r.get('n_tokens', 0)}</td></tr>
<tr><td>{html.escape(_rt(lang, 'td_green_tokens'))}</td><td>{r.get('green_count', 0)}</td></tr>
<tr><td>{html.escape(_rt(lang, 'td_p_value'))}</td><td>{r.get('p_value')}</td></tr>
</table>
<h2>{html.escape(_rt(lang, 'h2_unicode').format(uni=uni))}</h2>
<table><tr><th>{html.escape(_rt(lang, 'th_char'))}</th><th>{html.escape(_rt(lang, 'th_codepoint'))}</th><th>{html.escape(_rt(lang, 'th_name'))}</th></tr>{verdict_rows}</table>
{text_block}
<div class="rec"><b>{html.escape(_rt(lang, 'rec_label'))}</b>
{rec}
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
