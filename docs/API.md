# Text Watermark Studio — API Reference

Version 2.0.0 · FastAPI · 100% local, zero telemetry

The API server exposes the full toolkit as REST endpoints. Start it with:

```bash
ai-wm serve --host 127.0.0.1 --port 8080
# or
uvicorn ai_watermark_toolkit.api.fastapi_app:app --host 127.0.0.1 --port 8080
```

## Interactive documentation

FastAPI ships with two interactive API explorers:

| URL | Description |
|---|---|
| `http://127.0.0.1:8080/docs` | Swagger UI — try endpoints inline |
| `http://127.0.0.1:8080/redoc` | ReDoc — clean reference layout |
| `http://127.0.0.1:8080/openapi.json` | Raw OpenAPI 3.0 schema (for codegen) |

## Authentication

The API is **fail-closed**: when `AI_WM_ENV != development` and no `AI_WM_API_KEY` is set, every request returns 401 until the key is configured.

```bash
export AI_WM_API_KEY=your-secret-key
export AI_WM_ENV=production
ai-wm serve
```

Requests must include the key:

```bash
curl -H "Authorization: Bearer your-secret-key" http://127.0.0.1:8080/api/forensics/detect \
  -H "Content-Type: application/json" \
  -d '{"text": "sample text", "operator": "api"}'
```

## Probes

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness probe — returns `{ok, env, redis, version}` |
| GET | `/ready` | Readiness probe — 503 if Redis unavailable |
| GET | `/metrics` | Prometheus scrape target |

```bash
curl http://127.0.0.1:8080/health | python -m json.tool
# {"ok": true, "env": "production", "redis": true, "version": "2.4.1"}
```

## Text processing

### Detect

```
POST /api/detect
Body: {text: string, lang?: "auto"|"de"|"en"}
```

Returns unicode/stego findings + AI phrasing marker scores.

```bash
curl -s http://127.0.0.1:8080/api/detect \
  -H "Content-Type: application/json" \
  -d '{"text": "Sample text...", "lang": "auto"}' | python -m json.tool
```

### Clean

```
POST /api/clean
Body: {text: string, nfkc?: boolean, fold_confusables?: boolean}
```

Strips the invisible-character layer.

### Dilute

```
POST /api/dilute
Body: {text: string, intensity: "light"|"standard"|"aggressive"}
```

Rewrites marker-heavy phrasing.

### Pipeline

```
POST /api/pipeline
Body: {text: string, lang?, intensity?, rewrite_mode?, nfkc?, fold_confusables?}
```

Full chain: detect → clean → dilute → rewrite → detect.

### Rewrite

```
POST /api/rewrite/run
Body: {text: string, mode: "clarity"|"concise"|"plain"|"formal"|"structural"|"backtranslate", preserve?: string}
```

Auto-correction and rewrite engine.

## Forensics

### Multi-key detection

```
POST /api/forensics/detect
Body: {
  text: string,
  operator?: string,
  window?: integer,
  level?: "word"|"bpe",
  context?: integer,
  e_value?: boolean,
  signature_filter?: boolean
}
```

Runs KGW detection against all registered keys with Bonferroni correction. `e_value` adds anytime-valid e-process detection. `signature_filter` enables FPR control for repetitive-token texts.

### Embed

```
POST /api/forensics/embed
Body: {text: string, key_id: string, level?, context?, seed?, gamma?}
```

Greenlist-embeds text using a registered key.

### Keys

```
GET  /api/forensics/keys          — list registered keys (secrets stripped)
POST /api/forensics/keys          — register a key {key_id, family, secret?, gamma?, ...}
```

### Delta-Z

```
POST /api/forensics/delta-z
Body: {
  text_before?: string|null,
  text_after?: string|null,
  text?: string|null,
  key_id: string,
  level?: string,
  context?: integer,
  transform?: "clean"|"truncate"|"shuffle"|"reformat"|null,
  truncate_fraction?: number,
  seed?: integer,
  sign?: boolean
}
```

Measures KGW watermark strength before/after. Two modes: two-text comparison (`text_before` + `text_after`) or single-text transform (`text` + `transform`). With `sign=true`, the result is HMAC-signed.

### Finding (KI-Erklärungs-Befund C5)

```
POST /api/forensics/finding
Body: {
  text: string,
  key_id: string,
  level?: string,
  context?: integer|object|null,
  e_value?: boolean,
  delta_z?: object|null,
  sign?: boolean,
  frs?: boolean
}
```

Produces a structured forensic finding with evidence classes A-D, priority 0-5, and optional signing.

### Report signing

```
POST /api/forensics/report-sign
Body: {payload: object, key_id: string, algorithm?: "hmac-sha256"|"mldsa-44"|"mldsa-65"|"mldsa-87"}

POST /api/forensics/report-verify
Body: {signed: object, key_id?: string}
```

Sign and verify forensic findings. Default: HMAC-SHA256. Optional ML-DSA (FIPS 204, quantum-safe).

## Metadata (file provenance)

| Method | Path | Description |
|---|---|---|
| GET | `/api/metadata/formats` | List supported file formats |
| POST | `/api/metadata/inspect` | Inspect file for C2PA/EXIF/XMP (multipart upload) |
| POST | `/api/metadata/clean` | Strip AI provenance metadata (multipart upload) |
| POST | `/api/metadata/embed` | Embed HMAC provenance mark (multipart + key_id) |
| POST | `/api/metadata/detect` | Detect/verify studio provenance marks |
| POST | `/api/metadata/synthid-score` | Score image for SynthID pixel marks |

## Documents

| Method | Path | Description |
|---|---|---|
| GET | `/api/documents/formats` | List supported input/output formats |
| POST | `/api/documents/load` | Normalize document to lab text |
| POST | `/api/documents/export` | Export text to target format |

## PDF

| Method | Path | Description |
|---|---|---|
| GET | `/api/pdf/strategy` | Large-PDF optimization strategy |
| POST | `/api/pdf/extract-window` | Extract page window from PDF |

## RAG chunking

| Method | Path | Description |
|---|---|---|
| GET | `/api/rag/strategies` | List chunking strategies |
| POST | `/api/rag/chunk` | Chunk text for RAG ingestion |

## LLM

| Method | Path | Description |
|---|---|---|
| GET | `/api/llm/status` | Local LLM backend status |
| POST | `/api/llm/configure` | Configure local endpoint |

## Routing

| Method | Path | Description |
|---|---|---|
| GET | `/api/routing/status` | Model routing profiles + last decision |
| POST | `/api/routing/decide` | Compute a model route with fallbacks |
| POST | `/api/routing/configure` | Configure a routing profile |

## Prompts

| Method | Path | Description |
|---|---|---|
| GET | `/api/prompts/templates` | List versioned prompt templates |
| POST | `/api/prompts/render` | Render a template with variables |
| POST | `/api/prompts/create-version` | Create a new template version |

## Optimization

| Method | Path | Description |
|---|---|---|
| GET | `/api/optimization/evals` | Show baseline metadata |
| POST | `/api/optimization/candidates` | Generate optimizer candidates |
| POST | `/api/optimization/optimize` | Run optimization, return winner |
| POST | `/api/optimization/promote` | Promote winner to registry |
| GET | `/api/optimization/history/{template_id}` | List all versions |
| POST | `/api/optimization/rollback` | Restore a previous version |

## Multi-agent

| Method | Path | Description |
|---|---|---|
| GET | `/api/multi-agent/spec` | Feedback loop specification |
| POST | `/api/multi-agent/run` | Run the feedback loop |
| POST | `/api/multi-agent/promote` | Promote an approved result |

## Graph

| Method | Path | Description |
|---|---|---|
| GET | `/api/graph/schema` | Graph ontology |
| GET | `/api/graph/all` | Full graph snapshot |
| POST | `/api/graph/node` | Add/upsert a node |
| POST | `/api/graph/edge` | Add an edge |
| POST | `/api/graph/fact` | Ingest a fact as nodes + edge |
| GET | `/api/graph/query` | Query nodes by label |
| GET | `/api/graph/neighbors` | Fetch adjacent nodes |
| GET | `/api/graph/subgraph` | Fetch depth-limited subgraph |

## Community

| Method | Path | Description |
|---|---|---|
| POST | `/api/community/detect` | Detect graph communities |
| POST | `/api/community/summarize` | Generate community summaries |
| GET | `/api/community/list` | List all communities |
| GET | `/api/community/get` | Get a single community |

## Export

```
POST /api/export/run
Body: {title: string, text: string, format: string, style?: string, metadata?: object}
```

Export content in Markdown, HTML, JSON, CSV, or TXT.

## Cloud upload

| Method | Path | Description |
|---|---|---|
| POST | `/api/cloud/request-upload` | Request a direct upload URL |
| POST | `/api/cloud/confirm-upload` | Confirm a completed upload |
| GET | `/api/cloud/uploads` | List uploads |

## Queue & Streams (Redis)

| Method | Path | Description |
|---|---|---|
| POST | `/api/queue/enqueue` | Enqueue a text job |
| GET | `/api/queue/depth` | Queue depth + backpressure |
| GET | `/api/queue/{job_id}` | Get job status |
| POST | `/api/streams/enqueue` | Enqueue Redis Streams job |
| GET | `/api/streams/metrics` | Stream metrics |
| GET | `/api/streams/{job_id}` | Streams job status |

## Batch jobs

```
POST /api/jobs
Body: {input_dir: string, output_dir: string, mode: string, intensity?: string, lang?: string}

GET /api/jobs/{job_id}
```

## Studio

| Method | Path | Description |
|---|---|---|
| POST | `/api/studio/diff` | Line diff between original and modified |
| POST | `/api/studio/export/zip` | Export pipeline output as ZIP |

## Ops

| Method | Path | Description |
|---|---|---|
| GET | `/api/ops/status` | Operations status |
| GET | `/api/ops/metrics` | Prometheus metrics |
| POST | `/api/ops/dlq/replay/{job_id}` | Replay dead-letter-queue job |

## Lab

| Method | Path | Description |
|---|---|---|
| GET | `/api/lab/families` | List watermark families + capabilities |
| POST | `/api/lab/detect-all` | Run detection across all families |
| POST | `/api/lab/embed` | Run embed for one family |
| POST | `/api/lab/demo` | Run generation-time sampling-bias proof |

## Error responses

All endpoints return structured errors:

```json
{"detail": "error message"}
```

Status codes: `200` success, `400` bad request, `401` unauthorized, `404` not found, `422` validation error, `503` service unavailable (Redis down).

## Python client

```python
import httpx

client = httpx.Client(
    base_url="http://127.0.0.1:8080",
    headers={"Authorization": "Bearer your-key"},
)

# Detect
r = client.post("/api/forensics/detect", json={
    "text": "sample text",
    "level": "bpe",
    "e_value": True,
})
print(r.json())
```

## MCP integration

For agent/MCP usage, see [HERMES_MCP_INTEGRATION.md](../../HERMES_MCP_INTEGRATION.md). The `mcp/tools.json` manifest maps every endpoint to an MCP tool name with parameter schemas.
