"""A daily safety-net backup, independent of the manual "حفظ نسخة احتياطية"
button on the Settings page and the version-upgrade backup in upgrade.py -
so protecting the restaurant's books does not depend on someone remembering
to click anything. Runs once, the first time the app opens on a given
calendar day, using SQLite's own backup API (a consistent snapshot even if
the file is mid-write) rather than a raw file copy.

Shares its folder and pruning approach with upgrade.py's own backups, but
keeps its own prefix and retention count - the two are different safety
nets guarding against different things (a bad migration vs. everyday human
error) and pruning one must never touch the other's files.
"""

import os
import sqlite3
from datetime import datetime

from logic.upgrade import backups_dir

_AUTO_PREFIX = "نسخة-تلقائية-"
KEEP_DAILY_BACKUPS = 14


def _prune(folder):
    backups = sorted(
        (entry for entry in os.listdir(folder) if entry.startswith(_AUTO_PREFIX)),
        key=lambda name: os.path.getmtime(os.path.join(folder, name)),
    )
    for stale in backups[:-KEEP_DAILY_BACKUPS]:
        try:
            os.remove(os.path.join(folder, stale))
        except OSError:
            pass


def daily_auto_backup(db):
    """Takes at most one backup per calendar day. Returns the path taken, or
    None if today's backup already exists or nothing was there yet to back
    up. A failure here must never stop the app from starting - the same
    reasoning as backup_before_upgrade in upgrade.py.

    Takes the already-open DBManager, not a bare path - unlike
    backup_before_upgrade, this has no reason to run before one exists, and
    reusing it (rather than opening a second one just to log the event)
    avoids re-running the schema migrations a second time for nothing."""
    db_path = db.db_path
    if not os.path.exists(db_path):
        return None

    folder = backups_dir(db_path)
    target = os.path.join(folder, f"{_AUTO_PREFIX}{datetime.now().strftime('%Y-%m-%d')}.db")
    if os.path.exists(target):
        return None

    try:
        source = sqlite3.connect(db_path)
        try:
            dest = sqlite3.connect(target)
            try:
                source.backup(dest)
            finally:
                dest.close()
        finally:
            source.close()
        _prune(folder)
        try:
            from logic.audit import AuditLogger
            AuditLogger(db).log("backup_created", after={"kind": "auto_daily"})
        except Exception:
            pass
        return target
    except Exception:
        try:
            if os.path.exists(target):
                os.remove(target)
        except OSError:
            pass
        return None
