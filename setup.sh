#!/usr/bin/env bash
# Structura setup: Python backend + Piper voice + Next.js frontend.
# Works in Git Bash on Windows, and on macOS / Linux.  Usage:  bash setup.sh
set -euo pipefail
cd "$(dirname "$0")"

VOICE="en_US-lessac-medium"

# ---- 1. pick a Python between 3.10 and 3.14 (newest versions may lack wheels for onnxruntime)
pick_python() {
  local cands=()
  if command -v py >/dev/null 2>&1; then
    for v in 3.14 3.13 3.12 3.11 3.10; do cands+=("py -$v"); done
  fi
  cands+=(python3.14 python3.13 python3.12 python3.11 python3.10 python3 python)
  for c in "${cands[@]}"; do
    if $c -c 'import sys; exit(0 if (3,10) <= sys.version_info[:2] <= (3,14) else 1)' >/dev/null 2>&1; then
      echo "$c"; return 0
    fi
  done
  return 1
}
PY=$(pick_python) || { echo "Need Python 3.10 to 3.14 installed." >&2; exit 1; }
echo "==> Using Python: $($PY --version)"

# ---- 2. backend virtualenv + packages
cd backend
[ -d .venv ] || $PY -m venv .venv
if [ -x .venv/Scripts/python.exe ]; then VPY=.venv/Scripts/python.exe; else VPY=.venv/bin/python; fi
echo "==> Installing backend packages"
$VPY -m pip install --quiet --upgrade pip
$VPY -m pip install --quiet -r requirements.txt

# ---- 3. secrets file (never overwritten)
if [ ! -f .env ]; then
  cp .env.example .env
  echo "==> Created backend/.env from .env.example. Put your GEMINI_API_KEY in it."
fi

# ---- 4. Piper voice (local TTS)
mkdir -p voices
if [ ! -f "voices/$VOICE.onnx" ]; then
  echo "==> Downloading Piper voice $VOICE (~60 MB)"
  $VPY -m piper.download_voices "$VOICE" --data-dir voices
else
  echo "==> Piper voice already present"
fi

# ---- 5. video export: headless Chromium (Playwright) + ffmpeg, all local
echo "==> Installing Chromium for video export (Playwright)"
$VPY -m playwright install chromium
cd ..
if command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1; then
  echo "==> ffmpeg found: $(ffmpeg -version | head -1)"
else
  echo "==> ffmpeg NOT found. Video export needs it (lessons still work without it). Install it, then reopen the terminal:"
  echo "      Windows:  winget install Gyan.FFmpeg"
  echo "      macOS:    brew install ffmpeg"
  echo "      Linux:    sudo apt install ffmpeg"
fi

# ---- 6. frontend
echo "==> Installing frontend packages"
(cd frontend && npm install --no-fund --no-audit)

cat <<'EOF'

Setup complete.

  Backend  (terminal 1):  cd backend && source .venv/Scripts/activate   # macOS/Linux: source .venv/bin/activate
                          uvicorn main:app --reload
  Frontend (terminal 2):  cd frontend && npm run dev
  Tests:                  cd backend && python -m pytest -q

Then open the URL that "npm run dev" prints (usually http://localhost:3000).
Video export (the Download video button) needs ffmpeg on PATH and the frontend running.
EOF
