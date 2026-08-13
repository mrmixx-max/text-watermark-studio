"""Behavioral tests for product-truth gaps #5 (lab no-op) and #6 (MCP manifest).

#5: The lab service passed empty options to family plugins, so the KGW
    (sampling_bias) family always returned "kgw_*_requires_registered_secret_key"
    — /api/lab/embed was a guaranteed no-op, and plugin.demo() (the
    generation-time bias proof) had zero callers and no API endpoint.
#6: mcp/tools.json omitted 22 live core routes (detect/clean/dilute,
    forensics/embed, metadata/*, pdf/extract, queue/jobs/streams/studio), so a
    MCP client could not detect/clean/embed watermarks or check file provenance.

These tests are filesystem-safe: registry is monkeypatched onto tmp_path (never
data/); no writes to the repo data/ directory.
"""

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ai_watermark_toolkit.api import fastapi_app
from ai_watermark_toolkit.api.routes import lab as lab_route
from ai_watermark_toolkit.forensics.key_registry import KeyRegistry
from ai_watermark_toolkit.forensics.kgw import detect_kgw
from ai_watermark_toolkit.lab.service import WatermarkLabService

REPO = Path(__file__).resolve().parents[1]

SECRET = "lab-truth-secret-0001"
GAMMA = 0.25

EMBED_TEXT = (
    "Local AI models protect user privacy by processing information on the "
    "device instead of sending everything to a remote server. This approach "
    "reduces the amount of personal data shared with outside systems and "
    "gives people direct control over their information. The result is a "
    "lower risk of breaches and a stronger security posture."
)


def _tmp_registry(tmp_path: Path, entries: list[dict] | None = None) -> KeyRegistry:
    reg = KeyRegistry(str(tmp_path / "keys.json"))
    if entries is None:
        entries = [{"key_id": "kgw-1", "family": "kgw", "secret": SECRET, "gamma": GAMMA}]
    for e in entries:
        reg.add_key(e)
    return reg


def _resolve_routes(app_or_router):
    """Flatten (method, path) pairs from a FastAPI app or router (any version)."""
    result = set()
    for r in app_or_router.routes:
        if hasattr(r, "methods") and hasattr(r, "path"):
            for m in r.methods:
                result.add((m, r.path))
        orig = getattr(r, "original_router", None)
        if orig is not None and hasattr(orig, "routes"):
            result |= _resolve_routes(orig)
            continue
        nested = getattr(r, "router", None)
        if nested is not None and hasattr(nested, "routes"):
            result |= _resolve_routes(nested)
        elif hasattr(r, "routes"):
            result |= _resolve_routes(r)
    return result


# ---- FUND 5: lab no-op -----------------------------------------------------

class TestLabEmbedNoLongerNoOp:
    def test_service_embed_with_registered_key_is_real(self, tmp_path):
        svc = WatermarkLabService(registry=_tmp_registry(tmp_path))
        result = svc.embed_with("sampling_bias", EMBED_TEXT)
        assert result.get("family") == "sampling_bias", result
        assert "kgw_embedding_requires_registered_secret_key" not in result.get("notes", []), result
        assert result.get("replacements", 0) > 0, result
        assert result["text"] != EMBED_TEXT, result
        det = detect_kgw(result["text"], SECRET, GAMMA)
        assert det["verdict"] == "watermark_detected", det
        assert det["z_score"] >= 4.0, det

    def test_service_detect_all_with_registered_key_has_kgw_score(self, tmp_path):
        svc = WatermarkLabService(registry=_tmp_registry(tmp_path))
        marked = svc.embed_with("sampling_bias", EMBED_TEXT)
        results = svc.detect_all(marked["text"])
        sb = results["sampling_bias"]
        assert sb.get("score", 0.0) > 0.0, sb
        assert sb.get("kgw", {}).get("verdict") == "watermark_detected", sb

    def test_api_lab_embed_with_key_is_not_noop(self, tmp_path, monkeypatch):
        monkeypatch.setattr(lab_route.svc, "registry", _tmp_registry(tmp_path))
        c = TestClient(fastapi_app.app)
        r = c.post("/api/lab/embed", json={"family": "sampling_bias", "text": EMBED_TEXT})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("family") == "sampling_bias", body
        assert "kgw_embedding_requires_registered_secret_key" not in body.get("notes", []), body
        assert body.get("replacements", 0) > 0, body
        assert body["text"] != EMBED_TEXT, body

    def test_api_lab_embed_without_key_still_noop_honest(self, tmp_path, monkeypatch):
        # empty registry -> sampling_bias still reports it needs a secret
        monkeypatch.setattr(lab_route.svc, "registry", _tmp_registry(tmp_path, entries=[]))
        c = TestClient(fastapi_app.app)
        r = c.post("/api/lab/embed", json={"family": "sampling_bias", "text": EMBED_TEXT})
        assert r.status_code == 200, r.text
        body = r.json()
        assert "kgw_embedding_requires_registered_secret_key" in body.get("notes", []), body
        assert body["text"] == EMBED_TEXT, body


class TestLabDemoEndpoint:
    def test_service_demo_proves_generation_time_bias(self, tmp_path):
        svc = WatermarkLabService(registry=_tmp_registry(tmp_path))
        d = svc.demo_with("sampling_bias")
        assert d.get("demo") is True, d
        assert d["generated"]["green_rate"] > 0.7, d["generated"]
        assert d["detected"]["z_score"] >= 4.0, d["detected"]
        assert d["detected"]["verdict"] == "watermark_detected", d["detected"]

    def test_api_lab_demo_green_rate_above_0_7(self, tmp_path, monkeypatch):
        monkeypatch.setattr(lab_route.svc, "registry", _tmp_registry(tmp_path))
        c = TestClient(fastapi_app.app)
        r = c.post("/api/lab/demo", json={"family": "sampling_bias"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("demo") is True, body
        assert body["generated"]["green_rate"] > 0.7, body["generated"]
        assert body["detected"]["z_score"] >= 4.0, body["detected"]

    def test_api_lab_demo_unknown_family(self, tmp_path, monkeypatch):
        monkeypatch.setattr(lab_route.svc, "registry", _tmp_registry(tmp_path))
        c = TestClient(fastapi_app.app)
        r = c.post("/api/lab/demo", json={"family": "does_not_exist"})
        assert r.status_code == 200, r.text
        assert r.json() == {"error": "unknown_family"}


# ---- FUND 6: MCP manifest completeness ------------------------------------

class TestMCPManifestCoreRoutes:
    def test_manifest_covers_all_live_api_routes(self):
        manifest = json.loads((REPO / "mcp" / "tools.json").read_text(encoding="utf-8"))
        real = _resolve_routes(fastapi_app.app)
        man = {(t["method"], t["path"]) for t in manifest["tools"]}
        # system/doc routes + the self-referential manifest export are excluded
        missing = sorted(
            (m, p) for (m, p) in real
            if p not in ("/", "/health", "/ready", "/api/lab/mcp/tools")
            and not p.startswith(("/docs", "/redoc", "/openapi.json"))
            and (m, p) not in man
        )
        assert missing == [], missing

    def test_every_manifest_tool_resolves_to_a_live_route(self):
        manifest = json.loads((REPO / "mcp" / "tools.json").read_text(encoding="utf-8"))
        real = _resolve_routes(fastapi_app.app)
        bad = [t["name"] for t in manifest["tools"]
               if not t.get("optional") and (t["method"], t["path"]) not in real]
        assert bad == [], bad

    def test_core_watermark_tools_present(self):
        manifest = json.loads((REPO / "mcp" / "tools.json").read_text(encoding="utf-8"))
        names = {t["name"] for t in manifest["tools"]}
        for required in (
            "text_detect", "text_clean", "text_dilute", "forensics_embed",
            "metadata_formats", "metadata_inspect", "metadata_clean",
            "metadata_embed", "metadata_detect", "metadata_synthid_score",
            "pdf_extract", "queue_enqueue", "jobs_create", "streams_get_job",
            "studio_diff", "lab_demo",
        ):
            assert required in names, f"missing tool {required}"

    def test_manifest_tool_count_grew(self):
        manifest = json.loads((REPO / "mcp" / "tools.json").read_text(encoding="utf-8"))
        assert len(manifest["tools"]) >= 75, len(manifest["tools"])
