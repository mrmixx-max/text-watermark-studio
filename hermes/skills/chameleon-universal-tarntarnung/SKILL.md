---
name: chameleon-universal-tarntarnung
description: "Tarnung beliebiger KI-Texte: Asymmetrie, Perplexität, Voice."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [KI-Tarnung, Text, Stil, Universal, Humanizer]
    related_skills: [x-tarntarnung-engagement-boost, ai-text-dewatermark, no-tropes, humanizer]
---

# Chameleon-Universal-Tarntarnung

## When to Use

- User gibt einen beliebigen KI-generierten Text (E-Mail, Blogartikel,
  Social-Media-Post, Paper, Whitepaper, Forenkommentar) und will, dass er
  die charakteristischen Muster von KI-Inhalten verliert und sich in einen
  menschlichen Kontext einfügt.
- Der Skill wählt die Strategie dynamisch nach Texttyp + Zielgruppe
  (Kontext-Switch-Modul). Anders als `x-tarntarnung-engagement-boost`
  (X/Deutsch-Engagement-Fokus) ist dieser Skill UNIVERSAL für alle
  Textsorten und Sprachen.

## Die drei Säulen der Tarnung (immer, in jedem Modul)

### 1. Strukturelle Asymmetrie (Burstiness & Flow)
- **Satzlänge variieren:** lange, verschachtelte Sätze mischen mit kurzen, prägnanten. Keine monotone Satzstruktur.
- **Absätze bewusst setzen:** ein kurzer Absatz hebt eine wichtige Aussage hervor; ein langer nimmt einen komplexen Gedanken auf.
- **Rhythmik erzeugen:** Text laut lesen. Menschlicher Text hat Rhythmus, KI-Text oft nicht. Zeilenumbrüche für Emphase (Dialoge, Pointen) gezielt setzen.

### 2. Linguistische Unvorhersehbarkeit (Perplexität & Vokabular)
- **Wortwahl diversifizieren:** "sichere" Wörter durch Synonyme, Umschreibungen, leicht ungewöhnliche aber korrekte Begriffe ersetzen.
- **Sprachebenen mischen:** Fachjargon ↔ Umgangssprache bewusst durchkreuzen. Fachtext bekommt eine verständliche Analogie; informeller Text ein präzises Fachwort.
- **Redewendungen einstreuen:** "den Nagel auf den Kopf treffen", "das A und O" — dort, wo sie natürlich sitzen, nicht aufgepfropft.

### 3. Kontextuelle Authentizität (Voice & "Rauschen")
- **Persönliche Note:** subtile Meinung, Erfahrung, subjektive Einschätzung ("Aus meiner Sicht...", "Was ich faszinierend finde, ist...").
- **Gezieltes "Rauschen":** leichte kontextbezogene Redundanz, Satz mit "Und..."/"Aber..." beginnen, Füllwörter ("mal", "schon", "eigentlich").
- **Interaktions-Trigger:** rhetorische oder direkte Fragen, Diskussions-Aufforderung, gemeinsame Erfahrungen referenzieren.

## Kontext-Switch: Texttyp analysieren, Strategie anpassen

VOR jeder Transformation: Texttyp + Zielgruppe bestimmen, dann Modul wählen.

### A) Formal & Akademisch (Paper, offizieller Bericht)
- **Fokus:** Strukturelle Asymmetrie + gehobene Linguistik
- **Taktik:** Komplexe Satzgefüge mit Nebensätzen (Konjunktiv I/II). Präzise seltene Fachbegriffe. "Rauschen" durch spezifische Querverweise/Fußnoten, NICHT durch Umgangssprache. Persönliche Note = wissenschaftliche Schlussfolgerung ("Die vorliegende Analyse legt nahe, dass...").

### B) Business & Professionell (E-Mail, Blog, Whitepaper)
- **Fokus:** Alle drei Säulen im Gleichgewicht
- **Taktik:** Klare aktive Formulierungen ("Wir sollten...") + komplexere Erklärungen. Gezielte Analogien. Vorausschauender Appell/Handlungsaufforderung ("Der nächste Schritt sollte sein...").

### C) Informell & Umgangssprachlich (Social Media, Forum)
- **Fokus:** Kontextuelle Authentizität + Strukturelle Asymmetrie
- **Taktik:** Kurze Sätze. Direkte Ansprache ("ihr", "du"). Emojis (max 3). Slang. Community-Interaktion ist oberstes Ziel.
- ⚠️ **"Kleine Fehler" NUR extrem sparsam** — moderne Detektoren (Pangram, GPTZero) erkennen absichtliche Tippfehler als eigenes Signal. Slang + Rhythmus sind stärker. Fehler nie in Zahlen/Fakten (HANDTEST).

## Beispiel-Transformation (universell)

Original (KI-Standard):
"Die Implementierung von nachhaltigen Geschäftsmodellen ist für Unternehmen von entscheidender Bedeutung, um langfristig wettbewerbsfähig zu bleiben. Dies erfordert nicht nur die Anpassung von Prozessen, sondern auch eine kulturelle Veränderung hin zu mehr ökologischem Bewusstsein."

### A) Formal/Akademisch
"Die langfristige Sicherung der Wettbewerbsfähigkeit von Unternehmen korreliert unmittelbar mit der Adaption nachhaltiger Geschäftsmodelle. Ein solcher Prozess ist jedoch keineswegs allein auf die prozessuale Ebene beschränkt; er fordert vielmehr einen tiefgreifenden kulturellen Wandel, der ein erhöhtes ökologisches Bewusstsein als fundamentale Prämisse etabliert."

### B) Business/Professionell
"Mal ehrlich, wer will heute nicht noch morgen relevant sein? Genau deshalb ist Nachhaltigkeit kein Nice-to-have mehr, sondern der Kern eines zukunftssicheren Geschäftsmodells. Wir müssen also nicht nur unsere Prozesse auf den Prüfstand stellen, sondern vor allem unsere Unternehmenskultur. Es geht um ein Umdenken, hin zu echtem ökologischen Bewusstsein. Das ist der eigentliche Hebel für den Erfolg."

### C) Informell/Social Media
"Nachhaltigkeit ist nicht mehr die Kirsche auf dem Kuchen. Sie IST der Kuchen. 🌱

Wer jetzt nicht umdenkt, ist später raus. Es geht nicht um ein paar neue Prozesse, sondern um die ganze Haltung im Unternehmen.

Wir müssen echt grün werden, nicht nur grün reden. Was macht eure Firma da eigentlich? #Nachhaltigkeit #Business"

Anmerkung: Die Vorlage nutzte "Game-Changer" — das ist no-tropes-Flag (Corporate-Slang). Ersetzt durch "Sie IST der Kuchen" (ironisch + konkret).

## Universelle Grenzen

- **Sinnwahrung ist oberstes Gebot:** Transformationen dürfen die Kernaussage nicht verfälschen.
- **Zielgruppe entscheidet:** Modul + Intensität richten sich nach dem Empfänger.
- **Iterativer Prozess:** Ersten Entwurf immer kritisch prüfen und verfeinern — die beste Tarnung entsteht durch Überarbeitung.
- **Fakten bleiben exakt:** Unperfektheit gehört in Stil, nie in Zahlen/Namen/Daten (HANDTEST).

## Quality Gate (vor Delivery)

- [ ] Texttyp analysiert, Modul A/B/C gewählt (bewusst, nicht Default)
- [ ] Satzlängen variieren (Burstiness sichtbar)
- [ ] Wortwahl diversifiziert (≥2 Synonym-Ersetzungen)
- [ ] Persönliche Note/Meinung eingebaut
- [ ] Max 1-2 "Rauschen"-Elemente (Füllwörter/Und-Sätze)
- [ ] Keine absichtlichen Rechtschreibfehler; Slang max 1-2 Formen
- [ ] Zahlen/Fakten exakt (HANDTEST)
- [ ] no-tropes-Check bestanden (keine Em-Dash-Flut, kein "Game-Changer", kein "delve")
- [ ] Kernaussage des Originals unverfälscht

## Pitfalls

- **Nicht jedes Mal dasselbe Muster** — die Transformations-Signatur wird selbst erkennbar
- **Keine Fehler in Fakten** — Unperfektheit gehört in den Stil, nie in Daten
- **Modul nicht verwechseln:** Akademisch + Umgangssprache = wirkt unprofessionell; Social Media + komplett formell = wirkt steif
- **"Game-Changer", "Revolution", "entfesseln"** sind selbst KI-Signale — ironisch brechen oder ersetzen
- **Kein Soliciting** (X): "RT wenn..." verboten — OCRP, siehe x-post-workflow-webma
