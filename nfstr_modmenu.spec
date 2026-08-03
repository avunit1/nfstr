import os

block_cipher = None
VERSION = os.environ.get("NFSTR_VERSION", "dev")
EXE_NAME = f"nfstr-v{VERSION}"

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('data/signatures.json', 'data'),
        ('data/vehicles.json', 'data'),
        ('assets/logo.png', 'assets'),
    ],
    hiddenimports=[
        'pymem', 'pymem.process', 'pymem.ressources',
        'psutil',
        'tkinter', 'tkinter.messagebox',
        'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets', 'PySide6.QtSvg',
        'ui', 'ui.main_window', 'ui.theme', 'ui.icons', 'ui.toggle_switch',
        'ui.tooltip', 'ui.toast', 'ui.feature_row', 'ui.sidebar',
        'ui.vehicle_view', 'ui.settings_store', 'ui.settings_dialog',
        'ui.developer_panel', 'ui.workers',
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
    name=EXE_NAME,
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
    icon='assets/icon.ico',
    uac_admin=True,
)
