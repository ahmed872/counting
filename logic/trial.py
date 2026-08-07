"""Time-limited trial.

The licence state is kept in two places - inside the database and in a small
file under the user's profile - and the *earliest* install date wins. That way
deleting the database (or restoring an old backup) does not hand out a fresh
trial, and neither does deleting the marker file.

Honest limitation: this is an offline desktop app, so a determined user can
still defeat it (edit both stores, or roll the clock back before installing).
It is a courtesy limit for an evaluation copy, not copy protection. Rolling the
clock backwards after the fact is detected, because the last run date is
recorded and time is not allowed to move backwards.
"""

import json
import os
from datetime import date, datetime, timedelta

TRIAL_DAYS = 20

_INSTALL_KEY = "trial_install_date"
_LAST_RUN_KEY = "trial_last_run"
_TAMPER_KEY = "trial_tampered"


def arabic_days(count):
    """Arabic agreement for a number of days.

    1 -> يوم واحد, 2 -> يومان, 3-10 -> أيام, 11+ -> يوماً. Writing "20 أيام"
    everywhere is the kind of thing that makes a program feel machine-made to
    the people who have to read it all day.
    """
    count = int(count)
    if count == 1:
        return "يوم واحد"
    if count == 2:
        return "يومان"
    if 3 <= count <= 10:
        return f"{count} أيام"
    return f"{count} يوماً"



def _marker_path():
    base = (
        os.environ.get("APPDATA")                       # Windows
        or os.environ.get("XDG_CONFIG_HOME")            # Linux
        or os.path.join(os.path.expanduser("~"), ".config")
    )
    folder = os.path.join(base, "RestaurantERP")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "licence.json")


def _read_marker():
    try:
        with open(_marker_path(), "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def _write_marker(data):
    try:
        with open(_marker_path(), "w", encoding="utf-8") as handle:
            json.dump(data, handle)
    except OSError:
        pass  # a read-only profile must not stop the app from running


def _parse(value):
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


class TrialManager:
    def __init__(self, db, trial_days=TRIAL_DAYS):
        self.db = db
        self.trial_days = trial_days

    def check(self):
        """Returns (allowed, days_left, message)."""
        today = date.today()
        marker = _read_marker()

        db_install = _parse(self.db.get_setting(_INSTALL_KEY))
        file_install = _parse(marker.get("install"))
        # Earliest known install wins, so clearing one store does not reset it.
        install = min([d for d in (db_install, file_install) if d], default=today)

        db_last = _parse(self.db.get_setting(_LAST_RUN_KEY))
        file_last = _parse(marker.get("last_run"))
        last_run = max([d for d in (db_last, file_last) if d], default=None)

        tampered = (
            self.db.get_setting(_TAMPER_KEY) == "1"
            or marker.get("tampered") is True
        )
        if last_run and today < last_run:
            # The clock moved backwards since the last run.
            tampered = True

        self.db.set_setting(_INSTALL_KEY, install.isoformat())
        self.db.set_setting(_LAST_RUN_KEY, max(today, last_run or today).isoformat())
        if tampered:
            self.db.set_setting(_TAMPER_KEY, "1")
        _write_marker({
            "install": install.isoformat(),
            "last_run": max(today, last_run or today).isoformat(),
            "tampered": tampered,
        })

        if tampered:
            return False, 0, (
                "انتهت صلاحية النسخة التجريبية.\n\n"
                "تم رصد تغيير في تاريخ الجهاز. للحصول على النسخة الكاملة "
                "يرجى التواصل مع مزوّد البرنامج."
            )

        expiry = install + timedelta(days=self.trial_days)
        days_left = (expiry - today).days

        if days_left <= 0:
            return False, 0, (
                f"انتهت مدة النسخة التجريبية ({arabic_days(self.trial_days)}).\n\n"
                "بياناتك محفوظة ولم تُحذف.\n"
                "للحصول على النسخة الكاملة يرجى التواصل مع مزوّد البرنامج."
            )

        return True, days_left, ""
