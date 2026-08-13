# TWS Bau-Liste (Build List)

> Lebendiges Dokument. Stand: 2026-08-13, nach Runde-2-Forschung (Markt + Repo + Literatur).
> Regel: **Kein Block startet, bevor die laufenden Agents abgeschlossen sind.** Stale > 7 Tage → killen.
> KPI-Basis: 290 Tests · 76 MCP-Tools · Commit `696d903`.

## Status der laufenden Agents (13.08.2026, ~13:15)

| Agent | Auftrag | Status |
|---|---|---|
| `deleg_ea4bc6c9` | Literatur Runde 2 (Umsetzungs-Skizzen: Signature Filtering, E-Value, ML-DSA, FRS) | 🔄 läuft |
| `deleg_dc1517ef` | Fix F1-F3 (Embed-Auth, report-Key, Secret-Tracking) | 🔄 läuft |
| `deleg_b2405b0d` | Markt Runde 2 (Käufer/Vertrieb/Bewegungen) | ✅ fertig → `Downloads/tws-markt-runde2-2026.md` |
| `deleg_a6649650` | Repo Runde 2 (6 Funde) | ✅ fertig → F1-F3 in Fix, F4-F6 unten |

## Block A — Security & Gerichtsfestigkeit (LÄUFT, `deleg_dc1517ef`)

- [ ] F1: `require_api_key` auf Embed/Keys + alle Secret-Routen (401-Tests)
- [ ] F2: `report --key` Registry-Auflösung (falsches Negativ fixen, Regressionstest)
- [ ] F3: Key-Registry aus git (gitignore), Demo-Key-On-Demand, atomic writes, `--key-file`
- ⏳ danach: KPI-Sync wenn Testzahl steigt (Katalog/Manifest/PDFs)

## Block B — Repo-Performance & UI-Konsistenz (nächste Fix-Runde, wartet auf A)

- [ ] F4: MinHash 1×SHA256+XOR statt 128×SHA256, Corpus-Signatur-Cache, TUI async
- [ ] F5: TUI keyed-detect (detect_multi_key), level/context durchreichen, file-embed/detect Registry statt Demo-Key
- [ ] F6: API-Detect Doppel-Berechnung entfernen, `embed_kgw` deprecaten/entfernen + Docstring angleichen

## Block C — Produkt & Markt (Markt-Empfehlungen Q3 2026)

| # | Kandidat | Aufwand | USP-Bezug | Priorität | Abhängigkeit |
|---|---|---|---|---|---|
| C1 | **Repo-Relabeling: "unabhängige Verifikation"** (README-Tagline, PyPI-Description von "Detect, clean, dilute" umstellen, bei 0 Stars) | S | Positionierung | 1 | — |
| C2 | **Windows-Desktop-App + Installer** (PySide6-GUI als dünner Wrapper um Core + PyInstaller + Inno Setup + CI `build-desktop.yml`; Code-Signing optional) | M-L | Institutional-Verkauf (€149-499 Kanzleien, €490-1.490 Unis) | 2 | Markt-Bestätigung ✅; Signing-Entscheidung (Budget) |
| C3 | **Verifikations-Report als Produkt** (signierte Befunde: JSON+PDF, HMAC/ML-DSA, auditierbar; deckt Feature-Research-Top-1 + Markt-Prio-1) | S-M | Gerichtsfestigkeit, Institutional | 1 | Block A (F2), Literatur-Skizze ML-DSA |
| C4 | **ΔZ-Check als Service** (web, IMATAG-Muster, per-Authentifizierung) | M | Cleaner-Moat, Verifikation | 3 | C3; vor Anthropic-Detektor (Q4 26/Q1 27) |
| C5 | **KI-Erklärungs-Report-Modul** (kostenlos für 5-10 Pilot-Prüfungsämter im Ouriginal-Migrationsfenster) — **Blaupause: `dissertation-ai-authorship-audit`** (Evidenzklassen A-D, Befund-Schema, 12-Schritte-Workflow, 15-Abschnitt-Report, Prüfpriorität 0-5 statt Schuld-Scoring) | M | Institutions-Play | 3 | C3 |

## Block D — Forschung → Bau (Literatur Runde 1+2 ABGESCHLOSSEN, Skizzen geliefert)

**Verifizierte Entwarnung:** Greenlist-Hash-Bias-Prüfung (Literatur-Fund `byte % 100` verzerrt 8,6 %) → TWS nutzt `int(h[:8],16)/0xFFFFFFFF` — gemessen 0,499985 bei 200K Samples, **sauber**. Kein Fix nötig.

| # | Kandidat | Quelle | Aufwand | Priorität | Umsetzungs-Stand (Runde 2) |
|---|---|---|---|---|---|
| D1 | E-Prozess-Detektion (E-Wert statt/nach Z-Score; Early-Stop, Bonferroni via `E_max ≥ K/α`) | 2602.17608, 2607.21958 | S-M | **1** | ✅ Formel + Code-Skizze (20 Zeilen), Demo: schwaches Signal z=0.01 vs e=0.10; δ fix ok (Validität δ-unabhängig) |
| D2 | ML-DSA-Befund-Signatur (FIPS 204) | FIPS 204 | S | **1** | ✅ Komplette API verifiziert + Größen/Perf gemessen (MLDSA-44: 2420 B sig, ~1.7 ms); 5 Fallstricke (verify-Reihenfolge, PrivKey=Seed, non-deterministisch, sign_mu 64 B, context b"") |
| D3 | Signature Filtering — **ehrlich eingeordnet: primär FPR-Kontrolle** (98%→0% bei dominantem Token verifiziert), 78-99%-TPR-Claim braucht MILP-Lernset (nicht naiv erreichbar) | 2606.18430v2 | S-M | 2 | ✅ Heuristik-Skizze (Frequenz/χ²-Filter); kein öffentlicher Code gefunden |
| D4 | FRS-Report-Gates (G1 FPR/FNR dokumentiert+rechenbar, G2 Paradox-Rate <20%, G3 Cross-Session) | 2607.16010 | M | 2 | ✅ Pflicht-Feld-Liste pro Gate; **Report ehrlich "NICHT FORENSIC READY" kennzeichnen solange G1-G3 unbelegt** |
| D5 | Threat-Model.md (SeedHijack-PRNG, DHMark, C2PA-Lücke) | 2605.28632, 2608.03093, 2604.24890 | S | 3 | Skizze aus Runde 1 |
| D6 | CORE-BREW-LLR-Kalibrierung (δ automatisch aus Hit-Rate p*), Power-Calibrated (γ/δ-Wahl), Forensics-Info-Profile (Payload-Stufe) | 2606.24163, 2607.05694, 2607.13003 | M | 3 | Neu aus Runde 2, nach D1-D3 |

## Kill-Kandidaten (bewusst nicht bauen)

- Voller C2PA-Chain-Verify (Scope-Spread), Plagiats-Crawler, HSM/OS-Keyring, eigener "Cleaner ohne Nachweis"

## GUI-Eintrag (Detail, aufgenommen 13.08.2026)

**Windows-Desktop-App + Installer** — Priorität 2 in Block C, NICHT vor Abschluss von Runde-2-Agents starten.
- Oberfläche: PySide6, dünner Wrapper um existierende Core-Logik (kein Server), Screens: Datei-Auswahl → Detect (Verdict, Z-Score, Redlist-Badge) → Report-Export (JSON/PDF, signiert) → Key-Manager
- Installer: PyInstaller → Inno Setup (`tws-desktop-setup.exe`); CI-Workflow `build-desktop.yml` auf `windows-latest`
- Hürden: Bundle ~100-200 MB (CLI bleibt schlank), Code-Signing ~$100-300/Jahr (SmartScreen; für Institutionen Pflicht — Budget-Entscheidung)
- Markt-Link: Institutional-Edition (€149-499 Kanzleien via Gumroad, €490-1.490 Unis); Prüfungsämter kaufen kein CLI
- Abhängigkeiten: C3 (Verifikations-Report als Kern-Feature der App), Block A abgeschlossen

---
*Nächste Aktualisierung: nach Abschluss von `deleg_ea4bc6c9` + `deleg_dc1517ef`.*
