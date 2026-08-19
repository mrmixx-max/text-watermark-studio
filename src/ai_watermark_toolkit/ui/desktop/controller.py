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
from ...forensics.finding import classify_finding
from ...forensics.key_registry import DEFAULT_PATH, KeyRegistry, mask_secret_key_id
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

    def __init__(self, registry_path: str | Path | None = None, report_dir: str | Path | None = None):
        self.registry_path = Path(registry_path) if registry_path is not None else Path(DEFAULT_PATH)
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
        # Not in the registry -> treat as a raw secret (CLI contract). The
        # reported key_id is masked so the secret never leaks into detect
        # results / finding reports (the detection uses the real secret).
        return {
            "key_id": mask_secret_key_id(arg),
            "family": "kgw",
            "secret": arg,
            "gamma": None,
            "key_source": "raw_secret",
        }, False

    def _require_kgw_keys(self) -> list[dict]:
        """All registry keys usable for KGW detection; error when none."""
        keys = [k for k in KeyRegistry(self.registry_path).list_keys() if k.get("family") == "kgw" and k.get("secret")]
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
            raise IsADirectoryError(f"Erwartet eine Datei, erhalten ein Verzeichnis: {p}")
        return p.read_text(encoding="utf-8", errors="replace")

    def parse_json(self, text: str) -> dict:
        """Parse JSON for sign/verify; ValueError with a clear message."""
        if not text or not text.strip():
            raise ValueError("Kein JSON im Ergebnis-Panel — fuehre zuerst eine Aktion aus (z. B. Detektieren).")
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Ungueltiges JSON: {e}") from e
        if not isinstance(obj, dict):
            raise ValueError(f"Erwartet ein JSON-Objekt (dict), erhalten: {type(obj).__name__}")
        return obj

    # ------------------------------------------------------------- detect
    def detect_text(self, text: str, key_id_or_secret: str | None = None, lang: str = "de") -> dict:
        """KGW Z-score (+ e-process) detection of the given text.

        With a key argument: that single key (registry key_id or raw
        secret) is tested. Without: every registered KGW key is tested
        (multi-key, Bonferroni note). The e-process is the anytime-valid
        companion (stdlib, always available). Result shape mirrors the CLI
        ``ai-wm detect --key`` JSON, plus a localized ``finding`` block
        (``lang``: ``"de"`` or ``"en"``) with the forensic verdict text.
        """
        if not text or not text.strip():
            raise ValueError("Text ist leer — Text eingeben oder Datei oeffnen.")
        if key_id_or_secret:
            key, _from_registry = self._resolve_key(key_id_or_secret)
            gamma = key.get("gamma") or DEFAULT_GAMMA
            result = detect_multi_key(text, [key], gamma=gamma, level="word", context=1)
            e_result = e_detect(text, key["secret"], gamma=gamma, level="word", context=1)
        else:
            keys = self._require_kgw_keys()
            gamma = DEFAULT_GAMMA
            result = detect_multi_key(text, keys, gamma=gamma, level="word", context=1)
            e_result = e_detect_multi(text, keys, gamma=gamma)
        best = result.get("best") or {}
        out = {
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
        out["finding"] = classify_finding(
            out,
            key_id=best.get("key_id") or "unknown",
            lang=lang,
        )
        return out

    def detect_file(self, path: str | Path, key_id_or_secret: str | None = None, lang: str = "de") -> dict:
        """Detect a text file (registry key_id or raw secret, optional)."""
        return self.detect_text(self.load_file(path), key_id_or_secret, lang=lang)

    # ------------------------------------------------------------- embed
    def embed_text(
        self, text: str, key_id: str, gamma: float | None = None, level: str = "word", context: int = 1,
    ) -> dict:
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
                "detektieren).",
            )
        eff_gamma = gamma if gamma is not None else (key.get("gamma") or DEFAULT_GAMMA)
        result = mark_greenlist(text, key["secret"], gamma=eff_gamma, level=level, context=context)
        return {
            "key_id": key_id,
            "gamma": eff_gamma,
            "level": level,
            "context": context,
            **result,
        }

    # ------------------------------------------------------------- report
    def build_report(
        self,
        text: str,
        key_id: str,
        output_dir: str | Path | None = None,
        context: dict | None = None,
        lang: str = "de",
    ) -> dict:
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

        ``lang`` selects the report language (``"de"`` default, ``"en"``
        available); every human-readable string is localized.
        """
        if not text or not text.strip():
            raise ValueError("Text ist leer — Text eingeben oder Datei oeffnen.")
        key, from_registry = self._resolve_key(key_id)
        if not from_registry:
            raise ValueError(
                f"Key '{key_id}' ist nicht in der Registry — der Bericht benoetigt einen registrierten Key mit Secret.",
            )
        html = _build_report_html(text, key["secret"], key_label=key_id, lang=lang)
        target = Path(output_dir) if output_dir is not None else (self.report_dir or _default_report_dir())
        target.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        out = target / f"tws-report-{stamp}.html"
        out.write_text(html, encoding="utf-8")
        det = detect_kgw(text, key["secret"], gamma=key.get("gamma") or DEFAULT_GAMMA)
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
            raise TypeError("payload muss ein JSON-Objekt (dict) sein.")
        key, from_registry = self._resolve_key(key_id)
        if not from_registry:
            raise ValueError(
                f"Key '{key_id}' ist nicht in der Registry — Signieren benoetigt einen registrierten Key mit Secret.",
            )
        return sign_report(payload, key["secret"], key_id=key_id)

    def verify_report_json(self, signed: dict, key_id: str) -> dict:
        """Verify a signed findings payload with the registry secret."""
        if not isinstance(signed, dict):
            raise TypeError("signed muss ein JSON-Objekt (dict) sein.")
        key, from_registry = self._resolve_key(key_id)
        if not from_registry:
            raise ValueError(
                f"Key '{key_id}' ist nicht in der Registry — Verifizieren benoetigt einen registrierten Key mit Secret.",
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
        gen = generate_marked_text(
            prefix=text or "", key=SAMPLE_KEY, gamma=0.25, bias_strength=2.0, n_tokens=200, seed=int(seed), context=1,
        )
        det = detect_kgw(gen["text"], SAMPLE_KEY, 0.25, context=1)
        return {
            "generated": gen,
            "detected": det,
            "key": SAMPLE_KEY,
            "seed": int(seed),
            "note": "Synthetischer KGW-Sampling-Bias (Mechanik-Beweis, kein LLM)",
        }

    # ------------------------------------------------- TUI-Paritaet: Text-Tools
    def clean_text(self, text: str) -> dict:
        """Strip the invisible-character layer (transform.clean)."""
        if not text or not text.strip():
            raise ValueError("Text ist leer — Text eingeben oder Datei oeffnen.")
        from ...transform.clean import clean_text as _clean

        r = _clean(text)
        return {
            "text": r.text,
            "unicode_removed": r.unicode_removed,
            "confusable_folds": r.confusable_folds,
        }

    def dilute_text(self, text: str, intensity: str = "standard") -> dict:
        """Rewrite marker-heavy phrasing (transform.dilute)."""
        if not text or not text.strip():
            raise ValueError("Text ist leer — Text eingeben oder Datei oeffnen.")
        from ...transform.dilute import dilute_text as _dilute

        r = _dilute(text, intensity=intensity)
        return {
            "text": r.text,
            "changed": r.changed,
            "intensity": r.intensity,
            "frozen_blocks": r.frozen_blocks,
        }

    def rewrite_text(self, text: str, mode: str = "structural") -> dict:
        """Structural/backtranslate rewrite (rewrite.service, local)."""
        if not text or not text.strip():
            raise ValueError("Text ist leer — Text eingeben oder Datei oeffnen.")
        from ...rewrite.service import RewriteService

        result = RewriteService().rewrite(text, mode=mode)
        result["backend"] = result.get("backend", "local-structural")
        return result

    def run_pipeline(self, text: str, rewrite_mode: str | None = "structural") -> dict:
        """Full chain detect → clean → dilute → rewrite (pipeline)."""
        if not text or not text.strip():
            raise ValueError("Text ist leer — Text eingeben oder Datei oeffnen.")
        from ...pipeline import run_pipeline as _run_pipeline

        out, report = _run_pipeline(text, rewrite_mode=rewrite_mode)
        return {"output": out, "report": report}

    # --------------------------------------------- TUI-Paritaet: Datei-Aktionen
    def inspect_file(self, path: str | Path) -> dict:
        """Inspect C2PA/EXIF/XMP metadata of a file (metadata.service)."""
        from ...metadata.service import inspect

        src = Path(path)
        if not src.exists():
            raise FileNotFoundError(f"Datei nicht gefunden: {src}")
        try:
            return inspect(src.read_bytes(), src.name)
        except ValueError as e:
            return {"unsupported_format": src.name, "message": str(e)}

    def clean_file(self, path: str | Path) -> dict:
        """Strip metadata from a file, write `<stem>-clean<suffix>`."""
        from ...metadata.service import clean

        src = Path(path)
        if not src.exists():
            raise FileNotFoundError(f"Datei nicht gefunden: {src}")
        cleaned, report = clean(src.read_bytes(), src.name)
        out = src.with_name(src.stem + "-clean" + src.suffix)
        out.write_bytes(cleaned)
        return {"output_path": str(out), **report}

    def embed_file(self, path: str | Path, key_id: str) -> dict:
        """HMAC-sign a file (provenance packet), write `-signed` copy."""
        from ...metadata.provenance import embed_provenance

        src = Path(path)
        if not src.exists():
            raise FileNotFoundError(f"Datei nicht gefunden: {src}")
        key, from_registry = self._resolve_key(key_id)
        if not from_registry:
            raise ValueError(
                f"Key '{key_id}' ist nicht in der Registry — File-Embed benoetigt einen registrierten Key mit Secret.",
            )
        emb = embed_provenance(src.read_bytes(), src.name, key["key_id"], key["secret"])
        out = src.with_name(src.stem + "-signed" + src.suffix)
        out.write_bytes(emb.data)
        return {
            "output_path": str(out),
            "mark_size": emb.mark_size,
            "format": emb.format,
            "key_id": key["key_id"],
        }

    def detect_file_provenance(self, path: str | Path) -> dict:
        """Verify a file's provenance signature (all registered secrets)."""
        from ...metadata.provenance import detect_provenance

        src = Path(path)
        if not src.exists():
            raise FileNotFoundError(f"Datei nicht gefunden: {src}")
        secrets = {k["key_id"]: k["secret"] for k in self._require_kgw_keys()}
        det = detect_provenance(src.read_bytes(), src.name, secrets=secrets)
        return {"found": det.found, "valid": det.valid, "key_id": det.key_id, "file": src.name}

    def image_score(self, path: str | Path) -> dict:
        """SynthID pixel scoring (needs the checkpoint; honest hint)."""
        from ...metadata.synthid import score_synthid

        src = Path(path)
        if not src.exists():
            raise FileNotFoundError(f"Datei nicht gefunden: {src}")
        return score_synthid(str(src))

    def watch_once(self, path: str | Path) -> dict:
        """One scan pass over a directory (forensics.watcher)."""
        from ...forensics.watcher import watch_dir

        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Verzeichnis nicht gefunden: {p}")
        if not p.is_dir():
            raise NotADirectoryError(f"Erwartet ein Verzeichnis: {p}")
        lines: list[str] = []
        n = watch_dir(str(p), once=True, out=lines.append)
        return {"reported": n, "lines": lines}

    def attack_matrix(self) -> dict:
        """Run the attack matrix benchmark (benchmarks/attack_matrix.py)."""
        return self._run_benchmark("attack_matrix.py")

    def synthid_sweep(self) -> dict:
        """Run the gamma×paraphrase sweep (benchmarks/synthid_sweep.py)."""
        return self._run_benchmark("synthid_sweep.py")

    def _run_benchmark(self, script_name: str) -> dict:
        """Execute a repo benchmark script; tail of stdout on success."""
        import subprocess
        import sys

        script = Path(__file__).resolve().parents[2] / "benchmarks" / script_name
        if not script.exists():
            raise FileNotFoundError(f"benchmarks/{script_name} not found (repo install).")
        r = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=300)
        return {
            "script": script_name,
            "exit_code": r.returncode,
            "stdout_tail": r.stdout[-3000:],
            "stderr_tail": r.stderr[-2000:],
        }

    def system_state(self) -> dict:
        """Studio banner + system state (ui.banner + version)."""
        from ... import __version__
        from ...ui.banner import render_banner

        banner = render_banner() if callable(render_banner) else "Text Watermark Studio"
        return {"version": __version__, "banner": banner, "local": True, "telemetry": "none"}

    def check_update(self) -> dict:
        """Check PyPI for a newer release (read-only, no upgrade)."""
        import urllib.request
        from importlib.metadata import version as _pkg_version

        try:
            installed = _pkg_version("text-watermark-studio")
        except Exception:
            installed = "unknown"
        with urllib.request.urlopen("https://pypi.org/pypi/text-watermark-studio/json", timeout=15) as r:
            latest = json.loads(r.read().decode())["info"]["version"]
        return {"installed": installed, "latest": latest, "up_to_date": installed == latest}

    def install_llm_model(self, model_name: str) -> dict:
        """Pull a local model via the Ollama API (llm.service)."""
        if not model_name or not model_name.strip():
            raise ValueError("No model name given — type one (e.g. llama3.2:3b).")
        from ...llm.service import LocalLLMService

        return LocalLLMService().install_model(model_name.strip())

    def run_optimizer(self) -> dict:
        """Prompt-optimizer evaluator loop (locked evals, read-only)."""
        from ...optimization.service import PromptOptimizationService

        base = (
            "Rewrite the given text so it no longer reads like AI output. "
            "Keep all facts, numbers and names exactly as they are."
        )
        return PromptOptimizationService().optimize(base)

    def similarity(self, target: str | Path, corpus: str | Path, threshold: float | None = None) -> dict:
        """Compare a text file against a user-owned corpus (MinHash)."""
        from ...forensics.similarity import check_similarity

        target_path = Path(target)
        corpus_path = Path(corpus)
        if not target_path.exists() or not target_path.is_file():
            raise FileNotFoundError(f"Datei nicht gefunden: {target_path}")
        if not corpus_path.exists() or not corpus_path.is_dir():
            raise FileNotFoundError(f"Corpus-Ordner nicht gefunden: {corpus_path}")
        text = target_path.read_text(encoding="utf-8", errors="replace")
        r = check_similarity(text, [corpus_path])
        if threshold is not None:
            r["input"] = dict(r.get("input") or {})
            r["input"]["threshold"] = float(threshold)
            r["findings"] = [f for f in r.get("findings", []) if f["similarity"] >= float(threshold)]
        return r

    def delta_z(self, before: str | Path, after: str | Path, key_id: str | None = None) -> dict:
        """ΔZ check between two text files (forensics.delta_z)."""
        from ...forensics.delta_z import delta_z as _delta_z
        from ...forensics.key_registry import KeyRegistry

        before_text = self.load_file(before)
        after_text = self.load_file(after)
        keys = self._require_kgw_keys()
        key_arg = key_id or keys[0]["key_id"]
        if key_id and key_id not in [k["key_id"] for k in keys]:
            raise ValueError(f"Key {key_id} not found in registry.")
        return _delta_z(before_text, after_text, key_arg, registry=KeyRegistry(self.registry_path))

    def finding_report(
        self,
        path: str | Path,
        key_id: str | None = None,
        e_value: bool = False,
        delta_z_after: str | Path | None = None,
        context: dict | None = None,
    ) -> dict:
        """KI-Erklärungs-Befund A-D (forensics.finding)."""
        from ...forensics.delta_z import delta_z as _delta_z
        from ...forensics.e_value import e_detect
        from ...forensics.finding import build_finding_report
        from ...forensics.key_registry import KeyRegistry
        from ...forensics.kgw import DEFAULT_GAMMA, detect_multi_key

        text = self.load_file(path)
        keys = self._require_kgw_keys()
        if key_id:
            keys = [k for k in keys if k["key_id"] == key_id] or keys
        key = keys[0]
        gamma = key.get("gamma") or DEFAULT_GAMMA
        results = {"detect": detect_multi_key(text, [key], gamma=gamma)}
        if e_value:
            results["e_value"] = e_detect(text, key["secret"], gamma=gamma)
        if delta_z_after:
            after_text = self.load_file(delta_z_after)
            results["delta_z"] = _delta_z(text, after_text, key["key_id"], registry=KeyRegistry(self.registry_path))
        return build_finding_report(results, key_id=key["key_id"], context=context)

    def sign_report_file(self, path: str | Path, key_id: str | None = None) -> dict:
        """Sign a findings JSON file → `.signed.json` (secret stays local)."""
        from ...forensics.signed_report import sign_report

        src = Path(path)
        if not src.exists():
            raise FileNotFoundError(f"Datei nicht gefunden: {src}")
        payload = json.loads(src.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise TypeError("Payload muss ein JSON-Objekt (dict) sein.")
        key = self._resolve_key(key_id)[0] if key_id else self._require_kgw_keys()[0]
        if not key.get("secret"):
            raise ValueError(f"Key '{key.get('key_id')}' hat kein Secret.")
        signed = sign_report(payload, key["secret"], key_id=key["key_id"], algorithm="hmac-sha256")
        out = src.with_suffix(".signed.json")
        out.write_text(json.dumps(signed, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"output_path": str(out), "key_id": key["key_id"], "signature": signed.get("signature")}

    def verify_report_file(self, path: str | Path, key_id: str | None = None) -> dict:
        """Verify a signed findings JSON file."""
        from ...forensics.signed_report import verify_report

        src = Path(path)
        if not src.exists():
            raise FileNotFoundError(f"Datei nicht gefunden: {src}")
        signed = json.loads(src.read_text(encoding="utf-8"))
        algorithm = (signed.get("signature") or {}).get("algorithm") if isinstance(signed, dict) else None
        secret = ""
        if algorithm == "hmac-sha256":
            keys = self._require_kgw_keys()
            key_id = key_id or keys[0]["key_id"]
            key = next((k for k in keys if k["key_id"] == key_id), None)
            if key is None:
                raise ValueError(f"Key {key_id} not found in registry.")
            secret = key["secret"]
        result = verify_report(signed, secret, public_key_pem=None)
        result["file"] = src.name
        return result

    def generate_keypair(self, target_dir: str | Path, algorithm: str = "mldsa-44") -> dict:
        """Generate an ML-DSA keypair (report-keygen parity)."""
        from ...forensics.signed_report import generate_mldsa_keypair, mldsa_status

        status = mldsa_status()
        if not status["available"]:
            raise RuntimeError(status["hint"])
        pair = generate_mldsa_keypair(algorithm)
        out_dir = Path(target_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        prefix = "mldsa"
        priv = out_dir / f"{prefix}_private.pem"
        pub = out_dir / f"{prefix}_public.pem"
        priv.write_text(pair["private_key_pem"], encoding="utf-8")
        pub.write_text(pair["public_key_pem"], encoding="utf-8")
        return {
            "algorithm": pair["algorithm"],
            "private_key": str(priv),
            "public_key": str(pub),
            "hint": status.get("hint", ""),
        }
