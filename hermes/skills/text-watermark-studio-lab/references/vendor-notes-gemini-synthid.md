# How Gemini / SynthID marks AI-generated content (reference)

Class-level documentation of Google's SynthID provenance surfaces. Not an
implementation — the studio reports claims and separates verifiable from
best-effort.

## Primary sources

- Dathathri et al., "Scalable watermarking for identifying large language
  model outputs" (Nature 2024) — the SynthID-Text watermarks
- google-deepmind/synthid-text (research reference)
- Google AI for Developers, "SynthID safeguards" (Gemini API docs)
- aloshdenny/reverse-SynthID (research reference, non-commercial)

## The two SynthID surfaces

1. **SynthID-Text** — a *statistical* text watermark. It biases the token
   sampling of the underlying Gemini model (tournament sampling over a
   seeded PRF). It is the canonical KGW-family scheme and survives light
   paraphrase but degrades under heavy rewording, backtranslation, and
   low-entropy text.
   The public detector is gated (no free universal detector); detection
   requires the model + keys, which are not public.

2. **SynthID media (image/audio/video)** — an *imperceptible* watermark in
   the pixels/spectrogram. Detection uses a spectral codebook
   (`spectral_codebook_v4.npz`, ~220 MB) held under a non-commercial
   Research License by the reverse-SynthID project.

## What this means for the studio

| Surface | Studio handling |
| --- | --- |
| SynthID-Text | own **KGW detector** (PRF greenlist + Z-score) for *self-registered* keys; cannot detect Google's keys without them. The honest statement is "detects the *scheme* when you hold the key", not "finds Gemini text". |
| SynthID pixel marks | external **adapter** (`synthid.py` + `setup_synthid.sh`) that runs the reverse-SynthID scorer when a checkout is present; else `available: false`. Detection only — pixel removal is out of scope. |

## Residual risk

A statistical detector without the vendor's key cannot certify "this text is
Google AI". The studio's KGW detector proves the *method* works on
registered keys; it is not a claim of universal Gemini detection.
