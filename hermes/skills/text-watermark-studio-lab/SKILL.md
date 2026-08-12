---
name: text-watermark-studio-lab
version: 1.0.2
description: Hermes-compatible skill bundle for the Text Watermark Studio Lab, including API-guided MCP tools.
---

# Text Watermark Studio Lab

Use this skill to operate the lab, detect across families, inspect the key registry, and run the API-backed MCP tools.

## Primary capabilities
- Run pipeline actions.
- Inspect forensics families and key registry.
- Execute multi-key detection.
- Query operations status and metrics.
- Enqueue or inspect stream jobs.

## MCP tools
The following tools are available via the companion MCP manifest:
- health
- ready
- ops_status
- ops_metrics
- lab_families
- lab_detect_all
- lab_embed
- forensics_keys
- forensics_add_key
- forensics_detect
- lab_pipeline
- streams_enqueue
- streams_metrics

## Notes
- Treat sampling/logit-bias and training-time families as capability reports unless the backend has the required model or decoder access.
- Use the lab to inspect family behavior, not to claim universal proof.


## Document formats
- Import/normalize: docx, md, txt, rtf, odt, pdf, epub.
- Export: txt, md, rtf, docx, odt, pdf, epub.
- Use MCP tools `document_formats`, `document_load`, and `document_export` for agent-driven conversion flows.


## Large PDF optimization
- Use `pdf_strategy` for planning large-file handling.
- Use `pdf_extract_window` for page-window extraction instead of full-document scans.
- Prefer PyMuPDF-first extraction, with pypdf as fallback.


## RAG chunking
- Use `rag_strategies` to inspect defaults.
- Use `rag_chunk` for fixed, recursive, markdown, page and semantic-lite chunking.
- Recommended baseline: recursive 512-token chunks with light overlap.


## LLM rewriting
- Use `llm_providers` to inspect available backends.
- Use `llm_rewrite` for provider-routed text rewriting.
- Ollama is the default local path; OpenAI and Anthropic are available through hosted APIs.


## Prompt templates
- Use `prompt_templates` to inspect the registry.
- Use `prompt_render` to render variables into a versioned asset.
- Use `prompt_create_version` to add immutable prompt variants.
- Use `llm_rewrite_from_template` to combine versioned prompts with provider-routed rewriting.


## Automatic prompt optimization
- Use `opt_baseline` to capture the current prompt state.
- Use `opt_candidates` and `opt_score` to search prompt variants.
- Use `opt_optimize` to pick the winner against the golden set.
- Use `opt_promote` to write the optimized winner back into the registry.


## Multi-agent feedback loop
- Generator creates candidate prompt variants.
- Critic flags weak constraints and brittle instructions.
- Refiner rewrites the prompt using critique.
- Judge scores the refined result and determines approval.
- Promoter writes the approved result back to the registry.


## Graph knowledge representation
- Use `graph_schema` to inspect entity and relation types.
- Use `graph_ingest_fact` to convert facts into nodes and typed edges.
- Use `graph_neighbors` and `graph_subgraph` for relational retrieval.
- Combine graph memory with prompt, optimization and agent workflows for structured context.


## Community detection and summarization
- Use `community_detect` to group graph nodes into thematic clusters.
- Use `community_summarize` to create short summaries for each cluster.
- Use `community_list` and `community_get` to inspect detected communities.
- Community summaries can be used as high-level context for global graph questions.


## Auto-correction and rewrite engine
- Use `rewrite_run` to correct grammar and rewrite text in clarity, concise, plain, or formal mode.
- Protected preservation keeps numbers, names, and quotes stable during rewriting.
- Review similarity and change-log outputs before publishing.


## Export module
- Use `export_run` to generate Markdown, HTML, JSON, CSV, or TXT exports.
- Choose among clean, report, and terminal styles for HTML-oriented exports.
- Include metadata to preserve provenance and context across downstream systems.


## Direct cloud storage upload
- Use `cloud_request_upload` to create short-lived direct-upload credentials for object storage.
- Use `cloud_confirm_upload` after the client uploads bytes to storage.
- Use `cloud_list_uploads` to inspect pending and confirmed uploads.
- Validate filename, content type, size, and tenant/purpose before signing URLs in production.


## Local EuroLLM GGUF integration
- Use `llm_status` to inspect the configured local model endpoint.
- Use `llm_configure` to point the toolkit at a local OpenAI-compatible llama.cpp server.
- Default model family: `mradermacher/EuroLLM-9B-Instruct-2512-GGUF`.
- Recommended startup: `llama-server -hf mradermacher/EuroLLM-9B-Instruct-2512-GGUF:Q4_K_M --port 8080`.


## Automatic model fallback routing
- Use `routing_decide` to choose the active model and fallback chain.
- Use `routing_status` to inspect configured profiles and the last routing decision.
- Use `routing_configure` to define primary, fallbacks, timeouts, and failure rules.
- Recommended default: local EuroLLM primary, cloud mid-tier fallback, cloud mini tertiary fallback.
