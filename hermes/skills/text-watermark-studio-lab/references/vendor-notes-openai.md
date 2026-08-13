# OpenAI provenance surfaces (reference)

Class-level documentation of OpenAI's published provenance disclosures.
Not an implementation; the studio reports claims and separates verifiable
from best-effort.

## Known surfaces

1. **C2PA metadata on generated media.** OpenAI signs DALL-E output with
   C2PA Content Credentials. As with all current C2PA deployments this is
   *metadata* (soft binding) — the manifest is a linked record, not an
   in-pixel cryptographic seal.

2. **Generator metadata in file containers (EXIF/XMP/APP segments).** Images
   and some exports carry `created_by`, model, and prompt hints in metadata
   fields.

3. **Text watermarks.** OpenAI has researched text watermarking (a 2024
   blog post described a watermarking method it was withholding). There is
   **no public shipped detector or key parity** — the studio cannot detect a
   hypothetical OpenAI text watermark without a public scheme+key.

## What this means for the studio

| Surface | Studio handling |
| --- | --- |
| C2PA / EXIF / XMP on images | metadata layer strips the carriers; documents soft-binding limits |
| Text | no keyed detection claim — the KGW detector works on *registered* keys; the honest statement is "detects the scheme when you hold the key" |

## Residual risk

No public OpenAI text detector exists. Any "detects ChatGPT text" claim
would be a heuristic-style signal, not a provable match — and the studio
does not make that claim.
