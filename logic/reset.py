"""Wiping every business record and starting over, without losing the paid
activation the customer already has.

Used when the owner wants to hand the same installed copy to someone else,
or just clear out data entered while learning the program before going
live for real - "reset the books, not the program's licence". A safety
copy of the old data is always taken first: this overwrites the live
database file the same way logic/upgrade.py's restore already does, and
that one mistake (the wrong button on the wrong day) must stay
recoverable, exactly like restoring the wrong backup already is.
"""

import os
import shutil
import tempfile
from datetime import datetime

from logic.upgrade import backups_dir

# Carried over from the old database into the fresh one, so the customer
# never has to re-activate or lose trial days already granted just because
# the books were wiped - only the licence's own identity, none of the
# actual business data it came bundled with.
_CARRY_OVER_SETTINGS = (
    "licence_key",
    "device_code",
    "trial_install_date",
    "trial_last_run",
    "trial_tampered",
    "trial_extra_days",
)


def factory_reset(db):
    """Replaces the live database with a brand-new, empty one: same schema,
    same seeded chart of accounts and default admin accounts, none of the
    business data that had accumulated. Returns the path of the safety copy
    taken beforehand.

    The caller must tell the user to restart the app afterwards - this
    overwrites the file underneath the connections already open against it,
    the same way logic/upgrade.py's restore() does.
    """
    from database.db_manager import DBManager

    db_path = db.db_path
    folder = backups_dir(db_path)
    safety = os.path.join(
        folder, f"قبل-البدء-من-جديد-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
    )
    shutil.copyfile(db_path, safety)

    carried = {}
    for key in _CARRY_OVER_SETTINGS:
        value = db.get_setting(key)
        if value is not None:
            carried[key] = value

    fd, temp_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(temp_path)  # DBManager must create this fresh, not find it already there
    try:
        fresh = DBManager(temp_path)
        for key, value in carried.items():
            fresh.set_setting(key, value)
        from logic.audit import AuditLogger
        AuditLogger(fresh).log("factory_reset", after={"safety_backup": safety})

        shutil.copyfile(temp_path, db_path)
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass

    return safety
