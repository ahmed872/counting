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

# ---------------------------------------------------------------------------
# Trimming.
#
# The app imports exactly four Qt modules - QtCore, QtGui, QtWidgets and
# QtPrintSupport - but PyInstaller collects the whole of Qt's plugin and
# translation trees regardless, because it cannot know which of them Qt will
# decide to load at runtime. Most of that is dead weight in this program.
#
# Everything below is dropped by name rather than by a blanket wildcard, and
# each one is dropped for a stated reason. Over-trimming a Qt build produces
# failures that appear only on the customer's machine - a dialog that will not
# open, an icon that will not draw - so anything whose absence could not be
# proven harmless was left in.

def _drop(entry):
    name = entry[0].replace("\\", "/")
    # Plugin files are qjpeg.dll on Windows and libqjpeg.so on Linux, so match
    # on the stem with the platform's decoration stripped off.
    stem = os.path.basename(name)
    for prefix in ("lib",):
        if stem.startswith(prefix):
            stem = stem[len(prefix):]
    stem = stem.split(".")[0]

    # Qt's own UI translations. Every string this program shows is its own, and
    # QTranslator is never installed, so none of these is ever loaded.
    if "/translations/" in name or name.startswith("PyQt6/Qt6/translations"):
        return True

    # Image formats. The only image the program loads is its own PNG icon, and
    # ICO is kept because that is what the window icon may be read from.
    if "imageformats/" in name and stem in (
        "qjpeg", "qgif", "qtiff", "qwebp", "qicns", "qtga", "qwbmp", "qpdf", "qsvg"
    ):
        return True

    # Whole plugin families this program has no path to: it opens no sockets,
    # runs no QML, plays no media, and talks to no database through Qt (SQLite
    # goes through Python's own sqlite3).
    for family in ("sqldrivers/", "qmltooling/", "multimedia/", "position/",
                   "sensors/", "texttospeech/", "webview/", "networkinformation/",
                   "designer/", "assetimporters/", "renderers/", "geometryloaders/"):
        if family in name:
            return True

    return False


_before = len(a.binaries) + len(a.datas)
a.binaries = TOC([entry for entry in a.binaries if not _drop(entry)])
a.datas = TOC([entry for entry in a.datas if not _drop(entry)])
print(f"[spec] trimmed {_before - len(a.binaries) - len(a.datas)} bundled files")

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
