# nfstr_modmenu.spec
# Build with:  pyinstaller nfstr_modmenu.spec
# (or just run build.bat / build.ps1, which do this for you)
#
# Produces a single portable dist/NFSTR-ModMenu.exe. Static data
# (signatures.json, vehicles.json) is bundled read-only inside the exe;
# everything the tool writes at run time (calibration cache, logs) goes
# into an nfstr_data/ folder created next to wherever the exe is run from
# -- see core/paths.py.
#
# Deliberately NOT --windowed: a console window stays open alongside the
# GUI so any very-early startup error is visible immediately, on top of
# also being written to nfstr_data/logs/session.log and (for startup
# failures before logging is even up) nfstr_data/startup_crash.log.

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('data/signatures.json', 'data'),
        ('data/vehicles.json', 'data'),
    ],
    hiddenimports=[
        'pymem', 'pymem.process', 'pymem.ressources',
        'psutil',
        'tkinter', 'tkinter.ttk', 'tkinter.messagebox', 'tkinter.filedialog',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='NFSTR-ModMenu',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
