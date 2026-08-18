# Hermes MCP Integration

Text Watermark Studio bundles an MCP (Model Context Protocol) tool manifest
and Hermes-compatible skill bundles for agent-driven forensics workflows.

## MCP tool manifest

The manifest lives at `mcp/tools.json`. It maps every API endpoint to an MCP
tool name with parameter schemas. Tools are 1:1 with the FastAPI routes
documented in [docs/API.md](docs/API.md).

Categories:

| Category | Tools |
|---|---|
| Health & Ops | health, readiness, ops_status, ops_metrics, dlq_replay |
| Text Processing | detect, clean, dilute, pipeline, rewrite |
| Forensics | forensics_detect, forensics_embed, forensics_delta_z, forensics_finding, forensics_report_sign, forensics_report_verify |
| Documents & PDF | documents_load, documents_export, pdf_extract_window |
| RAG & LLM | rag_chunk, llm_status, llm_configure, routing_status, routing_decide |
| Prompts & Optimization | prompts_templates, prompts_render, prompts_create_version, optimization_optimize, optimization_promote |
| Graph & Community | graph_node, graph_edge, graph_fact, graph_query, graph_neighbors, graph_subgraph, community_detect, community_summarize |
| Export & Cloud | export_run, cloud_request_upload, cloud_confirm_upload |
| Lab | lab_families, lab_detect_all, lab_embed, lab_demo |

## Hermes skills

Hermes skill bundles live under `hermes/skills/`:

- `text-watermark-studio-lab/` — Main lab skill with vendor notes for Claude, Gemini/SynthID, and OpenAI
- `ai-text-detection-lab/` — AI text detection workflows
- `dewatermarking-pipeline/` — End-to-end watermark removal with measurement
- `text-forensics-workflow/` — Forensic analysis workflow
- `chameleon-universal-tarntarnung/` — Detection evasion techniques (research)

Each skill directory contains a `SKILL.md` file with triggers, steps, and
honest capability boundaries.

## Usage with Hermes Agent

The MCP tools are auto-discovered when the `mcp/tools.json` manifest is
loaded. Hermes Agent exposes them as native tool calls — `tws_detect`,
`tws_embed`, `twm_finding`, etc. — that route through the local FastAPI
server (`ai-wm serve`).

## Version

Manifest version: **2.4.1** — matches the studio package version.
