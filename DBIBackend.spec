# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — builds a self-contained "DBI Backend.app" for macOS.

Bundles libusb inside the app so end users need neither Homebrew nor Python.
Build with:  pyinstaller DBIBackend.spec --noconfirm
"""
import glob
import os

# Resolve the real libusb dylib (follow the Homebrew symlink) and bundle it.
_libusb = None
for pattern in (
    '/opt/homebrew/lib/libusb-1.0.dylib',
    '/usr/local/lib/libusb-1.0.dylib',
    '/opt/homebrew/lib/libusb-1.0*.dylib',
    '/usr/local/lib/libusb-1.0*.dylib',
):
    matches = sorted(glob.glob(pattern))
    if matches:
        _libusb = os.path.realpath(matches[0])
        break
if _libusb is None:
    raise SystemExit('libusb not found — run "brew install libusb" before building.')

binaries = [(_libusb, '.')]

a = Analysis(
    ['dbigui.py'],
    pathex=[],
    binaries=binaries,
    datas=[],
    hiddenimports=['usb.backend.libusb1'],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DBI Backend',
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name='DBI Backend',
)
app = BUNDLE(
    coll,
    name='DBI Backend.app',
    icon=None,
    bundle_identifier='com.dbibackend.gui',
    info_plist={
        'CFBundleName': 'DBI Backend',
        'CFBundleDisplayName': 'DBI Backend',
        'CFBundleShortVersionString': '1.2.0',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '11.0',
    },
)
