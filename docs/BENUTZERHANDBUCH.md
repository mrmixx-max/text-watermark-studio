# Text Watermark Studio — Benutzerhandbuch

Version 2.0.0 · MIT · 100% lokal, Zero Telemetry

Dieses Handbuch deckt ab, was das Toolkit kann, wie man verifiziert, dass es
funktioniert — und mit gleicher Sorgfalt, was es ehrlich nicht kann.

---

## 1. Überblick

Text Watermark Studio ist ein lokales Forensik-Labor für KI-Text- und
Datei-Wasserzeichen. Es läuft vollständig auf deiner Maschine; nichts wird
an eine Cloud geschickt.

Es arbeitet in beide Richtungen:

- **Detektieren** — Markierungen finden, die andere hinterlassen haben:
  unsichtbare Unicode-Zeichen, KI-Phrasierungsmuster und statistische
  Sampling-Wasserzeichen (KGW-Familie).
- **Entfernen** — clean, dilute, rewrite.
- **Beweisen** — ein Z-Score, den man verteidigen kann, statt eines
  „sieht aus wie KI"-Gefühls.
- **Schützen** — Greenlist-Marken auf Text, HMAC-Provenance-Signaturen auf
  Dateien.

Unterstützte Oberflächen:

| Oberfläche | Detektieren | Bereinigen | Setzen | Eigenes finden |
|---|---|---|---|---|
| Text (Unicode / Phrasierung) | ✅ | ✅ | — | — |
| Text (statistisch, KGW) | ✅ | — | ✅ | ✅ |
| Dateien (Metadaten: C2PA/EXIF/XMP) | ✅ | ✅ | — | — |
| Dateien (Provenance, HMAC) | ✅ | — | ✅ | ✅ |
| Bilder (SynthID-Pixel) | ✅ (externer Checkpoint) | — | — | — |

---

## 2. Installation

Benötigt Python 3.10+.

```bash
# Kern-Installation
pip install text-watermark-studio

# Mit BPE-Token-Ebene (cl100k via tiktoken)
pip install text-watermark-studio[bpe]

# Mit menügesteuerter Terminal-Oberfläche (textual)
pip install text-watermark-studio[tui]
```

Aus dem Quellcode:

```bash
git clone https://github.com/mrmixx-max/text-watermark-studio.git
cd text-watermark-studio
python -m venv .venv
# Windows: .\.venv\Scripts\activate | macOS/Linux: source .venv/bin/activate
pip install -e ".[dev,bpe]"
```

Installation prüfen:

```bash
ai-wm splash
ai-wm --help
```

---

## 3. Schnellstart

```bash
# Text auf unsichtbare Zeichen und KI-Marker scannen
ai-wm detect artikel.txt

# JSON-Ausgabe (Standard; --pretty für Menschen)
ai-wm detect artikel.txt --json

# Unicode-Layer bereinigen, in neue Datei schreiben
ai-wm clean artikel.txt -o sauber.txt

# Markerlastige Phrasen umschreiben (drei Intensitäten)
ai-wm dilute sauber.txt --intensity standard -o verdünnt.txt

# Gesamte Kette: detect → clean → dilute → rewrite → detect
ai-wm pipeline artikel.txt --rewrite-mode structural -o final.txt

# Text gegen einen KGW-Key testen
ai-wm report artikel.txt --key demo-kgw-1 --pdf

# Ordner überwachen, Metadaten- und Provenance-Befunde melden
ai-wm watch ./eingang --once
```

---

## 4. Konzepte: die drei Ebenen

KI-Systeme markieren Ausgaben auf drei Ebenen. Keine ist für das Auge
sichtbar.

**Ebene 1 — Unsichtbare Zeichen.** Bidirektionale Steuerzeichen (LRE, RLE,
LRO, RLO, PDF, Isolates), Zero-Width-Spaces, Joiner, Tag-Blöcke, veraltete
Formatzeichen. Überleben Copy-Paste, verändern sichtbar nichts.

**Ebene 2 — Stil-Marker.** Statistische Fingerabdrücke in der Phrasierung:
18 KI-Phrasierungsmuster inklusive gebeugter Formen.

**Ebene 3 — Statistische Wasserzeichen.** KGW, SynthID-Text und Verwandte
verzerren die Token-Wahl *während der Generierung*. Kein Zeichen, keine
Phrase — eine Verteilung. Erkennbar nur mit dem richtigen Key und einem
statistischen Test (Z-Score).

Ebenen 1 und 2 werden mit `clean`/`dilute` entfernt. Ebene 3 wird gemessen,
nicht entfernt: `detect_kgw` meldet, ob eine Marke vorhanden ist — mit
Score.

---

## 5. CLI-Referenz

17 Subcommands. Exit-Codes: `0` sauber, `1` Funde/Fehler/nicht verfügbar,
`2` Eingabefehler. `ai-wm tui` startet die menügesteuerte
Terminal-Oberfläche (siehe §6).

### detect
```bash
ai-wm detect [input] [--stdin] [--lang auto|de|en] [--json] [--pretty]
             [--aggressive] [-o OUTPUT]
```
Findet Unicode-/Stego- und KI-Phrasierungsmarker. `--aggressive` flaggt
zusätzlich skriptspezifische Füller (Braille-Leerzeichen, Hangul, Khmer,
…) — Opt-in, weil es legitimen Inhalt treffen kann.

### clean
```bash
ai-wm clean [input] [--stdin] [--nfkc] [--fold-confusables] [-o OUTPUT]
            [--report REPORT]
```
Entfernt den Unicode-Layer. `--nfkc` normalisiert Kompatibilitätsformen,
`--fold-confusables` bildet ähnlich aussehende Glyphen aufeinander ab.

### dilute
```bash
ai-wm dilute [input] [--stdin] --intensity light|standard|aggressive [-o OUTPUT]
```
Schreibt markerlastige Phrasen um, 33 Regeln mit geschützten Tokens.

### embed
```bash
ai-wm embed [input] [--stdin] --key KEY [--gamma GAMMA] [-o OUTPUT]
```
Setzt eine Greenlist-Marke in einen Text. `--key` muss eine key_id aus
`data/key_registry.json` referenzieren, die ein Secret trägt.

### pipeline
```bash
ai-wm pipeline [input] [--stdin] [--lang auto|de|en] [--nfkc]
               [--fold-confusables] --intensity light|standard|aggressive
               [--rewrite-mode clarity|concise|plain|formal|structural|backtranslate]
               [--aggressive] [-o OUTPUT] [--report REPORT]
```
Die volle Kette: detect → clean → dilute → rewrite → detect. `rewrite_mode`
ist standardmäßig aus; explizit aktivieren.

### report
```bash
ai-wm report [input] [--stdin] --key KEY [--lang en|de] [--pdf] [-o OUTPUT]
```
Selbsttragender HTML-Forensik-Befund: Z-Score, Green-Rate, p-Wert, Tabelle
unsichtbarer Zeichen, Empfehlung. `--pdf` rendert via Edge headless
(Windows). Ausgabe standardmäßig `tws-report-<ts>.html`.

### watch
```bash
ai-wm watch VERZEICHNIS [--once] [--interval SEKUNDEN]
```
Überwacht einen Ordner (stdlib, keine Abhängigkeiten), gibt JSON-Zeilen pro
Datei mit Metadaten- und Provenance-Befunden aus. `--once` macht einen
einzelnen Durchlauf und beendet (sicher für Skripte und Cron).

### rewrite
```bash
ai-wm rewrite [input] [--stdin] --mode clarity|concise|plain|formal|structural|backtranslate
              [--use-llm] [--no-preserve] [--json] [-o OUTPUT]
```
`structural` ist regelbasiert (Satz-Rotation, erste/letzte Sätze verankert).
`backtranslate` braucht das lokale LLM-Backend (siehe §12). `--use-llm`
erzwingt das LLM-Backend für die übrigen Modi.

### image-score
```bash
ai-wm image-score INPUT [--synthid-dir PFAD] [--json]
```
Bewertet ein Bild auf SynthID-Pixelmarken. Benötigt den externen Checkpoint
(siehe §10); ohne ihn meldet es ehrlich `available: false` und endet mit
Exit 1.

### batch
```bash
ai-wm batch INPUT_VERZ AUSGABE_VERZ [--mode detect|clean|dilute|pipeline]
              [--lang auto|de|en] [--intensity ...] [--report REPORT]
```
Führt einen Modus über jede Datei in einem Verzeichnis aus.

### serve
```bash
ai-wm serve [--host HOST] [--port PORT]
```
Startet den FastAPI-Server (siehe §14).

### file-inspect / file-clean / file-embed / file-detect
```bash
ai-wm file-inspect dokument.pdf [--json]
ai-wm file-clean  dokument.pdf -o sauber.pdf [--json]
ai-wm file-embed  dokument.pdf --key KEY -o signiert.pdf
ai-wm file-detect signiert.pdf [--json]
```
Metadaten prüfen/bereinigen (C2PA/EXIF/XMP), Dateien mit HMAC-Provenance
signieren, Signaturen verifizieren. Unterstützte Formate: PNG, JPEG, SVG,
PDF, DOCX, ODT, HTML, Markdown.

### splash
```bash
ai-wm splash
```
Studio-Banner + Systemstatus.

---

## 6. Menügesteuerte Terminal-Oberfläche

```bash
ai-wm tui
```

Eine menügesteuerte Textual-Oberfläche (Installation mit
`pip install text-watermark-studio[tui]`). Dunkles Studio-Theme, passend zur
Hero-Infographic des Repos. 17 Menüpunkte — detect, clean, dilute, embed,
pipeline, report, rewrite, die vier Datei-Werkzeuge, SynthID-Scoring,
Verzeichnis-Überwachung, beide Benchmarks, Systemstatus und Update.

Navigation:

- `↑`/`↓` bewegen das Menü von überall aus (App-Ebene-Prioritäts-Bindings —
  die Cursortasten steuern das Menü auch, während das Pfad-Feld fokussiert ist)
- `Enter` führt die gewählte Aktion aus
- Buchstaben-Shortcuts: `d` detect · `c` clean · `e` embed · `p` pipeline ·
  `r` report · `s` splash · `q` beenden · `^p` Befehlspalette
- Das Pfad-Feld unten nimmt einen Datei- oder Verzeichnispfad; die meisten
  Aktionen lesen ihn und schreiben Ergebnisse ins Ausgabe-Panel

**Update:** Punkt 17 vergleicht die installierte Version mit PyPI und führt
`pip install --upgrade text-watermark-studio` aus, wenn eine neuere Version
existiert.

**Burn-in:** `python benchmarks/tui_burnin.py` fährt alle 17 Aktionen
headless gegen eine echte Beispieldatei und schlägt bei jeder Exception laut
fehl — das Pre-Release-Gate für die Oberfläche.

![Menügesteuerte Studio-TUI](../docs/tws-tui.png)

---

## 7. KGW-Erkennung statistischer Wasserzeichen

Der Detektor implementiert das KGW-Greenlist-Schema (Kirchenbauer et al.):

1. Ein PRF-Hash von `(Key, vorheriges Token)` wählt eine Greenlist von ~γ
   des Vokabulars.
2. Wasserzeichenmarkierter Text nutzt grüne Tokens häufiger als der Zufall.
3. Der Z-Score der Grünzahl testet diese Verzerrung:
   `Z = (grün − γn) / √(nγ(1−γ))`.

Urteile: `Z ≥ 4,0` watermark_detected · `2,0 ≤ Z < 4` weak_signal ·
`Z < 2,0` no_signal. `γ` steht standardmäßig auf 0,25 (`--gamma` bei
`embed`, `DEFAULT_GAMMA` in `forensics/kgw.py`).

### Multi-Key mit Bonferroni

`detect_multi_key(text, keys)` testet eine Key-Liste und wendet
Bonferroni-Korrektur an, damit viele Keys die False-Positive-Rate nicht
aufblähen.

### Token-Ebenen (2.0.0)

```python
from ai_watermark_toolkit.forensics.kgw import detect_kgw

detect_kgw(text, "mein-key", level="word")   # schnelle Näherung (Standard)
detect_kgw(text, "mein-key", level="bpe")    # cl100k-Subwörter, Modell-Ebene
```

`level="bpe"` hasht die Greenlist über cl100k-Subwort-Tokens **an
Wortgrenzen** — die Oberfläche, die ein echter Tokenizer einem
Sampling-Wasserzeichen füttert. Markieren und Detektieren laufen auf
derselben Ebene. `level="word"` kleinschreibt und bewertet ganze Wörter.

### Der End-to-End-Beweis

`benchmarks/kgw_e2e_proof.py` führt den vollständigen Roundtrip gegen ein
echtes lokales Modell aus (Standard `eurollm-9b:latest` via Ollama): Text
generieren → Greenlist auf die eigenen Token des fremden Modells anwenden →
detektieren. Gemessen:

| Messung | Ergebnis |
|---|---|
| Unmarkierter Modell-Text, richtiger Key | z = 0,6, kein Signal |
| Markierter Text, richtiger Key | **z = 15,9, watermark_detected** |
| Markierter Text, falscher Key | z = −0,2, kein Signal |

---

## 8. Eigene Marken setzen

**Text:** `ai-wm embed text.txt --key demo-kgw-1` (bzw. `mark_greenlist()`
im Code) setzt die Greenlist durch Ersetzen nicht-grüner Wörter durch grüne
aus einem Frequenz-Pool. Die Marke ist key-gebunden: Nur der
Key-Inhaber detektiert sie; ein falscher Key meldet kein Signal.

Ehrliche Einschränkung: Die Ersetzungen stammen aus einem
Frequenzvokabular, keine Synonyme — Wort-für-Wort-Nuance bleibt nicht
erhalten. Das ist die dokumentierte Annäherung an Token-Sampling-Wasserzeichen
aus reinem Text-Rewriting.

**Dateien:** siehe §8.

Keys liegen in `data/key_registry.json`. Der mitgelieferte Key `demo-kgw-1`
trägt ein öffentliches Demo-Secret — vor echtem Einsatz ersetzen:

```json
{"keys": [{"key_id": "mein-key", "family": "kgw", "status": "active",
           "owner": "local", "secret": "<dein-secret>"}]}
```

---

## 9. Datei-Provenance (HMAC)

`file-embed`/`file-detect` signieren Dateien mit einem HMAC über den
Original-Inhalt und legen die Marke in der Datei ab (XMP-artiges Paket).
8 Formate: PNG, JPEG, SVG, PDF, DOCX, ODT, HTML, Markdown.

Eigenschaften:

- **Inhaltsgebunden:** Das Kippen eines einzelnen Bytes bricht die Signatur.
- **Key-gebunden:** Nur der Secret-Inhaber kann eine gültige Marke setzen
  *oder* fälschen.
- **`found`/`valid`-Paar:** Unterscheidet „falscher Key" von „manipulierter
  Inhalt".

```bash
ai-wm file-embed  bericht.pdf --key mein-key -o signiert.pdf
ai-wm file-detect signiert.pdf --key mein-key --json
# {"found": true, "valid": true, ...}
```

---

## 10. Metadaten-Bereinigung (C2PA / EXIF / XMP)

`file-inspect`/`file-clean` prüfen und entfernen Metadaten:

- PNG: eXIf-, XMP-Chunks
- JPEG: APP1/APP11-Segmente
- SVG: `<metadata>`-Elemente
- PDF: XMP-Metadaten-Streams
- DOCX/ODT: eigene Teile

Reine Standardbibliothek (zipfile, xml.etree, binäre Chunk-Parser) — kein
Abhängigkeitsgewicht.

---

## 11. SynthID (Pixel-Scoring)

SynthIDs Modell ist hier nicht weiterverteilbar (220 MB,
nicht-kommerzielle Research-Lizenz). Das Toolkit liefert einen Adapter +
Bootstrap, der es aus der Quelle baut, wenn du das möchtest:

```bash
scripts/setup_synthid.sh --verify
```

`--verify` führt nach dem Setup einen echten Scoring-Lauf auf einem
generierten Testbild aus — Beweis für „funktioniert wirklich", nicht
„sollte funktionieren". Danach:

```bash
ai-wm image-score foto.png
```

Ohne den Checkpoint meldet `image-score` ehrlich `available: false` und
endet mit Exit 1. Der Adapter tut nie so als ob.

---

## 12. Rewrite-Engine

`rewrite` und `pipeline --rewrite-mode` bieten:

- **structural** — regelbasierte Satz-Rotation, erste/letzte Sätze
  verankert. Deterministisch, kein LLM.
- **backtranslate** — zwei LLM-Aufrufe (DE→EN→DE) über das lokale
  LLM-Backend. Ohne Backend degradiert es ehrlich zu einem strukturellen
  Shuffle und sagt das im Änderungsprotokoll.

Lokales LLM-Backend (Ollama, OpenAI-kompatibel):

```bash
export LOCAL_LLM_ENABLED=1
export LOCAL_LLM_BASE_URL=http://127.0.0.1:11434/v1
export LOCAL_LLM_MODEL=eurollm-9b
```

**Jedes lokale Modell, nicht nur EuroLLM** — das Studio verwaltet das
Ollama-Backend direkt:

```bash
ai-wm llm list                  # alle Modelle, die das lokale Ollama kennt
ai-wm llm install llama3.2:3b   # Pull über die Ollama-API + Auswahl
ai-wm llm use qwen-coder        # auf ein installiertes Modell umschalten
ai-wm llm status                # aktuelle Backend-Konfiguration
```

`install` streamt den Pull-Fortschritt, prüft, dass das Modell angekommen
ist, und setzt die Konfiguration (und `LOCAL_LLM_MODEL`) darauf. Dieselbe
Aktion im TUI: Menüpunkt 18, Modellname im Pfad-Feld.

---

## 13. Befund-Report & Ordner-Watcher (2.0.0)

`ai-wm report` erzeugt einen selbsttragenden HTML-Befund — KGW-Statistik,
Tabelle unsichtbarer Zeichen, den analysierten Text und eine Empfehlung —
mit optionalem `--pdf`-Rendering.

`ai-wm watch` überwacht ein Verzeichnis und gibt pro neuer/geänderter Datei
eine JSON-Zeile mit `metadata`- (Inspect-Aktionen) und `provenance`-
(found/valid/key_id) Befunden aus. Gebaut für Redaktionen, Editoren und
Incident Response.

---

## 14. Benchmarks

Drei reproduzierbare Skripte in `benchmarks/` (standardmäßig
deterministisch, kein LLM nötig):

| Skript | Was es misst |
|---|---|
| `attack_matrix.py` | Z-Score-Abfall pro Attacke: structural, dilute (3 Intensitäten), Unicode-Spam, Wort-Shuffle |
| `attack_matrix_v2.py` | Blackbox v2: N echte EuroLLM-Generierungen + post-hoc KGW-Markierung (γ=0.25), Angriffs-Matrix mit ΔZ, 100-Token-Fenster-Analyse; Cache in %TEMP%, ohne Ollama reproduzierbar via `--skip-generation` |
| `synthid_sweep.py` | Detektions-Kurve: Gamma × Paraphrase-Rate-Raster |
| `kgw_e2e_proof.py` | Voller Roundtrip gegen ein echtes lokales Modell |

Ehrlicher Attack-Matrix-Befund: Stil-Attacken (dilute, Unicode-Spam,
regelbasiertes Structural) brechen die Greenlist-Marke **nicht**;
Wort-Permutation schon (z fällt auf ~−1,4). Die Detektions-Kurve zeigt:
Die Marke überlebt je nach γ etwa 45–60 % Wort-Umsatz.

---

## 15. API-Server

```bash
ai-wm serve --port 8000
```

FastAPI-App mit Routen für Textverarbeitung (`/api/pipeline`,
`/api/rewrite/run`), Metadaten (`/api/metadata/inspect|clean|synthid-score|file-embed|file-detect`)
sowie `/health`- und `/ready`-Probes. Swagger-UI unter `/docs`.

---

## 16. MCP-Tools & Hermes-Skills

Das Repo bündelt MCP-Tools und 5 Hermes-Skills
(`hermes/skills/text-watermark-studio-lab/`) mit Vendor-Notes auf
Klassen-Ebene für Claude, Gemini/SynthID und OpenAI — was nachweislich
bekannt ist vs. Best-Effort-Behauptungen je Anbieter.

---

## 17. Sicherheitsmodell & ehrliche Grenzen

- **Kein regelbasierter Detektor besiegt ein Sampling-Wasserzeichen**, das
  ein fremdes Modell auf Logit-Ebene anwendet. Was dieses Toolkit liefert,
  ist die Messung: Wenn die Marke da ist, wird sie gefunden — mit
  verteidigbarem Z-Score.
- **Pixel-Wasserzeichen-Entfernung ist kein Ziel.** Versuche, sichtbare oder
  unsichtbare Bild-Wasserzeichen zu entfernen, sind bewusst außerhalb des
  Scopes.
- **„Pangram-sicher" heißt:** keine bekannten Marker/Tropen/Stego-Muster
  verbleiben. Es ist keine Garantie gegen unbekannte Verfahren.
- Alles läuft lokal; keine Telemetrie. Nachprüfbar: Der Code ist MIT und
  kurz genug zum Lesen.

---

## 18. Fehlerbehebung

| Symptom | Lösung |
|---|---|
| `ModuleNotFoundError: tiktoken` | `pip install text-watermark-studio[bpe]` |
| `image-score` endet mit 1 | Checkpoint nicht eingerichtet — `scripts/setup_synthid.sh --verify` ausführen |
| `rewrite --mode backtranslate` liefert Structural-Ergebnis | LLM-Backend nicht konfiguriert — `LOCAL_LLM_*`-Env-Variablen setzen (§11) |
| `embed` endet mit 2 | `--key` referenziert eine key_id ohne Secret in `data/key_registry.json` |
| `watch` meldet `unsupported`-Format | Dateityp nicht im unterstützten Satz des Metadaten-Layers — erwartetes, ehrliches Signal |

---

## 19. Entwicklung & Tests

```bash
pip install -e ".[dev,bpe]"
pytest tests/          # 195 Tests, deterministisch, kein Netzwerk
python benchmarks/attack_matrix.py
```

CI läuft auf Windows und Linux. Tests nutzen `tmp_path`-Isolation — kein
Test schreibt in getrackte `data/`-Dateien.

---

## 20. Lokaler Corpus-Abgleich

```bash
ai-wm similarity text.txt --corpus ./archiv [--threshold 0.4] [--top 5] [--json]
```

MinHash-Fingerprint-Vergleich eines Textes gegen **Ihren eigenen**
Dokument-Korpus. Deterministisch, offline, mit Fundstellen-Zitaten als
Beleg. Exit-Code `1` bei Funden über dem Schwellwert, sonst `0`.

**Ehrliche Grenze (bewusst so gebaut):** Der Abgleich misst wörtliche
Überlappung (5-Gramm-MinHash-Signaturen), nicht umschriebene Bedeutung.
Eine stark paraphrasierte Kopie erzielt einen niedrigen Wert — der Bericht
sagt das ausdrücklich. Kein Web-Crawl, kein versteckter Korpus, kein
„Plagiatsbeweis": Ähnlichkeit zu *diesen* Quellen, mehr nicht. Binäre oder
unlesbare Korpus-Dateien werden als übersprungen gelistet, nicht als
Fehler behandelt.

---

Lizenz: MIT · Repository: <https://github.com/mrmixx-max/text-watermark-studio>
PyPI: <https://pypi.org/project/text-watermark-studio>
