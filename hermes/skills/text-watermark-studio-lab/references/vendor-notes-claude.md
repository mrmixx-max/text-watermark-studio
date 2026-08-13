# How Claude marks AI-generated content (reference)

This is class-level documentation of Anthropic's published provenance
surfaces, for use by the forensics workflow. It is NOT an implementation —
the studio reports which surfaces an artifact *claims*, and separates
verifiable from best-effort work.

## Primary source

Anthropic: "How Claude marks AI-generated content"
(https://support.claude.com/en/articles/16266773-how-claude-marks-ai-generated-content)

## What Claude does today

Claude's marking strategy is **disclosed, opt-in and per-surface**, not a
guaranteed covert signal in every output:

1. **Content Credentials (C2PA).** Claude optionally signs generated
   artifacts (images, and increasingly documents) with a C2PA manifest. This
   is metadata carried in the file container (PNG/JPEG JUMBF/APP11 boxes for
   images; DOCX/PDF metadata streams for documents). It is *soft-bound* by
   default — the signer links to a remote manifest rather than embedding a
   hard cryptographic seal into the pixels.

2. **Disclosure headers / metadata.** API responses and exported files may
   carry generator attribution (model name, request id) in metadata fields.

3. **No documented token-sampling watermark.** As of the current public
   documentation, Anthropic does not publish evidence of a KGW-style
   logit-bias or greenlist text watermark shipped by default. This is the
   honest gap: Claude text is *not* reliably detectable by a statistical
   detector, because no public detector+key pair exists.

## What this means for the studio

| Surface | Studio handling |
| --- | --- |
| C2PA manifest on images/documents | metadata layer flags `hard_bound_c2pa_present` / JUMBF markers; removes the metadata *carrier* but documents that soft-binding re-links the remote manifest |
| Generator metadata (EXIF/XMP/docProps) | metadata layer strips creator/generator fields |
| Statistical text mark | NOT detected — no public key; treated as an honest capability gap, not a hidden removal claim |

## Residual risk

Stripping C2PA metadata does NOT clear the remote Content Credentials
record. The studio reports *removal of the carrier*, never "this is now
undetectable." Verify externally with c2patool / contentcredentials.org/verify.
