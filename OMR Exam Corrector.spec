# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['omr_gui.py'],
    pathex=[],
    binaries=[('poppler_bin', 'poppler_bin')],
    datas=[('assets', 'assets')],
    # keyring (added for the email feature) picks its backend at runtime via
    # importlib.metadata entry points, which PyInstaller's static import
    # analysis can't see -- without this, the frozen .exe raises
    # "No recommended backend was available" the first time email settings
    # are opened, even though it works fine when run from source.
    hiddenimports=['keyring.backends.Windows'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='OMR Exam Corrector',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='OMR Exam Corrector',
)
