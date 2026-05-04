# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for OmniClone Agent (Target Machine / WinPE)
# Run from the omniclone\ directory:
#   pyinstaller OmniClone_Agent.spec

import os
from PyInstaller.utils.hooks import collect_all

block_cipher = None

lz4_datas, lz4_binaries, lz4_hiddenimports = collect_all('lz4')

a = Analysis(
    ['agent/main.py'],
    pathex=[os.path.abspath('.')],
    binaries=lz4_binaries,
    datas=lz4_datas,
    hiddenimports=[
        'lz4',
        'lz4.frame',
        'lz4.block',
        'ctypes',
        'ctypes.wintypes',
        'json',
        'struct',
        'socket',
        'threading',
        'hashlib',
        'subprocess',
        'logging',
        # Our modules
        'src.protocol.messages',
        'src.engine.boot_repair',
        'agent.partition_scanner',
        'agent.partition_writer',
        'agent.lock_manager',
    ] + lz4_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'PyQt6',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
        'unittest',
        'test',
        'email',
        'html',
        'http',
        'xml',
        'pydoc',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='OmniClone_Agent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,           # Console window for WinPE (shows progress)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=True,         # Require Admin (needed for raw disk access)
    uac_uiaccess=False,
    icon=None,
)
