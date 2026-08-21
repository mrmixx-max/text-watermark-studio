#!/usr/bin/env python3
"""GhostMark + Panoptes Integration for TWS.

Port of GhostMark's 7-pass SynthID destroyer (Apache 2.0) and
Panoptes attribution features (MIT) for watermark removal evaluation.

Modules:
- scrub_unicode: Remove invisible Unicode characters
- pass_synonyms: Replace AI-typical words
- pass_transitions: Replace formal transitions
- pass_contractions: Inject contractions
- pass_burstiness: Break/merge sentences
- pass_fillers: Inject human filler phrases
- pass_strip_ai_padding: Remove AI padding
- apply_homoglyphs: Cyrillic homoglyph perturbation
- shatter_synthid_text: Master function
- extract_attribution_features: Panoptes 7 features
- heuristic_ai_score: Panoptes AI-likelihood score
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

# ================================================================
# GHOSTMARK: 7-PASS SYNTHID DESTROYER
# Source: https://github.com/kilopal/GhostMark (Apache 2.0)
# ================================================================

# Pass 1: Unicode scrub
_UNICODE_STRIP = {
    "\u200b",
    "\u200c",
    "\u200d",
    "\u200e",
    "\u200f",
    "\ufeff",
}
_UNICODE_TAG_RE = re.compile(r"[\U000E0000-\U000E007F]")


def scrub_unicode(text: str) -> str:
    """Remove invisible Unicode characters (zero-width spaces, tags, BOM)."""
    result = []
    for c in text:
        if c in _UNICODE_STRIP or _UNICODE_TAG_RE.match(c):
            continue
        result.append(c)
    return "".join(result)


# Pass 2: Synonym replacement
_SYNONYMS: dict[str, list[str]] = {
    "delve": ["dig", "look", "explore", "get"],
    "delves": ["digs", "looks", "explores", "gets"],
    "delving": ["digging", "looking", "exploring", "getting"],
    "utilize": ["use", "work with", "rely on"],
    "utilizes": ["uses", "works with", "relies on"],
    "utilizing": ["using", "working with", "relying on"],
    "leverage": ["use", "tap into", "rely on"],
    "leverages": ["uses", "taps into", "relies on"],
    "leveraging": ["using", "tapping into", "relying on"],
    "navigate": ["handle", "deal with", "work through", "tackle"],
    "navigates": ["handles", "deals with", "works through", "tackles"],
    "navigating": ["handling", "dealing with", "working through", "tackling"],
    "foster": ["build", "grow", "encourage", "support"],
    "fosters": ["builds", "grows", "encourages", "supports"],
    "fostering": ["building", "growing", "encouraging", "supporting"],
    "empower": ["help", "let", "give power to", "enable"],
    "empowers": ["helps", "lets", "gives power to", "enables"],
    "empowering": ["helping", "letting", "giving power to", "enabling"],
    "streamline": ["simplify", "speed up", "cut down on"],
    "streamlines": ["simplifies", "speeds up", "cuts down on"],
    "streamlining": ["simplifying", "speeding up", "cutting down on"],
    "optimize": ["improve", "fine-tune", "make better"],
    "optimizes": ["improves", "fine-tunes", "makes better"],
    "optimizing": ["improving", "fine-tuning", "making better"],
    "enhance": ["boost", "improve", "strengthen"],
    "enhances": ["boosts", "improves", "strengthens"],
    "enhancing": ["boosting", "improving", "strengthening"],
    "facilitate": ["help", "make easier", "support"],
    "facilitates": ["helps", "makes easier", "supports"],
    "facilitating": ["helping", "making easier", "supporting"],
    "underscore": ["highlight", "show", "stress"],
    "underscores": ["highlights", "shows", "stresses"],
    "underscoring": ["highlighting", "showing", "stressing"],
    "bolster": ["strengthen", "support", "back up"],
    "bolsters": ["strengthens", "supports", "backs up"],
    "bolstering": ["strengthening", "supporting", "backing up"],
    "spearhead": ["lead", "drive", "push"],
    "spearheads": ["leads", "drives", "pushes"],
    "spearheading": ["leading", "driving", "pushing"],
    "revolutionize": ["change", "shake up", "transform"],
    "revolutionizes": ["changes", "shakes up", "transforms"],
    "implement": ["set up", "put in place", "roll out"],
    "implements": ["sets up", "puts in place", "rolls out"],
    "implementing": ["setting up", "putting in place", "rolling out"],
    "demonstrate": ["show", "prove", "make clear"],
    "demonstrates": ["shows", "proves", "makes clear"],
    "demonstrating": ["showing", "proving", "making clear"],
    "encompass": ["cover", "include", "span"],
    "encompasses": ["covers", "includes", "spans"],
    "prioritize": ["focus on", "put first", "rank"],
    "prioritizes": ["focuses on", "puts first", "ranks"],
    "integrate": ["combine", "blend", "mix", "merge"],
    "integrates": ["combines", "blends", "mixes", "merges"],
    "integrating": ["combining", "blending", "mixing", "merging"],
    "catalyze": ["trigger", "spark", "kick off"],
    "catalyzes": ["triggers", "sparks", "kicks off"],
    "crucial": ["key", "big", "major", "important"],
    "pivotal": ["key", "central", "major"],
    "comprehensive": ["full", "thorough", "complete", "broad"],
    "robust": ["strong", "solid", "tough"],
    "seamless": ["smooth", "easy", "effortless"],
    "seamlessly": ["smoothly", "easily", "effortlessly"],
    "unprecedented": ["never-before-seen", "unmatched", "record-breaking"],
    "transformative": ["game-changing", "ground-breaking", "radical"],
    "multifaceted": ["complex", "many-sided", "layered"],
    "innovative": ["creative", "fresh", "new", "clever"],
    "dynamic": ["active", "energetic", "lively", "changing"],
    "nuanced": ["subtle", "detailed", "layered"],
    "holistic": ["complete", "full-picture", "all-round"],
    "myriad": ["many", "tons of", "loads of", "countless"],
    "intricate": ["complex", "detailed", "involved"],
    "overarching": ["main", "broad", "overall"],
    "unparalleled": ["unmatched", "one-of-a-kind", "rare"],
    "cutting-edge": ["latest", "newest", "advanced"],
    "groundbreaking": ["revolutionary", "pioneering", "radical"],
    "invaluable": ["priceless", "extremely useful", "essential"],
    "indispensable": ["essential", "must-have", "necessary"],
    "noteworthy": ["worth noting", "remarkable", "interesting"],
    "profound": ["deep", "huge", "intense", "powerful"],
    "significant": ["big", "major", "important", "notable"],
    "substantial": ["large", "big", "considerable"],
    "remarkable": ["impressive", "striking", "notable"],
    "imperative": ["critical", "urgent", "necessary"],
    "paramount": ["top", "supreme", "most important"],
    "burgeoning": ["growing", "rising", "booming"],
    "salient": ["key", "main", "notable"],
    "commendable": ["praiseworthy", "admirable", "impressive"],
    "meticulous": ["careful", "precise", "thorough"],
    "discernible": ["noticeable", "visible", "clear"],
    "adept": ["skilled", "good at", "sharp"],
    "landscape": ["space", "scene", "world", "environment"],
    "paradigm": ["model", "framework", "approach"],
    "synergy": ["teamwork", "cooperation", "combined effort"],
    "synergistic": ["teamwork", "cooperation", "combined effort"],
    "tapestry": ["mix", "blend", "web"],
    "catalyst": ["driver", "trigger", "spark"],
    "catalysts": ["drivers", "triggers", "sparks"],
    "testament": ["proof", "sign", "evidence"],
    "prowess": ["skill", "talent", "ability"],
    "realm": ["area", "field", "world", "space"],
    "endeavor": ["effort", "project", "work"],
    "endeavors": ["efforts", "projects", "work"],
    "trajectory": ["path", "direction", "course"],
    "cornerstone": ["foundation", "basis", "pillar"],
    "underpinning": ["foundation", "basis", "core"],
    "underpinnings": ["foundations", "bases", "cores"],
    "stakeholders": ["people involved", "parties", "players"],
    "implications": ["effects", "consequences", "impact"],
    "ramifications": ["consequences", "effects", "fallout"],
    "juxtaposition": ["contrast", "comparison", "difference"],
    "plethora": ["ton", "bunch", "lots"],
    "intricacies": ["details", "complexities", "ins and outs"],
    "conundrum": ["puzzle", "problem", "dilemma"],
    "dichotomy": ["split", "divide", "contrast"],
    "rapidly": ["quickly", "fast", "at speed"],
    "increasingly": ["more and more", "gradually more"],
    "fundamentally": ["at its core", "basically", "at heart"],
    "inherently": ["by nature", "naturally", "at its core"],
    "undoubtedly": ["no doubt", "clearly", "for sure", "without question"],
    "arguably": ["you could say", "possibly", "some would say"],
    "moreover": ["also", "on top of that", "plus"],
    "nevertheless": ["still", "even so", "but"],
    "consequently": ["so", "as a result", "because of this"],
    "subsequently": ["then", "after that", "next"],
    "furthermore": ["also", "plus", "on top of that", "and"],
    "additionally": ["also", "plus", "on top of that"],
    "conversely": ["on the flip side", "on the other hand"],
    "simultaneously": ["at the same time", "together"],
    "predominantly": ["mostly", "mainly", "largely"],
    "particularly": ["especially", "mainly", "specifically"],
    "essentially": ["basically", "really", "at its core"],
    "notably": ["especially", "in particular", "worth noting"],
    "evidently": ["clearly", "obviously", "it seems"],
    "markedly": ["noticeably", "clearly", "significantly"],
    "interconnected": ["linked", "connected", "tied together"],
    "data-driven": ["based on data", "evidence-based"],
    "forward-thinking": ["progressive", "ahead of the curve"],
    "well-established": ["proven", "solid", "long-standing"],
    "ever-evolving": ["always changing", "constantly shifting"],
}

_WORD_RE = re.compile(r"\b[\w']+\b")


def _swap_word(word: str, rng: random.Random) -> str:
    lower = word.lower()
    if lower not in _SYNONYMS:
        return word
    is_cap = word[0].isupper() if word else False
    chosen = rng.choice(_SYNONYMS[lower])
    if is_cap:
        return chosen[0].upper() + chosen[1:] if chosen else ""
    return chosen


def pass_synonyms(text: str, rng: random.Random) -> str:
    """Replace AI-typical words with human alternatives."""
    parts = []
    last_end = 0
    for match in _WORD_RE.finditer(text):
        parts.append(text[last_end : match.start()])
        parts.append(_swap_word(match.group(), rng))
        last_end = match.end()
    parts.append(text[last_end:])
    return "".join(parts)


# Pass 3: Transition replacement
_TRANSITIONS: list[tuple[str, str]] = [
    ("In today's rapidly evolving", "These days, in a fast-moving"),
    ("In today's quickly evolving", "In a world that moves quickly"),
    ("In today's fast-paced world", "In a fast-moving world"),
    ("it becomes increasingly evident that", "it's pretty clear that"),
    ("it becomes evident that", "you can see that"),
    ("it is important to note that", "it's worth noting"),
    ("it is worth noting that", "one thing to keep in mind is"),
    ("it should be noted that", "keep in mind"),
    ("in the realm of", "in"),
    ("in the context of", "when it comes to"),
    ("in light of", "given"),
    ("with regard to", "about"),
    ("in order to", "to"),
    ("due to the fact that", "because"),
    ("as a matter of fact", "actually"),
    ("at the end of the day", "ultimately"),
    ("on the other hand", "then again"),
    ("by and large", "mostly"),
    ("a wide range of", "many different"),
    ("a diverse range of", "all sorts of"),
    ("plays a crucial role", "matters a lot"),
    ("plays a pivotal role", "is really important"),
    ("plays a key role", "is a big deal"),
    ("are not merely", "aren't just"),
    ("is not merely", "isn't just"),
    ("pave the way for", "open doors for"),
    ("the way for a more", "the door to a more"),
    ("across numerous", "across many"),
    ("across various", "in different"),
]


def pass_transitions(text: str) -> str:
    """Replace formal transitions with casual alternatives."""
    result = text
    for from_phrase, to_phrase in _TRANSITIONS:
        pattern = re.compile(re.escape(from_phrase), re.IGNORECASE)
        result = pattern.sub(to_phrase, result)
    return result


# Pass 4: Contraction injection
_CONTRACTIONS: list[tuple[str, str]] = [
    ("It is not", "It's not"),
    ("it is not", "it's not"),
    ("do not", "don't"),
    ("does not", "doesn't"),
    ("did not", "didn't"),
    ("is not", "isn't"),
    ("are not", "aren't"),
    ("was not", "wasn't"),
    ("were not", "weren't"),
    ("will not", "won't"),
    ("would not", "wouldn't"),
    ("could not", "couldn't"),
    ("should not", "shouldn't"),
    ("cannot", "can't"),
    ("can not", "can't"),
    ("it is", "it's"),
    ("that is", "that's"),
    ("there is", "there's"),
    ("they are", "they're"),
    ("we are", "we're"),
    ("you are", "you're"),
    ("I am", "I'm"),
    ("I have", "I've"),
    ("I will", "I'll"),
    ("it will", "it'll"),
    ("they will", "they'll"),
    ("we will", "we'll"),
    ("who is", "who's"),
    ("what is", "what's"),
    ("let us", "let's"),
    ("Do not", "Don't"),
    ("Does not", "Doesn't"),
    ("Did not", "Didn't"),
    ("Is not", "Isn't"),
    ("Are not", "Aren't"),
    ("Was not", "Wasn't"),
    ("Will not", "Won't"),
    ("Would not", "Wouldn't"),
    ("Could not", "Couldn't"),
    ("Should not", "Shouldn't"),
    ("Cannot", "Can't"),
    ("It is", "It's"),
    ("That is", "That's"),
    ("There is", "There's"),
    ("They are", "They're"),
    ("We are", "We're"),
    ("You are", "You're"),
    ("We will", "We'll"),
    ("They will", "They'll"),
    ("It will", "It'll"),
    ("Who is", "Who's"),
    ("What is", "What's"),
    ("Let us", "Let's"),
]


def pass_contractions(text: str) -> str:
    """Inject contractions for natural speech."""
    result = text
    for from_phrase, to_phrase in _CONTRACTIONS:
        result = result.replace(from_phrase, to_phrase)
    return result


# Pass 5: Burstiness injection
_SENTENCE_RE = re.compile(r"[.!?]+")


def pass_burstiness(text: str, rng: random.Random) -> str:
    """Break long sentences, merge short ones for natural rhythm."""
    sentences = [s.strip() for s in _SENTENCE_RE.split(text) if s.strip()]
    if len(sentences) < 3:
        return text

    result = []
    for sentence in sentences:
        words = sentence.split()
        word_count = len(words)
        if word_count > 25:
            split_at = word_count // 2
            for i in range(word_count // 3, (2 * word_count) // 3):
                if i < len(words) and words[i].endswith(","):
                    split_at = i + 1
                    break
            first_half = " ".join(words[:split_at]).rstrip(",")
            second_half = " ".join(words[split_at:])
            if second_half:
                second_half = second_half[0].upper() + second_half[1:]
            result.append(first_half)
            result.append(second_half)
        else:
            result.append(sentence)

    final = []
    i = 0
    while i < len(result):
        word_count = len(result[i].split())
        if word_count < 10 and i + 1 < len(result) and rng.random() < 0.3:
            connector = " — " if rng.random() < 0.5 else "; "
            merged = result[i] + connector + result[i + 1][0].lower() + result[i + 1][1:]
            final.append(merged)
            i += 2
        else:
            final.append(result[i])
            i += 1

    return ". ".join(final) + "." if final else text


# Pass 6: Human filler injection
_FILLERS = [
    "Honestly, ",
    "The thing is, ",
    "What's interesting is that ",
    "If you think about it, ",
    "Look, ",
    "Here's the deal: ",
    "To put it simply, ",
    "In simple terms, ",
    "The reality is, ",
    "At the end of the day, ",
    "Truth be told, ",
    "When you break it down, ",
]


def pass_fillers(text: str, rng: random.Random) -> str:
    """Inject casual filler phrases for human feel."""
    sentences = [s.strip() for s in _SENTENCE_RE.split(text) if s.strip()]
    if len(sentences) < 3:
        return text

    result = []
    filler_count = 0
    max_fillers = 3 if len(sentences) > 6 else 2

    for i, sentence in enumerate(sentences):
        if i > 0 and i % 2 == 0 and filler_count < max_fillers and rng.random() < 0.45:
            filler = rng.choice(_FILLERS)
            lower = sentence[0].lower() + sentence[1:] if sentence else ""
            result.append(filler + lower)
            filler_count += 1
        else:
            result.append(sentence)

    return ". ".join(result) + "." if result else text


# Pass 7: AI padding strip
_AI_PADDING: list[tuple[str, str]] = [
    ("It is important to understand that ", ""),
    ("It is crucial to recognize that ", ""),
    ("It is essential to acknowledge that ", ""),
    ("It is noteworthy that ", ""),
    ("It goes without saying that ", ""),
    ("Needless to say, ", ""),
    ("As we all know, ", ""),
    ("As previously mentioned, ", ""),
    ("In conclusion, ", "So, "),
    ("To summarize, ", "Basically, "),
    ("In summary, ", "So basically, "),
    ("All in all, ", "Overall, "),
    ("Taking everything into account, ", "All things considered, "),
    ("Given the above, ", "With all that, "),
]


def pass_strip_ai_padding(text: str) -> str:
    """Remove AI-typical padding phrases."""
    result = text
    for from_phrase, to_phrase in _AI_PADDING:
        result = result.replace(from_phrase, to_phrase)
    return result


# Pass 8: Homoglyph perturbation
_HOMOGLYPHS = {
    "a": "а",
    "c": "с",
    "e": "е",
    "o": "о",
    "p": "р",
    "x": "х",
    "y": "у",
    "A": "А",
    "C": "С",
    "E": "Е",
    "O": "О",
    "P": "Р",
    "X": "Х",
}


def apply_homoglyphs(text: str) -> str:
    """Inject Cyrillic homoglyphs to break tokenizers."""
    rng = random.Random(len(text) ^ 0xCAFE)
    result = []
    for c in text:
        if c in _HOMOGLYPHS and rng.random() < 0.15:
            result.append(_HOMOGLYPHS[c])
        else:
            result.append(c)
        if c != " " and rng.random() < 0.05:
            result.append("\u200c")
    return "".join(result)


# Master function
@dataclass
class GhostMarkResult:
    text: str
    passes_applied: int
    chars_changed: int


def shatter_synthid_text(text: str, aggressive: bool = False, seed: int | None = None) -> GhostMarkResult:
    """Run all GhostMark passes to destroy AI statistical patterns."""
    if seed is not None:
        rng = random.Random(seed)
    else:
        rng = random.Random(len(text) ^ 0xDEAD)

    original = text
    text = scrub_unicode(text)
    text = pass_synonyms(text, rng)
    text = pass_transitions(text)
    text = pass_contractions(text)
    text = pass_burstiness(text, rng)
    text = pass_fillers(text, rng)
    text = pass_strip_ai_padding(text)
    if aggressive:
        text = apply_homoglyphs(text)

    return GhostMarkResult(text=text, passes_applied=8, chars_changed=len(text) - len(original))


# ================================================================
# PANOPTES: Attribution Features
# Source: https://github.com/marketstandard/Panoptes (MIT)
# ================================================================

_PANOPTES_CONNECTORS = {"however", "therefore", "moreover", "additionally", "overall", "furthermore"}
_PANOPTES_STRUCTURE_MARKERS = ("\n-", "\n*", ":", ";", "(", ")", "[", "]")
_PANOPTES_WORD_RE = re.compile(r"\b[\w']+\b")
_PANOPTES_SENTENCE_RE = re.compile(r"[.!?]+")


def extract_attribution_features(text: str) -> dict[str, float]:
    """Extract the seven Panoptes attribution features."""
    words = _PANOPTES_WORD_RE.findall(text.lower())
    if not words:
        return {
            "long_words": 0.0,
            "connectors": 0.0,
            "unique_ratio": 0.0,
            "short_sentences": 0.0,
            "structured": 0.0,
            "digits": 0.0,
            "balanced_lines": 0.0,
        }

    counts = {}
    for w in words:
        counts[w] = counts.get(w, 0) + 1
    total = len(words)

    long_words = sum(1 for w in words if len(w) > 6) / total
    connectors = sum(1 for w in words if w in _PANOPTES_CONNECTORS) / total
    unique_ratio = len(counts) / total

    sentences = [s for s in _PANOPTES_SENTENCE_RE.split(text) if s.strip()]
    short_sentences = sum(1 for s in sentences if len(_PANOPTES_WORD_RE.findall(s)) < 10) / max(len(sentences), 1)
    structured = sum(1 for m in _PANOPTES_STRUCTURE_MARKERS if m in text) / len(_PANOPTES_STRUCTURE_MARKERS)
    digits = sum(1 for w in words if w.isdigit()) / total

    lines = [line for line in text.splitlines() if line.strip()]
    line_lengths = [len(line) for line in lines]
    if line_lengths:
        mean_len = sum(line_lengths) / len(line_lengths)
        variance = sum((l - mean_len) ** 2 for l in line_lengths) / len(line_lengths)
        import math

        balanced_lines = min(math.sqrt(variance) / 50.0, 1.0)
    else:
        balanced_lines = 0.5

    return {
        "long_words": round(long_words, 4),
        "connectors": round(connectors, 4),
        "unique_ratio": round(unique_ratio, 4),
        "short_sentences": round(short_sentences, 4),
        "structured": round(structured, 4),
        "digits": round(digits, 4),
        "balanced_lines": round(balanced_lines, 4),
    }


def heuristic_ai_score(text: str) -> float:
    """Compute heuristic AI-likelihood score (0-100, higher = more AI-like)."""
    features = extract_attribution_features(text)
    score = 0.0
    score += features["long_words"] * 15
    score += features["connectors"] * 25
    score += (1 - features["unique_ratio"]) * 20
    score += features["short_sentences"] * 15
    score += features["structured"] * 10
    score += features["balanced_lines"] * 15
    return min(max(score, 0.0), 100.0)


# ================================================================
# TWS Integration Helpers
# ================================================================


def tws_wash_text(text: str, mode: str = "ghostmark", aggressive: bool = False) -> dict:
    """TWS-native wash function combining GhostMark + Panoptes scoring.

    Args:
        text: Input text
        mode: "ghostmark" (statistical) or "panoptes" (feature extraction only)
        aggressive: Apply homoglyph perturbation

    Returns:
        dict with text, before_score, after_score, improvement, features
    """
    before_score = heuristic_ai_score(text)

    if mode == "ghostmark":
        result = shatter_synthid_text(text, aggressive=aggressive)
        after_text = result.text
    else:
        after_text = scrub_unicode(text)
        result = GhostMarkResult(text=after_text, passes_applied=1, chars_changed=len(after_text) - len(text))

    after_score = heuristic_ai_score(after_text)
    features = extract_attribution_features(after_text)

    return {
        "text": after_text,
        "before_score": round(before_score, 2),
        "after_score": round(after_score, 2),
        "improvement": round(before_score - after_score, 2),
        "passes_applied": result.passes_applied,
        "chars_changed": result.chars_changed,
        "features": features,
    }
