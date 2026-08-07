import sys
import os

# Add current directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication, QMessageBox
from database.db_manager import DBManager
from ui.main_window import MainWindow
from ui.theme import apply_theme
from logic.hr import HRLogic
from logic.trial import TrialManager
from logic.paths import database_path, icon_path


def apply_app_icon(app):
    """Sets the icon shown in the title bar, the taskbar and Alt-Tab.

    The packager embeds the .ico into the .exe, which covers Explorer and the
    desktop shortcut, but not the running window - Qt draws that from whatever
    the application sets here."""
    from PyQt6.QtGui import QIcon

    path = icon_path()
    if os.path.exists(path):
        app.setWindowIcon(QIcon(path))

    if sys.platform == "win32":
        # Without an explicit AppUserModelID, Windows groups the window under
        # the launching process and shows its icon on the taskbar instead of
        # ours. Harmless if it fails.
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "RestaurantERP.Desktop.1"
            )
        except Exception:
            pass


def enforce_trial(db):
    """Blocks startup once the evaluation period is over, unless the copy has
    been paid for.

    Returns the days left to show in the sidebar, or None when the copy is
    activated and there is no countdown to show at all.
    """
    from logic.licence import is_activated

    if is_activated(db):
        return None

    allowed, days_left, message = TrialManager(db).check()
    if allowed:
        return days_left

    # Not a message box and an exit. The customer needs somewhere to put the key
    # he was sent, and a program that has already closed is not somewhere.
    from ui.activation_dialog import ActivationDialog

    dialog = ActivationDialog(db, message)
    dialog.exec()
    if dialog.activated:
        return None
    sys.exit(0)


def show_expiry_notifications(db):
    hr_logic = HRLogic(db)
    alerts = hr_logic.get_document_alerts(days=30)
    if not alerts:
        return

    lines = [f"يوجد {len(alerts)} وثيقة/وثائق ستنتهي خلال 30 يوماً القادمة:", ""]
    for alert in alerts[:15]:
        lines.append(f"- {alert['name']}: {alert['doc_type']} بتاريخ {alert['expiry_date']}")
    if len(alerts) > 15:
        lines.append(f"... و {len(alerts) - 15} تنبيهات أخرى (راجع لوحة التحكم)")

    box = QMessageBox()
    box.setWindowTitle("تنبيهات انتهاء وثائق العمال")
    box.setIcon(QMessageBox.Icon.Warning)
    box.setText("\n".join(lines))
    box.exec()


def main():
    # Order matters: the copy is taken before DBManager exists, because
    # constructing one runs the schema migrations, and a backup taken after
    # those have rewritten the file is not a backup of anything.
    from logic.upgrade import backup_before_upgrade, record_version

    path = database_path()
    upgrade_backup = backup_before_upgrade(path)
    db = DBManager(path)
    record_version(db)

    app = QApplication(sys.argv)
    apply_theme(app)
    apply_app_icon(app)

    days_left = enforce_trial(db)

    window = MainWindow(db)
    window.set_trial_banner(days_left)
    window.show()

    if upgrade_backup:
        QMessageBox.information(
            None, "تم تحديث البرنامج",
            "تم تحديث البرنامج إلى نسخة أحدث.\n\n"
            "بياناتك كما هي ولم يتغيّر فيها شيء، وتم حفظ نسخة احتياطية "
            "منها قبل التحديث في:\n" + upgrade_backup,
        )

    show_expiry_notifications(db)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
