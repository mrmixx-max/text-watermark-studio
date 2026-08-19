# Text Watermark Studio — API Reference

Generated from the route modules under
`src/ai_watermark_toolkit/api/routes/` (22 routers) and the FastAPI
application defined in `src/ai_watermark_toolkit/api/fastapi_app.py`.

> All request/response schemas below are read directly from the Pydantic
> models declared in the route modules and the inline response dicts in the
> handlers. FastAPI auto-generates the canonical OpenAPI document from this
> same source — see **OpenAPI / interactive docs** below.

---

## 1. Service overview

| Field | Value |
|---|---|
| Service name | Text Watermark Studio v8 |
| API version | `2.3.0` |
| Summary | Watermarking lab with taxonomy-driven family plugins, demo embed/detect routines, and a lab UI. |
| Default host / port | `127.0.0.1:8080` (dev) |
| Base path | `/api/...` (system probes at `/health`, `/ready`, `/`) |

The service exposes one **monolithic FastAPI application**. All 22 routers are
included in `fastapi_app.py` via `app.include_router(...)`. Routes are mounted
under the `/api` namespace, grouped by functional tag.

---

## 2. Authentication & authorization

Authentication is **header-based API key**, implemented once in
`src/ai_watermark_toolkit/api/middleware/auth.py` as the reusable dependency
`require_api_key`.

```
X-API-Key: <AI_WM_API_KEY value>
```

Policy (fail-closed by design — see *P0-1* in `fastapi_app.py`):

- **Key configured** (`AI_WM_API_KEY` set): every protected endpoint requires
  the `X-API-Key` header to match exactly (`hmac.compare_digest`,
  timing-safe). Mismatch → `401 invalid_api_key`.
- **Key NOT configured & non-development env**: the API is **fail-closed** —
  every protected endpoint rejects with `401 api_key_not_configured`.
- **Key NOT configured & `AI_WM_ENV == development`**: open access (local
  studio convenience; dev server binds `127.0.0.1` only).

### Which endpoints require the API key

`require_api_key` is applied as a route dependency. The remaining endpoints
are **public by default** (no per-route auth).

| Tag | Protected endpoints | Public endpoints |
|---|---|---|
| **forensics** | all (`GET /keys`, `POST /keys`, `/detect`, `/embed`, `/report-sign`, `/report-verify`, `/delta-z`, `/finding`) | — |
| **metadata** | `/embed`, `/detect` | `/formats`, `/inspect`, `/clean`, `/synthid-score` |
| text, jobs, studio, queue, streams, ops, community, graph, multi-agent, llm, cloud, export, lab, documents, rag, prompts, routing, pdf, optimization, rewrite | — | all endpoints in these tags |

> **Security rationale (P0-1).** The forensic write endpoints (`/embed`,
> `/report-sign`, `/finding`) and key management (`/keys`) mutate or expose
> keying material. Leaving them open on a non-dev deployment would expose an
> open forensic/markup API. Fail-closed means a misconfigured instance
> refuses all protected traffic with a clean `401` instead of silently
> succeeding.

---

## 3. Global middleware & limits

| Layer | Setting | Behavior |
|---|---|---|
| **Rate limiting** | `RateLimitMiddleware` — `60 req / 60s` per `client:host + path` (env: `AI_WM_RATE_LIMIT_REQUESTS` / `AI_WM_RATE_LIMIT_WINDOW_SEC`) | Exceeded → `429 rate_limit_exceeded` + `Retry-After`. Response headers `X-RateLimit-Limit`, `X-RateLimit-Remaining`. Exempt: `/health`, `/ready`, `/docs`, `/openapi.json`, `/static/*`. |
| **CORS** | `CORSMiddleware` — `AI_WM_CORS_ORIGINS` (default `*` only in dev; empty elsewhere; `allow_credentials=False`) | Non-dev `*` would leak the forensic API to any origin — disallowed. |
| **Request ID** | `RequestIDMiddleware` | Injects/correlated request ids in logs. |
| **Prometheus** | `PrometheusMiddleware` | Observability metrics. See `GET /api/ops/metrics`. |
| **OpenAPI / docs** | FastAPI built-in | `GET /openapi.json` (schema), `GET /docs` (Swagger UI), `GET /redoc`. |

### Response conventions

- **Error envelope** — FastAPI `HTTPException` →
  `{"detail": "<error message>"}` with the matching status code.
- **htmx awareness** — routes using the shared `respond(request, payload)`
  helper return an `HTMLResponse` (rendered `<pre>` payload) when the request
  carries `HX-Request: true`; otherwise a `JSONResponse`. Affected tags:
  `llm`, `routing`, `community`, `export`, `queue`, `streams`, `rewrite`.
- **Redis-dependent routes** — `queue`, `streams`, `ops` resolve Redis via
  `get_redis(request)` and return a clean `503 Redis backend unavailable` when
  `app.state.redis` is `None` (i.e. no Redis at startup / connection refused).

---

## 4. System endpoints

| Method | Path | Auth | Summary |
|---|---|---|---|
| `GET` | `/health` | public | Liveness / basic service info. Exempt from rate limit. |
| `GET` | `/ready` | public | Readiness probe — pings Redis (`app.state.redis`); `503` if unavailable. |
| `GET` | `/` | public | Serves `web/index.html` (excluded from OpenAPI schema). |

**`GET /health` response schema**
```jsonc
{
  "ok": true,            // bool
  "env": "development",  // AI_WM_ENV
  "redis": "redis://localhost:6379/0",  // AI_WM_REDIS_URL
  "version": "0.8.0",
  "mode": "watermark_lab"
}
```

---

## 5. Endpoint index

Legend: 🔒 = API key required. `*` = request body is a file upload
(`multipart/form-data`).

| Tag | Method | Path | Summary | Auth |
|---|---|---|---|---|
| text | `POST` | `/api/detect` | Detect & clean, dilute, pipeline text watermarks | — |
| text | `POST` | `/api/clean` | Strip NFKC + confusable watermarks | — |
| text | `POST` | `/api/dilute` | Dilute watermark via structural rewrite | — |
| text | `POST` | `/api/pipeline` | Full detect→clean→dilute pipeline | — |
| jobs | `POST` | `/api/jobs` | Create + run a batch job | — |
| jobs | `GET` | `/api/jobs/{job_id}` | Fetch batch job status/result | — |
| studio | `POST` | `/api/studio/diff` | Create a simple line diff | — |
| studio | `POST` | `/api/studio/export/zip` | Export pipeline output as ZIP | — |
| queue | `POST` | `/api/queue/enqueue` | Enqueue a Redis queue job | — |
| queue | `GET` | `/api/queue/{job_id}` | Fetch queued job status | — |
| queue | `GET` | `/api/queue/depth` | Queue depth + backpressure flag | — |
| streams | `POST` | `/api/streams/enqueue` | Enqueue a Redis Streams job | — |
| streams | `GET` | `/api/streams/{job_id}` | Streams job status | — |
| streams | `GET` | `/api/streams/metrics` | Stream metrics (XINFO + dead-letter) | — |
| ops | `GET` | `/api/ops/metrics` | Prometheus metrics endpoint | — |
| ops | `GET` | `/api/ops/status` | JSON operations status | — |
| ops | `POST` | `/api/ops/dlq/replay/{job_id}` | Replay a DLQ job into the main stream | — |
| forensics | `GET` | `/api/forensics/keys` | List registered forensic keys | 🔒 |
| forensics | `POST` | `/api/forensics/keys` | Register a forensic key | 🔒 |
| forensics | `POST` | `/api/forensics/detect` | Run ensemble multi-key detection | 🔒 |
| forensics | `POST` | `/api/forensics/embed` | Embed a KGW watermark with a registered key | 🔒 |
| forensics | `POST` | `/api/forensics/report-sign` | Sign a findings payload (secret server-side) | 🔒 |
| forensics | `POST` | `/api/forensics/report-verify` | Verify a signed findings document | 🔒 |
| forensics | `POST` | `/api/forensics/delta-z` | ΔZ watermark-strength check (before/after or transform) | 🔒 |
| forensics | `POST` | `/api/forensics/finding` | KI-Erklärungs-Befund (evidence classes A–D) | 🔒 |
| community | `POST` | `/api/community/detect` | Detect small-community watermark (min_size) | — |
| community | `POST` | `/api/community/summarize` | Summarize community watermarking | — |
| community | `GET` | `/api/community/list` | List communities | — |
| community | `GET` | `/api/community/get?community_id=` | Get a community by id | — |
| graph | `GET` | `/api/graph/schema` | Graph schema | — |
| graph | `GET` | `/api/graph/all` | Full graph | — |
| graph | `POST` | `/api/graph/node` | Add a node | — |
| graph | `POST` | `/api/graph/edge` | Add an edge | — |
| graph | `POST` | `/api/graph/fact` | Ingest a fact (subject→relation→object) | — |
| graph | `GET` | `/api/graph/query?label=` | Query nodes by label | — |
| graph | `GET` | `/api/graph/neighbors?node_id=` | Neighbors of a node | — |
| graph | `GET` | `/api/graph/subgraph?seed=&depth=` | Subgraph around a seed | — |
| multi-agent | `GET` | `/api/multi-agent/spec` | Multi-agent loop spec (demo) | — |
| multi-agent | `POST` | `/api/multi-agent/run` | Run the multi-agent feedback loop | — |
| multi-agent | `POST` | `/api/multi-agent/promote` | Promote a draft (demo) | — |
| llm | `GET` | `/api/llm/status` | Local LLM backend status *(hx-aware)* | — |
| llm | `POST` | `/api/llm/configure` | Configure local LLM backend *(hx-aware)* | — |
| cloud | `POST` | `/api/cloud/request-upload` | Request a presigned upload URL | — |
| cloud | `POST` | `/api/cloud/confirm-upload` | Confirm a completed upload | — |
| cloud | `GET` | `/api/cloud/uploads` | List uploads | — |
| export | `POST` | `/api/export/run` | Export normalized text to a target format *(hx-aware)* | — |
| metadata | `GET` | `/api/metadata/formats` | List supported file formats for cleaning | — |
| metadata | `POST` | `/api/metadata/inspect` | Inspect file for AI provenance metadata | — |
| metadata | `POST` | `/api/metadata/clean` | Strip AI provenance metadata | — |
| metadata | `POST` | `/api/metadata/embed` | Embed signed provenance mark (HMAC) | 🔒 |
| metadata | `POST` | `/api/metadata/detect` | Detect & verify studio provenance marks | 🔒 |
| metadata | `POST` | `/api/metadata/synthid-score` | Score an image for SynthID pixel marks | — |
| lab | `GET` | `/api/lab/families` | List watermarking families + capabilities | — |
| lab | `POST` | `/api/lab/detect-all` | Run demo detectors across all families | — |
| lab | `POST` | `/api/lab/embed` | Run demo embed for one family | — |
| lab | `POST` | `/api/lab/demo` | Run generation-time sampling-bias proof | — |
| lab | `GET` | `/api/lab/mcp/tools` | Export the MCP tool manifest | — |
| documents | `GET` | `/api/documents/formats` | List supported document formats | — |
| documents | `POST` | `/api/documents/load` | Normalize a document payload to lab text | — |
| documents | `POST` | `/api/documents/export` | Export normalized text to a document format | — |
| rag | `GET` | `/api/rag/strategies` | List chunking strategies + defaults | — |
| rag | `POST` | `/api/rag/chunk` | Chunk text for RAG ingestion | — |
| prompts | `GET` | `/api/prompts/templates` | List prompt templates + versions | — |
| prompts | `POST` | `/api/prompts/render` | Render a template with variables | — |
| prompts | `POST` | `/api/prompts/create-version` | Create a new prompt template version | — |
| routing | `GET` | `/api/routing/status` *(hx-aware)* | Model-routing status | — |
| routing | `POST` | `/api/routing/decide` *(hx-aware)* | Decide routing target for a task | — |
| routing | `POST` | `/api/routing/configure` *(hx-aware)* | Configure a routing profile | — |
| pdf | `GET` | `/api/pdf/strategy` | PDF processing strategy info | — |
| pdf | `POST` | `/api/pdf/extract` | Extract text summary from PDF text layer | — |
| pdf | `POST` | `/api/pdf/extract-window` | Extract a page window (file upload) | — |
| optimization | `GET` | `/api/optimization/evals` | List the locked evaluation set | — |
| optimization | `POST` | `/api/optimization/candidates` | Generate base + one-variable candidates | — |
| optimization | `POST` | `/api/optimization/optimize` | Run the evaluator loop (no promotion) | — |
| optimization | `POST` | `/api/optimization/promote` | Promote winner into the prompt registry | — |
| optimization | `GET` | `/api/optimization/history/{template_id}` | All versions of a template | — |
| optimization | `POST` | `/api/optimization/rollback` | Restore a previous version as new stable | — |
| rewrite | `POST` | `/api/rewrite/run` | Rewrite text *(hx-aware)* | — |

---

## 6. Request schemas

### 6.1 `TextRequest` (text routes)
| Field | Type | Default | Notes |
|---|---|---|---|
| `text` | `str` | — | **required** |
| `lang` | `str` | `"auto"` | |
| `intensity` | `str` | `"standard"` | |
| `nfkc` | `bool` | `false` | NFKC normalization |
| `fold_confusables` | `bool` | `false` | Confusable character folding |
| `rewrite_mode` | `str \| null` | `null` | |
| `aggressive` | `bool` | `false` | |

### 6.2 `BatchJobRequest` (jobs)
| Field | Type | Default | Notes |
|---|---|---|---|
| `input_dir` | `str` | — | **required** |
| `output_dir` | `str` | — | **required** |
| `mode` | `str` | `"pipeline"` | |
| `intensity` | `str` | `"standard"` | |
| `lang` | `str` | `"auto"` | |

### 6.3 `QueuePayload` (queue) / `StreamJobRequest` (streams)
| Field | Type | Default | Notes |
|---|---|---|---|
| `text` | `str` | — | **required** |
| `lang` | `str` | `"auto"` | |
| `intensity` | `str` | `"standard"` | |
| `nfkc` | `bool` | `false` | |
| `fold_confusables` | `bool` | `false` | |

### 6.4 forensics request models

#### `KeyCreateRequest`
| Field | Type | Default | Notes |
|---|---|---|---|
| `key_id` | `str` | — | **required** |
| `family` | `str` | `"unknown"` | |
| `status` | `str` | `"active"` | |
| `owner` | `str` | `"local"` | |
| `trigger_phrase` | `str` | `""` | |
| `notes` | `str` | `""` | |
| `secret` | `str \| null` | `null` | |
| `gamma` | `float \| null` | `null` | |

#### `DetectRequest`
| Field | Type | Default | Notes |
|---|---|---|---|
| `text` | `str` | — | **required** |
| `operator` | `str` | `"local-user"` | |
| `window` | `int` | `400` | Token window |
| `level` | `str` | `"word"` | Detection granularity |
| `context` | `int` | `1` | KGW greenlist window `c` |
| `e_value` | `bool` | `false` | Opt-in anytime-valid e-process |
| `signature_filter` | `bool` | `false` | Opt-in signature pre-filter |

#### `EmbedRequest`
| Field | Type | Default | Notes |
|---|---|---|---|
| `text` | `str` | — | **required** |
| `key_id` | `str` | — | **required** — must be a registered key |
| `level` | `str` | `"word"` | |
| `context` | `int` | `1` | |
| `seed` | `int \| null` | `null` | Deterministic seeding |
| `gamma` | `float \| null` | `null` | Falls back to registry `gamma` or `0.25` |

#### `ReportSignRequest`
| Field | Type | Default | Notes |
|---|---|---|---|
| `payload` | `dict` | — | **required** — the findings payload |
| `key_id` | `str` | — | **required** — registered key; secret resolved server-side |
| `algorithm` | `str` | `"hmac-sha256"` | ML-DSA handled only via the CLI |

#### `ReportVerifyRequest`
| Field | Type | Default | Notes |
|---|---|---|---|
| `signed` | `dict` | — | **required** — the signed document |
| `key_id` | `str \| null` | `null` | Optional; falls back to the document's signature block |

#### `DeltaZRequest`
| Field | Type | Default | Notes |
|---|---|---|---|
| `text_before` | `str \| null` | `null` | Two-text mode |
| `text_after` | `str \| null` | `null` | Two-text mode |
| `text` | `str \| null` | `null` | Transform mode |
| `key_id` | `str` | — | **required** — registered key |
| `level` | `str` | `"word"` | |
| `context` | `int` | `1` | |
| `transform` | `str \| null` | `null` | `clean\|truncate\|shuffle\|reformat\|rewrite` |
| `truncate_fraction` | `float` | `0.6` | |
| `seed` | `int` | `42` | |
| `rewrite_mode` | `str` | `"structural"` | For `transform: rewrite` |
| `use_llm` | `bool` | `false` | |
| `sign` | `bool` | `false` | Attach signed_report HMAC block |

#### `FindingDeltaZOption` (nested in `FindingRequest`)
| Field | Type | Default | Notes |
|---|---|---|---|
| `text_after` | `str \| null` | `null` | Two-text mode |
| `transform` | `str \| null` | `null` | Transform mode |
| `text` | `str \| null` | `null` | |
| `truncate_fraction` | `float` | `0.6` | |
| `seed` | `int` | `42` | |

#### `FindingRequest`
| Field | Type | Default | Notes |
|---|---|---|---|
| `text` | `str` | — | **required** — top-level text (also ΔZ transform source) |
| `key_id` | `str` | — | **required** — registered key |
| `level` | `str` | `"word"` | |
| `context` | `int \| dict \| null` | `1` | `int` = KGW window `c`; `dict` = evidence-class-D context |
| `e_value` | `bool` | `false` | |
| `delta_z` | `FindingDeltaZOption \| null` | `null` | Optional ΔZ module |
| `sign` | `bool` | `false` | HMAC-sign the report |
| `frs` | `bool` | `false` | Attach forensic readiness self-assessment |
| `lang` | `str` | `"de"` | `de` / `en` report localization |

### 6.5 other request models

#### `DiffRequest` (studio) / `NodeRequest` (graph) / `EdgeRequest` (graph)
| Field | Type | Default | Notes |
|---|---|---|---|
| `original` / `node` / `edge` | `str` / `dict` | — | **required** |
| `modified` | `str` | — | **DiffRequest** only |

#### `FactRequest` (graph)
| Field | Type | Default | Notes |
|---|---|---|---|
| `subject` | `str` | — | **required** |
| `relation` | `str` | — | **required** |
| `object_` | `str` | — | **required** |
| `subject_type` | `str` | `"Entity"` | |
| `object_type` | `str` | `"Entity"` | |
| `evidence` | `list \| null` | `null` | |

#### `RunRequest` (multi-agent) / `LabTextRequest` (lab)
Both: `text: str` (**required**). `LabTextRequest` adds `family: str \| null`, `options: dict \| null`.

#### `ConfigureRequest` (llm)
| Field | Type | Default | Notes |
|---|---|---|---|
| `server_base_url` | `str \| null` | `null` | |
| `model_variant` | `str \| null` | `null` | |
| `installed` | `bool \| null` | `null` | Normalized via `checkbox_to_bool` |

#### `UploadRequest` / `ConfirmRequest` (cloud)
**UploadRequest**: `filename:str`, `content_type:str`, `size_bytes:int`, `provider="s3"`, `purpose="general"` — all except last two **required**.
**ConfirmRequest**: `upload_id:str` **required**, `etag:str \| null=null**.

#### `ExportRequest` (export)
| Field | Type | Default | Notes |
|---|---|---|---|
| `title` | `str` | `"Export"` | |
| `text` | `str` | — | **required** |
| `format` | `str` | `"md"` | |
| `style` | `str` | `"clean"` | |
| `metadata` | `dict[str,Any]` | `{}` | Normalized via `parse_metadata_field` |

#### `LabDemoRequest` (lab)
| Field | Type | Default | Notes |
|---|---|---|---|
| `family` | `str` | — | **required** |
| `secret` | `str \| null` | `null` | |
| `gamma` | `float \| null` | `null` | |
| `bias_strength` | `float \| null` | `null` | |
| `context` | `int \| null` | `null` | |
| `n_tokens` | `int \| null` | `null` | |
| `seed` | `int \| null` | `null` | |
| `prefix` | `str \| null` | `null` | |

#### `DocumentLoadRequest` / `DocumentExportRequest` (documents)
Load: `filename:str`, `content:str` — both **required**.
Export: `text:str` **required**, `target_format:str` **required**.

#### `ChunkRequest` (rag)
| Field | Type | Default | Notes |
|---|---|---|---|
| `text` | `str` | — | **required** |
| `strategy` | `str` | `"recursive"` | `fixed\|recursive\|markdown\|page\|semantic_lite` |
| `chunk_size` | `int` | `512` | |
| `overlap` | `int` | `64` | |

#### `RenderRequest` / `CreateTemplateRequest` (prompts)
Render: `template_id:str` **required**, `version:str\|null=null`, `variables:dict` **required**.
Create: `payload:dict` **required**.

#### `DecideRequest` / `ConfigureRequest` (routing)
Decide: `task="general"`, `profile="default"`, `need_large_context:bool=false` (normalized via `checkbox_to_bool`), `privacy_mode:bool=false` (normalized via `checkbox_to_bool`).
Configure: `profile="default"`, `config:dict[str,Any]={}`.

#### `ExtractWindow` fields (pdf)
`file: UploadFile` (**required**), `start_page:int=0`, `end_page:int|null=null`.

#### `OptimizeRequest` / `PromoteRequest` / `RollbackRequest` (optimization)
Optimize: `system:str` **required**.
Promote: `system:str` **required**, `template_id:str` **required**, `candidate_variant:str\|null=null`, `version:str\|null=null`.
Rollback: `template_id:str` **required**, `version:str` **required**.

#### `RewriteRequest` (rewrite)
| Field | Type | Default | Notes |
|---|---|---|---|
| `text` | `str` | — | **required** |
| `mode` | `str` | `"clarity"` | |
| `preserve` | `bool` | `true` | Normalized via `checkbox_to_bool` |
| `use_llm` | `bool \| null` | `null` | |

---

## 7. Per-route reference (selected detail)

The inline summaries/descriptions below come from `summary=` and `description=`
arguments and docstrings in the route modules.

### 7.1 `GET /api/metadata/synthid-score`
POST `/api/metadata/synthid-score` — `summary="Score an image for SynthID pixel marks (external checkout required)"`.
Request: `file: UploadFile` (**required**), `synthid_dir: str | null = null` (query/form).
Delegates to `score_synthid(tmp_path, synthid_dir=...)`; the uploaded file is
written to a `NamedTemporaryFile` and unlinked in a `finally` block.

### 7.2 `POST /api/studio/export/zip`
`summary="Export pipeline output as ZIP"`,
`description="Runs pipeline and returns a zip containing text and report."`.
Request body: `ExportRequest` (`text:str` **required**, `lang="auto"`, `intensity="standard"`).
Response: `application/zip` `Response` with header
`Content-Disposition: attachment; filename="text-watermark-studio-export.zip"`
containing two members: `output.txt` (pipeline text) and `report.json` (pipeline report).

### 7.3 `GET /api/ops/metrics`
`summary="Prometheus metrics endpoint"`. Renders the OpenTelemetry/Prometheus
text exposition via `render_metrics()` (content type from
`...observability.metrics`). Also pushes two gauges live from the stream
(`STREAM_PENDING_GAUGE`, `STREAM_DEAD_LETTER_GAUGE`) before rendering.

### 7.4 `GET /api/ops/status`
`summary="JSON operations status"`. Response fields: `service`, `env`, `redis`,
`stream`, `dlq_stream`, `metrics` (raw `stream_info()` payload).

### 7.5 `POST /api/ops/dlq/replay/{job_id}`
`summary="Replay a DLQ job back into the main stream"`. Path param `job_id`
**required**. Re-enqueues the DLQ payload via `svc.enqueue(payload)` and
marks the original job `replayed`; increments `DLQ_REPLAYS_TOTAL`. Response:
`{"replayed_from": job_id, "new_job": <enqueued job ref>}`; `{"error":"not_found"}` when the DLQ job is absent.

### 7.6 `POST /api/forensics/delta-z`
`summary="ΔZ check: measure KGW watermark strength before vs after (removal with receipt)"`.
Two modes selected by the body:
- **two-text** — `{text_before, text_after, key_id}`: measures ΔZ between the two texts.
- **transform** — `{text, key_id, transform}`: applies `clean|truncate|shuffle|reformat|rewrite`
  server-side (`delta_z_transform`) and measures its ΔZ. `rewrite` is the
  paraphrase path (`rewrite_mode` + `use_llm` select mode/backend).
The key secret is **always** resolved server-side from `KeyRegistry`; a raw
secret in the body is never accepted (`key_id` must be registered,
`404 key_not_found` otherwise, `400 key_has_no_secret` otherwise). `sign=true`
attaches a `signed_report` HMAC block (`removed:true` is a finding, not an error — response stays `200`).

### 7.7 `POST /api/forensics/finding`
`summary="KI-Erklärungs-Befund: Evidenzklassen A-D, Prüfpriorität 0-5, ehrlicher verdict_text (C5)"`.
Server-side composition: mandatory KGW detection
(`detect_multi_key`) + optional E-Wert (`e_value=true`, `e_detect`) + optional
ΔZ (`delta_z` block: two-text `{text_after}` or transform `{transform, text}`).
Each module maps to an evidence class (A = reproducible keyed artefact, B =
comparison, C = technical indicator — never standalone proof). `priority`
(0–5) is review urgency, not blame. `context` is dual-typed (`int` = KGW
window `c`; `dict` = evidence-class-D context, which forces the KGW window to
its default of 1). ML-DSA verification/signing is **not** offered here or in
`/report-sign`/`/report-verify` — those require the CLI with a local keypair.

### 7.8 `GET /api/rag/strategies`
Static manifest of recommended defaults and supported strategy names
(`fixed`, `recursive`, `markdown`, `page`, `semantic_lite`), independent of
the chunker.

### 7.9 `GET /api/lab/mcp/tools`
Reads `<repo>/mcp/tools.json` (path resolved from `__file__` parents) and
returns it parsed. No service dependency.

### 7.10 htmx-aware routes *(hx-aware)*
`llm.status/configure`, `routing.status/decide/configure`,
`community.*`, `export.run`, `queue.*`, `streams.*`, `rewrite.run` all flow
through `respond(request, payload)`: an `HX-Request: true` header yields an
`HTMLResponse` (`<pre>` render) instead of JSON.

---

## 8. Response schemas (observed)

Where a handler builds the response inline it is documented here; service
return shapes that are not inlined in the route are marked **service-defined**.

### `POST /api/studio/diff` → `{"rows": [...]}`
```jsonc
{
  "rows": [
    { "line": 1, "original": "str", "modified": "str", "changed": true }
  ]
}
```

### `POST /api/forensics/keys` (GET list) → `{"keys": [...]}`
Array of key metadata **with the `secret` field stripped** (never returned by
the API).

### `GET /api/ops/status`
```jsonc
{
  "service": "Text Watermark Studio v8",
  "env": "development",
  "redis": "redis://localhost:6379/0",
  "stream": "tws:stream:jobs",
  "dlq_stream": "tws:stream:jobs:dlq",
  "metrics": "<service-defined stream_info() payload>"
}
```

### `POST /api/ops/dlq/replay/{job_id}`
```jsonc
{ "replayed_from": "job_id", "new_job": "<service-defined enqueue ref>" }
// or { "error": "not_found" }
```

### `GET /api/graph/schema`, `GET /api/graph/all`
**Service-defined** (`GraphMemoryService.schema()` / `.graph()`).

### `GET /api/rag/strategies`
```jsonc
{
  "default": "recursive",
  "recommended_defaults": { "recursive": {"chunk_size":512,"overlap":64}, ... },
  "strategies": ["fixed","recursive","markdown","page","semantic_lite"]
}
```

### `POST /api/rag/chunk`
```jsonc
{
  "strategy": "recursive",
  "chunk_size": 512,
  "overlap": 64,
  "chunks": ["<service-defined list with metadata>"],
  "chunk_count": 12
}
```

### `POST /api/optimization/...`
| Endpoint | Response shape |
|---|---|
| `/evals` | `{"evals": "<service-defined eval cases>"}` |
| `/candidates` | `{"candidates": "<service-defined variants>"}` |
| `/optimize` | **service-defined** |
| `/promote` | `{"promoted": "<service-defined record>"}` (or `409` on `ValueError`) |
| `/history/{template_id}` | `{"history": "<service-defined versions>"}` |
| `/rollback` | `{"restored": "<service-defined record>"}` (or `404` on `ValueError`) |

### `POST /api/prompts/render` / `/create-version`
| Endpoint | Response shape |
|---|---|
| `/render` | **service-defined** (`ValueError` → `404`) |
| `/create-version` | **service-defined** (`ValueError` → `400`) |

### `POST /api/prompts/...`
Service-defined payloads for the graph (`add_node`, `add_edge`, `fact`,
`query`, `neighbors`, `subgraph`) and lab (`detect_all.results`,
`embed_with`, `demo_with`) returns — consult the respective service class.

---

## 9. Shared helpers used by routes

| Helper | Module | Effect on API |
|---|---|---|
| `respond(request, payload)` | `api/response_utils.py` | Returns `HTMLResponse` for `HX-Request: true`, else `JSONResponse` (re-serialized with `default=str` for non-JSON-native values). |
| `get_redis(request)` | `api/response_utils.py` | Returns `app.state.redis` or raises `503 Redis backend unavailable`. Used by `queue`, `streams`, `ops`. |
| `checkbox_to_bool(value)` | `api/response_utils.py` | Coerces HTML-checkbox strings (`"true"/"1"/"yes"/"on"`) to `bool` before validation. Used by `llm`, `routing`, `rewrite`. |
| `parse_metadata_field(metadata)` | `api/response_utils.py` | `None/""/{}->{}`; dict passthrough; else `json.loads` with fallback `{"raw_metadata": str}`. Used by `export`. |
| `require_api_key` | `api/middleware/auth.py` | API-key gate (header `X-API-Key`); applied to `forensics.*` and `metadata.embed/detect`. |

---

## 10. OpenAPI / interactive docs

FastAPI auto-generates the canonical OpenAPI schema from these route modules.
No custom `openapi` override is registered in `fastapi_app.py`.

- Schema: `GET /openapi.json`
- Swagger UI: `GET /docs`
- ReDoc: `GET /redoc`

Both docs endpoints (and `/openapi.json`) are exempt from the
`RateLimitMiddleware`.

---

## 11. How this document was produced

1. Loaded the 22 routers listed in `fastapi_app.py` and the shared
   `require_api_key` dependency.
2. Extracted every `@router.*` decorator together with its
   `path`, `summary`/`description`, `tags`, and `operation_id`.
3. Read each request body Pydantic model and the inline response dicts.
4. Cross-checked the global middleware (`RateLimitMiddleware`, `CORSMiddleware`,
   `RequestIDMiddleware`, `PrometheusMiddleware`) and the `Settings` dataclass
   (`src/ai_watermark_toolkit/core/config.py`) for env-var knobs.
