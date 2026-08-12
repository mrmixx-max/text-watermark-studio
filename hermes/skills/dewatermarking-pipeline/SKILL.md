---
name: dewatermarking-pipeline
description: "Dewatermarking: Detect→Clean→Dilute→LLM-Rewrite→Detect."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [Dewatermarking, Pipeline, Watermark, LLM, Rewrite, Forensik]
    related_skills: [text-watermark-studio-lab, ai-text-detection-lab, ai-watermark-toolkit, chameleon-universal-tarntarnung]
---

# Dewatermarking Pipeline

## When to Use

- User will einen KI-textmarkierten Text durch die vollständige Entfernungs-
  Kette schicken: detect → clean → dilute → LLM-Rewrite → detect, mit
  messbarem Marker-Before/After-Report.
- Backend: Text Watermark Studio (lokal, `C:\Users\webma\Downloads\tws-install`
  oder frischer Clone) + lokales Ollama-Modell (EuroLLM-9B, verifiziert
  2026-08-12: **5 Marker (3 high) → 0 Marker**).
- Verifizierte Kette — keine Theorie: jeder Schritt wurde gegen echte
  Beispieldaten ausgeführt.

## Voraussetzungen

1. **Studio installiert:** `git clone https://github.com/mrmixx-max/text-watermark-studio.git && cd text-watermark-studio && python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"` (Windows) bzw. `source .venv/bin/activate` (macOS/Linux)
2. **Ollama läuft** mit EuroLLM-9B: `ollama pull hf.co/bartowski/EuroLLM-9B-Instruct-GGUF:Q4_K_M` (Alias `eurollm-9b`); nach Windows-Neustart `ollama serve` starten
3. **Ollama-URL:** `http://127.0.0.1:11434/v1` (OpenAI-kompatibel)

## Die 5-Stufen-Kette

### Stufe 1: Detect (Baseline)
```
ai-wm detect <datei>.txt --lang auto
```
Notiere Marker-Zähler (high/mid/low) + Unicode-Funde. Das ist die Baseline.

### Stufe 2: Clean (Unicode/Stego entfernen)
```
ai-wm clean <datei>.txt -o clean.txt
```
Entfernt Zero-Width-Zeichen, RTL-Override, Bidi-Stego. Fixture: `tests/fixtures/stego_zwsp.txt` (2 invisibles: U+200B + U+202E).

### Stufe 3: Dilute (Regel-basiertes Verdünnen)
```
ai-wm dilute clean.txt -o diluted.txt --intensity standard
```
Regel-Rewrite: Stock-Opener, Buzzwords, Flexionen (nahtlos/nahtlose→ohne
Reibung, leverage/leveraging/leveragen→use/using/nutzen, Synergien→
Zusammenspiel). Verifiziert: "In der heutigen digitalen Welt ist es wichtig
zu betonen, dass wir nahtlose Synergien heben" → "Heute wir reibungslose
Zusammenspiel heben" (4 Marker eliminiert).

### Stufe 4: LLM-Rewrite (EuroLLM, optional aber empfohlen)
Über die Studio-API (Server starten):
```
LOCAL_LLM_ENABLED=1 LOCAL_LLM_BASE_URL=http://127.0.0.1:11434/v1 LOCAL_LLM_MODEL=eurollm-9b \
  uvicorn ai_watermark_toolkit.api.fastapi_app:app --port 8080
```
Dann:
```bash
curl -s -X POST http://127.0.0.1:8080/api/rewrite/run \
  -H "Content-Type: application/json; charset=utf-8" \
  --data-binary @request.json
# request.json: {"text": "<diluted text>", "mode": "clarity", "use_llm": true}
```
⚠️ **Encoding-Falle (Windows):** `ü/ö/ä` inline in curl -d kaputt (Windows-Konsole sendet nicht UTF-8) → IMMER JSON-Datei + `--data-binary @file.json` verwenden.

Alternative ohne Server: direkter Python-Aufruf
```python
from ai_watermark_toolkit.rewrite.service import RewriteService
svc = RewriteService(llm_backend=True)  # nutzt LOCAL_LLM_* env vars
print(svc.rewrite(text, mode='clarity', use_llm=True)['rewritten'])
```

### Stufe 5: Detect (After-Report)
```
ai-wm detect <rewritten>.txt --lang auto
```
Vergleiche high/mid/low mit Baseline. Ziel: **0 high, 0 mid**.

## Report-Format (immer liefern)

| Metrik | Baseline | Nach Clean | Nach Dilute | Nach LLM |
|---|---|---|---|---|
| Marker high | N | | | |
| Marker mid | N | | | |
| Unicode-Funde | N | | | |
| Similarity (LLM) | — | | | (Soll: <0.8 = echte Umschreibung) |
| Wortzahl | N | | | |

## Verifizierte Referenzergebnisse (2026-08-12, EuroLLM-9B Q4_K_M)

- DE-Beispiel: "In der heutigen digitalen Welt ist es wichtig zu betonen,
  dass wir nahtlose Synergien heben. Darüber hinaus zeigt sich ein
  ganzheitlicher Ansatz als entscheidend."
  → Detect: **5 hits, 3 high**
  → LLM-Rewrite (clarity): "In the current digital world, it's crucial to
    emphasize seamless synergies. A holistic approach is also vital."
  → Detect: **0 hits, 0 high** (similarity 0.42)
- EuroLLM-Rewrite via API braucht auf CPU ~30-60s (180s httpx-Timeout im
  Service ist gesetzt — geduldig warten, nicht abbrechen).

## Quality Gate

- [ ] Baseline-Detect vorhanden (Zahlen notiert)
- [ ] Clean durchgelaufen (Unicode 0 im After-Detect)
- [ ] Dilute durchgelaufen (Marker reduziert)
- [ ] LLM-Rewrite (falls genutzt): Backend `local-llm` in Response, Similarity <0.8
- [ ] After-Detect: high=0 (mid/low dokumentiert, nicht versteckt)
- [ ] Report-Tabelle gefüllt
- [ ] Encoding sauber (JSON-Datei statt inline-curl bei Umlauten)

## Pitfalls

- **Inline-curl mit Umlauten auf Windows** → 400 "error parsing the body"; IMMER `--data-binary @file.json`
- **Ollama nicht gestartet** → ConnectionError; `ollama serve` in eigenem Terminal
- **`LOCAL_LLM_ENABLED=1` vergessen** → Route nutzt Rules-Backend (similarity ~1.0), kein LLM-Call
- **Python-Encoding:** Dateien als UTF-8 öffnen (`encoding='utf-8'`), nie Default-Locale
- **Kurze Texte:** LLM-Rewrite bei <50 Wörtern kann den Sinn verfälschen — Similarity prüfen, ggf. auf Dilute allein zurückfallen
- **Kein absoluter Erfolg garantiert:** 0 Marker heißt "keine erkannten Marker", nicht "menschengemacht" (siehe ai-text-detection-lab, Einschränkungen)
