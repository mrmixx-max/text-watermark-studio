#!/usr/bin/env bash
set -euo pipefail

# Bootstrap an external reverse-SynthID checkout for the optional pixel scorer.
#
# The upstream project (https://github.com/aloshdenny/reverse-SynthID) is
# licensed under a non-commercial Research License and is NOT bundled in this
# repository. This script clones it locally and installs only the dependencies
# needed by the scorer wrapper (metadata/score_synthid_cli.py).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_DIR="${REVERSE_SYNTHID_DIR:-$HOME/reverse-SynthID}"
DIR=""
REF="main"
PYTHON="${PYTHON:-python3}"
FULL=0
VERIFY=0

usage() {
  cat <<'EOF'
Usage: setup_synthid.sh [--dir PATH] [--ref REF] [--full] [--verify] [--python PYTHON]

Clones (if needed) aloshdenny/reverse-SynthID, creates a venv, and installs
the Python dependencies required by the scorer wrapper.

Options:
  --dir PATH     checkout directory (default: $REVERSE_SYNTHID_DIR or ~/reverse-SynthID)
  --ref REF      git ref to clone (default: main)
  --full         install upstream requirements.txt (adds torch/diffusers)
  --verify       run a real score on a generated test image after setup,
                 so "it works" is proven rather than assumed
  --python PY    Python interpreter used to create the venv (default: python3)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir)   DIR="${2:?--dir requires a value}"; shift 2 ;;
    --ref)   REF="${2:?--ref requires a value}"; shift 2 ;;
    --full)  FULL=1; shift ;;
    --verify) VERIFY=1; shift ;;
    --python) PYTHON="${2:?--python requires a value}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

DIR="${DIR:-$DEFAULT_DIR}"
mkdir -p "$(dirname "$DIR")"
if command -v realpath >/dev/null 2>&1; then
  DIR="$(realpath -m "$DIR")"
else
  DIR="$(cd "$(dirname "$DIR")" && pwd)/$(basename "$DIR")"
fi

if [[ ! -d "$DIR/.git" ]]; then
  echo "Cloning reverse-SynthID into $DIR"
  git clone --depth 1 --filter=blob:none --sparse --branch "$REF" \
    https://github.com/aloshdenny/reverse-SynthID.git "$DIR"
  git -C "$DIR" sparse-checkout set --no-cone \
    '/src/' \
    '/artifacts/spectral_codebook_v4.npz' \
    '/requirements.txt' \
    '/LICENSE' \
    '/README.md'
else
  echo "Using existing checkout: $DIR"
fi

if [[ ! -x "$DIR/.venv/bin/python" && ! -x "$DIR/.venv/Scripts/python" ]]; then
  echo "Creating venv at $DIR/.venv"
  "$PYTHON" -m venv "$DIR/.venv"
fi

VENV_PY="$DIR/.venv/bin/python"
[[ -x "$VENV_PY" ]] || VENV_PY="$DIR/.venv/Scripts/python"

echo "Installing Python dependencies"
"$VENV_PY" -m pip install --upgrade pip
if [[ "$FULL" -eq 1 ]]; then
  echo "Installing full upstream requirements.txt (includes torch/diffusers)"
  "$VENV_PY" -m pip install -r "$DIR/requirements.txt"
else
  echo "Installing scorer-only dependencies"
  "$VENV_PY" -m pip install -r "$SCRIPT_DIR/requirements-synthid-scorer.txt"
fi

codebook="$DIR/artifacts/spectral_codebook_v4.npz"
if [[ ! -f "$codebook" ]]; then
  echo "warning: codebook not found at $codebook" >&2
  echo "run: git -C '$DIR' sparse-checkout add '/artifacts/spectral_codebook_v4.npz'" >&2
fi

if [[ "$VERIFY" -eq 1 ]]; then
  echo ""
  echo "=== Verifying the scorer with a real score run ==="
  if [[ ! -f "$codebook" ]]; then
    echo "FAIL: cannot verify — codebook missing at $codebook" >&2
    exit 1
  fi
  # Generate a small deterministic test image (stdlib, no Pillow needed).
  TEST_IMG="$(mktemp --suffix=.png)"
  "$VENV_PY" - "$TEST_IMG" <<'PYEOF'
import sys, struct, zlib
out = sys.argv[1]
def chunk(t, d):
    return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
w = h = 64
raw = b"\x00" + b"".join(b"\x00" + bytes([64, 128, 192] * (w // 3)) for _ in range(h))
ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
       + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
open(out, "wb").write(png)
PYEOF
  echo "Test image: $TEST_IMG"
  # Run the scorer wrapper through the checkout venv.
  SCORE_OUT="$("$VENV_PY" "$SCRIPT_DIR/../src/ai_watermark_toolkit/metadata/score_synthid_cli.py" "$TEST_IMG" 2>&1)"
  SCORE_RC=$?
  rm -f "$TEST_IMG"
  echo "$SCORE_OUT"
  if [[ $SCORE_RC -ne 0 ]] || echo "$SCORE_OUT" | grep -q '"error"'; then
    echo "FAIL: scorer did not produce a clean score (exit $SCORE_RC)." >&2
    echo "Check that the reverse-SynthID src/ package exposes a scoring entrypoint." >&2
    exit 1
  fi
  echo "VERIFY OK: scorer ran and returned a verdict."
fi

cat <<EOF

Done. Score an image with:

  export REVERSE_SYNTHID_DIR="$DIR"
  ai-wm image-score IMAGE.png --synthid-dir "$DIR"
  # or via the API: POST /api/metadata/synthid-score
EOF
