# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for OmniClone Universal Pro (Source Machine)
# Run from the omniclone\ directory:
#   pyinstaller OmniClone_Source.spec

import os
import sys
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# ── Collect lz4 package data ───────────────────────────────
lz4_datas, lz4_binaries, lz4_hiddenimports = collect_all('lz4')

# ── Main analysis ──────────────────────────────────────────
a = Analysis(
    ['src/main.py'],
    pathex=[os.path.abspath('.')],
    binaries=lz4_binaries,
    datas=[
        # WinPE boot files directory (populate before building)
        ('boot',             'boot'),
        # Resources (icons, etc.)
        ('resources',        'resources'),
        # Include the agent EXE so it can be extracted/used if needed
        # ('OmniClone_Agent.exe', '.'),   # Uncomment after building agent
    ] + lz4_datas,
    hiddenimports=[
        'lz4',
        'lz4.frame',
        'lz4.block',
        'PyQt6',
        'PyQt6.QtWidgets',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtNetwork',
        'ctypes',
        'ctypes.wintypes',
        'json',
        'struct',
        'socket',
        'threading',
        'hashlib',
        'subprocess',
        'logging',
        'time',
        'os',
        'sys',
        # Our modules
        'src.protocol.messages',
        'src.engine.partition_reader',
        'src.engine.cloner',
        'src.engine.boot_repair',
        'src.services.dhcp_server',
        'src.services.tftp_server',
        'src.services.network_manager',
        'src.gui.main_window',
        'src.gui.progress_dialog',
    ] + lz4_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
        'cv2',
        'unittest',
        'test',
        'distutils',
        'email',
        'html',
        'http',
        'xml',
        'xmlrpc',
        'pydoc',
        'doctest',
        'pdb',
        'profile',
        'cProfile',
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
    name='OmniClone_Universal_Pro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # No console window (GUI app)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Require Administrator for partition access
    uac_admin=True,
    uac_uiaccess=False,
    # Icon (place OmniClone.ico in resources\ before building)
    icon='resources\\OmniClone.ico' if os.path.exists('resources\\OmniClone.ico') else None,
    version='version_info.txt' if os.path.exists('version_info.txt') else None,
)
