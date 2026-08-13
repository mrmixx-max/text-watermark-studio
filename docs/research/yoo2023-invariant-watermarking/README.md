# Yoo et al. (2023) — Robust Multi-bit Natural Language Watermarking through Invariant Features

ACL 2023 Long Paper (pages 2092–2115)
- **Authors:** KiYoon Yoo (SNU), Wonhyuk Ahn (Webtoon AI), Jiho Jang (SNU), Nojun Kwak (SNU)
- **Official code:** https://github.com/bangawayoo/nlp-watermarking
- **Files in this directory:** `yoo2023-invariant-features.pdf` (original paper), `yoo2023-invariant-features.txt` (full extracted text, 24 pages)

---

## TL;DR

Multi-bit text watermarking that survives corruption by embedding the mark at
**invariant positions**: semantic keywords (NER + YAKE) and syntactic dependency
anchors. A **corruption-resistant infill model** (BERT fine-tuned with a
reverse-KL consistency loss against corrupted inputs) keeps the candidate sets
stable under 2.5–5 % word-level corruption.

**Result:** +16.8 pp average bit-error-rate (BER) robustness improvement over
the prior baseline (ContextLS) across four datasets, three corruption types
(deletion/insertion/substitution), two corruption ratios.

---

## Core Method (two phases)

### Phase 1 — Mask Position Selection (state S)

Pick mask positions using *invariant features* — parts of the text an adversary
cannot change without destroying utility:

1. **Keyword anchors (semantic):** NER entities (proper nouns can't be
   synonym-swapped) + YAKE keywords. Masks go *adjacent to* keywords, keywords
   themselves are never masked.
2. **Syntactic anchors:** spaCy dependency parse. Dependency types are ordered by
   semantic drift (mask + infill + NLI entailment score, Algorithm 1 in paper),
   then masks are applied to high-invariance dependency types first. Fragile
   relations (coordination etc.) are deprioritized.

Robustness metric: `R_g1 = E[1(S = S̃)]` — same state recovered from corrupted
text. Yoo et al. achieve R_g1 ≈ 0.92–0.97 vs. ContextLS's 0.61–0.65 at 5%
corruption.

### Phase 2 — Watermark Encoding (message → text)

1. For each mask position `i ∈ S`: infill model returns top-k1 candidates.
2. Filter: drop punctuation, subwords, stopwords; keep top-k2, sort alphabetically.
3. Cartesian product of per-position candidate sets = codebook.
4. Keep only combinations where `g1(X_wm) = g1(X)` (state preserved) → valid
   watermark set. Each combination encodes a bit string; extraction reads the
   combination back from the (possibly corrupted) text.

### Robust Infill Model (the key novelty)

A vanilla BERT infiller is fragile: corrupted context changes the candidate set
(R_g2 << R_g1). Fix: fine-tune the infiller so the word distribution on corrupted
inputs stays close to the distribution on clean inputs:

```
L_consistency = Σ_{i∈S} KL(p̃_i ‖ p_i)
p̃_i = P(X̃_{∖i} | θ)          # corrupted context, trainable
p_i = P(X_{∖i} | FREEZE(θ))  # clean context, detached target
```

Details:
- **Sparse target** over top-k1 tokens (not the full 30k+ vocabulary) — matches
  what the watermarking actually uses.
- **Same invariant masking strategy at train time** as at inference (not random
  masking) — aligns train/test distributions.
- **Reverse KL** (not forward) — prevents "zero-forcing" predicted distributions.

Effect: R_g2 gains +0.07…+0.15 across datasets while R_g1 stays flat (Table 2).

---

## Key Numbers (Table 3, main results)

| Dataset | Method | BPW ↑ | BER ↓ @ 5% corr (D/I/S avg) |
|---|---|---|---|
| IMDB | ContextLS | 0.100 | ~0.36 |
| IMDB | Yoo (Syntactic + RI) | 0.144 | ~0.18 |
| WikiText-2 | ContextLS | 0.083 | ~0.36 |
| WikiText-2 | Yoo (Syntactic + RI) | 0.136 | ~0.23 |
| Dracula | Yoo (Syntactic + RI) | 0.146 | ~0.21 |

Payload ≈ 0.1 bit/word; semantic similarity stays high; human fluency ratings competitive.

---

## Relevance to Text Watermark Studio

This paper is the academic foundation for **robust multi-bit embedding at
invariant positions** — the family the studio's lab taxonomy calls
`semantic_structure` (`src/ai_watermark_toolkit/lab/families/semantic_structure.py`,
currently a demo placeholder counting phrases like "in summary"). The Yoo method
is the *real* implementation that placeholder should point to. Direct applicability:

| Studio concept | Yoo et al. contribution |
|---|---|
| Semantic markers | NER + YAKE anchors, masks adjacent to keywords |
| Syntactic markers | spaCy dependency parse, NLI-ordered mask types |
| Sampling/logit bias markers | Infill model candidate selection (top-k) |
| Robustness (forensics) | Reverse-KL consistency-trained infiller |
| Payload (multi-bit) | Cartesian-product codebook over candidate sets |

**Implementation sketch for studio integration:**

```
src/ai_watermark_toolkit/markers/
  invariant/
    __init__.py
    state.py        # Phase 1: S = f(X) — keyword + syntactic anchors (spaCy + YAKE + NER)
    encode.py       # Phase 2: S + message → watermarked text (infill model + codebook)
    decode.py       # S + text → message bits
    infill.py       # Robust infill wrapper (BERT + reverse-KL checkpoint or API)
```

Dependencies: `spacy` (+ `en_core_web_sm`/`de_core_news_sm`), `yake`, sentence
transformer (`all-MiniLM-L6-v2`) for corruption filtering, infill model
(BERT-style; optionally the official repo's fine-tuned checkpoint).

**Testing against studio benchmarks:** the studio already benchmarks
detect/clean/dilute on German+English fixtures. The invariant suite should add
corruption-robustness fixtures (D/I/S at 2.5%/5%) to match the paper's eval —
see `tests/` for the existing marker family patterns.

---

## Source

- Paper PDF: ACL Anthology `2023.acl-long.117`
- Extracted text generated 2026-08-13 from the ACL PDF (PyMuPDF), 24 pages, no OCR needed
