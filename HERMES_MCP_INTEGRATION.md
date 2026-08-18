# Text Watermark Studio — MCP & Hermes Integration

Version 2.0.0 · 65+ MCP tools · 5 Hermes skills

The studio ships with a full MCP (Model Context Protocol) tool manifest and Hermes-compatible skill bundle, so AI agents can call the toolkit's capabilities directly.

---

## Contents

1. [MCP Tools Overview](#mcp-tools-overview)
2. [Setting up the MCP server](#setting-up-the-mcp-server)
3. [Tool catalog](#tool-catalog)
4. [Hermes skills](#hermes-skills)
5. [Vendor notes](#vendor-notes)
6. [Example agent workflows](#example-agent-workflows)

---

## MCP Tools Overview

`mcp/tools.json` defines 65+ MCP tools that map directly to the API server endpoints. Each tool has:

- `name` — the MCP tool identifier
- `method` — HTTP method (GET/POST)
- `path` — API endpoint path
- `description` — what the tool does
- `body_schema` — JSON schema for POST bodies
- `optional: true` — tools that require runtime subsystems (lab/ops)

The manifest is consumed by Hermes and any MCP-compatible client (Claude Desktop, Cursor, VS Code, etc.).

### Tool categories

| Category | Tools | Description |
|---|---|---|
| System | `health`, `ready` | Liveness/readiness probes |
| Ops | `ops_status`, `ops_metrics` | Operations status + Prometheus metrics |
| Lab | `lab_families`, `lab_detect_all`, `lab_embed`, `lab_pipeline`, `lab_demo` | Watermark family demos |
| Forensics | `forensics_keys`, `forensics_add_key`, `forensics_detect`, `forensics_embed`, `forensics_report_sign`, `forensics_report_verify`, `forensics_delta_z`, `forensics_finding` | Core forensics operations |
| Text | `text_detect`, `text_clean`, `text_dilute` | Text processing |
| Metadata | `metadata_formats`, `metadata_inspect`, `metadata_clean`, `metadata_embed`, `metadata_detect`, `metadata_synthid_score` | File provenance |
| Documents | `document_formats`, `document_load`, `document_export` | Document normalization |
| PDF | `pdf_strategy`, `pdf_extract_window` | PDF optimization |
| RAG | `rag_strategies`, `rag_chunk` | Chunking strategies |
| LLM | `llm_status`, `llm_configure` | Local model backend |
| Routing | `routing_status`, `routing_decide`, `routing_configure` | Model fallback routing |
| Prompts | `prompt_templates`, `prompt_render`, `prompt_create_version` | Template registry |
| Optimization | `opt_baseline`, `opt_candidates`, `opt_optimize`, `opt_promote`, `opt_history`, `opt_rollback` | Prompt optimization |
| Multi-agent | `ma_spec`, `ma_run`, `ma_promote` | Feedback loop |
| Graph | `graph_schema`, `graph_all`, `graph_add_node`, `graph_add_edge`, `graph_ingest_fact`, `graph_query`, `graph_neighbors`, `graph_subgraph` | Knowledge graph |
| Community | `community_detect`, `community_summarize`, `community_list`, `community_get` | Graph communities |
| Rewrite | `rewrite_run` | Auto-correction engine |
| Export | `export_run` | Multi-format export |
| Cloud | `cloud_request_upload`, `cloud_confirm_upload`, `cloud_list_uploads` | Direct upload |
| Queue | `queue_enqueue`, `queue_depth`, `queue_get_job` | Redis queue |
| Streams | `streams_enqueue`, `streams_metrics`, `streams_get_job` | Redis Streams |
| Jobs | `jobs_create`, `jobs_get` | Batch processing |
| Studio | `studio_diff`, `studio_export_zip` | Utilities |

---

## Setting up the MCP server

### Prerequisites

```bash
pip install text-watermark-studio
# or from source:
pip install -e ".[dev]"
```

### Start the API server

```bash
ai-wm serve --host 127.0.0.1 --port 8080
```

### Configure your MCP client

#### Hermes Agent

Hermes auto-discovers the `mcp/tools.json` manifest. Place the repo where Hermes can find it, or reference it in your Hermes config:

```yaml
# ~/.hermes/config.yaml
mcp:
  servers:
    tws:
      command: "ai-wm"
      args: ["serve", "--host", "127.0.0.1", "--port", "8080"]
```

Or use the Hermes skill installer:

```bash
hermes skill install hermes/skills/text-watermark-studio-lab/
```

#### Claude Desktop / Cursor / VS Code

Add to your MCP client config:

```json
{
  "mcpServers": {
    "text-watermark-studio": {
      "command": "uvicorn",
      "args": [
        "ai_watermark_toolkit.api.fastapi_app:app",
        "--host", "127.0.0.1",
        "--port", "8080"
      ]
    }
  }
}
```

### Verify

```bash
curl http://127.0.0.1:8080/health
# {"ok": true, "env": "development", ...}
```

---

## Tool catalog

### forensics_detect

Run multi-key KGW detection on text.

```json
{
  "name": "forensics_detect",
  "arguments": {
    "text": "The text to analyze...",
    "level": "bpe",
    "context": 1,
    "e_value": true,
    "signature_filter": false
  }
}
```

### forensics_embed

Embed a KGW greenlist mark.

```json
{
  "name": "forensics_embed",
  "arguments": {
    "text": "Original text...",
    "key_id": "my-key",
    "level": "word",
    "gamma": 0.25
  }
}
```

### forensics_delta_z

Measure watermark strength before/after.

```json
{
  "name": "forensics_delta_z",
  "arguments": {
    "text_before": "original watermarked text...",
    "text_after": "cleaned text...",
    "key_id": "my-key",
    "level": "word"
  }
}
```

### forensics_finding

Produce a KI-Erklärungs-Befund (C5).

```json
{
  "name": "forensics_finding",
  "arguments": {
    "text": "text to analyze...",
    "key_id": "my-key",
    "e_value": true,
    "sign": true
  }
}
```

### metadata_clean

Strip AI provenance metadata from a file (multipart upload).

### metadata_embed

Embed an HMAC provenance mark into a file.

### rag_chunk

Chunk text for RAG ingestion.

```json
{
  "name": "rag_chunk",
  "arguments": {
    "text": "Long document text...",
    "strategy": "recursive",
    "chunk_size": 512,
    "overlap": 50
  }
}
```

### llm_rewrite

Rewrite text through the local LLM backend.

```json
{
  "name": "llm_rewrite",
  "arguments": {
    "text": "Original text...",
    "mode": "structural",
    "preserve": "numbers,names,quotations"
  }
}
```

---

## Hermes skills

The repo bundles 5 Hermes skills under `hermes/skills/`:

| Skill | Path | Description |
|---|---|---|
| `text-watermark-studio-lab` | `hermes/skills/text-watermark-studio-lab/` | Lab operations, family demos, forensics |
| `text-forensics-workflow` | `hermes/skills/text-forensics-workflow/` | Full forensic case workflow |
| `dewatermarking-pipeline` | `hermes/skills/dewatermarking-pipeline/` | End-to-end removal chain |
| `ai-text-detection-lab` | `hermes/skills/ai-text-detection-lab/` | Multi-signal AI-text detection |
| `chameleon-universal-tarntarnung` | `hermes/skills/chameleon-universal-tarntarnung/` | Universal text camouflage |

### Install

```bash
# Install a single skill
hermes skill install hermes/skills/text-watermark-studio-lab/

# Install all
for skill in hermes/skills/*/; do
  hermes skill install "$skill"
done
```

Or manually copy:

```bash
# Windows
cp -r hermes/skills/text-watermark-studio-lab ~/AppData/Local/hermes/skills/

# macOS/Linux
cp -r hermes/skills/text-watermark-studio-lab ~/.hermes/skills/
```

### Skill structure

Each skill has:
- `SKILL.md` — trigger + instructions for the agent
- `references/` — vendor-specific notes (Claude, Gemini/SynthID, OpenAI)

---

## Vendor notes

The `text-watermark-studio-lab` skill includes class-level vendor notes:

| File | Vendor | Content |
|---|---|---|
| `vendor-notes-claude.md` | Anthropic | What Claude's watermarking is verifiably known to do |
| `vendor-notes-gemini-synthid.md` | Google | SynthID detection/scoring capabilities |
| `vendor-notes-openai.md` | OpenAI | OpenAI watermarking claims vs. verifiable behavior |

These notes help agents give honest, evidence-based answers about vendor watermarking — not marketing claims.

---

## Example agent workflows

### 1. Detect and report

```
Agent: "Scan this text for AI watermark signals"
→ Calls forensics_detect with the text
→ If detected, calls forensics_finding for a structured report
→ Optionally calls forensics_report_sign for an auditable document
```

### 2. Remove and verify

```
Agent: "Remove the watermark and prove it worked"
→ Calls forensics_delta_z (before measurement)
→ Calls text_clean + text_dilute + rewrite_run
→ Calls forensics_delta_z (after measurement)
→ Reports ΔZ to the user
```

### 3. Sign and verify findings

```
Agent: "Create a signed forensic document"
→ Calls forensics_finding to produce the finding
→ Calls forensics_report_sign to sign it
→ Later: calls forensics_report_verify to verify
```

### 4. Batch process a directory

```
Agent: "Process all files in ./incoming"
→ Calls jobs_create with input_dir, output_dir, mode
→ Polls jobs_get for status
→ Reports results
```

### 5. RAG chunking

```
Agent: "Chunk this document for our vector DB"
→ Calls document_load to normalize
→ Calls rag_chunk with strategy="recursive"
→ Returns chunks ready for embedding
```

---

## Conditional tools

Some tools are marked `optional: true` in the manifest. They require runtime subsystems:

- `lab_*` tools — require the lab/ops subsystem
- `ops_status`, `ops_metrics` — require the ops module

If a tool is unavailable, the API returns 503 with a clear message. Agents should handle this gracefully.

---

## Security

- The API is **fail-closed**: no `AI_WM_API_KEY` in production = 401 on every request.
- Secrets never travel in request bodies — the server resolves them from the registry.
- CORS is disabled by default in production (no open cross-origin access).
- Rate limiting is enabled (configurable via `RATE_LIMIT_REQUESTS` / `RATE_LIMIT_WINDOW_SEC`).

---

## Troubleshooting

| Issue | Fix |
|---|---|
| MCP tools not appearing | Ensure the API server is running: `curl /health` |
| 401 errors | Set `AI_WM_API_KEY` and include it in requests |
| 503 on lab tools | Lab/ops subsystem not available — check server logs |
| `available: false` on SynthID | Run `scripts/setup_synthid.sh --verify` first |
| Empty results from forensics_detect | Register a KGW key with a secret first |

---

## See also

- [API Reference](docs/API.md) — full REST endpoint documentation
- [User Guide](docs/USER-GUIDE.md) — CLI and concepts
- [MCP Tool Manifest](../../mcp/tools.json) — raw tool definitions
- [Hermes Agent Docs](https://hermes-agent.nousresearch.com/docs)
