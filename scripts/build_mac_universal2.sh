#!/bin/bash
# Build a UNIVERSAL2 macOS package for ATBWorkup -- one .app that runs on
# both Apple Silicon and Intel Macs, so it can be shared across machines
# with different chips instead of each person building their own.
#
# THIS PATH IS UNVERIFIED (written/tested on Windows, never run on real
# Mac hardware). If it fails, or the resulting app won't launch, fall back
# to the proven single-architecture path:
#   bash scripts/build_mac.sh
# which every Mac can run for itself -- slower to distribute but has no
# unusual requirements.
#
# Run this ON A MAC, from the project root:
#   bash scripts/build_mac_universal2.sh
#
# First time on this Mac, install dependencies:
#   python3 -m venv .venv
#   source .venv/bin/activate
#   pip install -r requirements-dev.txt
#
# Produces:
#   dist/ATBWorkup.app                              the built app bundle
#   dist/ATBWorkup-v<version>-mac-universal2.zip     zipped app, ready to upload
#   dist/How to Install.md                           copy of the student instructions

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION=$(grep -oE '^APP_VERSION = "[^"]+"' atbworkup/constants.py | sed -E 's/APP_VERSION = "(.*)"/\1/')
if [ -z "$VERSION" ]; then
  echo "Could not find APP_VERSION in atbworkup/constants.py" >&2
  exit 1
fi
echo "Building ATBWorkup v$VERSION for macOS (universal2)..."

rm -rf build dist

python3 -m PyInstaller atbworkup-mac-universal2.spec --noconfirm

if [ ! -d "dist/ATBWorkup.app" ]; then
  echo "Build did not produce dist/ATBWorkup.app -- see PyInstaller output above." >&2
  echo "Fall back to: bash scripts/build_mac.sh" >&2
  exit 1
fi

BIN="dist/ATBWorkup.app/Contents/MacOS/ATBWorkup"
echo ""
echo "Checking architectures actually in the built binary..."
lipo -info "$BIN" || true
if ! lipo -info "$BIN" 2>/dev/null | grep -q "x86_64" || ! lipo -info "$BIN" 2>/dev/null | grep -q "arm64"; then
  echo ""
  echo "WARNING: the binary above is NOT universal2 -- it's missing x86_64"
  echo "and/or arm64. This usually means pip installed a single-architecture"
  echo "PySide6 wheel instead of a universal2 one. This .app will only work"
  echo "on the chip that matches whatever it actually contains."
  echo ""
  echo "Recommended: stop here and use the proven path instead:"
  echo "  bash scripts/build_mac.sh"
fi

ZIP_NAME="dist/ATBWorkup-v$VERSION-mac-universal2.zip"
ditto -c -k --sequesterRsrc --keepParent "dist/ATBWorkup.app" "$ZIP_NAME"
cp "How to Install.md" "dist/How to Install.md"

echo ""
echo "Build complete. Upload these two files to Teams / Drive:"
echo "  $ZIP_NAME"
echo "  dist/How to Install.md"
echo ""
echo "Before uploading: launch dist/ATBWorkup.app yourself first to confirm"
echo "it actually opens on this machine (right-click -> Open, since it's"
echo "unsigned), AND ideally have someone with the OTHER chip type test it"
echo "too -- that's the entire point of a universal2 build, and it hasn't"
echo "been verified on either architecture yet."
