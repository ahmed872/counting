"""Where files live, once the app is a packaged .exe rather than a folder of
Python files.

Two different questions, two different answers:

- *Read-only things that ship with the app* (schema.sql, the PDF manual) are
  unpacked by PyInstaller into a temporary folder that is deleted when the app
  closes. Their path is sys._MEIPASS, not the folder next to the .exe.

- *The database* must go somewhere writable and permanent. The folder next to
  the .exe is neither if the owner puts the program in Program Files, so the
  database lives under the user's profile instead. It is the one file that
  matters, and the backup button copies it out from wherever it is.

Running from source behaves exactly as before, so development and the tests are
unaffected.
"""

import os
import sys

APP_FOLDER_NAME = "RestaurantERP"
DB_FILE_NAME = "restaurant_erp.db"


def is_frozen():
    return getattr(sys, "frozen", False)


def resource_path(*parts):
    """A file that shipped with the app and is only ever read."""
    if is_frozen():
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def data_dir():
    """A folder the app may write to, that survives closing the program."""
    if not is_frozen():
        return os.getcwd()
    base = (
        os.environ.get("APPDATA")                        # Windows
        or os.environ.get("XDG_DATA_HOME")               # Linux
        or os.path.join(os.path.expanduser("~"), ".local", "share")
    )
    folder = os.path.join(base, APP_FOLDER_NAME)
    os.makedirs(folder, exist_ok=True)
    return folder


def database_path():
    return os.path.join(data_dir(), DB_FILE_NAME)


def manual_path():
    """The manual, at a path that outlives the program.

    Inside a one-file build the bundled copy lives in a temp folder that is
    deleted the moment the app closes - so opening it handed the PDF reader a
    file that vanished from under the reader while it was being read. The
    bundled copy is therefore taken out to the data folder first, and that is
    what gets opened.
    """
    bundled = resource_path("docs", "دليل-الاستخدام.pdf")
    if not is_frozen():
        return bundled

    import shutil

    permanent = os.path.join(data_dir(), "دليل-الاستخدام.pdf")
    try:
        need_copy = (
            not os.path.exists(permanent)
            or os.path.getsize(permanent) != os.path.getsize(bundled)
        )
        if need_copy and os.path.exists(bundled):
            shutil.copyfile(bundled, permanent)
        if os.path.exists(permanent):
            return permanent
    except OSError:
        pass          # fall back to the bundled copy rather than failing to open
    return bundled


def icon_path():
    """The window/taskbar icon. PNG rather than the .ico: the .ico is embedded
    into the .exe by the packager and is never read at runtime, and Qt's ICO
    support is not guaranteed to be present in every build."""
    return resource_path("packaging", "app_icon.png")


def set_window_icon(widget):
    """Sets the icon on this specific top-level window, not just once on the
    QApplication.

    The owner reported the taskbar showing a generic icon while the app was
    running, even though the title bar and shortcut are both correct. On
    Windows, the taskbar button's icon comes from the native window handle
    (WM_SETICON), and a widget that never set its own icon is only supposed
    to fall back to QApplication.windowIcon() - that inheritance is not
    reliable for the taskbar specifically across every Qt/DWM combination.
    Every top-level window (the main window, and the activation screen shown
    before it on an expired trial) now sets its own icon explicitly instead
    of depending on that fallback."""
    from PyQt6.QtGui import QIcon

    path = icon_path()
    if os.path.exists(path):
        widget.setWindowIcon(QIcon(path))
