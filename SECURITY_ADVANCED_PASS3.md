# TWS v108 — Third Pass: Advanced Security Audit Report

**Date:** 2026-08-18  
**Scope:** Timing attacks, PRNG, file permissions, log injection, CORS, demo key restrictions, path traversal, bandit full scan  
**Workspace:** `C:\Users\webma\Downloads\tws-v108\text-watermark-studio-v108-deep-debug\`

---

## Executive Summary

| Check | Status | Severity |
|-------|--------|----------|
| Timing attacks (key comparison) | **VULNERABILITY FOUND** | HIGH |
| Insecure PRNG in security contexts | Clean | — |
| File permissions on written files | Good | — |
| Log injection | Clean | — |
| CORS misconfiguration | Good | — |
| Demo key restrictions | Good | — |
| Path traversal in file operations | Low risk | — |
| Bandit full profile scan | Clean (0 issues) | — |

**One HIGH-severity finding:** API key comparison uses non-constant-time `!=` operator.

---

## 1. Timing Attacks in Key Comparison ⚠️ HIGH

**File:** `src/ai_watermark_toolkit/api/middleware/auth.py`, line 20

**Vulnerable code:**
```python
if x_api_key != settings.api_key:
    raise HTTPException(status_code=401, detail='invalid_api_key')
```

**Issue:** Python's `!=` operator on strings performs a byte-by-byte comparison that short-circuits on the first mismatch. An attacker can measure response time differences to deduce the API key one character at a time (timing side-channel attack).

**Fix:** Use `hmac.compare_digest()` for constant-time comparison:
```python
import hmac
# ...
if not hmac.compare_digest(x_api_key or '', settings.api_key):
    raise HTTPException(status_code=401, detail='invalid_api_key')
```

**Note:** The `signed_report.py` module already uses `hmac.compare_digest()` correctly (line 361-362) for HMAC verification — the auth middleware should follow the same pattern.

---

## 2. Insecure PRNG in Security Contexts ✅ Clean

**Files checked:**
- `src/ai_watermark_toolkit/generation/kgw_sampler.py` (line 156): `random.Random(seed)` — used for deterministic synthetic text generation, marked `# nosec B311`. **Not security-relevant.**
- `src/ai_watermark_toolkit/forensics/delta_z.py` (line 41): `import random` — imported but no `random.` calls found.
- `src/ai_watermark_toolkit/forensics/invariant.py` (line 410): `import random` — used for invariant testing, not security.
- `src/ai_watermark_toolkit/forensics/kgw.py` (line 32): `import random` — imported but no `random.` calls found.

**No security-relevant use of insecure PRNG found.** Key generation uses `cryptography.hazmat.primitives.asymmetric.mldsa` (FIPS 204) which uses OS-level CSPRNG.

---

## 3. File Permissions on Written Files ✅ Good

**File:** `src/ai_watermark_toolkit/cli.py`, lines 625-626

```python
os.chmod(priv, 0o600)  # Private key: owner read/write only
os.chmod(pub, 0o644)   # Public key: world-readable
```

**Assessment:** Proper permissions applied to generated ML-DSA key files. Private key is restricted to owner (0o600), public key is appropriately world-readable (0o644).

**Key registry writes** (`key_registry.py`, lines 167-184) use atomic writes via `tempfile.mkstemp()` + `os.replace()`, preventing torn writes. No explicit chmod on registry file, but it contains only key metadata (secrets are masked via SHA-256).

---

## 4. Log Injection ✅ Clean

**File:** `src/ai_watermark_toolkit/core/logging.py`

The logging setup uses a `JsonFormatter` that serializes log records as JSON. No user-controlled data is directly interpolated into log messages without sanitization. No `logger.*` calls with user input found in the source tree.

**Assessment:** No log injection vectors identified.

---

## 5. CORS Configuration ✅ Good

**File:** `src/ai_watermark_toolkit/api/fastapi_app.py`, lines 71-87

```python
# P0-1: CORS '*' ist nur im Dev-Modus akzeptabel
if settings.cors_origins and settings.cors_origins != '*':
    _origins = [o.strip() for o in settings.cors_origins.split(',')]
elif settings.app_env == 'development':
    _origins = ['*']
else:
    _origins = []
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False,
    allow_methods=['*'],
    allow_headers=['*'],
)
```

**Assessment:** 
- Wildcard CORS (`*`) only allowed in development mode
- Non-dev deployments default to empty origin list (no CORS)
- `allow_credentials=False` properly set (prevents credentialed wildcard CORS)
- Operators can configure explicit origins via `AI_WM_CORS_ORIGINS` env var

**Note:** `allow_methods=['*']` and `allow_headers=['*']` are permissive but acceptable since the API is key-gated and CORS origin is the primary control.

---

## 6. Demo Key Restrictions ✅ Good

**File:** `src/ai_watermark_toolkit/forensics/key_registry.py`, lines 17-27

Demo keys are clearly marked with `"is_demo": True`:
```python
DEMO_KEYS = [
    {"key_id": "demo-green-1", "family": "greenlist_bias", ..., "is_demo": True},
    {"key_id": "demo-semantic-1", "family": "semantic_pattern", ..., "is_demo": True},
    {"key_id": "demo-kgw-1", "family": "kgw", ..., "secret": "demo-kgw-secret-0001", "is_demo": True},
]
```

**File:** `src/ai_watermark_toolkit/forensics/ensemble.py`, line 64

```python
if exclude_demo and key.get('is_demo'):
    excluded_demo += 1
    continue
```

**Assessment:**
- Demo keys are clearly identified and can be excluded from ensemble detection
- The demo KGW secret is intentionally public (documented as "public demo secret")
- Demo keys function for detection (demo purposes) but can be programmatically excluded
- The `is_demo` flag is propagated through detection results for transparency

---

## 7. Path Traversal in File Operations ✅ Low Risk

**API Routes:**
- `fastapi_app.py` line 140: `FileResponse(WEB_ROOT / 'index.html')` — fixed path, no user input
- `metadata.py` lines 85-87: `tempfile.NamedTemporaryFile(suffix=".png")` — safe, no user-controlled filename
- `documents.py`: Pure in-memory processing, no filesystem writes

**CLI:**
- `cli.py` uses `Path(args.output)` for writes — user-controlled but CLI is a local tool running with user's own permissions

**Assessment:** No path traversal vulnerabilities in API endpoints. CLI paths are user-controlled but this is expected for a command-line tool.

---

## 8. Bandit Full Profile Scan ✅ Clean

**Command:** `bandit -r src/ -c pyproject.toml`

**Results:**
```
Test results:
    No issues identified.

Code scanned:
    Total lines of code: 10,016
    Total lines skipped (#nosec): 0
    Total potential issues skipped via #nosec: 22

Run metrics:
    Total issues (by severity):
        Undefined: 0
        Low: 0
        Medium: 0
        High: 0
```

**Note:** The 22 `#nosec` suppressions are intentional and documented (e.g., `B105` for demo key constants, `B311` for seeded RNG in non-crypto context).

---

## Recommendations

1. **CRITICAL — Fix timing attack in auth.py:** Replace `!=` with `hmac.compare_digest()` for API key comparison. This is the only HIGH-severity finding.

2. **Consider adding bandit config to pyproject.toml:** A `[tool.bandit]` section would make the scan profile explicit and reproducible.

3. **Consider rate limiting on auth failures:** The auth middleware could benefit from exponential backoff or account lockout after repeated failures to slow down brute-force attempts.

---

## Files Examined

- `src/ai_watermark_toolkit/api/middleware/auth.py` — **VULNERABLE** (timing attack)
- `src/ai_watermark_toolkit/api/fastapi_app.py` — CORS configuration (good)
- `src/ai_watermark_toolkit/core/config.py` — Settings (good)
- `src/ai_watermark_toolkit/core/logging.py` — Logging setup (clean)
- `src/ai_watermark_toolkit/forensics/signed_report.py` — HMAC verification (uses `hmac.compare_digest` correctly)
- `src/ai_watermark_toolkit/forensics/key_registry.py` — Demo keys, atomic writes (good)
- `src/ai_watermark_toolkit/forensics/ensemble.py` — Demo key exclusion (good)
- `src/ai_watermark_toolkit/generation/kgw_sampler.py` — PRNG usage (non-crypto, acceptable)
- `src/ai_watermark_toolkit/api/routes/metadata.py` — File upload handling (safe)
- `src/ai_watermark_toolkit/api/routes/documents.py` — Document processing (in-memory, safe)
- `src/ai_watermark_toolkit/cli.py` — File permissions, path handling (good)
- `src/ai_watermark_toolkit/documents/service.py` — In-memory processing (safe)
