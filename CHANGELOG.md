# Changelog ## 0.9.2 - Taxonomy-driven watermarking lab: plugin families for Unicode, lexical,
syntactic, format/layout, sampling/logit bias, semantic/structure,
localized provenance and training-time ownership workflows.
- Document layer: txt, markdown, rtf, docx, odt, pdf, epub workflows with
PyMuPDF-first extraction path, page-window extraction and result caching.
- RAG chunking: fixed, recursive, markdown-aware, page-aware, semantic-lite.
- LLM text rewriting: provider abstraction for Ollama, OpenAI, Anthropic.
- Prompt registry with versioned templates; automatic prompt optimization
with candidate generation, scoring and winner promotion.
- Multi-agent feedback loop (generator → critic → refiner → judge → promoter).
- Graph knowledge representation, community detection and summarization.
- Auto-correction and rewrite engine with protected-token preservation.
- Unified export service (Markdown, HTML, JSON, CSV, TXT).
- Direct cloud-storage upload with pseudo-presigned URLs.
- Local LLM integration for EuroLLM GGUF (llama.cpp OpenAI-compatible API).
- Automatic model fallback routing with deterministic fallback ladder.
- MCP tool manifest (`mcp/tools.json`) and Hermes plugin bundle (`hermes/`).
- Desktop Python GUI (Tkinter) and packaging scripts. ## 0.1.0 - Initial publishing-ready release
- CLI commands: detect, clean, dilute, pipeline, batch, serve
- FastAPI app and local web UI
- Docker and GitHub Actions setup
- Tests, issue templates, release workflow, and MIT license