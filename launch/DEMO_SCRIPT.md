# Demo Script — Text Watermark Studio v2.0.0

> Three copy-pasteable use-cases that show what the toolkit can do.
> Each scenario is self-contained and runs locally.

---

## Demo 1: Detect & Remove — "Is this AI-generated?"

**Scenario:** You received a text and want to know if it carries invisible unicode markers or AI phrasing patterns — and if so, clean it.

```bash
# Step 1: Install
pip install text-watermark-studio

# Step 2: Scan the text for invisible characters and AI markers
ai-wm detect suspicious_article.txt

# Output shows:
#   - Zero-width character count and positions
#   - Bidi override markers
#   - AI phrasing pattern density (e.g., "It's important to note...")
#   - KGW statistical score (Z-score)

# Step 3: Clean the unicode layer — strip all invisible characters
ai-wm clean suspicious_article.txt -o cleaned.txt

# Step 4: Dilute AI phrasing markers (3 intensities: light / standard / aggressive)
ai-wm dilute suspicious_article.txt -o diluted.txt --intensity standard

# Step 5: Full pipeline — detect → clean → dilute → rewrite → re-detect
ai-wm pipeline suspicious_article.txt -o final.txt --report report.json

# Step 6: View the forensic report
cat report.json --pretty
```

**One-liner version:**
```bash
ai-wm pipeline article.txt -o clean.txt --report report.json && cat report.json
```

---

## Demo 2: Watermark Strength Measurement — "Prove the delta"

**Scenario:** You need to quantify exactly how much an attack (truncation, reformatting, paraphrasing) degraded a KGW watermark — with a signed receipt.

```bash
# Step 1: Embed a greenlist watermark (keyed)
ai-wm embed original.txt -o watermarked.txt --key "demo-key-2025"

# Step 2: Verify the watermark is detectable (Z > 4)
ai-wm detect watermarked.txt --key "demo-key-2025"

# Step 3: Simulate an attack — truncate the text
head -n 50 watermarked.txt > truncated.txt

# Step 4: Measure the delta — how much did truncation hurt?
ai-wm delta-z watermarked.txt truncated.txt --key "demo-key-2025"

# Output shows:
#   - Z-score before (e.g., 8.2)
#   - Z-score after (e.g., 3.1)
#   - ΔZ = -5.1 (significant degradation)
#   - Statistical confidence

# Step 5: Sign the measurement for auditability
ai-wm delta-z watermarked.txt truncated.txt --key "demo-key-2025" \
  --sign --secret "$DEMO_SECRET" -o delta_receipt.json

# Step 6: Verify the receipt later
ai-wm report-verify delta_receipt.json --secret "$DEMO_SECRET"
```

**One-liner version:**
```bash
ai-wm delta-z before.txt after.txt --key "demo-key-2025" --sign --secret "$SECRET"
```

---

## Demo 3: Quantum-Safe Forensic Report — "Sign & verify a finding"

**Scenario:** A legal team needs a signed forensic finding that proves — in court, if necessary — that a text was watermarked with a specific key. The signature must be quantum-safe (ML-DSA FIPS 204).

```bash
# Step 1: Generate a quantum-safe ML-DSA keypair
ai-wm report-keygen --algorithm mldsa-44 --output-dir ./forensic-keys

# Output: forensic-keys/mldsa_public.pem, forensic-keys/mldsa_private.pem

# Step 2: Generate a forensic finding on the text
ai-wm finding evidence.txt --key "case-2025-044" -o finding.json

# Output (finding.json):
#   - Evidence class (A: confirmed / B: strong / C: moderate / D: weak)
#   - Check priority (0-5)
#   - Z-score, e-value, green-rate
#   - Timestamp, key fingerprint

# Step 3: Sign the finding with ML-DSA (quantum-safe)
ai-wm report-sign finding.json \
  --algorithm mldsa-44 \
  --private-key forensic-keys/mldsa_private.pem \
  -o signed_finding.json

# Step 4: Share signed_finding.json with the counterparty

# Step 5: Counterparty verifies the signature
ai-wm report-verify signed_finding.json \
  --public-key forensic-keys/mldsa_public.pem

# Output: "✅ Signature valid — ML-DSA-44 · finding class A · priority 5"

# Step 6: (Alternative) Sign with HMAC-SHA256 for quick internal use
ai-wm report-sign finding.json --secret "$CASE_SECRET" -o hmac_signed.json
ai-wm report-verify hmac_signed.json --secret "$CASE_SECRET"
```

**One-liner version:**
```bash
ai-wm report-keygen --algorithm mldsa-44 -o ./keys && \
ai-wm finding evidence.txt --key "case-key" -o f.json && \
ai-wm report-sign f.json --algorithm mldsa-44 --private-key keys/mldsa_private.pem -o signed.json && \
ai-wm report-verify signed.json --public-key keys/mldsa_public.pem
```

---

## Bonus: Launch the TUI

```bash
# Terminal UI — 25 actions, menu-driven
ai-wm tui
```

## Bonus: Serve the API

```bash
# FastAPI server with Swagger at /docs
ai-wm serve --host 127.0.0.1 --port 8080
```

---

> **Note:** All demos run 100% locally. Nothing leaves your machine. The quantum-safe ML-DSA path requires `cryptography` ≥ 50 (`pip install cryptography>=50`). The HMAC-SHA256 path is zero-dependency (stdlib only).
