#!/bin/bash
# Build a distributable macOS package for ATBWorkup.
#
# Run this ON A MAC, from the project root:
#   bash scripts/build_mac.sh
#
# First time on this Mac, install dependencies:
#   python3 -m venv .venv
#   source .venv/bin/activate
#   pip install -r requirements-dev.txt
#
# Produces:
#   dist/ATBWorkup.app                    the built app bundle
#   dist/ATBWorkup-v<version>-mac.zip     zipped app, ready to upload
#   dist/How to Install.md                copy of the student instructions
#
# Upload the .zip and "How to Install.md" together -- same Teams Files tab
# / Drive folder -- so nobody ends up with one but not the other.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Pull the version straight from constants.py so the zip's filename can
# never drift out of sync with what's actually running inside it.
VERSION=$(grep -oE '^APP_VERSION = "[^"]+"' atbworkup/constants.py | sed -E 's/APP_VERSION = "(.*)"/\1/')
if [ -z "$VERSION" ]; then
  echo "Could not find APP_VERSION in atbworkup/constants.py" >&2
  exit 1
fi
echo "Building ATBWorkup v$VERSION for macOS..."

rm -rf build dist

python3 -m PyInstaller atbworkup-mac.spec --noconfirm

if [ ! -d "dist/ATBWorkup.app" ]; then
  echo "Build did not produce dist/ATBWorkup.app -- see PyInstaller output above." >&2
  exit 1
fi

ZIP_NAME="dist/ATBWorkup-v$VERSION-mac.zip"
# ditto (not zip -r) preserves the .app bundle's resource forks and
# extended attributes correctly -- a plain zip can silently corrupt a mac
# app bundle's metadata.
ditto -c -k --sequesterRsrc --keepParent "dist/ATBWorkup.app" "$ZIP_NAME"
cp "How to Install.md" "dist/How to Install.md"

echo ""
echo "Build complete. Upload these two files to Teams / Drive:"
echo "  $ZIP_NAME"
echo "  dist/How to Install.md"
echo ""
echo "Before uploading: launch dist/ATBWorkup.app yourself first to confirm"
echo "it actually opens on this machine (right-click -> Open, since it's"
echo "unsigned) -- an untested build is not a build you should hand out."
