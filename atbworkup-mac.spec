# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for ATBWorkup -- macOS .app bundle.

MUST be run on an actual Mac -- PyInstaller does not cross-compile, and this
was written/tested on Windows (see scripts/build_mac.sh for the one-command
wrapper someone on a Mac should run instead of invoking this directly).

Build with:
    pyinstaller atbworkup-mac.spec --noconfirm

Output:
    dist/ATBWorkup.app   <- zip this for distribution (see build_mac.sh)

This produces a build for whatever CPU architecture it's built on (Apple
Silicon arm64, or Intel x86_64) -- it does NOT produce a universal2 binary.
If your test machines mix Apple Silicon and Intel Macs, either build once
per architecture or add `universal2` to target_arch below (requires a
universal2 Python interpreter, which python.org installers provide but
Homebrew's typically does not).
"""
import re

from PyInstaller.utils.hooks import collect_submodules

_version_text = open("atbworkup/constants.py").read()
_match = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', _version_text, re.M)
APP_VERSION = _match.group(1) if _match else "0.1.0"

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=[],
    # app_icon.png ships for the in-app window icon (main.py loads it via
    # QIcon at runtime); app_icon.icns is used below only at build time, to
    # brand the .app bundle itself -- it isn't needed as bundled data.
    datas=[("atbworkup/assets/app_icon.png", "atbworkup/assets")],
    hiddenimports=collect_submodules("atbworkup"),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # numpy/scipy are only used by scripts/make_app_icon.py, and lxml only
    # by python-docx (installed once to read a class assignment file) --
    # none of them are used by atbworkup itself. Exclude them so an
    # incidental dev-env install doesn't bloat every student's download.
    excludes=["numpy", "scipy", "lxml", "docx"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ATBWorkup",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ATBWorkup",
)

app = BUNDLE(
    coll,
    name="ATBWorkup.app",
    icon="atbworkup/assets/app_icon.icns",
    bundle_identifier="tax.zbcpa.atbworkup",
    info_plist={
        "CFBundleName": "ATBWorkup",
        "CFBundleDisplayName": "ATBWorkup",
        "CFBundleShortVersionString": APP_VERSION,
        "CFBundleVersion": APP_VERSION,
        "NSHighResolutionCapable": True,
        # Unsigned build: no NSAppTransportSecurity/entitlements needed since
        # this app makes no network calls. Gatekeeper will still show the
        # "unidentified developer" prompt on first launch -- see
        # "How to Install.md" for the one-time click-through.
    },
)
