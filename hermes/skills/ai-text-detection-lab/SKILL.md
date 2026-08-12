---
name: ai-text-detection-lab
description: "Multi-Signal KI-Text-Erkennung: Stil, Statistik, Provenienz."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [KI-Erkennung, Textforensik, Detection, Provenance, Analyse]
    related_skills: [ai-text-forensik, claude-watermark-detection, ai-watermark-toolkit, chameleon-universal-tarntarnung]
---

# AI Text Detection Lab

## When to Use

- User will systematisch prüfen, ob ein Text KI-generiert sein könnte:
  Content-Review, Provenance-Prüfung, Pipeline-Audit, Verdachtsfall-Einordnung.
- Für echte Forensik mit mehreren Signalebenen — NICHT für schnelle
  Ja/Nein-Urteile. Wenn nur ein einzelnes Signal gefragt ist, reicht
  `ai-text-forensik` oder `claude-watermark-detection`.
- Gegenstück zu den Tarn-Skills (`chameleon-universal-tarntarnung`,
  `x-tarntarnung-engagement-boost`): Dieser Skill erkennt, was jene
  entfernen sollen.

## Leitidee

KI-Texte hinterlassen selten ein einzelnes Signal — meist ein Muster aus
mehreren schwachen Indikatoren: zu glatte Satzrhythmen, wenig Reibung,
stereotypische Übergänge, gleichmäßige Komposition, auffällige
Wortverteilungen, unnatürliche Wiederholungen, inkonsistente Stilsprünge.

**Kein einzelner Indikator beweist KI-Nutzung.** Gute Erkennung arbeitet
mit Wahrscheinlichkeit, Evidenzgewichtung und Kontext — nie mit binären
Behauptungen.

## Die 7 Analyseebenen

### 1. Statistische Signale (formale Muster, ohne Inhaltsinterpretation)
- Wortfrequenzverteilungen, N-Gramm-Muster, Perplexity-Auffälligkeiten
- Burstiness + Variationsbreite, Satzlängenverteilung
- Token-/Zeichenrhythmus, Wiederholungsraten, Übergangswahrscheinlichkeiten, Entropiemuster
- ⚠️ Stark von Stil, Genre und Prompting beeinflusst — nur Teil eines größeren Befunds

### 2. Stilistische Signale (wie der Text klingt)
- Übermäßige Ausgewogenheit, gleichförmige Satzarchitektur, zu saubere Abschnitte
- Häufige generische Verknüpfungen, wiederkehrende Metasprache, Overexplaining
- Mangel an echten stilistischen Kanten, fehlende persönliche Eigenheiten, eingeebnete Tonalität
- Kern: viele KI-Texte sind nicht falsch, sondern **zu symmetrisch** — Form, aber wenig Reibung

### 3. Semantische Signale (zu perfekt / zu allgemein)
- Allgemeine Aussagen ohne konkrete Verankerung
- Hohe Plausibilität bei geringer Dichte, geringe innere Überraschung
- Wiederholung bekannter Argument-Schemata
- Hohe semantische Kohärenz bei niedriger situativer Spezifität
- Fehlende gelebte Referenzen, vorsichtige ausweichende Schlussfolgerungen

### 4. Strukturelle Signale (Makrostruktur)
- Gleichförmige Absatzlängen, standardisierte Einleitung-Mittelteil-Schluss
- Wiederkehrende Listenmuster, vorhersagbare Argumentbewegung, zu saubere Gliederung
- Fehlende Abschweifung, kaum natürliche Umwege, keine echte Eskalation
- Menschen springen, setzen nach, holen aus, relativieren, korrigieren sich — KI glättet weg

### 5. Linguistische Signale (Oberfläche + Grammatik)
- Typische Füllphrasen, zu häufige Konnektoren, übervorsichtige Modalität
- "im Wesentlichen", "darüber hinaus", "insgesamt", "wichtig zu beachten"
- Überkorrekte Formulierungen, zu wenige idiosynkratische Wortwahlen
- Kernfrage: klingt es wie eine Person mit Denkspur oder wie ein generisch optimierter Antwortkörper?

### 6. Provenance- und Format-Signale (nur wenn Dokumente vorliegen)
- Erstellungs-/Bearbeitungsmetadaten, Copy/Paste-Indizien, Formatbruchstellen
- Unicode-Anomalien, Zero-width-Zeichen, Layout-Störungen
- Unterschiedliche Schrift-/Absatzsignaturen, Wechsel maschinell/manuell
- Inkonsistenzen zwischen Inhalt und Dokumentstruktur
- Besonders wertvoll bei PDF, DOCX, Webseiten, gemischten Workflows

### 7. Vergleichs- und Autorensignale (nur mit Referenztexten)
- Tonalitätskonstanz, typische Satzlängen, Lieblingswörter, Argumentmuster
- Wiederkehrende rhetorische Bewegung, Formulierungspräferenzen, Strukturgewohnheiten
- Oft robuster als Einzeltext-Detektion: misst **Abweichung von bekannter Baseline**

## Methodenspektrum (je nach Zugriff kombinieren)

| Weg | Für | Kern |
|---|---|---|
| A. Reine Textanalyse | Keine Zusatzdaten | Stil-/Strukturvergleich, Häufigkeits-/Musteranalyse, heuristische Indikatoren, multidimensionale Score-Kombination |
| B. Dokumentanalyse | Office/PDF/HTML | Text+Metadaten-Extraktion, Unicode-/Stego-Checks, Format-/Layout-Prüfung, Versionsvergleich |
| C. Vergleichende Analyse | Bekannte Autoren/Teams | Autorenprofiling, Stilabweichung, Segmentvergleich, Vorher/Nachher-Differenzen |
| D. Pipeline-Analyse | Automatisierte Prozesse | LLM-Rewrite-Erkennung, Rohtext→Finaltext-Übergänge, Prompt-Template-Spuren, Multi-Agent-Signale, wiederholte semantische Glättung |
| E. Hybrid-Analyse | Alles verfügbar | Kontextgewichtung, Evidenzfusion, Unsicherheitsmodell, Priorisierung stärkster Signale |

## Bewertungslogik (nie binär)

Mögliche Ausgabeformen:
- niedriges KI-Risiko
- gemischtes Profil
- mittleres KI-Risiko
- hohes KI-Risiko
- stark KI-typisches Muster
- unklar wegen zu wenig Kontext

WICHTIG: Signalgruppen einzeln ausweisen, damit die Einschätzung
nachvollziehbar bleibt.

## Output-Format

1. **Gesamturteil** (eine der Stufen oben)
2. **Konfidenz** (niedrig/mittel/hoch)
3. **Wichtige Indikatoren** (mit Signal-Ebene)
4. **Gegenindikatoren** (was dagegen spricht)
5. **Kurzbegründung** (2-3 Sätze, forensisch)
6. **Dokument-/Vergleichssignale** (falls vorhanden)
7. **Empfohlene nächste Prüfungsschritte**

Beispiel:
- Gesamturteil: mittleres bis hohes KI-Risiko
- Konfidenz: mittel
- Hauptgründe: sehr gleichförmige Satzstruktur, generische Übergänge, geringe situative Spezifität
- Gegenindikatoren: einzelne natürliche Unsauberkeiten, inkonsistente Metadaten
- Nächster Schritt: Vergleich mit Referenztexten desselben Autors

## Wichtige Einschränkungen (Pflicht, nicht optional)

- Stilistische Perfektion beweist KEINE KI
- Menschliche Texte können KI-ähnlich wirken, KI-Texte können menschlich wirken
- Kurze Texte sind schwieriger zuverlässig zu bewerten
- Genre, Fachgebiet und Redaktionsstil beeinflussen die Signale stark
- Ohne Referenzdaten sinkt die Sicherheit
- Der Skill kann Muster erkennen, Wahrscheinlichkeiten gewichten, Befunde transparent machen — NIE absolute Wahrheit liefern

## Tonalität des Skills

Nüchtern, präzise, forensisch, modular, klar dokumentierend, frei von
Marketing-Sprache. Wie ein ernstes Analysewerkzeug, nicht wie ein
Buzzword-Produkt.

## Quality Gate (vor Delivery)

- [ ] ≥3 Signal-Ebenen analysiert (nicht nur Stil)
- [ ] Indikatoren UND Gegenindikatoren ausgewiesen
- [ ] Konfidenz explizit benannt (nie falsche Sicherheit)
- [ ] Kein binäres Ja/Nein als Allein-Aussage
- [ ] Einschränkungen erwähnt (kurzer Text, fehlende Referenzen, Genre-Einfluss)
- [ ] Nächste Prüfungsschritte genannt
- [ ] Nüchterner Ton (kein "revolutionär", kein "100% sicher")

## Pitfalls

- **Nicht auf ein einzelnes Signal reduzieren** — der Kern des Skills ist Multi-Signal
- **Keine "100% KI"-Behauptung** — immer Konfidenz + Gegenindikatoren
- **Kurze Texte (<100 Wörter) nicht überbewerten** — als "unklar wegen zu wenig Kontext" ausweisen
- **Genre ignorieren** — ein rechtliches Dokument IST formell; das ist kein KI-Signal
- **Tarn-Skills verwechseln** — dieser Skill ERKENNT, `chameleon`/`x-tarntarnung` ENTARNEN
