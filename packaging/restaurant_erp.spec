# PyInstaller build for the Windows evaluation copy.
#
# Produces a single folder, dist/نظام-إدارة-المطعم/, containing the .exe and
# everything it needs. A one-file .exe was deliberately not used: it unpacks
# itself on every launch, which adds several seconds of apparent hang on the
# cheap machines this is likely to run on, and it makes some antivirus products
# nervous.
#
# Run it with packaging\build_windows.bat, or by hand:
#     pyinstaller packaging\restaurant_erp.spec --noconfirm

import os

project_root = os.path.abspath(os.path.join(SPECPATH, ".."))

datas = [
    # Loaded at runtime by DBManager - not importable Python, so PyInstaller
    # cannot find it on its own.
    (os.path.join(project_root, "database", "schema.sql"), "database"),
    # The manual, opened by the button on the settings page.
    (os.path.join(project_root, "docs", "دليل-الاستخدام.pdf"), "docs"),
]

a = Analysis(
    [os.path.join(project_root, "main.py")],
    pathex=[project_root],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    # Trimmed because they are large and unused; leaving them in roughly
    # doubles the size of what has to be sent over WhatsApp.
    excludes=["tkinter", "matplotlib", "numpy", "PyQt6.QtWebEngineCore"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="نظام إدارة المطعم",
    debug=False,
    strip=False,
    upx=False,
    console=False,          # no black terminal window behind the app
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="نظام-إدارة-المطعم",
)
