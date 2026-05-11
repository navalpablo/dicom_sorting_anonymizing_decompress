# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# Resolve the .spec's directory so the build is portable across machines.
SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))

# Collect all submodules of pydicom
pydicom_hidden_imports = collect_submodules('pydicom')

a = Analysis(
    ['GUI_dicom_sorting_tool.py'],        # your main GUI
    pathex=[SPEC_DIR],
    binaries=[],
    # Include helper modules as data files
    datas=[
        ('dicom_sorting_tool.py', '.'),
        ('dicom_sorting_tool_uid_filter.py', '.'),
        ('to_explicit_pydicom.py', '.'),
    ],
    hiddenimports=pydicom_hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(
    a.pure, 
    a.zipped_data,
    cipher=block_cipher
)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],                     # runtime hooks go here if you have any
    name='DICOM_Sorting_Tool_v1.6.0',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # or True if you want a console
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None
)
