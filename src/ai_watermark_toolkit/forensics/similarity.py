"""Local corpus similarity check (honest plagiarism-adjacent tooling).

What this does: compares a document against YOUR OWN corpus and reports
literal-overlap similarity per source — deterministically, offline, with
fundstelle evidence.

What this does NOT do: it does not claim to detect plagiarism against the
web or any hidden corpus. MinHash measures near-duplicate literal overlap,
not paraphrased meaning. A heavily rewritten copy scores low, and the
report says so. That is the honest boundary: similarity to THESE sources,
no more, no less.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import OrderedDict
from pathlib import Path

_TOKEN_RE = re.compile(r"[\wäöüßÄÖÜ]+", flags=re.UNICODE)
_K_DEFAULT = 5
_SIG_LEN = 128
_MASK64 = (1 << 64) - 1
# splitmix64 constants (well-known 64-bit bijections)
_MIX1 = 0xBF58476D1CE4E5B9
_MIX2 = 0x94D049BB133111EB
_GOLDEN = 0x9E3779B97F4A7C15  # golden-ratio constant for permutation indexing


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _shingles(text: str, k: int = _K_DEFAULT) -> list[tuple[str, ...]]:
    """Token-based k-grams. Falls k > available tokens (very short text),
    fall back to a single shingle of all tokens so the text still hashes."""
    toks = _tokens(text)
    if not toks:
        return []
    kk = min(k, len(toks))
    return [tuple(toks[i:i + kk]) for i in range(len(toks) - kk + 1)]


def _shingle_digest(shingle: tuple[str, ...]) -> int:
    """ONE SHA256 per shingle -> 64-bit digest.

    The 128 per-signature permutations are derived from this single digest
    via splitmix64 bit-mixing (see _permute), so a document costs 1 SHA256
    per shingle instead of 128 (previous _hash_shingle did 128 SHA256 per
    shingle — the F4 hotspot).
    """
    h = hashlib.sha256(" ".join(shingle).encode("utf-8")).hexdigest()
    return int(h[:16], 16)


def _permute(h64: int, i: int) -> int:
    """Bijective bit-mixing permutation of a 64-bit hash for permutation i.

    splitmix64 finalizer is a permutation of the 64-bit space (invertible
    xor-shift/multiply chain); XOR-ing the permutation index (scaled by the
    golden ratio) into the digest before mixing yields 128 distinct
    permutations of the shingle hashes. Each permutation's minimum over the
    shingle set is the classic MinHash estimator — no second SHA256 needed.
    """
    x = (h64 ^ (i * _GOLDEN)) & _MASK64
    x = ((x ^ (x >> 30)) * _MIX1) & _MASK64
    x = ((x ^ (x >> 27)) * _MIX2) & _MASK64
    return (x ^ (x >> 31)) & _MASK64


def _minhash(text: str, n: int = _SIG_LEN, k: int = _K_DEFAULT) -> tuple[tuple[int, ...], list[tuple[str, ...]]]:
    sh = _shingles(text, k)
    if not sh:
        return (), []
    digests = [_shingle_digest(s) for s in sh]
    # Transposed scan: track the running minimum per permutation while
    # iterating shingles once (same minima as `min(...)` per permutation,
    # but without 128 generator passes over the shingle list).
    mins = [_MASK64] * n
    perm = _permute
    for d in digests:
        for i in range(n):
            v = perm(d, i)
            if v < mins[i]:
                mins[i] = v
    return tuple(mins), sh


def _jaccard(sig_a: tuple[int, ...], sig_b: tuple[int, ...]) -> float:
    if not sig_a or not sig_b:
        return 0.0
    equal = sum(1 for a, b in zip(sig_a, sig_b, strict=False) if a == b)
    return equal / len(sig_a)


def _find_overlaps(sh_a: list[tuple[str, ...]], sh_b: list[tuple[str, ...]],
                   limit: int = 3) -> list[str]:
    """Example matching shingles as fundstelle evidence (word-level quotes)."""
    set_b = set(sh_b)
    seen: set[str] = set()
    out: list[str] = []
    for s in sh_a:
        if s in set_b:
            quote = " ".join(s)
            if quote not in seen:
                seen.add(quote)
                out.append(quote)
                if len(out) >= limit:
                    break
    return out


def _readable_text(path: Path) -> str:
    data = path.read_bytes()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return ""


def _iter_corpus(corpus_paths) -> list[Path]:
    """Resolve a list of str/Path entries into files.

    Direct callers (TUI action_similarity, API) pass plain strings; the CLI
    handler passes Path objects — one contract for both.
    """
    files: list[Path] = []
    for entry in corpus_paths:
        p = Path(entry)
        if p.is_dir():
            files.extend(sorted(f for f in p.rglob("*") if f.is_file()))
        elif p.is_file():
            files.append(p)
    return files


# ---------------------------------------------------------------------------
# Corpus signature cache (F4): check_similarity re-minhashed every corpus file
# on EVERY call. Signatures + shingles are now memoized keyed on
# (path, mtime_ns, size), so repeated checks over an unchanged corpus are
# near-instant. The cache is process-local (pragmatic, no data/ writes) and
# self-invalidating: any content change flips mtime/size and rebuilds that
# file's entry. clear_signature_cache() exists for tests / long-running UIs.
# ---------------------------------------------------------------------------
_SIG_CACHE_MAX = 512
_sig_cache: OrderedDict[tuple, tuple] = OrderedDict()


def _corpus_entry(path: Path, k: int = _K_DEFAULT) -> tuple:
    """Memoized (kind, payload) per corpus file.

    Returns ("ok", signature, shingles) for readable text files or
    ("skip",) for empty/binary/unreadable ones — the skip decision is
    cached too so a re-check does not re-read skipped files. ``k`` is part
    of the cache key: different shingle widths must never share entries.
    """
    try:
        st = path.stat()
    except OSError:
        return ("skip",)
    key = (str(path), st.st_mtime_ns, st.st_size, k)
    hit = _sig_cache.get(key)
    if hit is not None:
        return hit
    text = _readable_text(path)
    if not text.strip():
        entry = ("skip",)
    else:
        sig, sh = _minhash(text, k=k)
        entry = ("ok", sig, sh)
    _sig_cache[key] = entry
    if len(_sig_cache) > _SIG_CACHE_MAX:
        _sig_cache.popitem(last=False)
    return entry


def clear_signature_cache() -> None:
    """Drop all cached corpus signatures (next check re-hashes everything)."""
    _sig_cache.clear()


def check_similarity(input_text: str, corpus_paths: list[Path],
                     threshold: float = 0.4, top: int = 5,
                     k: int = _K_DEFAULT) -> dict:
    """Compare input_text against every readable file in the corpus.

    Returns a dict with per-document similarity, verdicts and fundstelle
    evidence. Binary/unreadable files are listed as skipped, not errors.
    Corpus signatures are cached keyed on (path, mtime, size); repeated
    checks over an unchanged corpus skip re-hashing entirely.
    """
    sig_a, sh_a = _minhash(input_text, k=k)
    results: list[dict] = []
    skipped: list[str] = []
    for path in _iter_corpus(corpus_paths):
        entry = _corpus_entry(path, k=k)
        if entry[0] == "skip":
            skipped.append(str(path))
            continue
        _, sig_b, sh_b = entry
        score = _jaccard(sig_a, sig_b)
        overlaps = _find_overlaps(sh_a, sh_b)
        results.append({
            "path": str(path),
            "similarity": round(score, 4),
            "verdict": _verdict(score, threshold),
            "fundstellen": overlaps,
        })
    results.sort(key=lambda r: r["similarity"], reverse=True)
    findings = [r for r in results if r["similarity"] >= threshold]
    return {
        "input": {"tokens": len(_tokens(input_text)), "threshold": threshold},
        "corpus": {"files": len(results), "skipped": len(skipped),
                   "skipped_paths": skipped},
        "findings": findings[:top],
        "top_similarity": results[0]["similarity"] if results else 0.0,
    }


def _verdict(score: float, threshold: float) -> str:
    if score >= threshold:
        return "high"
    if score >= threshold * 0.5:
        return "medium"
    if score > 0.0:
        return "low"
    return "none"


def render_text(report: dict) -> str:
    lines = [f"Similarity check — {report['input']['tokens']} tokens input, "
             f"threshold {report['input']['threshold']}",
             f"Corpus: {report['corpus']['files']} files"
             + (f", {report['corpus']['skipped']} skipped" if report["corpus"]["skipped"] else "")]
    for f in report["findings"]:
        lines.append(f"  {f['similarity']:.2f}  {f['verdict']:<7} {f['path']}")
        for quote in f["fundstellen"]:
            lines.append(f"        ~ \"{quote[:80]}\"")
    if not report["findings"]:
        lines.append("  no findings above threshold")
    return "\n".join(lines)


def render_json(report: dict) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2, default=str)
