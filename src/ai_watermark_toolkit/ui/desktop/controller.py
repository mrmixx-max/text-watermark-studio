"""Qt-free desktop controller — a thin facade over the core forensic API.

The desktop GUI is a SECOND CLIENT of the same truth as the CLI/API/TUI:
it calls the exact same core functions directly. There is NO HTTP server
and NO duplicated logic — this controller is the only bridge the PySide6
shell (``app.py``) needs, so the shell stays a dumb view: menus/buttons map
1:1 to controller methods, results are plain dicts, errors are exceptions
with readable German messages.

Design rules (enforced by tests):
- NO Qt import anywhere in this module. It must import and run in a plain
  CPython process — the GUI is an optional layer, the controller is not.
- No I/O beyond what the controller abstracts: file paths are parameters
  (``load_file``, ``build_report(output_dir=...)``). The only implicit
  defaults are the canonical registry path (same contract as the CLI:
  ``data/key_registry.json``) and the report output directory (Downloads,
  falling back to the system temp dir) — both documented here.
- The controller NEVER writes the key registry. A missing/empty registry
  is reported as an error with a hint, never silently created or seeded.
- Return values are JSON-serializable dicts (same shape the CLI prints).
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from ...forensics.e_value import e_detect, e_detect_multi
from ...forensics.key_registry import DEFAULT_PATH, KeyRegistry
from ...forensics.kgw import (
    DEFAULT_GAMMA,
    detect_kgw,
    detect_multi_key,
    mark_greenlist,
)
from ...forensics.report import build_report as _build_report_html
from ...forensics.signed_report import sign_report, verify_report
from ...generation.kgw_sampler import generate_marked_text

# Default key for the synthetic generation-time sampling demo (same default
# as the CLI ``ai-wm kgw-sample`` and the sampler module itself).
SAMPLE_KEY = "demo-sampling-bias-key"

# Default report output: the user's Downloads folder when it exists,
# otherwise the system temp dir. Overridable per call (``output_dir``).
def _default_report_dir() -> Path:
    downloads = Path.home() / "Downloads"
    return downloads if downloads.is_dir() else Path(tempfile.gettempdir())


def _key_hint(registry_path: Path) -> str:
    return (
        f"Keine KGW-Keys mit Secret in der Registry ({registry_path}). "
        "Key anlegen: POST /api/forensics/keys ueber `ai-wm serve`, oder "
        "einen Key-Eintrag direkt in data/key_registry.json ergaenzen."
    )


class DesktopController:
    """Core facade for the desktop shell (no Qt, no server, no network)."""

    def __init__(self, registry_path: str | Path | None = None,
                 report_dir: str | Path | None = None):
        self.registry_path = Path(registry_path) if registry_path is not None \
            else Path(DEFAULT_PATH)
        # None -> _default_report_dir() at call time (Downloads-or-tmp).
        self.report_dir = Path(report_dir) if report_dir is not None else None

    # ------------------------------------------------------------- registry
    def list_keys(self) -> list[dict]:
        """All registered keys (public metadata incl. secret — local tool)."""
        return KeyRegistry(self.registry_path).list_keys()

    def _resolve_key(self, key_id_or_secret: str) -> tuple[dict, bool]:
        """Resolve a key_id (registry) or a raw secret.

        Returns ``(key_dict, from_registry)`` mirroring the CLI's
        ``_resolve_key``: a registry hit is preferred, anything else is
        treated as a raw secret. Raises ValueError with a usable message
        when the argument is empty or the registry key has no secret.
        """
        if not key_id_or_secret or not str(key_id_or_secret).strip():
            raise ValueError("Kein Key angegeben — waehle einen Key aus der Liste.")
        arg = str(key_id_or_secret).strip()
        for k in KeyRegistry(self.registry_path).list_keys():
            if k.get("key_id") == arg:
                if not k.get("secret"):
                    raise ValueError(f"Key '{arg}' hat kein Secret.")
                return k, True
        # Not in the registry -> treat as a raw secret (CLI contract).
        return {"key_id": arg, "family": "kgw", "secret": arg, "gamma": None}, False

    def _require_kgw_keys(self) -> list[dict]:
        """All registry keys usable for KGW detection; error when none."""
        keys = [k for k in KeyRegistry(self.registry_path).list_keys()
                if k.get("family") == "kgw" and k.get("secret")]
        if not keys:
            raise ValueError(_key_hint(self.registry_path))
        return keys

    # ----------------------------------------------------------------- I/O
    def load_file(self, path: str | Path) -> str:
        """Read a text file (UTF-8, replacement on decode errors)."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Datei nicht gefunden: {p}")
        if p.is_dir():
            raise IsADirectoryError(
                f"Erwartet eine Datei, erhalten ein Verzeichnis: {p}"
            )
        return p.read_text(encoding="utf-8", errors="replace")

    def parse_json(self, text: str) -> dict:
        """Parse JSON for sign/verify; ValueError with a clear message."""
        if not text or not text.strip():
            raise ValueError("Kein JSON im Ergebnis-Panel — fuehre zuerst "
                             "eine Aktion aus (z. B. Detektieren).")
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Ungueltiges JSON: {e}") from e
        if not isinstance(obj, dict):
            raise ValueError("Erwartet ein JSON-Objekt (dict), "
                             f"erhalten: {type(obj).__name__}")
        return obj

    # ------------------------------------------------------------- detect
    def detect_text(self, text: str,
                    key_id_or_secret: str | None = None) -> dict:
        """KGW Z-score (+ e-process) detection of the given text.

        With a key argument: that single key (registry key_id or raw
        secret) is tested. Without: every registered KGW key is tested
        (multi-key, Bonferroni note). The e-process is the anytime-valid
        companion (stdlib, always available). Result shape mirrors the CLI
        ``ai-wm detect --key`` JSON.
        """
        if not text or not text.strip():
            raise ValueError("Text ist leer — Text eingeben oder Datei oeffnen.")
        if key_id_or_secret:
            key, _from_registry = self._resolve_key(key_id_or_secret)
            gamma = key.get("gamma") or DEFAULT_GAMMA
            result = detect_multi_key(text, [key], gamma=gamma,
                                      level="word", context=1)
            e_result = e_detect(text, key["secret"], gamma=gamma,
                                level="word", context=1)
        else:
            keys = self._require_kgw_keys()
            gamma = DEFAULT_GAMMA
            result = detect_multi_key(text, keys, gamma=gamma,
                                      level="word", context=1)
            e_result = e_detect_multi(text, keys, gamma=gamma)
        best = result.get("best") or {}
        return {
            "verdict": best.get("verdict", "no_signal"),
            "signal": best.get("signal"),
            "z_score": best.get("z_score"),
            "p_value": best.get("p_value"),
            "green_rate": best.get("green_rate"),
            "key_id": best.get("key_id"),
            "best_p_adjusted": result.get("best_p_adjusted"),
            "tested_keys": result.get("tested_keys"),
            "note": result.get("note"),
            "e_value": e_result,
            "kgw": result,
            "text_length": len(text),
        }

    def detect_file(self, path: str | Path,
                    key_id_or_secret: str | None = None) -> dict:
        """Detect a text file (registry key_id or raw secret, optional)."""
        return self.detect_text(self.load_file(path), key_id_or_secret)

    # ------------------------------------------------------------- embed
    def embed_text(self, text: str, key_id: str, gamma: float | None = None,
                   level: str = "word", context: int = 1) -> dict:
        """Greenlist-mark the text with a REGISTERED key (mark_greenlist).

        ``gamma`` defaults to the registry key's gamma, then the core
        DEFAULT_GAMMA. Returns the marked text plus stats; the marked text
        is guaranteed to detect (z > 4) with the same key.
        """
        if not text or not text.strip():
            raise ValueError("Text ist leer — Text eingeben oder Datei oeffnen.")
        key, from_registry = self._resolve_key(key_id)
        if not from_registry:
            raise ValueError(
                f"Key '{key_id}' ist nicht in der Registry — Embed benoetigt "
                "einen registrierten Key mit Secret (raw Secrets koennen nur "
                "detektieren)."
            )
        eff_gamma = gamma if gamma is not None else (key.get("gamma") or DEFAULT_GAMMA)
        result = mark_greenlist(text, key["secret"], gamma=eff_gamma,
                                level=level, context=context)
        return {
            "key_id": key_id,
            "gamma": eff_gamma,
            "level": level,
            "context": context,
            **result,
        }

    # ------------------------------------------------------------- report
    def build_report(self, text: str, key_id: str,
                     output_dir: str | Path | None = None,
                     context: dict | None = None) -> dict:
        """Build the self-contained HTML forensic report (build_report).

        Writes the HTML to ``output_dir`` (default: Downloads, fallback
        tmp) and returns the path plus the underlying verdict.

        ``context`` (Evidenzklasse D, Runde-3-Lücke E1) nimmt die
        institutionelle Regel (``institutional_rule``) und/oder die
        Entstehungshistorie (``origin_history``) entgegen. Der HTML-Befund
        rendert die Kontext-Dimension noch nicht ein (offen: GUI-Eingabefeld
        und HTML-Sektion); die Controller-Signatur ist vorbereitet und der
        erhaltene Kontext wird im Rückgabe-Dict ausgewiesen, damit die GUI
        die Übergabe später verdrahten kann.
        """
        if not text or not text.strip():
            raise ValueError("Text ist leer — Text eingeben oder Datei oeffnen.")
        key, from_registry = self._resolve_key(key_id)
        if not from_registry:
            raise ValueError(
                f"Key '{key_id}' ist nicht in der Registry — der Bericht "
                "benoetigt einen registrierten Key mit Secret."
            )
        html = _build_report_html(text, key["secret"], key_label=key_id)
        target = Path(output_dir) if output_dir is not None \
            else (self.report_dir or _default_report_dir())
        target.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        out = target / f"tws-report-{stamp}.html"
        out.write_text(html, encoding="utf-8")
        det = detect_kgw(text, key["secret"],
                         gamma=key.get("gamma") or DEFAULT_GAMMA)
        return {
            "html_path": str(out.resolve()),
            "verdict": det.get("verdict"),
            "z_score": det.get("z_score"),
            "html_bytes": len(html.encode("utf-8")),
            "context": {
                "provided": bool(context),
                "keys": sorted(context) if isinstance(context, dict) else [],
            },
        }

    # ------------------------------------------------------------- sign/verify
    def sign_report_json(self, payload: dict, key_id: str) -> dict:
        """Sign a findings payload (HMAC-SHA256, registry secret)."""
        if not isinstance(payload, dict):
            raise ValueError("payload muss ein JSON-Objekt (dict) sein.")
        key, from_registry = self._resolve_key(key_id)
        if not from_registry:
            raise ValueError(
                f"Key '{key_id}' ist nicht in der Registry — Signieren "
                "benoetigt einen registrierten Key mit Secret."
            )
        return sign_report(payload, key["secret"], key_id=key_id)

    def verify_report_json(self, signed: dict, key_id: str) -> dict:
        """Verify a signed findings payload with the registry secret."""
        if not isinstance(signed, dict):
            raise ValueError("signed muss ein JSON-Objekt (dict) sein.")
        key, from_registry = self._resolve_key(key_id)
        if not from_registry:
            raise ValueError(
                f"Key '{key_id}' ist nicht in der Registry — Verifizieren "
                "benoetigt einen registrierten Key mit Secret."
            )
        return verify_report(signed, key["secret"])

    # ------------------------------------------------------------- sampler
    def kgw_sample(self, text: str = "", seed: int = 0) -> dict:
        """Synthetic generation-time KGW sampling demo (kgw_sampler).

        Generates a greenlist-biased text seeded from ``text`` (prefix)
        and detects it — the mechanics proof that generation-time bias is
        recoverable. No LLM involved; the sampler is a controlled random
        walk over a synthetic vocabulary (documented honest limit).
        """
        gen = generate_marked_text(prefix=text or "", key=SAMPLE_KEY,
                                   gamma=0.25, bias_strength=2.0,
                                   n_tokens=200, seed=int(seed), context=1)
        det = detect_kgw(gen["text"], SAMPLE_KEY, 0.25, context=1)
        return {
            "generated": gen,
            "detected": det,
            "key": SAMPLE_KEY,
            "seed": int(seed),
            "note": "Synthetischer KGW-Sampling-Bias (Mechanik-Beweis, kein LLM)",
        }
