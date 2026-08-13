# Measurement First — das Manifest

> Warum Text Watermark Studio ein Instrument ist, das nicht lügt — und warum das im aktuellen Markt das härteste Asset überhaupt ist.

## Die Lage

Der Markt für „AI-Wasserzeichen-Werkzeuge" spaltet sich in zwei Sorten. Die erste verkauft **Claims**: Werkzeuge, die Signale entfernen oder erkennen sollen, ohne dass jemand ihre Wirkung messen kann. Die zweite verkauft **Messung**: Werkzeuge, deren Befunde mit Zahlen, Kontrollgruppen und reproduzierbaren Befehlen kommen.

Text Watermark Studio gehört zur zweiten Sorte — durchgehend, in jedem Modul.

## Grundsatz: Kein Detektor, kein Urteil

Ein Befund ohne Messung ist ein Ritual. Deshalb gilt im Studio:

- Jede Detektion liefert **Z-Score, Green-Rate, Tokenzahl, p-Wert und Verdict** — keine „AI-Confidence %".
- Jede keyed-Verifikation hat **Kontrollgruppen**: right-key, wrong-key und unmarkierte Baseline.
- Jede Grenze ist **veröffentlicht und reproduzierbar** — nicht versteckt.

Gemessene Realität (2026-08, Attack-Matrix, EuroLLM-9B-E2E):

| Messung | Wert | Bedeutung |
|---|---|---|
| Right-key (KGW, 304 Tokens) | z = 15.9 | Der richtige Schlüssel schreit. |
| Wrong-key | z = −0.2 | Der falsche Schlüssel schweigt. |
| Unmarkierte Kontrolle | z = 0.6 | Kein Signal ohne Marke. |
| Word-Shuffle | ΔZ ≈ −12.8 | Starke lexikalische Zerstörung kollabiert das Signal — und den Text. |
| Stil-Rewrite / Dilute | ΔZ ≈ 0 bis −2 | Paraphrase-ähnliche Angriffe halten das Signal. |
| Redlist (Vorzeichen) | z = −11.55 | z < 0 = Redlist-Unterdrückung — sichtbar, nicht versteckt. |
| Kontextfenster c=4 | z = 9.75 | Richtig markiert + richtig detektiert = starkes Signal. |
| Kontextfenster falsch (c=1/2/8) | z ≈ 0.3 bis 1.3 | Falsche Annahme → Signal kollabiert. |

Diese Grenzen decken sich wörtlich mit dem, was Plattform-Anbieter selbst über ihre Marken dokumentieren (Paraphrase, Editing und Übersetzung schwächen Marken; kurze Passagen sind unzuverlässig). **Ehrlichkeit ist kein Bug, sondern das Feature.**

## Das Repo jagt seine eigenen Fehler

Qualität ist keine Behauptung, sondern Prozess. Der Audit-Zyklus des Studios:

1. Autonome Agenten prüfen das Repo read-only mit harter Qualitätsschwelle: Ein Befund zählt nur mit Code-Zeile + reproduzierbarem Beweis.
2. Gefundene Fehler werden **gefixt + mit Regressionstests abgesichert**, nicht wegerklärt.
3. Die CI muss grün sein — auch wenn eine neue Framework-Version das Verhalten ändert (die Wurzel wird gefunden, nicht der Test verbogen).

Verifizierte Audit-Befunde (2026-08), alle gefixt und getestet:

- Doku-Lüge im Multi-Agent-Modul → Doku korrigiert, Test abgesichert.
- API-Secret-Leak (`GET /keys` gab Registry-Secrets aus) → Secrets werden gestrippt, sensitive Routen auth-geschützt, CORS ohne Credentials.
- Web-UI/API-Vertragsbruch (422 bei jedem Klick) → Manifest auf echte Routen abgeglichen.
- fastapi-Versions-Breaking-Change (0.137+ verschachtelt Router) → Test versionsunabhängig, gegen zwei Versionen verifiziert.

## Der Stack

- **247 automatisierte Tests** (0 failed, CI grün auf Windows + Linux)
- **12-Stufen-Burn-in** inklusive KGW-E2E gegen ein echtes Modell
- **19 CLI-Subcommands** mit hartem Exit-Code-Contract (0 = sauber, 1 = Funde, 2 = Input-Fehler)
- **20 TUI-Aktionen**, **5 API-Routen**, **53 MCP-Tools** — jeder Pfad testbar, keine Stubs
- **0 €, MIT, Open Source** — der Code liegt auf GitHub, damit jeder die Messungen nachbauen kann
- Kern lokal, deterministisch, offline — keine Cloud, kein Tracking, keine Datenabflüsse

## Was das Studio nicht kann (und sagt, dass es es nicht kann)

- Kein Zugriff auf Plattform-Schlüssel (z.B. SynthID) — Verifikation dort nur über die Plattform.
- Keine „99 %"-Claims — Stil-Heuristik ohne Schlüssel ist Evidenz, kein Beweis.
- Paraphrase schwächt statistische Wasserzeichen — die Attack-Matrix misst, wie stark.
- Kein Plagiats-Crawler — nur Ähnlichkeit zu *Ihren* Dokumenten.
- Kein Allheilmittel gegen entschlossene Angreifer — aber dokumentierte, messbare Robustheit.

Diese Liste steht in der Doku, nicht nur im Marketing. **Ehrlichkeit ist das Produkt.**

---

*Stand: 2026-08-13 · Text Watermark Studio 2.0 · by Erik Gieske · MIT*
