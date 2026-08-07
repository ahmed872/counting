# PyInstaller build for the Windows evaluation copy.
#
# One spec, two shapes, chosen with the ONEFILE environment variable:
#
#   ONEFILE=1   ->  dist/نظام إدارة المطعم.exe
#                   A single file. The customer downloads it and double clicks
#                   it - no unzipping, no folder, nothing to explain. This is
#                   what gets sent. The cost is a few seconds on every launch
#                   while it unpacks itself into a temp folder, and a slightly
#                   higher chance of an antivirus false positive.
#
#   (unset)     ->  dist/نظام-إدارة-المطعم/
#                   The same program as a folder. Starts instantly and is
#                   calmer with antivirus, but the customer has to unzip it
#                   first. Kept as the fallback for when the single file is
#                   blocked or feels too slow.
#
# Both are built from the same Analysis, so the two can never drift apart.
#
# Run it with packaging\build_windows.bat, or by hand:
#     pyinstaller packaging\restaurant_erp.spec --noconfirm

import os

project_root = os.path.abspath(os.path.join(SPECPATH, ".."))
onefile = os.environ.get("ONEFILE") == "1"

datas = [
    # Loaded at runtime by DBManager - not importable Python, so PyInstaller
    # cannot find it on its own.
    (os.path.join(project_root, "database", "schema.sql"), "database"),
    # The manual, opened by the button on the settings page.
    (os.path.join(project_root, "docs", "دليل-الاستخدام.pdf"), "docs"),
    # Window / taskbar icon. The .ico below is embedded into the executable and
    # is not read at runtime; this PNG is what Qt draws on the window.
    (os.path.join(project_root, "packaging", "app_icon.png"), "packaging"),
]

icon_file = os.path.join(project_root, "packaging", "app_icon.ico")

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

if onefile:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="نظام إدارة المطعم",
        debug=False,
        strip=False,
        upx=False,
        console=False,      # no black terminal window behind the app
        icon=icon_file,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        exclude_binaries=True,
        name="نظام إدارة المطعم",
        debug=False,
        strip=False,
        upx=False,
        console=False,
        icon=icon_file,
    )

    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name="نظام-إدارة-المطعم",
    )
