# Measurement first: how TWS differs from the viral "watermark strippers"

> Stand: 2026-08-18. Dieses Dokument ist ehrliche Markt-Einordnung, kein
> Shit-Talk. Es nennt keine Namen — die Muster sind branchenweit bekannt.

## Das Muster der viralen Stripper

Seit Anthropic die Claude-Marke dokumentiert hat (2026-08-02), schießen
"Watermark Remover"-Repos aus dem Boden — teils 10k+ GitHub-Stars innerhalb
von Tagen. Das Marktbedürfnis ist real (EU AI Act, Privacy, eigene Inhalte
hygienisieren). Aber die Architektur dieser Repos hat ein wiederkehrendes
Muster:

| Behauptung | Realität |
|---|---|
| "Entfernt Wasserzeichen von Claude/Gemini/OpenAI" | Layer A (Unicode) und Container-Metadaten (C2PA/EXIF/XMP) sind **deterministisch entfernbar** — okay |
| "Statistische Marks werden entfernt" | Nur **best-effort Paraphrase**; ohne Vendor-Detektor nicht verifizierbar |
| "Verifiziert mit MarkLLM" | Häufig: Tests laufen gegen **selbstgebaute Fake-Module** (`FAKE_TRANSFORMERS`, Fake-`AutoWatermark`), nie gegen die echte Referenzimplementierung |
| "Removal mit Receipt" | Fehlt meist komplett — kein Vorher/Nachher-Maß, kein signierter Befund |

Der Hype kauft eine **Behauptung**. Die Verifikationsschicht ist oft selbst
getestet gegen Fakes — die `cleared: true`-Logik wurde nie gegen echtes
MarkLLM/echte Detektoren bewiesen.

## Was TWS anders macht

### 1. Interop-Beweis statt Fake-Tests

`tests/test_markllm_interop.py` importiert das **echte** `markllm`-Paket
(THU-BPM/MarkLLM, EMNLP 2024) und beweist byte-identische Greenlists und
identische z-Scores gegen die Referenzimplementierung. Der KGW-Detektor, der
`delta-z` und der Rewrite-Transform messen, ist gegen den akademischen
Standard kalibriert — nicht gegen eigene Fakes.

### 2. ΔZ mit Receipt statt "cleared"-Feld

| | Viral Stripper | TWS |
|---|---|---|
| Messung | `cleared: bool` (oft fake-verifiziert) | `delta_z`, `z_before`, `z_after`, `verdict_*` **oder** `--verify`‑Befund (`verified_clear` / `residual_hard_bound` / `no_c2pa_present`) |
| Beweis | Behauptung | **Signierter Befund** (HMAC/ML-DSA, `report-verify`) |
| Ehrlichkeit | "cannot certify" als Kleingedrucktes | Grenzen im Kern-Code dokumentiert + im Report benannt |
| Was zählt als entfernt | Signal nicht messbar (oft gar nicht gemessen) | Vorher provable (z≥4), nachher nicht — sonst `removed: false` |

### 3. Kein "cleaner honesty"-Bluff

Der ΔZ-Kern dokumentiert unmissverständlich: `removed: true` heißt Signal
kollabiert — bei LLM-Rewrite ist das **Regeneration, kein Cleaning**. ΔZ
beweist Signaländerung, nie die Ehrlichkeit des Cleaners. Diese Grenze ist
im Code (Modul-Docstring), im CLI und im Report präsent, nicht nur im
README-Kleingedruckten.

### 4. Gleiche ehrliche Layer wie die Guten

Was die seriösen Stripper deterministisch können, können wir auch — und es
ist getestet, nicht behauptet:

- Layer A: Unicode-Hygiene (ZWSP, Bidi, Homoglyphen) — `sanitize_unicode`
- Container: C2PA/EXIF/XMP für PNG, JPEG, **WebP**, **AVIF/HEIC**, SVG, PDF,
  DOCX, ODT, HTML, MD — `metadata/service.py` (stdlib-only, verifizierte
  Actions pro entferntem Marker)
- Rewrite: rule-based structural (kein LLM) oder lokales Ollama —
  `delta-z --transform rewrite`, gemessen statt versprochen

## Die Positionierung

> **"Watermark removal, measured — not claimed."**

- Wir verkaufen **Messung** (ΔZ, signed reports, Interop-Beweis)
- Die viralen verkaufen **Reichweite** (Stars auf einer Behauptung)
- Beides zusammen ist der Markt: Removal wird gebraucht, aber der Käufer
  (Agent-Operator, Publisher, Compliance) braucht einen **Befund**, keinen
  Tweet

## Offene ehrliche Lücken (Stand 2.4.1)

- Pixel-Domain (SynthID-media, StegaStamp, Tree-Ring): out of scope — braucht
  schwere Regenerations-Backends, driftet das Bild, kein Vendor-Oracle
- C2PA *soft binding* (In-Content-Link auf Remote-Manifest): überlebt
  Metadata-Strip — Vendor-Detektor nötig
- Audio/Video-Marks: out of scope
- Kommerzielle Closed-Source-Marken (Claude, Gemini): kein öffentlicher
  Detektor → ehrlich als "nicht verifizierbar" benannt, nur gegen eigenes
  keyed KGW messbar
