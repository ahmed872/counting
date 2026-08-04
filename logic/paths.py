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
    return resource_path("docs", "دليل-الاستخدام.pdf")
