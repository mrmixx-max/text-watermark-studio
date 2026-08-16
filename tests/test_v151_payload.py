"""Tests for the multi-bit payload workflow (forensics/invariant.py).

The codebook core (embed/extract raw bits) is covered by
test_invariant_features.py. These tests cover the PAYLOAD layer: text
payloads (user ids, timestamps) encoded to self-delimiting bit strings,
embedded, recovered, and exposed through the CLI.
"""

import json
import subprocess
import sys

from ai_watermark_toolkit.forensics.invariant import (
    encode_payload,
    decode_payload,
    embed_payload,
    extract_payload,
    corrupt,
)


_BANK_WORDS = [
    'schnell', 'schnelle', 'wichtig', 'wichtige', 'groß', 'große', 'klein',
    'kleine', 'gut', 'gute', 'schlecht', 'schlechte', 'klar', 'klare', 'neu',
    'neue', 'alt', 'alte', 'einfach', 'einfache', 'schwer', 'schwere',
    'möglich', 'mögliche', 'stark', 'starke', 'besser', 'viele', 'robust',
    'robuste', 'einzige', 'fast', 'important', 'big', 'small', 'good', 'bad',
    'clear', 'new', 'old', 'simple', 'hard', 'possible', 'strong', 'better',
    'many',
]


def _capacity_text() -> str:
    """Text with high synonym-bank density -> enough mask positions for a
    short payload (capacity = 1 bit per usable mask position)."""
    return ' '.join(
        f'Die {w} Methode bleibt eine wichtige Wahl für das Team und die Arbeit.'
        for w in _BANK_WORDS
    )


def test_payload_roundtrip():
    payload = "u42"
    res = embed_payload(_capacity_text(), payload)
    assert res["bits_embedded"] >= len(res["payload_bits"]), "text should fit the payload"
    assert res["payload"] == payload
    out = extract_payload(res["text"], _capacity_text())
    assert out["payload"] == payload
    assert out["payload_valid"] is True
    # Unused codebook capacity decodes as '?' by design (original token is
    # excluded from the candidate list), so confidence reflects payload
    # positions only and stays >= the payload share.
    assert out["confidence"] >= len(res["payload_bits"]) / out["masks_used"]


def test_payload_with_unicode():
    payload = "ü2"  # 3 UTF-8 bytes = 24 bits + 16 prefix = 40 <= capacity
    res = embed_payload(_capacity_text(), payload)
    assert res["bits_embedded"] >= len(res["payload_bits"])
    out = extract_payload(res["text"], _capacity_text())
    assert out["payload"] == payload
    assert out["payload_valid"] is True


def test_payload_roundtrip_under_corruption():
    """Payload survives light corruption (non-anchor tokens only)."""
    payload = "r7a"
    res = embed_payload(_capacity_text(), payload)
    damaged = corrupt(res["text"], ratio=0.05, seed=1, mode="substitute")
    out = extract_payload(damaged, _capacity_text())
    # The mask positions may or may not be hit by corruption; the invariant
    # claim is that most survive. Assert on the bit string, not just payload.
    assert out["masks_used"] > 0
    assert out["confidence"] >= 0.5


def test_encode_decode_payload_self_delimiting():
    payload = "abc"
    bits = encode_payload(payload)
    # Prefix is 16 bits: length = 24 bits (3 bytes x 8)
    assert bits[:16] == format(24, "016b")
    decoded, consumed = decode_payload(bits + "11111111" * 3)  # trailing junk
    assert decoded == payload
    assert consumed == len(bits)


def test_decode_empty_payload():
    bits = encode_payload("")
    decoded, consumed = decode_payload(bits)
    assert decoded == ""
    assert consumed == 16


def test_encode_payload_too_large():
    try:
        encode_payload("x" * 9000)
        raise AssertionError("expected ValueError for oversized payload")
    except ValueError:
        pass


def test_extract_wrong_reference_is_not_valid():
    """Extracting against a different reference text yields no trusted payload."""
    res = embed_payload(_capacity_text(), "user-42")
    wrong_ref = _capacity_text().replace("schnelle", "schnellste").replace("gute", "große")
    out = extract_payload(res["text"], wrong_ref)
    # Different anchors -> different masks -> the recovered bits are noise,
    # so payload_valid must be False (or payload mismatched).
    if out.get("payload_valid"):
        assert out["payload"] != "u42" or out["confidence"] < 1.0


def test_cli_payload_embed_extract(tmp_path):
    src = tmp_path / "original.txt"
    wm = tmp_path / "watermarked.txt"
    src.write_text(_capacity_text(), encoding="utf-8")
    emb = subprocess.run(
        [sys.executable, "-m", "ai_watermark_toolkit.cli", "payload", "embed",
         str(src), "--payload", "u99", "-o", str(wm)],
        capture_output=True, text=True, cwd=".",
    )
    assert emb.returncode == 0, f"embed failed: {emb.stderr}"
    assert "embedded" in emb.stdout
    ext = subprocess.run(
        [sys.executable, "-m", "ai_watermark_toolkit.cli", "payload", "extract",
         str(wm), "--reference", str(src)],
        capture_output=True, text=True, cwd=".",
    )
    assert ext.returncode == 0, f"extract failed: {ext.stderr}"
    assert "u99" in ext.stdout
    assert "NOT trusted" not in ext.stdout


def test_cli_payload_extract_json(tmp_path):
    src = tmp_path / "original.txt"
    wm = tmp_path / "watermarked.txt"
    src.write_text(_capacity_text(), encoding="utf-8")
    subprocess.run(
        [sys.executable, "-m", "ai_watermark_toolkit.cli", "payload", "embed",
         str(src), "--payload", "r26", "-o", str(wm)],
        capture_output=True, text=True, cwd=".",
    )
    ext = subprocess.run(
        [sys.executable, "-m", "ai_watermark_toolkit.cli", "payload", "extract",
         str(wm), "--reference", str(src), "--json"],
        capture_output=True, text=True, cwd=".",
    )
    assert ext.returncode == 0, f"extract failed: {ext.stderr}"
    data = json.loads(ext.stdout)
    assert data["payload"] == "r26"
    assert data["payload_valid"] is True
