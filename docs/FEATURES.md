# Feature Reference — Text Watermark Studio

Full feature inventory beyond the README quickstart. Automatically maintained alongside the code; the README links here for depth.

## v2.0.0: model-grade detection + measurement suite

- **BPE token level**: `detect_kgw(text, key, level="bpe")` runs the greenlist over cl100k subword tokens at word boundaries — the surface a real tokenizer feeds sampling watermarks. Mark + detect round-trip on the same level. Needs `tiktoken` (`pip install text-watermark-studio[bpe]`).
- **Attack matrix**: `python benchmarks/attack_matrix.py` — structural, dilute (all intensities), unicode spam and word shuffle against a marked text; measures the Z-score drop per attack.
- **SynthID-style sweep**: `python benchmarks/synthid_sweep.py` — gamma × paraphrase-rate grid producing the detection curve.
- **Findings report**: `ai-wm report file.txt --key <key> [--pdf]` — self-contained HTML forensics report, optional PDF via Edge headless.
- **Directory watcher**: `ai-wm watch ./docs --once|--interval 5` — JSON lines with metadata + provenance findings per file.
- **Local corpus similarity**: `ai-wm similarity text.txt --corpus ./archiv` — MinHash
  fingerprint comparison against YOUR OWN documents, with fundstelle quotes
  and an honest boundary (literal overlap, not paraphrased meaning; no web
  crawl, no hidden corpus).
- **Prompt optimizer (real evaluator loop)**: locked eval set
  (`data/optimization_evals.json`), candidates changing one variable each,
  deterministic scoring (protected-term guardrail, length, marker reduction,
  lexical balance), promotion only on improvement over a hashed baseline,
  immutable versioning + rollback via the prompt registry. Offline
  deterministic backend; LLM backend via `LOCAL_LLM_*`.
- **Menu-driven TUI**: `ai-wm tui` — Textual terminal UI, 25 menu actions,
  cursor-key navigation with app-level priority (works from any focus),
  keyboard shortcuts, built-in check-and-upgrade and in-menu local model
  install (Ollama pull). Needs `textual`
  (`pip install text-watermark-studio[tui]`).

## What removing a text watermark costs (honest disclaimer)

Text watermarks live in **the wording itself**: the signal is spread across token choices, so nearly every sentence carries a little of it. Two consequences follow:

1. **Removal means rewording, not restructuring.** Shuffling paragraphs, changing headings, or light touch-ups barely move the signal. Stripping a statistical mark requires rewriting a substantial fraction of the text — sentence by sentence, not section by section.

2. **Rewording degrades the copy.** Any rewrite replaces the original word choices with the rewriting model's, which flattens tone, voice, and precision. On production copy (SEO, marketing, client work) that degradation is real and often visible to the people who care most about the writing.

The full-circle question worth asking: if the plan is to rewrite the text with a cheaper model anyway, why pay for a premium model in the first place? Generating directly with the cheaper model is simpler, cheaper, and produces the same — or better — end result.

Layer B makes sense when you specifically want the premium model's **thinking and drafting** and accept a rewrite pass to satisfy a hygiene or privacy requirement — not as a cheap route to mark-free text. When quality matters more than hygiene, use the lossless path: the Unicode scrub plus the file metadata cleaners, and keep the original prose.

## Large PDF performance

PyMuPDF is widely documented as a high-performance PDF engine and recent benchmarks report faster plain-text extraction than pypdf on large documents, while PyMuPDF documentation also recommends excluding images and using the simplest text extraction modes for speed. Large-file FastAPI guidance likewise recommends `UploadFile`, chunked streaming, running byte limits and page-scoped processing instead of bulk in-memory ingestion. This edition therefore adds a PyMuPDF-first extraction path, page-window extraction, result caching and PDF-specific MCP tools.

## RAG chunking

Current retrieval guidance consistently recommends recursive chunking as the pragmatic default for general corpora, commonly around 400–512 tokens with 10–20% overlap, because it preserves structure better than fixed-size cutting without semantic-chunking cost. Newer playbooks then layer in document-aware, semantic, hierarchical or late/contextual methods when eval results justify extra complexity. This edition adds fixed, recursive, markdown-aware, page-aware and semantic-lite chunking through the API, UI and MCP manifests.

### LLM text rewriting

The rewrite service (`POST /api/rewrite/run`) supports **clarity, concise, plain, formal, structural and backtranslate** modes. `structural` reorders paragraphs/sentences while keeping facts, numbers and names identical. `backtranslate` is the literature-standard two-hop attack on sampling watermarks (text → English → original language, two LLM calls) — with an honest rule-based structural fallback when no LLM backend is configured.

Ollama exposes local generation and chat APIs over HTTP, including `/api/generate` and `/api/chat`, making it a straightforward local backend for rewriting workflows. OpenAI recommends the Responses API for direct model requests in newer GPT generations, while Anthropic's Messages API is the standard text-generation interface for Claude models. This edition adds a provider abstraction and rewriting routes for Ollama, OpenAI and Anthropic, plus MCP exposure and UI controls.

## Prompt templates and versioning

Current production guidance recommends keeping prompts outside application code, assigning stable IDs and immutable versions, separating system instructions from user templates and variables, and storing the full execution context such as provider, model and decoding parameters together with the prompt asset. Semantic versioning, changelogs, approval metadata and rollback-ready registries are repeatedly cited as the operational baseline for prompt governance. This edition adds a JSON prompt registry, versioned template metadata, render APIs, version creation and template-driven LLM rewriting.

## Automatic prompt optimization

Production prompt optimization is usually framed as an evaluator-driven loop: define a locked eval set, generate candidate prompt variants, score them against your metric, and promote the winner with rollback-ready versioning. Recent guidance recommends changing one variable at a time, tracking a baseline hash, and promoting only variants that improve the target metric without harming guardrails. This edition adds an optimizer service, candidate generation, scoring, winner promotion, and MCP/UI integration for prompt optimization.

## Multi-agent feedback loop

A practical multi-agent prompt loop usually follows generator → critic → refiner → judge → promoter, with hard stop conditions on max iterations, no-improvement rounds, and score thresholds.

**Status: minimal demo scaffold.** This edition ships the multi-agent service with API routes and MCP hooks, but the loop itself is a two-draft placeholder (`text.strip()` plus a fixed append) — there is no critic, refiner, judge, promoter, or scoring. The **prompt optimizer** (above) implements the real evaluator loop; do not rely on the multi-agent module for production. This honesty note matches the code, and the MCP manifest lists only routes that exist.

## Graph knowledge representation

Current agent-memory guidance increasingly treats vector search, working memory and knowledge graphs as complementary subsystems, with graphs handling typed entities, relationships and multi-hop traversal that flat similarity search cannot express well. Recommended build steps are to define a schema, populate entities and typed edges, expose a query layer to agents, and monitor freshness and drift over time. This edition adds a schema file, node/edge graph store, fact ingestion, neighbor/subgraph retrieval, graph APIs, UI controls and MCP integration.

## Community detection and summarization

GraphRAG-style systems commonly detect graph communities and pregenerate summaries for each cluster so that global or corpus-level questions can be answered from community summaries rather than only local node retrieval. Leiden-style clustering is common, but deterministic alternatives such as core-based hierarchies are also discussed; in all cases the general pattern is cluster first, summarize second, and aggregate answers across community reports when needed. This edition adds graph community detection, persisted community metadata, community summaries, API routes, UI controls and MCP tools.

## Auto-correction and rewrite engine

Good rewrite systems are typically layered: first correct orthography and grammar, then apply style or tone transformations under explicit constraints, and finally compare original versus rewritten text to catch meaning drift. Multiple 2026 practitioner guides recommend separating these stages, preserving numbers, names, and quotations, and keeping a change log for review. This edition adds a lightweight rewrite engine with protected-token preservation, rewrite modes, similarity metrics, change logs, API integration, UI controls, and MCP access.

## Export module for multiple styles and formats

Current export guidance consistently separates human-readable formats from machine-oriented formats: Markdown and HTML are favored for readable reports, JSON for machine-to-machine exchange, CSV for tabular interoperability, and plain text for durable low-friction transfer. Preservation guidance also recommends using open text formats and, when useful, shipping more than one export format for long-term access and downstream compatibility. This edition adds a unified export service for Markdown, HTML, JSON, CSV, and TXT, with selectable visual styles and metadata support through the API, UI, and MCP layer.

## Direct cloud storage upload

The current production pattern for browser uploads is to split control plane and data plane: the client first asks the backend for a short-lived, scoped signed upload URL, then uploads bytes directly to object storage, and finally confirms completion so the backend can persist metadata or trigger post-processing. Current guidance emphasizes validating filename, content type, and size before signing; using short expirations; keeping buckets private; and attaching asynchronous scanning or reconciliation after upload. This edition adds a direct cloud-upload module with upload request records, pseudo-presigned URLs, confirmation, listing, API routes, UI controls, and MCP tools.

## Local LLM integration: EuroLLM GGUF

The Hugging Face model page for `mradermacher/EuroLLM-9B-Instruct-2512-GGUF` explicitly documents direct local usage with llama.cpp-style tooling, including commands such as `llama serve -hf mradermacher/EuroLLM-9B-Instruct-2512-GGUF:Q4_K_M` and `./llama-server -hf mradermacher/EuroLLM-9B-Instruct-2512-GGUF:Q4_K_M`. Recent llama.cpp guides also note that `llama-server` exposes an OpenAI-compatible API, typically under `http://localhost:8080/v1`, which can be consumed by standard OpenAI clients and local tools without major code changes. This edition adds direct configuration support for the local model `mradermacher/EuroLLM-9B-Instruct-2512-GGUF`, stores provider and endpoint metadata in `data/local_llm.json`, and exposes configuration/status routes and UI hooks for a local OpenAI-compatible backend.

## Any local model via Ollama (not just EuroLLM)

The studio is not locked to EuroLLM. Any model your local Ollama instance
knows works — including everything you've pulled from Hugging Face GGUF
mirrors:

```bash
ai-wm llm list                    # every model the local Ollama knows
ai-wm llm install llama3.2:3b     # pull via the Ollama API + select it
ai-wm llm use qwen-coder          # switch to an installed model
ai-wm llm status                  # current backend configuration
```

`install` streams pull progress, verifies the model landed, and points
`data/local_llm.json` (and the rewrite/optimizer backends via
`LOCAL_LLM_MODEL`) at it. The TUI has the same action as menu entry 18
(model name in the Path field). The rewrite and optimizer backends honor
`LOCAL_LLM_BASE_URL` + `LOCAL_LLM_MODEL` — so any OpenAI-compatible endpoint
works, not just Ollama.

## Automatic model fallback routing

Current gateway and routing guidance recommends putting all model calls behind a single routing layer that applies a deterministic fallback ladder, with distinct handling for timeouts, 5xx errors, rate limits, context overflow, and invalid outputs. Multiple 2026 engineering references also recommend same-tier fallback first, immediate failover on 429s, circuit-breaker style thinking, and explicit logging of the routing decision and its reason. This edition adds an automatic model-routing module with profiles, primary/fallback chains, per-condition rules, route-decision persistence, API routes, UI controls, and MCP tools.

## Debugging and hardening

HTMX + FastAPI integrations often fail in a few recurring places: unchecked checkboxes disappear from the request body instead of sending `false`, `json-enc` forms need explicit JSON handling, and HTMX usually expects HTML fragments rather than raw JSON when targeting DOM nodes. Current debugging guidance recommends inspecting actual request payloads, normalizing checkbox values on the server, and returning HTML partials whenever `HX-Request: true` is present. This edition hardens the app by adding unified HTMX/JSON response helpers, checkbox normalization, metadata parsing for export requests, HTML fragment responses for HTMX calls, and a repaired rewrite module.

## Roadmap: MarkDiffusion (image watermarking) — planned, not built

Evaluated integrating MarkDiffusion (THU-BPM, JMLR, Apache-2.0) for image
watermarking (Tree-Ring, RIGL, Gaussian Shading). Decision: **roadmap item,
not a current build** — scope discipline over feature sprawl.

Why deferred:
- MarkDiffusion requires a real Stable Diffusion model (multi-GB download) for
  every mark/detect run; interop verification without the model would be
  showcase measurement, not evidence.
- 42 dependencies (diffusers, transformers, accelerate, opencv) — heavy for an
  image feature outside the text-watermark core.
- CI cost explodes (diffusion sampling = minutes, not seconds).

If image watermarking moves forward, it should be a **sibling repository**
(image-watermark-studio) with the same measurement-first philosophy, dedicated
GPU runners, and its own release cycle — not a dependency expansion of this
package. Tracking: GitHub issue #1.
