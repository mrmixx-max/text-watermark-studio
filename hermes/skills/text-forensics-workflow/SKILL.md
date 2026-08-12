---
name: text-forensics-workflow
description: "End-to-end KI-Text-Forensik: Datei rein, Befund raus."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [Forensik, KI-Erkennung, Workflow, Textanalyse, Provenance]
    related_skills: [ai-text-detection-lab, ai-watermark-toolkit, dewatermarking-pipeline, text-watermark-studio-lab]
---

# Text Forensics Workflow

## When to Use

- User hat eine konkrete Datei oder einen konkreten Text und will einen
  **begründeten forensischen Befund** — nicht nur "KI oder nicht?".
- Eingänge: TXT/MD, DOCX, PDF, HTML, gemischte Workflows (Copy/Paste,
  Pipeline-Ausgaben, verdächtige Rewrites).
- Methodik: `ai-text-detection-lab` (7 Analyseebenen) + Studio-Tools als
  Backend. Dieser Skill macht aus der Methodik einen ausführbaren Ablauf.

## Workflow-Übersicht

```
Datei → 1. Material sichern → 2. Text+Metadaten extrahieren → 3. Technische
Signale scannen → 4. Stil/Struktur analysieren → 5. (Optional) Referenz-
vergleich → 6. Evidenz gewichten → 7. Befund dokumentieren
```

## Schritt 1: Material sichern (Chain of Custody)

- Original-Datei UNVERÄNDERT kopieren (nie in-place arbeiten)
- SHA-256 der Originaldatei notieren (für den Befund)
- Datei-Metadaten erfassen: Erstellt/Geändert/Letzter Zugriff, Autor (nur
  wenn ethisch/rechtlich zulässig — bei fremden Dateien Datenschutz beachten)

```bash
sha256sum <datei>   # Windows git-bash: sha256sum, native: certutil -hashfile
```

## Schritt 2: Text + Metadaten extrahieren

| Quelle | Werkzeug |
|---|---|
| TXT/MD | direkt lesen (UTF-8!) |
| DOCX | `python -c "import docx; print(docx.Document('x.docx').paragraphs...)"` oder Studio-Dokument-API |
| PDF | Studio `pdf_strategy`/`pdf_extract_window` oder PyMuPDF (System-Python311: `/c/PROGRA~1/Python311/python.exe`, fitz 1.28) |
| HTML | Text-Layer extrahieren, Layout-Reste prüfen |

⚠️ Encoding: IMMER UTF-8 (`encoding='utf-8'`), sonst verfälschen die
Zeichen-Analysen.

## Schritt 3: Technische Signale scannen (hart, schnell)

1. **Unicode-Anomalien** (Zero-Width, RTL-Override, Bidi, Homoglyphen):
   ```bash
   python <skill-dir>/../../hermes/skills/ai-watermark-toolkit/scripts/unicode_sanitize.py <datei> --detect-only
   ```
   (Oder `ai-wm detect <datei>` — deckt Unicode + Marker in einem Rutsch)
2. **KI-Marker** (Stock-Opener, Buzzwords, Flexionen):
   ```bash
   python <skill-dir>/../../hermes/skills/ai-watermark-toolkit/scripts/marker_patterns.py <datei> --lang auto
   ```
3. **Format/Provenance:** Copy/Paste-Bruchstellen, Layout-Inkonsistenzen,
   wechselnde Schrift-/Absatzsignaturen, Metadaten-Widersprüche (Dokument
   "erstellt" vor dem Inhalt etc.)

## Schritt 4: Stil/Struktur analysieren (die 7 Ebenen aus ai-text-detection-lab)

Bewusst NACH den harten Scans (Befund aufbauen, nicht vorab fixieren):

1. **Statistik:** Satzlängenverteilung, Burstiness, Wiederholungsraten
   ```bash
   python -c "
   import sys, re
   t = open(sys.argv[1], encoding='utf-8').read()
   sents = [s for s in re.split(r'(?<=[.!?])\s+', t.strip()) if s]
   lens = [len(s.split()) for s in sents]
   print(f'Sätze: {len(sents)}, Ø-Länge: {sum(lens)/max(1,len(lens)):.1f}, Min: {min(lens) if lens else 0}, Max: {max(lens) if lens else 0}')
   print(f'Burstiness-Hinweis: {len(set(lens))} verschiedene Satzlängen / {len(lens)} Sätze')
   " <datei>
   ```
2. **Stil:** Ausgewogenheit, generische Verknüpfungen, Overexplaining, fehlende Kanten
3. **Semantik:** hohe Plausibilität bei geringer Dichte, keine situative Verankerung
4. **Struktur:** gleichförmige Absätze, standardisierte Gliederung, keine Abschweifung
5. **Linguistik:** Füllphrasen (Darüber hinaus/insgesamt/wichtig zu beachten), übervorsichtige Modalität
6. **Provenance:** Metadaten, Copy/Paste, Unicode (aus Schritt 3)
7. **Vergleich:** falls Referenztexte vorhanden (Tonalität, Satzlängen, Lieblingswörter)

## Schritt 5: Referenzvergleich (optional, aber stark)

Wenn Texte desselben Autors/Teams existieren:
- Satzlängen + Wortschatz der Referenz vs. Verdachtstext
- Lieblingswörter/Argumentmuster der Referenz im Verdachtstext?
- Abweichung von der Baseline ist oft das stärkste Signal

## Schritt 6: Evidenz gewichten (Score statt Bauchgefühl)

| Signal | Gewicht | Befund |
|---|---|---|
| Unicode-Stego (U+200B etc.) | hoch | technischer Nachweis |
| Marker high (Stock-Opener etc.) | hoch | stilistischer Nachweis |
| Burstiness fehlt (Ø-Länge ~konstant) | mittel | statistischer Hinweis |
| Generische Übergänge | mittel | stilistischer Hinweis |
| Fehlende situative Verankerung | mittel | semantischer Hinweis |
| Metadaten-Widerspruch | hoch | Provenance-Hinweis |
| Referenz-Abweichung | hoch | Vergleichshinweis |

## Schritt 7: Befund dokumentieren (Output-Format)

1. **Gesamturteil** (aus ai-text-detection-lab): niedrig/mittel/hoch/unklar
2. **Konfidenz** (niedrig/mittel/hoch — nie weglassen)
3. **Indikatoren** (mit Ebene + Gewicht)
4. **Gegenindikatoren** (natürliche Unsauberkeiten, inkonsistente Metadaten...)
5. **Kurzbegründung** (2-3 Sätze, nüchtern, forensisch)
6. **Dokument-/Vergleichssignale** (falls vorhanden)
7. **Empfohlene nächste Schritte** (z.B. "Referenztexte desselben Autors
   beschaffen", "Datei-Git-Historie prüfen", "Pipeline-Logs anfordern")

## Beispiel-Befund

- Gesamturteil: mittleres bis hohes KI-Risiko
- Konfidenz: mittel
- Hauptgründe: sehr gleichförmige Satzstruktur (Ø 14,2 Wörter, Range 8-19),
  generische Übergänge, 2× Stock-Opener-Marker, geringe situative Spezifität
- Gegenindikatoren: einzelne natürliche Unsauberkeiten, kein Unicode-Befund
- Nächster Schritt: Vergleich mit Referenztexten desselben Autors

## Quality Gate

- [ ] Original unverändert gesichert + SHA-256 notiert
- [ ] Harte Scans (Unicode + Marker) gelaufen, Ergebnisse dokumentiert
- [ ] ≥3 der 7 Analyseebenen bewertet
- [ ] Indikatoren UND Gegenindikatoren ausgewiesen
- [ ] Konfidenz explizit (nie falsche Sicherheit)
- [ ] Befund im Standard-Format (7 Felder)
- [ ] Nüchterner, forensischer Ton (kein "definitiv KI!", kein "100%")

## Pitfalls

- **Kein binäres Urteil** — Konfidenz + Gegenindikatoren sind Pflicht
- **Kurze Texte (<100 Wörter):** "unklar wegen zu wenig Kontext" ist ein valider Befund
- **Genre ignorieren:** ein juristisches Dokument IST formell — kein KI-Signal
- **In-place arbeiten:** Datei nie überschreiben, immer Kopie
- **Encoding-Fehler:** Nicht-UTF-8-Dateien verfälschen Unicode-Scans
- **Fremde Dateien:** Metadaten/Autor nur anfassen, wenn rechtlich/ethisch ok
- **Nicht mit dewatermarking-pipeline verwechseln:** dieser Skill ANALYSIERT, der andere ENTFERNT
