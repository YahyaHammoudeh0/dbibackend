#!/usr/bin/env bash
# Launcher for dbibackend on macOS (Apple Silicon).
# Sets the libusb path so pyusb can find the Homebrew backend, then runs the server.
#
# Usage: ./run.sh /path/to/titles_dir [--debug]
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Locate Homebrew's libusb (Apple Silicon: /opt/homebrew, Intel: /usr/local).
BREW_PREFIX="$(brew --prefix 2>/dev/null || echo /opt/homebrew)"
export DYLD_FALLBACK_LIBRARY_PATH="${BREW_PREFIX}/lib:${DYLD_FALLBACK_LIBRARY_PATH:-}"

exec "${DIR}/.venv/bin/python" "${DIR}/dbibackend/dbibackend.py" "$@"
