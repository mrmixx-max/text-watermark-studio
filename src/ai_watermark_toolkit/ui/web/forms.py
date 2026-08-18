"""Form-data adapter endpoints for the HTMX dashboard.

HTMX sends `application/x-www-form-urlencoded` data, but the existing API
routes expect JSON bodies. These adapter endpoints accept form fields and
delegate to the same underlying services, returning HTML snippets for HTMX
swaps.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from ...core.config import settings
from ...exporting.service import ExportService
from ...forensics.key_registry import KeyRegistry
from ...forensics.report import build_report
from ...forensics.signed_report import sign_report
from ...llm.service import LocalLLMService
from ...prompts.service import PromptRegistryService
from ...rewrite.service import RewriteService
from ...routing.service import ModelRoutingService
from ...services.text_service import TextService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard/api", tags=["dashboard-forms"])

text_svc = TextService()
rewrite_svc = RewriteService()
llm_svc = LocalLLMService()
routing_svc = ModelRoutingService()
prompt_svc = PromptRegistryService()
export_svc = ExportService()


def _render(data) -> str:
    """Render a JSON-serializable payload as a styled <pre> block."""
    safe = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    return '<pre class="overflow-x-auto whitespace-pre-wrap rounded-xl border border-white/10 bg-black/30 p-4 text-xs text-emerald-200">' + safe + "</pre>"


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@router.get("/health")
async def form_health(request: Request):
    """Health check that works with HTMX (returns HTML snippet)."""
    redis_ok = False
    if request.app.state.redis is not None:
        try:
            await request.app.state.redis.ping()
            redis_ok = True
        except (ConnectionError, TimeoutError, OSError):
            redis_ok = False
    body = {
        "ok": redis_ok,
        "env": settings.app_env,
        "redis": redis_ok,
        "version": "2.4.1",
        "mode": "watermark_lab",
    }
    return HTMLResponse(_render(body))


# ---------------------------------------------------------------------------
# Text operations
# ---------------------------------------------------------------------------
@router.post("/detect")
async def form_detect(
    text: str = Form(...),
    lang: str = Form("auto"),
    aggressive: str = Form(""),
):
    result = text_svc.detect(text, lang=lang)
    return HTMLResponse(_render(result))


@router.post("/clean")
async def form_clean(
    text: str = Form(...),
    nfkc: str = Form(""),
    fold_confusables: str = Form(""),
):
    result = text_svc.clean(text, nfkc=nfkc in ("true", "on", "1"), fold_confusables=fold_confusables in ("true", "on", "1"))
    return HTMLResponse(_render(result))


@router.post("/dilute")
async def form_dilute(
    text: str = Form(...),
    intensity: str = Form("standard"),
):
    result = text_svc.dilute(text, intensity=intensity)
    return HTMLResponse(_render(result))


@router.post("/embed")
async def form_embed(
    text: str = Form(...),
    key: str = Form(""),
    gamma: str = Form(""),
    level: str = Form("word"),
    context: str = Form("1"),
):
    if not key:
        return HTMLResponse('<div class="text-[var(--color-warning)]">Error: key is required</div>')
    from ...forensics.kgw import DEFAULT_GAMMA, mark_greenlist
    registry = KeyRegistry("data/key_registry.json")
    key_entry = next((k for k in registry.list_keys() if k.get("key_id") == key), None)
    if key_entry is None:
        return HTMLResponse(f'<div class="text-[var(--color-warning)]">Error: key not found: {key}</div>')
    if not key_entry.get("secret"):
        return HTMLResponse(f'<div class="text-[var(--color-warning)]">Error: key {key} has no secret</div>')
    g = float(gamma) if gamma else key_entry.get("gamma") or DEFAULT_GAMMA
    result = mark_greenlist(text, key_entry["secret"], gamma=g, level=level, context=int(context))
    return HTMLResponse(_render(result))


# ---------------------------------------------------------------------------
# Lab
# ---------------------------------------------------------------------------
@router.post("/lab/detect-all")
async def form_lab_detect(text: str = Form(...)):
    from ...lab.service import WatermarkLabService
    svc = WatermarkLabService()
    results = svc.detect_all(text)
    return HTMLResponse(_render({"text_length": len(text), "results": results}))


# ---------------------------------------------------------------------------
# Forensics keys
# ---------------------------------------------------------------------------
@router.get("/forensics/keys")
async def form_list_keys():
    registry = KeyRegistry("data/key_registry.json")
    return HTMLResponse(_render({"keys": registry.list_keys()}))


@router.post("/forensics/keys")
async def form_add_key(
    key_id: str = Form(...),
    family: str = Form("kgw"),
    status: str = Form("active"),
    owner: str = Form("local"),
):
    registry = KeyRegistry("data/key_registry.json")
    item = registry.add_key({"key_id": key_id, "family": family, "status": status, "owner": owner})
    return HTMLResponse(_render(item))


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------
@router.get("/llm/status")
async def form_llm_status():
    return HTMLResponse(_render(llm_svc.status()))


@router.post("/llm/configure")
async def form_llm_configure(
    server_base_url: str = Form(""),
    model_variant: str = Form(""),
    installed: str = Form(""),
):
    result = llm_svc.configure(
        server_base_url or None,
        model_variant or None,
        installed in ("true", "on", "1"),
    )
    return HTMLResponse(_render(result))


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------
@router.post("/routing/decide")
async def form_routing_decide(
    task: str = Form("general"),
    profile: str = Form("default"),
    need_large_context: str = Form(""),
    privacy_mode: str = Form(""),
):
    result = routing_svc.decide(
        task, profile,
        need_large_context in ("true", "on", "1"),
        privacy_mode in ("true", "on", "1"),
    )
    return HTMLResponse(_render(result))


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
@router.get("/prompts/templates")
async def form_prompt_templates():
    return HTMLResponse(_render({"templates": prompt_svc.list_templates()}))


@router.post("/prompts/render")
async def form_prompt_render(
    template_id: str = Form(...),
    version: str = Form(""),
    variables: str = Form("{}"),
):
    try:
        vars_dict = json.loads(variables)
    except json.JSONDecodeError as e:
        return HTMLResponse(f'<div class="text-[var(--color-warning)]">Invalid JSON: {e}</div>')
    result = prompt_svc.render(template_id, vars_dict, version or None)
    return HTMLResponse(_render(result))


# ---------------------------------------------------------------------------
# Queue / Streams
# ---------------------------------------------------------------------------
@router.get("/queue/depth")
async def form_queue_depth(request: Request):
    from ...queue.redis_queue import RedisQueueService
    q = RedisQueueService(request.app.state.redis)
    try:
        depth = await q.queue_depth()
        return HTMLResponse(_render({"depth": depth}))
    except (ValueError, RuntimeError, ConnectionError) as e:
        return HTMLResponse(_render({"error": str(e)}))


@router.get("/streams/metrics")
async def form_streams_metrics(request: Request):
    from ...streams.redis_streams import RedisStreamsService
    svc = RedisStreamsService(request.app.state.redis)
    try:
        info = await svc.stream_info()
        return HTMLResponse(_render(info))
    except (ValueError, RuntimeError, ConnectionError) as e:
        return HTMLResponse(_render({"error": str(e)}))


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------
@router.post("/report")
async def form_report(
    text: str = Form(...),
    lang: str = Form("de"),
    key: str = Form(""),
    level: str = Form("word"),
    context: str = Form("1"),
):
    from ...pipeline import detect_text as _detect_text
    from ...sanitize_unicode import analyze as _uni_analyze
    uni = _uni_analyze(text)
    d = _detect_text(text, lang=lang)
    marker_hits = d.get("layers", {}).get("lexical", {}).get("score", 0) if isinstance(d, dict) else 0
    html_out = build_report(
        text, key or None, lang=lang,
        unicode_findings=uni,
        marker_hits=marker_hits,
        key_label=key or None,
        level=level,
        context=int(context),
    )
    return HTMLResponse('<div class="text-[var(--color-success)]">Report generated (HTML length: ' + str(len(html_out)) + ')</div>' + _render({"html_length": len(html_out), "lang": lang}))


@router.post("/report-sign")
async def form_report_sign(
    input: str = Form(...),
    algorithm: str = Form("hmac-sha256"),
    key_id: str = Form("default"),
    secret: str = Form(""),
):
    try:
        payload = json.loads(input)
    except json.JSONDecodeError as e:
        return HTMLResponse(f'<div class="text-[var(--color-warning)]">Invalid JSON: {e}</div>')
    if not secret:
        return HTMLResponse('<div class="text-[var(--color-warning)]">Secret is required</div>')
    result = sign_report(payload, secret, key_id=key_id, algorithm=algorithm)
    return HTMLResponse(_render(result))


@router.post("/report-verify")
async def form_report_verify(
    input: str = Form(...),
    secret: str = Form(""),
):
    try:
        payload = json.loads(input)
    except json.JSONDecodeError as e:
        return HTMLResponse(f'<div class="text-[var(--color-warning)]">Invalid JSON: {e}</div>')
    from ...forensics.signed_report import verify_report
    result = verify_report(payload, secret)
    return HTMLResponse(_render(result))


@router.post("/report-keygen")
async def form_report_keygen(
    algorithm: str = Form("mldsa-44"),
    prefix: str = Form("mldsa"),
):
    from ...forensics.signed_report import generate_mldsa_keypair
    result = generate_mldsa_keypair(algorithm)
    return HTMLResponse(_render(result))


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
@router.post("/export/run")
async def form_export(
    title: str = Form("Export"),
    text: str = Form(...),
    format: str = Form("md"),
    style: str = Form("clean"),
):
    result = export_svc.export(title, text, format, style, {})
    return HTMLResponse(_render(result))


# ---------------------------------------------------------------------------
# File operations
# ---------------------------------------------------------------------------
@router.post("/file-inspect")
async def form_file_inspect(input: str = Form(...)):
    from ...metadata.service import inspect
    data = bytes(input, "utf-8") if input else b""
    try:
        data = __import__("pathlib").Path(input).read_bytes()
    except (OSError, ValueError):
        return HTMLResponse(f'<div class="text-[var(--color-warning)]">Cannot read: {input}</div>')
    report = inspect(data, input)
    return HTMLResponse(_render(report))


@router.post("/file-clean")
async def form_file_clean(
    input: str = Form(...),
    output: str = Form(...),
    verify: str = Form(""),
):
    from ...metadata.service import clean
    try:
        data = __import__("pathlib").Path(input).read_bytes()
    except (OSError, ValueError) as e:
        return HTMLResponse(f'<div class="text-[var(--color-warning)]">Cannot read: {e}</div>')
    cleaned, report = clean(data, input)
    __import__("pathlib").Path(output).write_bytes(cleaned)
    return HTMLResponse(_render({"output": output, "report": report}))


@router.post("/file-embed")
async def form_file_embed(
    input: str = Form(...),
    output: str = Form(...),
    key: str = Form(...),
):
    from ...forensics.key_registry import KeyRegistry
    from ...metadata.provenance import embed_provenance
    registry = KeyRegistry("data/key_registry.json")
    key_entry = next((k for k in registry.list_keys() if k.get("key_id") == key), None)
    if key_entry is None:
        return HTMLResponse(f'<div class="text-[var(--color-warning)]">Key not found: {key}</div>')
    try:
        data = __import__("pathlib").Path(input).read_bytes()
    except (OSError, ValueError) as e:
        return HTMLResponse(f'<div class="text-[var(--color-warning)]">Cannot read: {e}</div>')
    result = embed_provenance(data, input, key, key_entry["secret"])
    if not result.embedded:
        return HTMLResponse(f'<div class="text-[var(--color-warning)]">Unsupported format: {result.format}</div>')
    __import__("pathlib").Path(output).write_bytes(result.data)
    return HTMLResponse(_render({"embedded": True, "format": result.format, "output": output}))


@router.post("/file-detect")
async def form_file_detect(input: str = Form(...)):
    from ...forensics.key_registry import KeyRegistry
    from ...metadata.provenance import detect_provenance
    registry = KeyRegistry("data/key_registry.json")
    secrets = {k.get("key_id"): k.get("secret") for k in registry.list_keys() if k.get("secret")}
    try:
        data = __import__("pathlib").Path(input).read_bytes()
    except (OSError, ValueError) as e:
        return HTMLResponse(f'<div class="text-[var(--color-warning)]">Cannot read: {e}</div>')
    result = detect_provenance(data, input, secrets)
    return HTMLResponse(_render(result.to_dict()))


# ---------------------------------------------------------------------------
# Jobs / Batch
# ---------------------------------------------------------------------------
@router.post("/jobs")
async def form_jobs(
    input_dir: str = Form(...),
    output_dir: str = Form(...),
    mode: str = Form("pipeline"),
    intensity: str = Form("standard"),
    lang: str = Form("auto"),
):
    from ...services.job_service import JobService
    svc = JobService()
    job = svc.create_batch_job(input_dir, output_dir, mode, intensity, lang)
    result = svc.run_batch_job(job["job_id"])
    return HTMLResponse(_render(result))
