# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for ATBWorkup — Windows onedir build.

Build with:
    pyinstaller atbworkup.spec --noconfirm

Output:
    dist/ATBWorkup/   <- the whole folder is the app; zip it for distribution
                         (onedir, not onefile: no per-launch unpack-to-temp
                         delay, and fewer antivirus/SmartScreen false
                         positives than a single self-extracting exe).

scripts/build_windows.ps1 wraps this step and produces the final zip.
"""
from PyInstaller.utils.hooks import collect_submodules

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    # app_icon.png ships for the in-app window/taskbar icon (main.py loads it
    # at runtime via QIcon); app_icon.ico is used below only at build time,
    # to brand the .exe itself -- it isn't needed as bundled data.
    datas=[('atbworkup/assets/app_icon.png', 'atbworkup/assets')],
    hiddenimports=collect_submodules('atbworkup'),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # numpy/scipy are only used by scripts/make_app_icon.py, and lxml only
    # by python-docx (installed once to read a class assignment file) --
    # none of them are used by atbworkup itself. Exclude them so an
    # incidental dev-env install doesn't bloat every student's download.
    excludes=['numpy', 'scipy', 'lxml', 'docx'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ATBWorkup',
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
    icon='atbworkup/assets/app_icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='ATBWorkup',
)
