#!/usr/bin/env bash
# Build SemanticAlphabet.ttf from the 256 SVG sources.
#
# Wraps build_font.py with automatic Python venv management so you don't
# have to touch pip directly. Creates .venv/ on first run and reuses it
# afterwards; any extra args are passed through to build_font.py.
set -euo pipefail

# Always run from this script's directory so relative paths inside
# build_font.py resolve regardless of where you invoke the script from.
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

# Only touch pip if the imports aren't satisfied — keeps repeat runs fast.
if ! "$VENV/bin/python" -c "import fontTools, picosvg" 2>/dev/null; then
    echo "Installing dependencies from $REQS ..."
    "$VENV/bin/pip" install --quiet --upgrade pip
    "$VENV/bin/pip" install --quiet -r "$REQS"
fi

exec "$VENV/bin/python" build_font.py "$@"
