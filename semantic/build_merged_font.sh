#!/usr/bin/env bash
# Build SemanticMono-Regular.ttf by merging the 256 pictograms into
# JetBrains Mono Regular.
#
# Wraps build_merged_font.py with the same venv handling as
# build_font.sh — they share the same .venv/ directory.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

VENV=".venv"
REQS="requirements.txt"

if ! command -v python3 >/dev/null 2>&1; then
    echo "error: python3 not found on PATH. Install it first (e.g. 'brew install python')." >&2
    exit 1
fi

if [ ! -d "$VENV" ]; then
    echo "Creating Python virtual environment in $VENV ..."
    python3 -m venv "$VENV"
fi

if ! "$VENV/bin/python" -c "import fontTools, picosvg" 2>/dev/null; then
    echo "Installing dependencies from $REQS ..."
    "$VENV/bin/pip" install --quiet --upgrade pip
    "$VENV/bin/pip" install --quiet -r "$REQS"
fi

exec "$VENV/bin/python" build_merged_font.py "$@"
