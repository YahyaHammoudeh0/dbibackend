#!/usr/bin/env bash
# Build "DBI Backend.app" (self-contained, libusb bundled) from source.
#
#   ./build_macos.sh
#
# Output: dist/DBI Backend.app
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required to build (it provides libusb). https://brew.sh" >&2
  exit 1
fi
brew list libusb >/dev/null 2>&1 || brew install libusb

# Isolated build venv.
python3 -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet pyusb==1.1.0 pyinstaller

.venv/bin/pyinstaller DBIBackend.spec --noconfirm --clean

echo
echo "Built: dist/DBI Backend.app"
echo "Zip it for distribution:  ditto -c -k --keepParent 'dist/DBI Backend.app' 'DBI-Backend-macOS.zip'"
