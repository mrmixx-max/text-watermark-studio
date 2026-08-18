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
CONTEXT_KEYS = ("institutional_rule", "origin_history", "rules", "history", "institution")

# ---------------------------------------------------------------- i18n
# Report language. Default "de" keeps the existing contract; "en" switches
# every human-readable text field (observation, explanations, exculpatory,
# next steps, verdict, schlussfolgerung_hinweis) to English. The structured
# fields (evidence_class, category, priority, risk, beleg) stay language-
# neutral by design.
_TEXTS

_TEXTS: dict[str, dict[str, str]] = {
    "de": {
        "obs_redlist": (
            "Reproduzierbares Redlist-Vorzeichen (z = {z}): Die "
            "Token-Auswahl meidet die Hash-basierte Tokenmenge des "
            "Schlüssels — ein keyed-Verifikations-Artefakt, keine "
            "Stil-Heuristik."
        ),
        "obs_delta_removed": (
            "Der ΔZ-Vergleich belegt einen messbaren "
            "Signalabfall (ΔZ = {delta_z}): Das "
            "Wasserzeichen-Signal war vorher nachweisbar "
            "(z = {z_before}) und danach nicht mehr "
            "(z = {z_after})."
        ),
        "obs_delta_kept": (
            "Der ΔZ-Vergleich zeigt keinen nachweisbaren Signalwechsel (ΔZ = {delta_z}, removed: false)."
        ),
        "obs_e_detected": (
            "Der E-Wert-Prozess überschreitet die Schwelle "
            "(e = {e_value} >= {threshold}). Technischer "
            "Indikator — kein Beweis für KI-Beteiligung."
        ),
        "obs_e_clean": ("Der E-Wert-Prozess bleibt unter der Schwelle (e = {e_value} < {threshold})."),
        "obs_class_a": (
            "Überprüfbarer Dokumentbefund: Bonferroni-adjustierter "
            "p-Wert {p_adj} unter der Signifikanzschwelle bzw. "
            "konsistente Segment-Z-Werte — ein reproduzierbares "
            "Artefakt."
        ),
        "obs_signal": (
            "Statistisches Wasserzeichen-Signal (z = {z}, "
            "p = {p}). Technischer Indikator der Evidenzklasse C — "
            "nie allein beweisend."
        ),
        "obs_none": ("Kein statistisches Wasserzeichen-Signal mit dem angegebenen Schlüssel nachweisbar."),
        "exp_redlist_1": (
            "Der Text wurde mit einem Redlist-Verfahren unter "
            "dem rechten Schlüssel erzeugt (reproduzierbares "
            "Artefakt)."
        ),
        "exp_redlist_2": (
            "Ein Bearbeitungs- oder Filterungsprozess hat Token "
            "vermieden, die zufällig der Hash-Tokenmenge des "
            "Schlüssels entsprechen."
        ),
        "exp_redlist_3": (
            "Zufällige Unterrepräsentation: bei vielen hundert "
            "Token ist die Wahrscheinlichkeit sehr klein, aber "
            "nicht mathematisch null."
        ),
        "exp_delta_removed_1": (
            "Der Text wurde nachweislich verändert (z. B. Shuffle oder Neuschreibung), sodass das Signal verschwand."
        ),
        "exp_delta_removed_2": (
            "Der Vergleich misst einen Signalwechsel, "
            "beweist aber nicht die Ursache (auch "
            "vollständige Neuformulierung entfernt das "
            "Signal ohne ‚Reinigung')."
        ),
        "exp_delta_kept_1": (
            "Die Transformation hat das Signal nicht berührt (tokens unverändert) — die Marke ist weiterhin messbar."
        ),
        "exp_delta_kept_2": (
            "Das Signal war bereits vorher schwach oder nicht vorhanden — kein Signalwechsel ist messbar."
        ),
        "exp_e_1": (
            "Der Text wurde mit dem rechten Schlüssel markiert — der "
            "E-Wert-Prozess sammelt die Greenlist-Abweichung "
            "tokenweise an."
        ),
        "exp_e_2": (
            "Koinzidenz bei vielen Token-Positionen: ein einzelner "
            "Text kann auch ohne Markierung überzufällig viele grüne "
            "Token enthalten."
        ),
        "exp_a_1": (
            "Der Text trägt ein unter dem rechten Schlüssel "
            "verifizierbares Wasserzeichen-Artefakt (keyed-"
            "Verifikation)."
        ),
        "exp_a_2": (
            "Eine strukturelle Text-Eigenschaft (z. B. extrem "
            "repetitive Tokenstruktur) kann statistische Tests ohne "
            "Markierung beeinflussen — FPR-Kontrollen sind zu "
            "dokumentieren."
        ),
        "exp_signal_1": (
            "Der Text wurde mit dem rechten Schlüssel markiert oder KI-generiert (keyed-Verifikation schlägt an)."
        ),
        "exp_signal_2": (
            "Koinzidenz oder stilistische Varianz: ein einzelner "
            "Text kann ohne Markierung überzufällig viele grüne "
            "Token enthalten (zweiseitiger p-Wert, kein "
            "deterministischer Beweis)."
        ),
        "exp_signal_3": (
            "Ein anderer Prozess mit ähnlicher Token-Statistik (z. B. maschinelle Übersetzung mit stabiler Wortwahl)."
        ),
        "exp_none_1": ("Der Text ist unmarkiert — kein KGW-Signal unter dem rechten Schlüssel."),
        "exp_none_2": (
            "Der Text wurde markiert und anschließend so "
            "verändert, dass das Signal zerstört wurde (Paraphrase, "
            "Shuffle, Neuformulierung)."
        ),
        "exp_none_3": ("Der Text ist zu kurz für einen statistischen Test (n < 10 bewertete Token-Positionen)."),
        "excu_1": (
            "Technische Detektorwerte sind nie allein beweisend "
            "(Evidenzklasse-C-Regel): Sie belegen ein Signal, keine "
            "Autorenschaft und keine Täuschungsabsicht."
        ),
        "excu_2": (
            "Keine Aussage über menschliche vs. KI-Autorenschaft "
            "möglich — ein statistischer Befund ersetzt keine "
            "fachliche Prüfung."
        ),
        "excu_ctx": (
            "Keine institutionelle Regel / Entstehungshistorie "
            "geprüft — ohne Kontext ist die Aussagekraft begrenzt "
            "(Evidenzklasse D nicht belegbar)."
        ),
        "step_1": ("Entstehungshistorie prüfen (Entwürfe, Versionsvergleich, Betreuungsfeedback, Abgabedatum)."),
        "step_2": ("Institutionelle KI-Regel und Deklarationspflicht einholen und den Befund dagegen halten."),
        "step_3": ("Fachliches Gespräch zur Entstehung des Textes führen (Forschungsfrage, Methodenwahl, Quellen)."),
        "step_redlist": (
            "Befund mit einem zweiten unabhängigen Verfahren gegenprüfen (z. B. E-Wert-Prozess, Segment-Analyse)."
        ),
        "step_delta": (
            "Quelltext-Vergleich: welche Transformation hat das Signal entfernt (Shuffle/Paraphrase statt ‚Cleaner')?"
        ),
        "step_sign": ("Befund signieren lassen (sign_report), wenn er archiviert oder übergeben wird."),
        "verdict_none": ("Herkunft nicht bestimmbar — keine technischen Indikatoren vorgelegt."),
        "verdict_a": (
            "Die Befunde sind mit KI-Unterstützung vereinbar, "
            "beweisen sie aber nicht. Eine vertiefte Prüfung ist "
            "dringend angezeigt."
        ),
        "verdict_b": (
            "Ein messbarer Signalwechsel wurde belegt "
            "(Vergleichsbefund) — mit KI-Unterstützung vereinbar, "
            "beweist sie aber nicht. Die Herkunft des Textes ist "
            "ohne weitere Prüfung nicht bestimmbar."
        ),
        "verdict_prio3": (
            "Die technischen Indikatoren sind mit "
            "KI-Unterstützung vereinbar, beweisen sie aber "
            "nicht. Herkunft nicht bestimmbar."
        ),
        "verdict_low": ("Herkunft nicht bestimmbar — keine belastbaren technischen Indikatoren."),
        "verdict_ctx": (" Ohne institutionelle Regel und Entstehungshistorie bleibt die Aussagekraft begrenzt."),
        "schluss": (
            "Dieser Befund stellt keine KI-Nutzung, kein Plagiat und "
            "keine Täuschung fest. ‚Herkunft nicht bestimmbar' ist "
            "eine legitime Schlussfolgerung."
        ),
    },
    "en": {
        "obs_redlist": (
            "Reproducible redlist sign (z = {z}): the token "
            "selection avoids the key's hash-based token set — a "
            "keyed verification artifact, not a style heuristic."
        ),
        "obs_delta_removed": (
            "The ΔZ comparison shows a measurable signal "
            "drop (ΔZ = {delta_z}): the watermark signal "
            "was present before (z = {z_before}) and gone "
            "after (z = {z_after})."
        ),
        "obs_delta_kept": ("The ΔZ comparison shows no measurable signal change (ΔZ = {delta_z}, removed: false)."),
        "obs_e_detected": (
            "The e-value process exceeds the threshold "
            "(e = {e_value} >= {threshold}). Technical "
            "indicator — not proof of AI involvement."
        ),
        "obs_e_clean": ("The e-value process stays below the threshold (e = {e_value} < {threshold})."),
        "obs_class_a": (
            "Verifiable document finding: Bonferroni-adjusted "
            "p-value {p_adj} below the significance threshold or "
            "consistent segment Z-values — a reproducible "
            "artifact."
        ),
        "obs_signal": (
            "Statistical watermark signal (z = {z}, p = {p}). "
            "Evidence-class-C technical indicator — never "
            "conclusive on its own."
        ),
        "obs_none": ("No statistical watermark signal detectable with the given key."),
        "exp_redlist_1": (
            "The text was produced with a redlist procedure under the correct key (reproducible artifact)."
        ),
        "exp_redlist_2": (
            "An editing or filtering process avoided tokens that happen to match the key's hash token set."
        ),
        "exp_redlist_3": (
            "Random under-representation: across many hundreds "
            "of tokens the probability is very small, but not "
            "mathematically zero."
        ),
        "exp_delta_removed_1": (
            "The text was verifiably altered (e.g. shuffle or rewrite), so the signal disappeared."
        ),
        "exp_delta_removed_2": (
            "The comparison measures a signal change but "
            "does not prove the cause (even a full "
            "rewrite removes the signal without "
            "‘cleaning')."
        ),
        "exp_delta_kept_1": (
            "The transformation did not touch the signal (tokens unchanged) — the mark stays measurable."
        ),
        "exp_delta_kept_2": ("The signal was already weak or absent before — no signal change is measurable."),
        "exp_e_1": (
            "The text was marked with the correct key — the e-value "
            "process accumulates the greenlist deviation token by "
            "token."
        ),
        "exp_e_2": (
            "Coincidence across many token positions: a single text "
            "can contain more green tokens than expected by chance "
            "without being marked."
        ),
        "exp_a_1": ("The text carries a watermark artifact verifiable under the correct key (keyed verification)."),
        "exp_a_2": (
            "A structural text property (e.g. extremely repetitive "
            "token structure) can influence statistical tests without "
            "a mark — FPR controls must be documented."
        ),
        "exp_signal_1": ("The text was marked with the correct key or AI-generated (keyed verification fires)."),
        "exp_signal_2": (
            "Coincidence or stylistic variance: a single text "
            "can contain more green tokens than expected by "
            "chance without a mark (two-sided p-value, no "
            "deterministic proof)."
        ),
        "exp_signal_3": (
            "Another process with similar token statistics (e.g. machine translation with stable word choice)."
        ),
        "exp_none_1": ("The text is unmarked — no KGW signal under the correct key."),
        "exp_none_2": (
            "The text was marked and then altered in a way that destroyed the signal (paraphrase, shuffle, rewrite)."
        ),
        "exp_none_3": ("The text is too short for a statistical test (n < 10 evaluated token positions)."),
        "excu_1": (
            "Technical detector values are never conclusive on their "
            "own (evidence-class-C rule): they show a signal, not "
            "authorship and not intent to deceive."
        ),
        "excu_2": (
            "No statement about human vs. AI authorship is possible — "
            "a statistical finding does not replace expert review."
        ),
        "excu_ctx": (
            "No institutional rule / origin history reviewed — "
            "without context the evidentiary power is limited "
            "(evidence class D cannot be established)."
        ),
        "step_1": ("Review the origin history (drafts, version comparison, supervisor feedback, submission date)."),
        "step_2": ("Obtain the institutional AI rule and declaration duty and hold the finding against it."),
        "step_3": (
            "Conduct an expert conversation about how the text came to be (research question, method choice, sources)."
        ),
        "step_redlist": (
            "Cross-check the finding with a second independent method (e.g. e-value process, segment analysis)."
        ),
        "step_delta": (
            "Source comparison: which transformation removed the signal (shuffle/paraphrase instead of ‘cleaner')?"
        ),
        "step_sign": ("Have the finding signed (sign_report) if it is archived or handed over."),
        "verdict_none": ("Origin undetermined — no technical indicators presented."),
        "verdict_a": (
            "The findings are consistent with AI assistance but do not prove it. Deeper review is urgently indicated."
        ),
        "verdict_b": (
            "A measurable signal change was established "
            "(comparison finding) — consistent with AI assistance "
            "but not proof. The text's origin cannot be determined "
            "without further review."
        ),
        "verdict_prio3": (
            "The technical indicators are consistent with AI assistance but do not prove it. Origin undetermined."
        ),
        "verdict_low": ("Origin undetermined — no reliable technical indicators."),
        "verdict_ctx": (" Without an institutional rule and origin history the evidentiary power stays limited."),
        "schluss": (
            "This finding does not establish AI use, plagiarism, or "
            "deception. ‘Origin undetermined' is a legitimate "
            "conclusion."
        ),
    },
}


def _lang_text(lang: str, key: str) -> str:
    """Resolve a human-readable report text for the requested language."""
    table = _TEXTS.get(lang, _TEXTS["de"])
    return table.get(key, _TEXTS["de"].get(key, key))


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
    canonical = json.dumps(evidence, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
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
def _observation(result: dict, cls: str, category: str, lang: str = "de") -> str:
    """Clear description of what is concretely measurable — localized."""
    z = result.get("z_score")
    p = result.get("p_value")
    if category == "Redlist":
        return _lang_text(lang, "obs_redlist").format(z=z)
    if category == "Delta-Z":
        removed = result.get("removed")
        if removed:
            return _lang_text(lang, "obs_delta_removed").format(
                delta_z=result.get("delta_z"), z_before=result.get("z_before"), z_after=result.get("z_after")
            )
        return _lang_text(lang, "obs_delta_kept").format(delta_z=result.get("delta_z"))
    if category == "E-Wert":
        ev = result.get("e_value")
        if result.get("detected"):
            return _lang_text(lang, "obs_e_detected").format(e_value=f"{ev:.3g}", threshold=result.get("threshold"))
        return _lang_text(lang, "obs_e_clean").format(e_value=f"{ev:.3g}", threshold=result.get("threshold"))
    if cls == "A":
        return _lang_text(lang, "obs_class_a").format(p_adj=result.get("best_p_adjusted"))
    if z is not None and isinstance(z, (int, float)) and abs(z) >= 2.0:
        return _lang_text(lang, "obs_signal").format(z=z, p=p)
    return _lang_text(lang, "obs_none")


def _explanations(result: dict, cls: str, category: str, lang: str = "de") -> list[str]:
    """At least two plausible explanations — including counter-hypothesis."""
    z = result.get("z_score")
    if category == "Redlist":
        return [_lang_text(lang, k) for k in ("exp_redlist_1", "exp_redlist_2", "exp_redlist_3")]
    if category == "Delta-Z" and result.get("removed"):
        return [_lang_text(lang, k) for k in ("exp_delta_removed_1", "exp_delta_removed_2")]
    if category == "Delta-Z":
        return [_lang_text(lang, k) for k in ("exp_delta_kept_1", "exp_delta_kept_2")]
    if category == "E-Wert":
        return [_lang_text(lang, k) for k in ("exp_e_1", "exp_e_2")]
    if cls == "A":
        return [_lang_text(lang, k) for k in ("exp_a_1", "exp_a_2")]
    if z is not None and isinstance(z, (int, float)) and abs(z) >= 2.0:
        return [_lang_text(lang, k) for k in ("exp_signal_1", "exp_signal_2", "exp_signal_3")]
    return [_lang_text(lang, k) for k in ("exp_none_1", "exp_none_2", "exp_none_3")]


def _exculpatory(result: dict, cls: str, context_missing: bool, lang: str = "de") -> list[str]:
    """Exculpatory aspects — what speaks against rushed conclusions."""
    out = [_lang_text(lang, "excu_1"), _lang_text(lang, "excu_2")]
    if context_missing:
        out.append(_lang_text(lang, "excu_ctx"))
    return out


def _next_steps(result: dict, cls: str, category: str, lang: str = "de") -> list[str]:
    """Concrete, prioritized review actions for the expert."""
    steps = [_lang_text(lang, k) for k in ("step_1", "step_2", "step_3")]
    if category == "Redlist":
        steps.insert(0, _lang_text(lang, "step_redlist"))
    if category == "Delta-Z" and result.get("removed"):
        steps.insert(0, _lang_text(lang, "step_delta"))
    if cls == "A" or result.get("removed"):
        steps.append(_lang_text(lang, "step_sign"))
    return steps


# ---------------------------------------------------------------- public API
def classify_finding(
    detect_result: dict,
    context: dict | None = None,
    *,
    alpha: float = DEFAULT_ALPHA,
    key_id: str = "unknown",
    lang: str = "de",
) -> dict:
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
        raise TypeError("detect_result must be a dict")
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
    for k in (
        "z_score",
        "p_value",
        "best_p_adjusted",
        "green_rate",
        "n_tokens",
        "e_value",
        "threshold",
        "delta_z",
        "z_before",
        "z_after",
        "removed",
        "verdict",
        "signal",
    ):
        if k in detect_result and detect_result[k] is not None:
            beleg[k] = detect_result[k]

    finding = {
        "finding_id": _finding_id(detect_result, category, key_id),
        "evidence_class": cls,
        "category": category,
        "observation": _observation(detect_result, cls, category, lang=lang),
        "beleg": beleg,
        "possible_explanations": _explanations(detect_result, cls, category, lang=lang),
        "exculpatory": _exculpatory(detect_result, cls, cm, lang=lang),
        "risk": risk,
        "priority": priority,
        "recommended_next_steps": _next_steps(detect_result, cls, category, lang=lang),
        "context_missing": cm,
    }
    if not cm and isinstance(context, dict):
        finding["context_notes"] = {
            k: (str(context[k])[:300] + ("…" if len(str(context[k])) > 300 else ""))
            for k in CONTEXT_KEYS
            if context.get(k)
        }
    return finding


def _verdict_text(findings: list[dict], priority: int, lang: str = "de") -> str:
    """Honest final wording — never "AI-generated" as a statement."""
    if not findings:
        return _lang_text(lang, "verdict_none")
    classes = [f["evidence_class"] for f in findings]
    if "A" in classes:
        base = _lang_text(lang, "verdict_a")
    elif "B" in classes:
        base = _lang_text(lang, "verdict_b")
    elif priority >= 3:
        base = _lang_text(lang, "verdict_prio3")
    else:
        base = _lang_text(lang, "verdict_low")
    if all(f.get("context_missing") for f in findings):
        base += _lang_text(lang, "verdict_ctx")
    return base


def build_finding_report(
    results: dict,
    key_id: str = "unknown",
    *,
    context: dict | None = None,
    alpha: float = DEFAULT_ALPHA,
    sign_secret: str | None = None,
    frs: dict | None = None,
    lang: str = "de",
) -> dict:
    """Bündelt detect + e_value + delta_z zu einem strukturierten Befund.

    ``results`` ist entweder ein einzelnes Detektor-Ergebnis (flach) oder ein
    Dict mit den Modulen ``detect``/``e_value``/``delta_z``. Jedes vorhandene
    Modul wird mit :func:`classify_finding` in einen Einzelbefund übersetzt;
    daraus entstehen ``findings``, eine ``evidence_matrix`` (Blaupausen-Format:
    ID | Beobachtung | Klasse | Risiko | Gegenhypothesen | Nächster Schritt),
    eine Gesamt-``priority`` (max der Einzelprioritäten, 0-5) und ein
    ehrlicher ``verdict_text``.

    ``context`` (Evidenzklasse D) liefert die institutionelle Regel
    (``institutional_rule``) und/oder die Entstehungshistorie
    (``origin_history``); fehlt sie, wird ``context_missing: true`` gesetzt
    (Runde-3-Lücke E1: über CLI ``--institutional-rule``/``--origin-history``
    und API ``context`` übergebbar).

    ``frs`` (optional) hängt den Forensic-Readiness-Score-Block
    (:func:`ai_watermark_toolkit.forensics.frs.compute_frs`) an den Report.
    Der Block wird MIT-signiert — ``sign_report`` hasht den ganzen Payload,
    sodass der FRS nicht nachträglich manipuliert werden kann, ohne die
    Signatur zu brechen.

    ``sign_secret`` (optional) signiert den Report via ``signed_report``
    (HMAC-SHA256, stdlib) — der Befund wird ein auditierbares Dokument
    (verify mit ``ai-wm report-verify`` oder :func:`verify_report`).
    """
    if not isinstance(results, dict):
        raise TypeError("results must be a dict")
    detect = results.get("detect", results)
    modules = [("detect", detect)]
    if results.get("e_value") is not None:
        modules.append(("e_value", results["e_value"]))
    if results.get("delta_z") is not None:
        modules.append(("delta_z", results["delta_z"]))

    findings = [classify_finding(r, context=context, alpha=alpha, key_id=key_id, lang=lang) for _, r in modules]
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
            "next_step": (f["recommended_next_steps"][0] if f["recommended_next_steps"] else ""),
        }
        for f in findings
    ]

    report = {
        "report_type": "ki-erklaerungs-befund",
        "lang": lang,
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
        "verdict_text": _verdict_text(findings, priority, lang=lang),
        "schlussfolgerung_hinweis": _lang_text(lang, "schluss"),
    }
    if frs is not None:
        report["frs"] = frs
    if sign_secret:
        from .signed_report import sign_report

        report = sign_report(report, sign_secret, key_id=key_id)
    return report
