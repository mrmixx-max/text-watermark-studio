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
from pathlib import Path

_TOKEN_RE = re.compile(r"[\wäöüßÄÖÜ]+", flags=re.UNICODE)
_K_DEFAULT = 5
_SIG_LEN = 128


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


def _hash_shingle(shingle: tuple[str, ...], seed: int) -> int:
    h = hashlib.sha256(f"{seed}:{' '.join(shingle)}".encode("utf-8")).hexdigest()
    return int(h[:16], 16)


def _minhash(text: str, n: int = _SIG_LEN, k: int = _K_DEFAULT) -> tuple[tuple[int, ...], list[tuple[str, ...]]]:
    sh = _shingles(text, k)
    if not sh:
        return tuple(), []
    sig = tuple(min(_hash_shingle(s, i) for s in sh) for i in range(n))
    return sig, sh


def _jaccard(sig_a: tuple[int, ...], sig_b: tuple[int, ...]) -> float:
    if not sig_a or not sig_b:
        return 0.0
    equal = sum(1 for a, b in zip(sig_a, sig_b) if a == b)
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


def _iter_corpus(corpus_paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for p in corpus_paths:
        if p.is_dir():
            files.extend(sorted(f for f in p.rglob("*") if f.is_file()))
        elif p.is_file():
            files.append(p)
    return files


def check_similarity(input_text: str, corpus_paths: list[Path],
                     threshold: float = 0.4, top: int = 5,
                     k: int = _K_DEFAULT) -> dict:
    """Compare input_text against every readable file in the corpus.

    Returns a dict with per-document similarity, verdicts and fundstelle
    evidence. Binary/unreadable files are listed as skipped, not errors.
    """
    sig_a, sh_a = _minhash(input_text, k=k)
    results: list[dict] = []
    skipped: list[str] = []
    for path in _iter_corpus(corpus_paths):
        text = _readable_text(path)
        if not text.strip():
            skipped.append(str(path))
            continue
        sig_b, sh_b = _minhash(text, k=k)
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
