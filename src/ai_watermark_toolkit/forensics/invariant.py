"""Invariant-feature multi-bit text watermarking (Yoo et al., ACL 2023, light).

Implements the core architecture of
"Robust Multi-bit Natural Language Watermarking through Invariant Features"
without heavy dependencies:

Phase 1 (state): mask positions are pinned to *invariant anchors* — keywords /
proper nouns that an adversary cannot change without destroying utility.
Anchors are detected with a lightweight stopword + casing + frequency
heuristic (NER/YAKE from the paper are optional heavy extras; the principle
is the same). Anchors themselves are never masked; masks sit adjacent.

Phase 2 (embedding): for each mask position, candidate tokens are collected
(optional Ollama infill, otherwise a built-in synonym bank), filtered and
alphabetically sorted. The Cartesian product of per-position candidates is the
codebook; a bit string is encoded by choosing one combination. Extraction
reconstructs the state from (possibly corrupted) text and reads the
combination back.

Robust infill model (paper's reverse-KL trick) is NOT reproduced here — that
requires BERT fine-tuning. The state-side invariance (R_g1) is the part that
carries most of the robustness and is fully implemented. Use
``ollama_infill=True`` to get better candidate quality from a local model.
"""

from __future__ import annotations

import json
import re
import urllib.request
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Built-in anchors / stopwords (DE + EN, small but sufficient for tests/demo)
# ---------------------------------------------------------------------------

_STOPWORDS = frozenset(
    """
    a an and are as at be by for from has have he her his i in is it its
    of on or that the their them they this to was we were will with you your
    auch auf aus bei das dem den der die ein eine einem einen einer es für
    hat ich im in ist mit nach nicht nur sein sich sie so und vom von vor
    war werden wie zu zum zur über
    """.split()
)


def _is_proper_noun(word: str, index: int, tokens: Sequence[str]) -> bool:
    """Lightweight proper-noun heuristic: capitalized mid-sentence word."""
    if not word or word[0].islower():
        return False
    if index == 0:
        # First token is capitalized anyway — only counts if a later
        # token in the sentence is also capitalized (sentence-initial
        # capitalization is not a name signal).
        return any(i > 0 and t[0].isupper() for i, t in enumerate(tokens[1:], start=1))
    return True


def detect_anchors(tokens: Sequence[str]) -> List[int]:
    """Return indices of invariant anchor words (keywords / proper nouns).

    Heuristic: drop stopwords and pure punctuation; keep words that appear
    more than once (frequency signal, YAKE-lite) or that look like proper
    nouns (capitalized mid-sentence). Matches the paper's intent: anchors
    are the words an adversary cannot replace without losing meaning.
    """
    clean = [re.sub(r"[^A-Za-zÄÖÜäöüß0-9'\-]", "", t) for t in tokens]
    freq: Dict[str, int] = {}
    for w in clean:
        low = w.lower()
        if low and low not in _STOPWORDS and not low.isdigit():
            freq[low] = freq.get(low, 0) + 1

    anchors: List[int] = []
    for i, w in enumerate(clean):
        if not w:
            continue
        low = w.lower()
        if low in _STOPWORDS or low.isdigit():
            continue
        if freq.get(low, 0) > 1 or _is_proper_noun(w, i, clean):
            anchors.append(i)
    return anchors


# ---------------------------------------------------------------------------
# Phase 1: state S = mask positions adjacent to anchors
# ---------------------------------------------------------------------------

def select_mask_positions(
    tokens: Sequence[str],
    anchors: Sequence[int],
    max_masks: int | None = None,
) -> List[int]:
    """Choose mask positions: adjacent to anchors, never the anchors themselves.

    Anchors are invariant by construction; the words *next* to them are the
    softest insertion points (paper: "word adjacent to the keyword can be
    selected as the mask"). Falls back to non-anchor positions when there
    are not enough neighbours. ``max_masks`` caps payload per sentence.
    """
    anchor_set = set(anchors)
    n = len(tokens)
    candidates: List[int] = []
    # 1st pass: immediate neighbours of anchors
    for a in anchors:
        for idx in (a - 1, a + 1):
            if 0 <= idx < n and idx not in anchor_set and idx not in candidates:
                candidates.append(idx)
    # 2nd pass: any non-anchor, non-stopword position
    for i in range(n):
        if i in anchor_set or i in candidates:
            continue
        low = re.sub(r"[^A-Za-zÄÖÜäöüß0-9'\-]", "", tokens[i]).lower()
        if low and low not in _STOPWORDS:
            candidates.append(i)
    if max_masks is not None:
        candidates = candidates[:max_masks]
    return sorted(candidates)


def state_of(text: str, max_masks: int | None = None) -> dict:
    """Compute state S for a text: tokens, anchors, mask positions."""
    tokens = text.split()
    anchors = detect_anchors(tokens)
    masks = select_mask_positions(tokens, anchors, max_masks)
    return {"tokens": tokens, "anchors": anchors, "masks": masks}


# ---------------------------------------------------------------------------
# Candidate source: built-in synonym bank + optional Ollama infill
# ---------------------------------------------------------------------------

_SYNONYMS: Dict[str, Tuple[str, ...]] = {
    # DE (incl. common inflections so demo text hits the bank)
    "schnell": ("flink", "rasch", "zügig"),
    "schnelle": ("flinke", "rasche", "zügige"),
    "wichtig": ("bedeutend", "relevant", "wesentlich"),
    "wichtige": ("bedeutende", "relevante", "wesentliche"),
    "groß": ("riesig", "gewaltig", "enorm"),
    "große": ("riesige", "gewaltige", "enorme"),
    "klein": ("winzig", "minimal", "gering"),
    "kleine": ("winzige", "minimale", "geringe"),
    "gut": ("stark", "solide", "exzellent"),
    "gute": ("starke", "solide", "exzellente"),
    "schlecht": ("mangelhaft", "schwach", "dürftig"),
    "schlechte": ("mangelhafte", "schwache", "dürftige"),
    "klar": ("deutlich", "eindeutig", "offensichtlich"),
    "klare": ("deutliche", "eindeutige", "offensichtliche"),
    "neu": ("frisch", "aktuell", "modern"),
    "neue": ("frische", "aktuelle", "moderne"),
    "alt": ("veraltet", "betagt", "herkömmlich"),
    "alte": ("veraltete", "betagte", "herkömmliche"),
    "einfach": ("simpel", "unkompliziert", "leicht"),
    "einfache": ("simplе", "unkomplizierte", "leichte"),
    "schwer": ("komplex", "anspruchsvoll", "schwierig"),
    "schwere": ("komplexe", "anspruchsvolle", "schwierige"),
    "möglich": ("denkbar", "realisierbar", "machbar"),
    "mögliche": ("denkbare", "realisierbare", "machbare"),
    "stark": ("kräftig", "mächtig", "intensiv"),
    "starke": ("kräftige", "mächtige", "intensive"),
    "besser": ("überlegen", "vorteilhafter", "höherwertig"),
    "viele": ("zahlreiche", "unzählige", "diverse"),
    "robust": ("widerstandsfähig", "stabil", "belastbar"),
    "robuste": ("widerstandsfähige", "stabile", "belastbare"),
    "einzige": ("alleinige", "exklusive", "einzeln"),
    # EN
    "fast": ("quick", "rapid", "swift"),
    "important": ("significant", "crucial", "essential"),
    "big": ("large", "huge", "massive"),
    "small": ("tiny", "minor", "slight"),
    "good": ("solid", "strong", "excellent"),
    "bad": ("poor", "weak", "inferior"),
    "clear": ("obvious", "evident", "explicit"),
    "new": ("fresh", "current", "modern"),
    "old": ("dated", "aged", "conventional"),
    "simple": ("plain", "straightforward", "easy"),
    "hard": ("complex", "demanding", "difficult"),
    "possible": ("feasible", "achievable", "viable"),
    "strong": ("powerful", "robust", "intense"),
    "better": ("superior", "preferable", "higher"),
    "many": ("numerous", "countless", "various"),
}


def _synonym_candidates(word: str) -> List[str]:
    low = word.lower()
    return [s for s in _SYNONYMS.get(low, ()) if s.lower() != low]


def _ollama_infill(
    sentence: str,
    mask_index: int,
    model: str,
    top_k: int = 3,
    timeout: float = 30.0,
) -> List[str]:
    """Ask a local Ollama model to fill one masked position (best effort).

    Returns up to ``top_k`` candidate tokens. Failures (model missing,
    timeout, non-JSON) degrade to [] — callers fall back to the synonym bank.
    Also rejects chatty/meta responses (e.g. tool-instruct models that answer
    "The user wants me to...") by length and stopword content, so garbage
    never enters the codebook.
    """
    tokens = sentence.split()
    prompt_sentence = " ".join(
        w if i != mask_index else "[MASK]" for i, w in enumerate(tokens)
    )
    payload = json.dumps({
        "model": model,
        "prompt": (
            "List 3 different natural words that fit the [MASK] in this "
            "sentence. Reply with ONLY the words, comma-separated, no "
            f"explanation.\nText: {prompt_sentence}\nWords:"
        ),
        "stream": False,
        "options": {"num_predict": 24, "temperature": 0.0},
    }).encode("utf-8")
    req = urllib.request.Request(
        "http://localhost:11434/api/generate", data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    out = (data.get("response") or "").strip()
    # The prompt demands a comma-separated answer. If the model rambled
    # (meta-text like "The user wants me to...") there are no commas and
    # many words — reject before it can seed the codebook.
    if "," not in out:
        words = out.split()
        if len(words) > 1:
            return []
    else:
        words = [w for part in out.split(",") for w in re.findall(r"[A-Za-zÄÖÜäöüß'\-]+", part)]
    if not words:
        return []
    # Meta-text guard: a genuine infill answer is 1-3 words. A model that
    # rambles ("The user wants me to complete...") must not seed candidates.
    if len(words) > 4:
        return []
    # Stopword guard: fillers ("the", "user", "wants") are not usable
    # codebook candidates — they'd let unmarked text decode as bits.
    content = [w for w in words if w.lower() not in _STOPWORDS]
    if not content:
        return []
    # dedupe (case-neutral), cap at top_k
    seen, result = set(), []
    for w in content:
        low = w.lower()
        if low not in seen:
            seen.add(low)
            result.append(w)
        if len(result) >= top_k:
            break
    return result


def candidate_sets(
    state: dict,
    options: dict | None = None,
) -> Tuple[Dict[int, List[str]], Dict[int, str]]:
    """Per-mask candidate lists + the original token (for decode comparison).

    Priority: explicit ``candidates`` option (caller-provided) > Ollama infill
    (if ``ollama_infill`` and a model is given) > built-in synonym bank. If a
    position yields <2 candidates it is dropped from the codebook (no bit).
    """
    opts = options or {}
    tokens = state["tokens"]
    masks = state["masks"]
    orig: Dict[int, str] = {i: tokens[i] for i in masks}
    explicit = opts.get("candidates") or {}
    model = opts.get("ollama_model")
    use_ollama = bool(opts.get("ollama_infill") and model)

    cands: Dict[int, List[str]] = {}
    for i in masks:
        word = tokens[i]
        pool: List[str] = []
        if isinstance(explicit, dict) and str(i) in explicit:
            pool = list(explicit[str(i)])
        elif use_ollama:
            pool = _ollama_infill(" ".join(tokens), i, model, top_k=opts.get("top_k", 3))
        if len(pool) < 2:
            pool = _synonym_candidates(word)
        if len(pool) >= 2:
            # filter + alphabetically sort (paper §3.2 step 2).
            # The ORIGINAL token is deliberately excluded from the codebook:
            # an unmarked token must NOT decode as a valid bit.
            dedup = sorted(set(p.lower() for p in pool if p.lower() != word.lower()))
            if len(dedup) >= 2:
                cands[i] = dedup[:4]
    return cands, orig


# ---------------------------------------------------------------------------
# Phase 2: encode bits into the codebook, extract them back
# ---------------------------------------------------------------------------
#
# Codebook scheme (paper §3.2): each mask position i has an alphabetically
# sorted candidate list cands[i] (>=2 entries, original token excluded).
# Encoding a bit b at position i means choosing cands[i][b]. The message is
# the sequence of choices — the combination IS the payload. Deterministic and
# injective by construction, so extraction is a pure table lookup (no hash
# guessing). Payload = 1 bit per usable mask position.

def embed(
    text: str,
    message: str,
    options: dict | None = None,
) -> dict:
    """Embed a binary message (string of 0/1) into the text via the codebook.

    Returns the watermarked text, state, per-position choices, and the number
    of bits actually embedded. Bits beyond codebook capacity are left unused.
    """
    opts = dict(options or {})
    max_masks = opts.get("max_masks")
    state = state_of(text, max_masks=max_masks)
    cands, orig = candidate_sets(state, options)
    masks = sorted(cands.keys())
    if not masks:
        return {"text": text, "bits_embedded": 0, "masks": [], "choices": {}, "state": state}

    bits = [int(c) for c in re.sub(r"[^01]", "", message)]
    if not bits:
        return {"text": text, "bits_embedded": 0, "masks": masks, "choices": {}, "state": state}

    tokens = list(state["tokens"])
    choices: Dict[int, str] = {}
    used = 0
    for i in masks:
        if used >= len(bits):
            break
        pool = cands[i]
        bit = bits[used]
        chosen = pool[bit % len(pool)]
        tokens[i] = chosen
        choices[i] = {"original": orig[i], "chosen": chosen, "bit": bit}
        used += 1

    return {
        "text": " ".join(tokens),
        "bits_embedded": used,
        "masks": masks,
        "choices": choices,
        "state": state,
    }


def extract(
    watermarked: str,
    original: str,
    options: dict | None = None,
) -> dict:
    """Recover the embedded bit string from a (possibly corrupted) text.

    Recomputes state from the *original* (the invariant anchors come from the
    reference, matching the paper's setup where both parties share g1) and
    reads the combination that appears at each mask position. Positions whose
    token is not in the candidate list (corrupted / edited) are reported with
    an unknown marker and a lower confidence.
    """
    opts = dict(options or {})
    ref_state = state_of(original, max_masks=opts.get("max_masks"))
    cands, orig = candidate_sets(ref_state, options)
    masks = sorted(cands.keys())

    wm_tokens = watermarked.split()
    recovered_bits: List[str] = []
    recovered: Dict[int, str] = {}
    known = 0
    total = 0
    for i in masks:
        if i >= len(wm_tokens):
            continue
        seen = wm_tokens[i].lower()
        pool = cands[i]
        total += 1
        if seen in pool:
            recovered[i] = seen
            recovered_bits.append(str(pool.index(seen)))
            known += 1
        else:
            recovered[i] = orig[i]
            recovered_bits.append("?")

    return {
        "bits": "".join(recovered_bits),
        "recovered": recovered,
        "masks_used": total,
        "confidence": round(known / total, 3) if total else 1.0,
        "state": ref_state,
    }


# ---------------------------------------------------------------------------
# Corruption robustness helpers (paper §2.2)
# ---------------------------------------------------------------------------

def corrupt(text: str, ratio: float = 0.05, seed: int = 0, mode: str = "substitute") -> str:
    """Apply D/I/S corruption to non-anchor tokens (for robustness tests).

    ``mode``: 'delete' | 'insert' | 'substitute'. Only tokens that are NOT
    anchors get corrupted — this mirrors the paper's invariant-feature claim:
    corruption that preserves utility hits the replaceable parts.
    """
    import random
    rng = random.Random(seed)
    tokens = text.split()
    anchors = set(detect_anchors(tokens))
    n_corrupt = max(1, int(round(ratio * len(tokens))))
    corruptible = [i for i in range(len(tokens)) if i not in anchors]
    if not corruptible:
        return text
    idxs = rng.sample(corruptible, min(n_corrupt, len(corruptible)))
    out = list(tokens)
    filler = ["der", "die", "das", "und", "ist", "a", "the", "of", "to", "in"]
    for i in sorted(idxs, reverse=True):
        if mode == "delete":
            out.pop(i)
        elif mode == "insert":
            out.insert(i + 1, rng.choice(filler))
        else:  # substitute
            out[i] = rng.choice(filler)
    return " ".join(out)
