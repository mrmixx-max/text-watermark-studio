"""Forensic Readiness Score (FRS, C6) — 12 Kriterien, 3 Gates, ehrliches Selbst-Assessment.

Was der Score ist: eine strukturierte, nachvollziehbare Selbst-Einschätzung
der forensischen Einsatzbereitschaft eines Detektor-/Befund-Produkts. Er
folgt der Literatur-Spec (Forensic-Readiness-Modelle: Was muss ein System
vorweisen, damit seine Befunde vor einer Prüfungskommission oder vor Gericht
bestehen können?) und übersetzt die Runde-3-Mapping-Ergebnisse in Zahlen.

Was der Score NICHT ist: ein Gütesiegel. ``basis="self_assessed"`` ist die
ehrliche Klammer — jede Kriterienzahl ist eine Selbst-Bewertung, keine
unabhängig validierte Messung. Der ``limit_note`` sagt das ausdrücklich:
Ohne eine Adversarial-Suite und ohne Korpus-Studie ist der Score
irreführend, wenn man ihn als „gerichtsverwendbar" liest.

Kriterien (je 0-5, max 60):
- T1-T4 (technical): Detektor keyed+deterministisch (5), FPR/FNR auf realem
  Korpus dokumentiert (2 — Lücke), Adversarial-Robustheit gemessen (3 —
  Attack-Matrix vorhanden, aber keine Vollstudie), Evidenzklassen A-D
  implementiert (5).
- L1-L4 (legal): Befund-Schema gerichtsfest dokumentiert (4), unabhängige
  Validierung/Peer-Review (0 — Lücke), DSGVO/Rechtsgrundlage dokumentiert
  (2 — Ansatz), Audit-Trail/Signatur HMAC+ML-DSA (3 — HMAC überall,
  ML-DSA nur CLI).
- O1-O4 (operational): Betriebs-Dokumentation (2 — Ansatz), Incident-Prozess
  (0 — Lücke), 100% lokal/keine Telemetrie (5), Redundanz (0 — Lücke).

Summe der Defaults: 5+2+3+5 + 4+0+2+3 + 2+0+5+0 = **31** von 60.

Gates (hart, nicht verhandelbar):
- G1 „FPR+FNR dokumentiert": **false** bis eine Korpus-Studie die Raten
  gemessen hat. Ohne sie ist jeder Score irreführend.
- G2 „Paradox-Risiko < 20%": **true** — die ΔZ-Messung belegt den
  Signalabfall bei Shuffle (z 13.6 -> 0.0, removed:true); das „Cleaner
  entfernt das Signal"-Paradoxon ist damit gemessen.
- G3 „Cross-Session-Reproduzierbarkeit": **true** — deterministisch
  (gleicher Text/Key -> gleiche finding_id, F-xxxxxxxx).

Verdict-Regeln (bewusst streng):
- ``FORENSIC_READY``: Score >= 40 UND alle Gates erfüllt UND Basis
  ``validated`` (unabhängig bestätigt). Ein reines Selbst-Assessment kann
  diesen Status nicht erreichen — sonst wäre der Score ein Selbst-Gütesiegel.
- ``CONDITIONALLY_READY``: Score >= 40 UND alle Gates erfüllt, aber Basis
  noch ``self_assessed`` — einsatzbereit unter der Bedingung, dass eine
  unabhängige Validierung die Selbst-Bewertung bestätigt.
- ``NOT_FORENSIC_READY``: alles andere — Score < 40 ODER ein Gate offen
  (G1 ist aktuell offen, also ist der Default-Befund NOT_FORENSIC_READY;
  das ist die ehrliche Aussage dieses Moduls).

Aufruf::

    compute_frs()                                  # Defaults, score 31, NOT
    compute_frs(scores={"T2": 5}, gates={"G1": {"met": True}})
    compute_frs(basis="validated")                 # hebt auf FORENSIC/CONDITIONAL
"""

from __future__ import annotations

# Kriterien-Katalog: id -> (gruppe, label, default 0-5).
CRITERIA: dict[str, dict] = {
    "T1": {"group": "technical", "default": 5, "label": "Detektor ist keyed und deterministisch (reproduzierbar)"},
    "T2": {"group": "technical", "default": 2, "label": "FPR/FNR auf realem Korpus dokumentiert (Studie)"},
    "T3": {"group": "technical", "default": 3, "label": "Adversarial-Robustheit gemessen (Attack-Matrix)"},
    "T4": {"group": "technical", "default": 5, "label": "Evidenzklassen A-D implementiert (Anti-Hype-Regeln)"},
    "L1": {"group": "legal", "default": 4, "label": "Befund-Schema gerichtsfest dokumentiert"},
    "L2": {"group": "legal", "default": 0, "label": "Unabhängige Validierung / Peer-Review"},
    "L3": {"group": "legal", "default": 2, "label": "DSGVO / Rechtsgrundlage dokumentiert"},
    "L4": {"group": "legal", "default": 3, "label": "Audit-Trail / Signatur (HMAC überall, ML-DSA CLI)"},
    "O1": {"group": "operational", "default": 2, "label": "Betriebs-Dokumentation (Runbooks)"},
    "O2": {"group": "operational", "default": 0, "label": "Incident- / Fehlerprozess etabliert"},
    "O3": {"group": "operational", "default": 5, "label": "100% lokal / keine Telemetrie"},
    "O4": {"group": "operational", "default": 0, "label": "Redundanz / Ausfallsicherheit"},
}

# Gates: hart, nicht verhandelbar (G1 blockiert aktuell FORENSIC_READY).
GATES: dict[str, dict] = {
    "G1": {
        "label": "FPR+FNR auf einem Korpus dokumentiert",
        "met": False,
        "note": "false bis Korpus-Studie — ohne gemessene FPR/FNR ist der Score irreführend",
    },
    "G2": {
        "label": "Paradox-Risiko < 20% (ΔZ-Messung)",
        "met": True,
        "note": "true — delta_z-Messung belegt Signalabfall bei Shuffle (z 13.6 -> 0.0, removed:true)",
    },
    "G3": {
        "label": "Cross-Session-Reproduzierbarkeit",
        "met": True,
        "note": "true — deterministisch: gleicher Text/Key -> gleiche finding_id",
    },
}

MAX_SCORE = 60
FORENSIC_THRESHOLD = 40


# Ehrliche Klammer: ohne Adversarial-Suite und ohne Korpus-Studie ist der
# Score als „Gerichtstauglichkeits-Notenschnitt" irreführend.
LIMIT_NOTE = (
    "Selbst-Assessment (basis=self_assessed): Score ohne unabhängige "
    "Validierung und ohne Korpus-Studie (T2=2, G1=false) ist irreführend, "
    "wenn er als Nachweis gerichtlicher Verwendbarkeit gelesen wird — die "
    "Zahlen belegen das Vorhandensein von Mechanismen, nicht deren "
    "empirische Wirkung unter realen Bedingungen."
)


def _clamp(value, lo: int = 0, hi: int = 5) -> int:
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return lo


def compute_frs(scores: dict | None = None, gates: dict | None = None, *, basis: str = "self_assessed") -> dict:
    """Berechnet den Forensic Readiness Score (12 Kriterien, 3 Gates).

    ``scores``: optionale Overrides je Kriterium (``{"T2": 5}``); nicht
    genannte Kriterien behalten die ehrlichen Defaults aus dem
    Runde-3-Mapping. ``gates``: optionale Overrides je Gate — entweder
    ``{"G1": {"met": True, ...}}`` oder ``{"G1": True}``.

    Rückgabe (JSON-fähig, für den finding-Report-Block): ``score`` (0-60),
    ``max_score``, ``basis``, ``criteria`` (je Gruppe/Label/Score/Max),
    ``gates`` (je met/label/note), ``verdict``, ``limit_note``.
    """
    eff = {k: c["default"] for k, c in CRITERIA.items()}
    if isinstance(scores, dict):
        for k, v in scores.items():
            if k in eff:
                eff[k] = _clamp(v)

    gate_met: dict[str, bool] = {}
    for gid, g in GATES.items():
        override = gates.get(gid) if isinstance(gates, dict) else None
        if isinstance(override, dict):
            met = bool(override.get("met", g["met"]))
        elif override is not None:
            met = bool(override)
        else:
            met = g["met"]
        gate_met[gid] = met

    total = sum(eff.values())
    all_gates = all(gate_met.values())
    if basis != "validated":
        basis = "self_assessed"  # nur ein explizit validierter Status zählt

    if total >= FORENSIC_THRESHOLD and all_gates:
        verdict = "FORENSIC_READY" if basis == "validated" else "CONDITIONALLY_READY"
    else:
        verdict = "NOT_FORENSIC_READY"

    return {
        "score": total,
        "max_score": MAX_SCORE,
        "basis": basis,
        "criteria": {
            k: {
                "score": eff[k],
                "max": 5,
                "group": CRITERIA[k]["group"],
                "label": CRITERIA[k]["label"],
            }
            for k in CRITERIA
        },
        "gates": {
            gid: {
                "met": gate_met[gid],
                "label": GATES[gid]["label"],
                "note": GATES[gid]["note"],
            }
            for gid in GATES
        },
        "verdict": verdict,
        "limit_note": LIMIT_NOTE,
    }
