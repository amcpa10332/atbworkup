# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for BlueprintTB -- macOS .app bundle, UNIVERSAL2 (one binary
that runs on both Apple Silicon and Intel Macs).

MUST be run on an actual Mac -- PyInstaller does not cross-compile. This was
written/tested on Windows and NOT YET VERIFIED on real hardware -- treat a
successful build here as "worth testing," not "known good." If this build
fails or the resulting .app won't launch, fall back to blueprinttb-mac.spec
(scripts/build_mac.sh), which builds a single-architecture app matched to
whichever Mac runs it -- slower to distribute (one build per architecture)
but has no unusual requirements and is the proven path.

Requirements this spec needs that the plain one doesn't:
  - A universal2 Python interpreter. The python.org installer provides this;
    Homebrew's python3 typically does NOT (it's single-arch, matching
    whatever Mac brewed it). Check with:
        python3 -c "import platform; print(platform.machine())"
    A universal2 interpreter reports differently per-arch when run under
    `arch -x86_64` vs `arch -arm64`; a single-arch one will error under the
    architecture it wasn't built for.
  - Universal2 wheels for every compiled dependency -- chiefly PySide6/
    shiboken6. Recent PySide6 releases publish universal2 wheels on PyPI,
    but this is NOT guaranteed for whatever version requirements.txt pins.
    If `pip install` pulls a single-arch wheel instead, this build will
    either fail outright or silently produce a single-arch binary despite
    target_arch="universal2" below -- check with:
        lipo -info dist/BlueprintTB.app/Contents/MacOS/BlueprintTB
    which should print "Architectures in the fat file: ... x86_64 arm64".
    A single-arch result there means the wheel wasn't universal2 -- use
    blueprinttb-mac.spec instead.

Build with:
    pyinstaller blueprinttb-mac-universal2.spec --noconfirm

Output:
    dist/BlueprintTB.app   <- zip this for distribution
"""
import re

from PyInstaller.utils.hooks import collect_submodules

_version_text = open("blueprinttb/constants.py").read()
_match = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', _version_text, re.M)
APP_VERSION = _match.group(1) if _match else "2.0.0"

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=[],
    datas=[("blueprinttb/assets/app_icon.png", "blueprinttb/assets")],
    hiddenimports=collect_submodules("blueprinttb"),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
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
    name="BlueprintTB",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch="universal2",
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
    name="BlueprintTB",
)

app = BUNDLE(
    coll,
    name="BlueprintTB.app",
    icon="blueprinttb/assets/app_icon.icns",
    bundle_identifier="tax.zbcpa.blueprinttb",
    info_plist={
        "CFBundleName": "BlueprintTB",
        "CFBundleDisplayName": "Blueprint Trial Balance",
        "CFBundleShortVersionString": APP_VERSION,
        "CFBundleVersion": APP_VERSION,
        "NSHighResolutionCapable": True,
    },
)
