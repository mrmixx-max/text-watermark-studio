"""KI-Erklärungs-Befund (C5, 2026-08-13) — Evidenzklassen statt Schuld-Scoring.

Blaupause: ``dissertation-ai-authorship-audit`` (Evidenzklassen A-D,
Befund-Schema, Prüfpriorität 0-5 statt Schuld-Scoring). Dieses Modul
übersetzt DETEKTOR-Ergebnisse (detect_multi_key, e_value, delta_z) in einen
strukturierten Befund, der vor einer Prüfungskommission oder vor Gericht
hält: Fakten und Interpretation getrennt, >= 2 Gegenhypothesen je Befund,
entlastende Aspekte, ehrlicher ``verdict_text``.

ANTI-HYPE-REGEL (verbindlich, keine Ausnahme)
---------------------------------------------
- Ein **z-Score oder e-Wert ist ein TECHNISCHER INDIKATOR (Evidenzklasse C)
  und NIE allein beweisend.** Klasse A erfordert ein reproduzierbares,
  keyed-Verifikations-Artefakt (Redlist-Vorzeichen, Bonferroni-adjustierter
  p-Wert, konsistente Segmente). Klasse B erfordert einen Vergleich
  (ΔZ mit removed:true). Klasse D (Kontext) ist aus dem Text NICHT ableitbar —
  fehlt die institutionelle Regel/Entstehungshistorie, wird
  ``context_missing: true`` gesetzt und die Aussagekraft ehrlich begrenzt.
- ``priority`` (0-5) beschreibt den **PRÜFBEDARF**, nie eine
  Schuld-Wahrscheinlichkeit und nie eine KI-Wahrscheinlichkeit.
- „Herkunft nicht bestimmbar" ist eine legitime Schlussfolgerung;
  „KI-generiert" ist NIE eine Feststellung dieses Moduls — erlaubt ist nur
  die Formulierung „mit KI-Unterstützung vereinbar, beweist es nicht".

Ein einzelner Befund ist nie ein Urteil. Der Report ist ein
Prüf-Artefakt für Fachpersonen, die den Kontext (Gespräch,
Entstehungshistorie, institutionelle Regel) einbringen.
"""

from __future__ import annotations

import hashlib
import json

# Default significance level for the Bonferroni-adjusted p-value gate (Klasse A).
DEFAULT_ALPHA = 0.05

# Threshold for the keyed verification artifact (|z| >= 4 is the product's
# watermark_detected / redlist_detected boundary).
Z_THRESHOLD = 4.0

# Context keys that count as "institutionelle Regel / Entstehungshistorie".
# Anything else in `context` is not enough to lift the context_missing flag.
CONTEXT_KEYS = ("institutional_rule", "origin_history", "rules", "history",
                "institution")

# ---------------------------------------------------------------- internals
def _context_missing(context) -> bool:
    """True when no institutional rule / origin history was supplied.

    A falsy context or a dict without any of CONTEXT_KEYS means the caller
    provided no context dimension at all — the honest finding is that the
    evidentiary power is limited (Evidenzklasse-D-Abhängigkeit).
    """
    if not context:
        return True
    if not isinstance(context, dict):
        return False  # some opaque context was given; treat as provided
    return not any(context.get(k) for k in CONTEXT_KEYS)


def _segments_consistent(result: dict, threshold: float = Z_THRESHOLD) -> bool:
    """Klasse-A gate: all segment mean-Z values above the threshold.

    ``segments`` is a list of dicts carrying ``mean_z`` (or ``z``). At least
    two segments must be present — a single segment is just the whole text
    and proves nothing beyond the global Z-test.
    """
    segs = result.get("segments")
    if not isinstance(segs, (list, tuple)) or len(segs) < 2:
        return False
    for s in segs:
        if not isinstance(s, dict):
            return False
        z = s.get("mean_z")
        if z is None:
            z = s.get("z")
        if not isinstance(z, (int, float)) or z <= threshold:
            return False
    return True


def _category(result: dict) -> str:
    """Befund-Kategorie: Redlist / Delta-Z / E-Wert / Signatur / Detektion."""
    verdict = str(result.get("verdict") or "")
    if "redlist" in verdict:
        return "Redlist"
    if result.get("removed") is not None or "z_before" in result:
        return "Delta-Z"
    if "e_value" in result and "detected" in result:
        return "E-Wert"
    if "signature_filtered" in result:
        return "Signatur"
    return "Detektion"


def _technical_class(result: dict, alpha: float) -> str:
    """Evidenzklasse A/B/C aus den technischen Indikatoren.

    - A: Redlist-Vorzeichen (reproduzierbares, keyed-Verifikations-Artefakt),
      Bonferroni-adjustierter p-Wert < alpha, konsistente Segmente.
    - B: Vergleichsbefund (ΔZ mit removed:true).
    - C: alles andere — z-Score und e-Wert sind NIE allein beweisend.
    """
    verdict = result.get("verdict")
    if verdict == "redlist_detected":
        z = result.get("z_score")
        signal = result.get("signal")
        if signal == "redlist" or (isinstance(z, (int, float)) and z < 0):
            return "A"
    p_adj = result.get("best_p_adjusted")
    if isinstance(p_adj, (int, float)) and p_adj < alpha:
        return "A"
    if _segments_consistent(result):
        return "A"
    if result.get("removed") is True:
        return "B"
    return "C"


def _finding_id(result: dict, category: str, key_id: str) -> str:
    """Deterministische Befund-ID (F-xxxxxxxx): gleicher Text/Key -> gleiche ID.

    Gehasht wird die kanonische Evidenz (key_id, Kategorie, verdict und die
    tragenden Zahlen), nicht der Zeitpunkt — ein Befund ist reproduzierbar.
    """
    evidence = {
        "key_id": key_id,
        "category": category,
        "verdict": result.get("verdict"),
        "z_score": result.get("z_score"),
        "p_value": result.get("p_value"),
        "best_p_adjusted": result.get("best_p_adjusted"),
        "e_value": result.get("e_value"),
        "delta_z": result.get("delta_z"),
        "removed": result.get("removed"),
        "z_before": result.get("z_before"),
        "z_after": result.get("z_after"),
        "n_tokens": result.get("n_tokens"),
    }
    canonical = json.dumps(evidence, sort_keys=True, ensure_ascii=False,
                           default=str).encode("utf-8")
    return "F-" + hashlib.sha256(canonical).hexdigest()[:8]


def _priority_risk(result: dict, cls: str, category: str) -> tuple[int, str]:
    """(priority, risk) — PRÜFpriorität 0-5, nie Schuld-Wahrscheinlichkeit.

    5 = starkes, reproduzierbares Artefakt (Redlist) -> sofortige Prüfung;
    4 = Klasse-A-Beleg ohne Redlist bzw. Klasse-B-Vergleich;
    3 = technischer Indikator über der Schwelle (z >= 4 oder e-Wert);
    2 = schwacher Indikator (2 <= |z| < 4) / ΔZ ohne Signalwechsel;
    1 = kein Signal oder zu kurzer Text (kein Prüfbedarf aus dem Befund).
    """
    if cls == "A":
        return (5, "high") if category == "Redlist" else (4, "high")
    if cls == "B":
        return (4, "medium")
    verdict = str(result.get("verdict") or "")
    if verdict == "too_short":
        return (1, "low")
    if category == "E-Wert":
        return (3, "medium") if result.get("detected") else (1, "low")
    if verdict in ("no_signal", "no_e_value"):
        return (1, "low")
    z = result.get("z_score")
    if isinstance(z, (int, float)):
        if abs(z) >= Z_THRESHOLD:
            return (3, "medium")
        if abs(z) >= 2.0:
            return (2, "low")
    return (1, "low")


# ---------------------------------------------------------------- observations
def _observation(result: dict, cls: str, category: str) -> str:
    """Klare deutsche Beschreibung dessen, was konkret messbar sichtbar ist."""
    z = result.get("z_score")
    p = result.get("p_value")
    if category == "Redlist":
        return (
            f"Reproduzierbares Redlist-Vorzeichen (z = {z}): Die Token-Auswahl "
            f"meidet die Hash-basierte Tokenmenge des Schlüssels — ein "
            f"keyed-Verifikations-Artefakt, keine Stil-Heuristik."
        )
    if category == "Delta-Z":
        removed = result.get("removed")
        if removed:
            return (
                f"Der ΔZ-Vergleich belegt einen messbaren Signalabfall "
                f"(ΔZ = {result.get('delta_z')}): Das Wasserzeichen-Signal war "
                f"vorher nachweisbar (z = {result.get('z_before')}) und danach "
                f"nicht mehr (z = {result.get('z_after')})."
            )
        return (
            f"Der ΔZ-Vergleich zeigt keinen nachweisbaren Signalwechsel "
            f"(ΔZ = {result.get('delta_z')}, removed: false)."
        )
    if category == "E-Wert":
        ev = result.get("e_value")
        if result.get("detected"):
            return (
                f"Der E-Wert-Prozess überschreitet die Schwelle "
                f"(e = {ev:.3g} >= {result.get('threshold')}). Technischer "
                f"Indikator — kein Beweis für KI-Beteiligung."
            )
        return (
            f"Der E-Wert-Prozess bleibt unter der Schwelle "
            f"(e = {ev:.3g} < {result.get('threshold')})."
        )
    if cls == "A":
        return (
            f"Überprüfbarer Dokumentbefund: Bonferroni-adjustierter p-Wert "
            f"{result.get('best_p_adjusted')} unter der Signifikanzschwelle "
            f"bzw. konsistente Segment-Z-Werte — ein reproduzierbares Artefakt."
        )
    if z is not None and isinstance(z, (int, float)) and abs(z) >= 2.0:
        return (
            f"Statistisches Wasserzeichen-Signal (z = {z}, p = {p}). "
            f"Technischer Indikator der Evidenzklasse C — nie allein beweisend."
        )
    return "Kein statistisches Wasserzeichen-Signal mit dem angegebenen Schlüssel nachweisbar."


def _explanations(result: dict, cls: str, category: str) -> list[str]:
    """Mindestens zwei plausible Erklärungen — inklusive Gegenhypothese."""
    z = result.get("z_score")
    if category == "Redlist":
        return [
            "Der Text wurde mit einem Redlist-Verfahren unter dem rechten "
            "Schlüssel erzeugt (reproduzierbares Artefakt).",
            "Ein Bearbeitungs- oder Filterungsprozess hat Token vermieden, "
            "die zufällig der Hash-Tokenmenge des Schlüssels entsprechen.",
            "Zufällige Unterrepräsentation: bei vielen hundert Token ist die "
            "Wahrscheinlichkeit sehr klein, aber nicht mathematisch null.",
        ]
    if category == "Delta-Z" and result.get("removed"):
        return [
            "Der Text wurde nachweislich verändert (z. B. Shuffle oder "
            "Neuschreibung), sodass das Signal verschwand.",
            "Der Vergleich misst einen Signalwechsel, beweist aber nicht die "
            "Ursache (auch vollständige Neuformulierung entfernt das Signal "
            "ohne ‚Reinigung').",
        ]
    if category == "Delta-Z":
        return [
            "Die Transformation hat das Signal nicht berührt (tokens "
            "unverändert) — die Marke ist weiterhin messbar.",
            "Das Signal war bereits vorher schwach oder nicht vorhanden — "
            "kein Signalwechsel ist messbar.",
        ]
    if category == "E-Wert":
        return [
            "Der Text wurde mit dem rechten Schlüssel markiert — der "
            "E-Wert-Prozess sammelt die Greenlist-Abweichung tokenweise an.",
            "Koinzidenz bei vielen Token-Positionen: ein einzelner Text kann "
            "auch ohne Markierung überzufällig viele grüne Token enthalten.",
        ]
    if cls == "A":
        return [
            "Der Text trägt ein unter dem rechten Schlüssel verifizierbares "
            "Wasserzeichen-Artefakt (keyed-Verifikation).",
            "Eine strukturelle Text-Eigenschaft (z. B. extrem repetitive "
            "Tokenstruktur) kann statistische Tests ohne Markierung "
            "beeinflussen — FPR-Kontrollen sind zu dokumentieren.",
        ]
    if z is not None and isinstance(z, (int, float)) and abs(z) >= 2.0:
        return [
            "Der Text wurde mit dem rechten Schlüssel markiert oder "
            "KI-generiert (keyed-Verifikation schlägt an).",
            "Koinzidenz oder stilistische Varianz: ein einzelner Text kann "
            "ohne Markierung überzufällig viele grüne Token enthalten "
            "(zweiseitiger p-Wert, kein deterministischer Beweis).",
            "Ein anderer Prozess mit ähnlicher Token-Statistik (z. B. "
            "maschinelle Übersetzung mit stabiler Wortwahl).",
        ]
    return [
        "Der Text ist unmarkiert — kein KGW-Signal unter dem rechten "
        "Schlüssel.",
        "Der Text wurde markiert und anschließend so verändert, dass das "
        "Signal zerstört wurde (Paraphrase, Shuffle, Neuformulierung).",
        "Der Text ist zu kurz für einen statistischen Test (n < 10 bewertete "
        "Token-Positionen).",
    ]


def _exculpatory(result: dict, cls: str, context_missing: bool) -> list[str]:
    """Entlastende Aspekte — was gegen vorschnelle Schlüsse spricht."""
    out = [
        "Technische Detektorwerte sind nie allein beweisend (Evidenzklasse-C-"
        "Regel): Sie belegen ein Signal, keine Autorenschaft und keine "
        "Täuschungsabsicht.",
        "Keine Aussage über menschliche vs. KI-Autorenschaft möglich — ein "
        "statistischer Befund ersetzt keine fachliche Prüfung.",
    ]
    if context_missing:
        out.append(
            "Keine institutionelle Regel / Entstehungshistorie geprüft — ohne "
            "Kontext ist die Aussagekraft begrenzt (Evidenzklasse D nicht "
            "belegbar)."
        )
    return out


def _next_steps(result: dict, cls: str, category: str) -> list[str]:
    """Konkrete, priorisierte Prüfaktionen für die Fachperson."""
    steps = [
        "Entstehungshistorie prüfen (Entwürfe, Versionsvergleich, "
        "Betreuungsfeedback, Abgabedatum).",
        "Institutionelle KI-Regel und Deklarationspflicht einholen und den "
        "Befund dagegen halten.",
        "Fachliches Gespräch zur Entstehung des Textes führen "
        "(Forschungsfrage, Methodenwahl, Quellen).",
    ]
    if category == "Redlist":
        steps.insert(0, "Befund mit einem zweiten unabhängigen Verfahren "
                        "gegenprüfen (z. B. E-Wert-Prozess, Segment-Analyse).")
    if category == "Delta-Z" and result.get("removed"):
        steps.insert(0, "Quelltext-Vergleich: welche Transformation hat das "
                        "Signal entfernt (Shuffle/Paraphrase statt ‚Cleaner')?")
    if cls == "A" or result.get("removed"):
        steps.append("Befund signieren lassen (sign_report), wenn er "
                     "archiviert oder übergeben wird.")
    return steps


# ---------------------------------------------------------------- public API
def classify_finding(detect_result: dict, context: dict | None = None, *,
                     alpha: float = DEFAULT_ALPHA,
                     key_id: str = "unknown") -> dict:
    """Übersetzt ein Detektor-Ergebnis in einen Befund mit Evidenzklasse.

    ``detect_result`` akzeptiert die Ergebnisformen der Produktpfade:
    - ein Per-Key-Ergebnis von ``detect_kgw`` (z_score, p_value, verdict, ...),
    - das Gesamtergebnis von ``detect_multi_key`` (best + best_p_adjusted
      werden automatisch zusammengeführt),
    - ein E-Wert-Ergebnis von ``e_detect`` (e_value, detected, ...),
    - ein ΔZ-Ergebnis von ``delta_z`` (z_before, z_after, removed, ...).

    ``context`` liefert die Kontext-Dimension (Evidenzklasse D): eine
    institutionelle Regel (``institutional_rule``) und/oder die
    Entstehungshistorie (``origin_history``). Fehlt sie, wird
    ``context_missing: true`` gesetzt — ehrlich, ohne Kontext ist die
    Aussagekraft begrenzt.

    Rückgabe: finding_id (F-xxxxxxxx, deterministisch), evidence_class
    (A/B/C), category, observation (deutsch), beleg (Zahlen), 
    possible_explanations (>= 2), exculpatory, risk, priority (0-5,
    PRÜFbedarf — nicht Schuld), recommended_next_steps, context_missing.
    """
    if not isinstance(detect_result, dict):
        raise ValueError("detect_result must be a dict")
    # detect_multi_key-Gesamtergebnis -> best + Bonferroni-p zusammenführen.
    if isinstance(detect_result.get("best"), dict):
        merged = dict(detect_result["best"])
        merged["best_p_adjusted"] = detect_result.get("best_p_adjusted")
        merged["tested_keys"] = detect_result.get("tested_keys")
        merged["note"] = detect_result.get("note")
        detect_result = merged

    cm = _context_missing(context)
    category = _category(detect_result)
    cls = _technical_class(detect_result, alpha)
    priority, risk = _priority_risk(detect_result, cls, category)

    beleg = {}
    for k in ("z_score", "p_value", "best_p_adjusted", "green_rate",
              "n_tokens", "e_value", "threshold", "delta_z", "z_before",
              "z_after", "removed", "verdict", "signal"):
        if k in detect_result and detect_result[k] is not None:
            beleg[k] = detect_result[k]

    finding = {
        "finding_id": _finding_id(detect_result, category, key_id),
        "evidence_class": cls,
        "category": category,
        "observation": _observation(detect_result, cls, category),
        "beleg": beleg,
        "possible_explanations": _explanations(detect_result, cls, category),
        "exculpatory": _exculpatory(detect_result, cls, cm),
        "risk": risk,
        "priority": priority,
        "recommended_next_steps": _next_steps(detect_result, cls, category),
        "context_missing": cm,
    }
    if not cm and isinstance(context, dict):
        finding["context_notes"] = {
            k: (str(context[k])[:300] + ("…" if len(str(context[k])) > 300 else ""))
            for k in CONTEXT_KEYS if context.get(k)
        }
    return finding


def _verdict_text(findings: list[dict], priority: int) -> str:
    """Ehrliche Schlussformulierung — NIE „KI-generiert" als Feststellung."""
    if not findings:
        return ("Herkunft nicht bestimmbar — keine technischen Indikatoren "
                "vorgelegt.")
    classes = [f["evidence_class"] for f in findings]
    if "A" in classes:
        base = ("Die Befunde sind mit KI-Unterstützung vereinbar, beweisen sie "
                "aber nicht. Eine vertiefte Prüfung ist dringend angezeigt.")
    elif "B" in classes:
        base = ("Ein messbarer Signalwechsel wurde belegt (Vergleichsbefund) — "
                "mit KI-Unterstützung vereinbar, beweist sie aber nicht. Die "
                "Herkunft des Textes ist ohne weitere Prüfung nicht "
                "bestimmbar.")
    elif priority >= 3:
        base = ("Die technischen Indikatoren sind mit KI-Unterstützung "
                "vereinbar, beweisen sie aber nicht. Herkunft nicht "
                "bestimmbar.")
    else:
        base = "Herkunft nicht bestimmbar — keine belastbaren technischen Indikatoren."
    if all(f.get("context_missing") for f in findings):
        base += (" Ohne institutionelle Regel und Entstehungshistorie bleibt "
                 "die Aussagekraft begrenzt.")
    return base


def build_finding_report(results: dict, key_id: str = "unknown", *,
                         context: dict | None = None,
                         alpha: float = DEFAULT_ALPHA,
                         sign_secret: str | None = None) -> dict:
    """Bündelt detect + e_value + delta_z zu einem strukturierten Befund.

    ``results`` ist entweder ein einzelnes Detektor-Ergebnis (flach) oder ein
    Dict mit den Modulen ``detect``/``e_value``/``delta_z``. Jedes vorhandene
    Modul wird mit :func:`classify_finding` in einen Einzelbefund übersetzt;
    daraus entstehen ``findings``, eine ``evidence_matrix`` (Blaupausen-Format:
    ID | Beobachtung | Klasse | Risiko | Gegenhypothesen | Nächster Schritt),
    eine Gesamt-``priority`` (max der Einzelprioritäten, 0-5) und ein
    ehrlicher ``verdict_text``.

    ``sign_secret`` (optional) signiert den Report via ``signed_report``
    (HMAC-SHA256, stdlib) — der Befund wird ein auditierbares Dokument
    (verify mit ``ai-wm report-verify`` oder :func:`verify_report`).
    """
    if not isinstance(results, dict):
        raise ValueError("results must be a dict")
    detect = results.get("detect", results)
    modules = [("detect", detect)]
    if results.get("e_value") is not None:
        modules.append(("e_value", results["e_value"]))
    if results.get("delta_z") is not None:
        modules.append(("delta_z", results["delta_z"]))

    findings = [classify_finding(r, context=context, alpha=alpha,
                                 key_id=key_id) for _, r in modules]
    priority = max((f["priority"] for f in findings), default=0)
    classes = [f["evidence_class"] for f in findings]

    evidence_matrix = [
        {
            "finding_id": f["finding_id"],
            "evidence_class": f["evidence_class"],
            "category": f["category"],
            "observation": f["observation"],
            "beleg": f["beleg"],
            "risk": f["risk"],
            "priority": f["priority"],
            "possible_explanations": f["possible_explanations"],
            "next_step": (f["recommended_next_steps"][0]
                          if f["recommended_next_steps"] else ""),
        }
        for f in findings
    ]

    report = {
        "report_type": "ki-erklaerungs-befund",
        "key_id": key_id,
        "summary": {
            "findings_total": len(findings),
            "class_a": classes.count("A"),
            "class_b": classes.count("B"),
            "class_c": classes.count("C"),
            "context_missing": all(f.get("context_missing") for f in findings),
            "priority": priority,
        },
        "findings": findings,
        "evidence_matrix": evidence_matrix,
        "priority": priority,
        "verdict_text": _verdict_text(findings, priority),
        "schlussfolgerung_hinweis": (
            "Dieser Befund stellt keine KI-Nutzung, kein Plagiat und keine "
            "Täuschung fest. ‚Herkunft nicht bestimmbar' ist eine legitime "
            "Schlussfolgerung."
        ),
    }
    if sign_secret:
        from .signed_report import sign_report
        report = sign_report(report, sign_secret, key_id=key_id)
    return report
