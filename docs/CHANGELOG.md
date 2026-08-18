# Changelog Summary

> Full changelog: [CHANGELOG.md](../CHANGELOG.md)

## v2.4.1 (2026-08-18) — Current

**CLI** — 7 focused subcommands: `detect`, `clean`, `dilute`, `pipeline`, `batch`, `serve`, `dashboard`.

**API** — FastAPI server with 22 route modules: text processing, forensics (KGW, e-process, delta-z, finding, report-sign/verify), metadata (C2PA/EXIF/XMP, HMAC provenance, SynthID), documents, PDF, RAG chunking, LLM backend, model routing, prompt registry, prompt optimization, multi-agent loop, knowledge graph, community detection, multi-format export, cloud upload, Redis queue/streams, batch jobs, studio ops.

**TUI** — 25-action menu-driven terminal UI (Textual).

**Desktop** — PySide6 GUI for Windows (PyInstaller + Inno Setup).

**Security** — Constant-time API key comparison, production CORS locking, atomic key writes, ML-DSA key hardening, Bandit clean.

**Testing** — Deterministic pytest suite, `tmp_path` isolation, CI on Windows + Linux.

**Measurement** — Z-score + green-rate + p-value on every detection, keyed verification with baselines, signed findings (HMAC-SHA256 / ML-DSA FIPS 204), ΔZ measurement, MarkLLM interop-proven.

---

## v0.1.0 — Initial release

First publishing-ready release with core CLI, FastAPI app, Docker, CI, tests, and MIT license.
