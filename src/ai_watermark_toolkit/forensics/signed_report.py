"""Signed forensic findings — make a detect/report run an auditable product.

``sign_report()`` turns any findings payload (dict) into a self-signed
document: HMAC-SHA256 by default (pure stdlib), ML-DSA-44 optionally (when
the ``cryptography`` library with the ``mldsa`` module is installed).
``verify_report()`` recomputes the signature and reports ``valid: true/false``
plus a best-effort tamper diagnosis (which payload fields differ from the
signed state, when that is observable).

Security model (honest boundaries, documented not hidden):
- The signature covers the canonical JSON of the payload WITHOUT the
  ``signature`` block itself, so the signature fields are never part of the
  hashed content — re-attaching a different signature block to the same
  payload changes nothing (and is not an attack: the payload is what the
  signature binds).
- Canonical form: ``json.dumps(sort_keys=True, separators=(',', ':'))`` —
  the same payload bytes every time, independent of key order or whitespace.
- HMAC is symmetric: anyone holding the secret can forge. That is the right
  trust model for studio-internal attestation (the secret lives in the
  KeyRegistry / a --secret-file the operator controls).
- ML-DSA-44 is asymmetric and non-deterministic: the private key signs, the
  public key verifies, two signatures of the same payload differ. The public
  key is embedded in the signature block for convenience; ``verify_report``
  also accepts it as an explicit parameter. Note the API order trap:
  ``public_key.verify(signature, data)`` — signature FIRST.
- ``payload_sha256`` / ``field_hashes`` inside the signature block are
  diagnostics only (they are not covered by the signature — an attacker can
  recompute them trivially). They never carry security; they only make the
  tamper report readable.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import mldsa
    import cryptography as _cryptography

    _MLDSA_AVAILABLE = True
    _CRYPTOGRAPHY_VERSION = getattr(_cryptography, "__version__", "?")
except Exception:  # pragma: no cover - optional dependency
    mldsa = None
    serialization = None
    _MLDSA_AVAILABLE = False
    _CRYPTOGRAPHY_VERSION = None

SUPPORTED_ALGORITHMS = ("hmac-sha256", "mldsa-44")
DEFAULT_ALGORITHM = "hmac-sha256"
FORMAT_VERSION = 1


# ---------------------------------------------------------------- feature probe
def mldsa_available() -> bool:
    """True when cryptography with the mldsa module is importable."""
    return _MLDSA_AVAILABLE


def mldsa_status() -> dict:
    """Feature probe for ML-DSA-44 — honest availability + install hint."""
    return {
        "available": _MLDSA_AVAILABLE,
        "algorithm": "mldsa-44",
        "version": _CRYPTOGRAPHY_VERSION,
        "hint": None if _MLDSA_AVAILABLE else "pip install 'cryptography>=50'",
    }


# ---------------------------------------------------------------- canonical form
def canonical_json(payload: dict) -> bytes:
    """Canonical JSON bytes of the payload, signature block excluded.

    ``sort_keys=True`` sorts nested keys too; ``separators=(',', ':')`` gives
    the compact form. The ``signature`` key is popped before serializing so a
    signature never covers itself.
    """
    p = dict(payload)
    p.pop("signature", None)
    return json.dumps(p, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _field_hashes(payload: dict) -> dict:
    """Per-field SHA-256 hashes — diagnostics for the tamper report.

    Not covered by the signature (see module docstring); recomputed on verify
    and diffed against the stored values to name changed/added/removed fields.
    """
    p = dict(payload)
    p.pop("signature", None)
    return {
        str(k): hashlib.sha256(
            json.dumps(v, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        for k, v in p.items()
    }


def _diff_fields(stored: dict, received: dict) -> list[str]:
    """Best-effort field-level tamper list: changed, added, removed."""
    if not isinstance(stored, dict) or not isinstance(received, dict):
        return []
    out = []
    for k in sorted(set(stored) | set(received)):
        if k not in stored:
            out.append(f"{k} (added)")
        elif k not in received:
            out.append(f"{k} (removed)")
        elif stored[k] != received[k]:
            out.append(k)
    return out


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hmac_digest(secret: str, data: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), data, hashlib.sha256).hexdigest()


def _mldsa_import_error() -> RuntimeError:
    return RuntimeError(
        "mldsa-44 requires the cryptography library with the mldsa module — "
        "pip install 'cryptography>=50' (stdlib HMAC stays available as hmac-sha256)"
    )


def _mldsa_sign(private_key, data: bytes) -> bytes:
    """Sign with ML-DSA-44, tolerating both sign(data) and sign(data, context=...)."""
    try:
        return private_key.sign(data)
    except TypeError:  # cryptography with context parameter
        return private_key.sign(data, context=b"")


def _mldsa_verify(public_key, signature: bytes, data: bytes) -> None:
    """Verify with ML-DSA-44 — signature FIRST, then data (API trap)."""
    try:
        public_key.verify(signature, data)
    except TypeError:  # cryptography with context parameter
        public_key.verify(signature, data, context=b"")
    # raises InvalidSignature on mismatch


# ---------------------------------------------------------------- key management
def public_pem_of(private_key) -> str:
    """Derive the PEM SubjectPublicKeyInfo of a private key."""
    return private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")


def _generate_mldsa_key():
    """Generate an ML-DSA-44 private key, tolerating both cryptography APIs.

    cryptography < 50 exposes ``mldsa.MLDSA44.generate_private_key()``;
    cryptography >= 50 renamed the class to ``MLDSA44PrivateKey.generate()``
    (verified against 50.0.0: sign(data, context=None),
    verify(signature, data, context=None) — signature FIRST — and
    ~2420-byte signatures).
    """
    gen = getattr(mldsa, "MLDSA44", None)
    if gen is not None:
        return gen.generate_private_key()
    return mldsa.MLDSA44PrivateKey.generate()


def generate_mldsa_keypair(algorithm: str = "mldsa-44") -> dict:
    """Generate an ML-DSA-44 keypair (PEM). Requires cryptography + mldsa.

    The private key is a PKCS#8 PEM; the public key is a SubjectPublicKeyInfo
    PEM. Key management stays the operator's business — the CLI ``report-keygen``
    writes both files; ``sign_report``/``verify_report`` take the PEMs as
    parameters.
    """
    if not _MLDSA_AVAILABLE:
        raise _mldsa_import_error()
    if algorithm != "mldsa-44":
        raise ValueError("report-keygen supports only mldsa-44")
    private_key = _generate_mldsa_key()
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("utf-8")
    return {
        "algorithm": algorithm,
        "private_key_pem": private_pem,
        "public_key_pem": public_pem_of(private_key),
    }


# ---------------------------------------------------------------- sign / verify
def sign_report(report_payload: dict, secret: str, *,
                key_id: str | None = None,
                algorithm: str = DEFAULT_ALGORITHM,
                private_key_pem: str | None = None) -> dict:
    """Sign a findings payload; returns the payload plus a ``signature`` block.

    - algorithm='hmac-sha256': ``signature.digest`` = hex HMAC-SHA256 over the
      canonical payload (signature block excluded), keyed with ``secret``.
    - algorithm='mldsa-44': ``signature.signature_b64`` = base64 ML-DSA-44
      signature over the canonical payload, made with ``private_key_pem``;
      the public key is embedded as ``signature.public_key_pem``.
    - Both record key_id (default 'default') and signature_date (UTC ISO).
    """
    if not isinstance(report_payload, dict):
        raise ValueError("report_payload must be a dict")
    if algorithm not in SUPPORTED_ALGORITHMS:
        raise ValueError(
            f"unsupported algorithm: {algorithm} (supported: {SUPPORTED_ALGORITHMS})"
        )
    resolved_key_id = key_id or "default"
    canonical = canonical_json(report_payload)
    sig: dict = {
        "algorithm": algorithm,
        "key_id": resolved_key_id,
        "signature_date": _now_iso(),
        "format_version": FORMAT_VERSION,
        "payload_sha256": hashlib.sha256(canonical).hexdigest(),
        "field_hashes": _field_hashes(report_payload),
    }
    if algorithm == "hmac-sha256":
        if not secret:
            raise ValueError("secret is required for hmac-sha256")
        sig["digest"] = _hmac_digest(secret, canonical)
    else:  # mldsa-44
        if not _MLDSA_AVAILABLE:
            raise _mldsa_import_error()
        if not private_key_pem:
            raise ValueError(
                "mldsa-44 requires private_key_pem (generate a keypair with ai-wm report-keygen)"
            )
        private_key = serialization.load_pem_private_key(
            private_key_pem.encode("utf-8"), password=None
        )
        sig["signature_b64"] = base64.b64encode(
            _mldsa_sign(private_key, canonical)
        ).decode("ascii")
        sig["public_key_pem"] = public_pem_of(private_key)
    out = dict(report_payload)
    out["signature"] = sig
    return out


def verify_report(signed: dict, secret: str | None = None, *,
                  public_key_pem: str | None = None) -> dict:
    """Verify a signed document; returns {valid, algorithm, key_id, reason, ...}.

    Reason values:
    - 'ok'                    — signature matches the canonical payload
    - 'payload_tampered'      — digest/signature invalid AND field-level diff
                                shows which payload fields changed
    - 'digest_mismatch'       — digest invalid while the field hashes match the
                                signed state: the secret/key differs, or the
                                attacker re-hashed the fields (best-effort)
    - 'missing_signature' / 'missing_digest' / 'missing_public_key'
                              — malformed signed document
    - 'unsupported_algorithm' / 'mldsa_unavailable' / 'missing_secret'
                              — environment or usage problem
    """
    def _vr(valid: bool, reason: str, algorithm: str | None,
            key_id: str | None, sig_date: str | None, **extra) -> dict:
        base: dict = {
            "valid": valid,
            "algorithm": algorithm,
            "key_id": key_id,
            "signature_date": sig_date,
            "reason": reason,
            "tampered_fields": [],
        }
        base.update(extra)
        return base

    if not isinstance(signed, dict):
        return _vr(False, "malformed", None, None, None)
    sig = signed.get("signature")
    if not isinstance(sig, dict):
        return _vr(False, "missing_signature", None, None, None)
    algorithm = sig.get("algorithm")
    key_id = sig.get("key_id")
    sig_date = sig.get("signature_date")
    if algorithm not in SUPPORTED_ALGORITHMS:
        return _vr(False, "unsupported_algorithm", algorithm, key_id, sig_date)

    canonical = canonical_json(signed)
    tampered = _diff_fields(sig.get("field_hashes"), _field_hashes(signed))

    if algorithm == "hmac-sha256":
        stored_digest = sig.get("digest")
        if not secret:
            return _vr(False, "missing_secret", algorithm, key_id, sig_date,
                       stored_digest=stored_digest)
        if not stored_digest:
            return _vr(False, "missing_digest", algorithm, key_id, sig_date)
        recomputed = _hmac_digest(secret, canonical)
        ok = hmac.compare_digest(
            recomputed.encode("ascii"), stored_digest.encode("ascii")
        )
        extra = {"recomputed_digest": recomputed, "stored_digest": stored_digest}
        if ok:
            return _vr(True, "ok", algorithm, key_id, sig_date, **extra)
        if tampered:
            return _vr(False, "payload_tampered", algorithm, key_id, sig_date,
                       tampered_fields=tampered, **extra)
        return _vr(False, "digest_mismatch", algorithm, key_id, sig_date, **extra)

    # mldsa-44
    if not _MLDSA_AVAILABLE:
        return _vr(False, "mldsa_unavailable", algorithm, key_id, sig_date)
    signature_b64 = sig.get("signature_b64")
    if not signature_b64:
        return _vr(False, "missing_signature", algorithm, key_id, sig_date)
    pub_pem = public_key_pem or sig.get("public_key_pem")
    if not pub_pem:
        return _vr(False, "missing_public_key", algorithm, key_id, sig_date)
    try:
        public_key = serialization.load_pem_public_key(pub_pem.encode("utf-8"))
        _mldsa_verify(public_key, base64.b64decode(signature_b64), canonical)
        ok = True
    except Exception:
        ok = False
    extra = {"public_key_embedded": bool(sig.get("public_key_pem"))}
    if ok:
        return _vr(True, "ok", algorithm, key_id, sig_date, **extra)
    if tampered:
        return _vr(False, "payload_tampered", algorithm, key_id, sig_date,
                   tampered_fields=tampered, **extra)
    return _vr(False, "signature_invalid", algorithm, key_id, sig_date, **extra)
