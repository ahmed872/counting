"""Protects the customer's books across version upgrades.

The customer gets a newer copy, replaces the old executable with it, and opens
it. His database is not inside the program folder, so it is still there - but a
newer program opening an older database is the moment where an accounting
program can quietly destroy someone's year, and "the migration looked fine when
I wrote it" is not a safety net.

So: the first time a given version runs against an existing database, a copy of
that database is taken before anything touches it. It costs a few megabytes and
a fraction of a second, and it means a bad migration is an inconvenience rather
than a catastrophe. Backups are kept for the last few versions and then the
oldest are dropped, so the folder cannot grow without limit.

Nothing here runs on a brand new database - there is nothing to lose yet.
"""

import os
import shutil
import sqlite3
from datetime import datetime

# Bump this on every release that ships a schema change (new table, new
# column, a migration). backup_before_upgrade() below skips the backup
# entirely once a database is already stamped with the current value - this
# constant sitting still while the schema kept moving is exactly how a build
# could ship a real migration with the safety net silently turned off.
APP_VERSION = "1.2.0"

_VERSION_KEY = "app_version"
_BACKUP_PREFIX = "قبل-التحديث-"
KEEP_BACKUPS = 5


def _backup_dir(db_path):
    folder = os.path.join(os.path.dirname(os.path.abspath(db_path)), "نسخ-احتياطية")
    os.makedirs(folder, exist_ok=True)
    return folder


def _prune(folder):
    backups = sorted(
        (entry for entry in os.listdir(folder) if entry.startswith(_BACKUP_PREFIX)),
        key=lambda name: os.path.getmtime(os.path.join(folder, name)),
    )
    for stale in backups[:-KEEP_BACKUPS]:
        try:
            os.remove(os.path.join(folder, stale))
        except OSError:
            pass


def _read_version(db_path):
    """Read the stored version with raw sqlite, deliberately not through
    DBManager: opening one runs the migrations, and a backup taken after the
    migrations have already rewritten the file protects nothing at all."""
    try:
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key = ?", (_VERSION_KEY,)
            ).fetchone()
            return row[0] if row else None
        finally:
            conn.close()
    except sqlite3.Error:
        return None          # older database with no settings table at all


def _has_data(db_path):
    """A database with nothing in it is a fresh install, not an upgrade."""
    try:
        conn = sqlite3.connect(db_path)
        try:
            for table in ("sales", "purchases", "employees", "journal_entries"):
                try:
                    if conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]:
                        return True
                except sqlite3.Error:
                    continue    # table does not exist in that old schema
        finally:
            conn.close()
    except sqlite3.Error:
        pass
    return False


def backup_before_upgrade(db_path):
    """Takes the copy, and returns where it went, or None if none was needed.

    Takes a *path*, and must be called before a DBManager is constructed for it.
    DBManager runs the schema migrations inside its constructor, so by the time
    one exists the file has already been altered - which is the exact thing this
    is here to be able to undo.

    A failure never raises. A customer locked out because a backup could not be
    written would be a worse outcome than the risk this guards against.
    """
    if not os.path.exists(db_path) or os.path.getsize(db_path) < 4096:
        return None

    if _read_version(db_path) == APP_VERSION:
        return None

    if not _has_data(db_path):
        return None

    previous = _read_version(db_path) or "قديمة"
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    target = os.path.join(
        _backup_dir(db_path), f"{_BACKUP_PREFIX}{previous}-إلى-{APP_VERSION}-{stamp}.db")

    try:
        shutil.copyfile(db_path, target)
        _prune(os.path.dirname(target))
        return target
    except OSError:
        return None


def record_version(db):
    """Stamp the database once the new version has opened it successfully.

    Separate from the copy, and after it: if the upgrade crashes on the way up,
    the version is not yet recorded, so the next attempt still takes a backup
    rather than deciding the job was already done.
    """
    db.set_setting(_VERSION_KEY, APP_VERSION)
