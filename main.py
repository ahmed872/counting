import sys
import os

# Add current directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtCore import Qt, QTranslator
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication, QMessageBox
from database.db_manager import DBManager
from ui.main_window import MainWindow
from ui.theme import apply_theme
from logic.hr import HRLogic
from logic.trial import TrialManager
from logic.paths import database_path, icon_path


# Every "OK"/"Yes"/"No"/"Cancel" a QMessageBox shows without its own custom
# button text comes from Qt's own QPlatformTheme translation context, not
# from any string this app writes - so it stays in English unless something
# translates it. Bundling Qt's own translation catalogs was deliberately
# skipped (see packaging/restaurant_erp.spec - every string the app shows is
# its own), so this covers just the handful of standard-button labels Qt
# actually asks for, without pulling in a whole translation file.
STANDARD_BUTTON_LABELS = {
    "OK": "موافق",
    "Save": "حفظ",
    "Save All": "حفظ الكل",
    "Open": "فتح",
    "&Yes": "نعم",
    "Yes to &All": "نعم للكل",
    "&No": "لا",
    "N&o to All": "لا للكل",
    "Abort": "إيقاف",
    "Retry": "إعادة المحاولة",
    "Ignore": "تجاهل",
    "Close": "إغلاق",
    "Cancel": "إلغاء",
    "Discard": "تجاهل",
    "Help": "مساعدة",
    "Apply": "تطبيق",
    "Reset": "إعادة تعيين",
    "Restore Defaults": "استعادة الافتراضي",
}


class ArabicStandardButtonTranslator(QTranslator):
    def translate(self, context, source_text, disambiguation=None, n=-1):
        if context == "QPlatformTheme":
            return STANDARD_BUTTON_LABELS.get(source_text, "")
        return ""


def install_arabic_dialog_buttons(app):
    translator = ArabicStandardButtonTranslator()
    app.installTranslator(translator)
    # installTranslator() does not keep the Python object alive on its own -
    # without this, the translator is garbage-collected right after this
    # call returns and every button silently reverts to English.
    app._arabic_button_translator = translator


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
    # Every string this program shows is its own Arabic text - Qt's built-in
    # standard-button labels are the one exception, since they come from Qt's
    # own translation catalog rather than this codebase, and that catalog is
    # never loaded (see packaging/restaurant_erp.spec). Without an explicit
    # label, exec() falls back to Qt's compiled-in English "OK".
    ok_button = box.addButton("موافق", QMessageBox.ButtonRole.AcceptRole)
    box.setDefaultButton(ok_button)
    box.exec()


def setup_logging():
    """P2: a plain, size-capped log file, and a hook that catches whatever
    Python itself does not - an uncaught exception that would otherwise
    just make the window disappear with nothing for the customer to
    describe and nothing for whoever supports the program to go on.

    Deliberately never logs a password, a licence key, or a row of
    business data - only exception types, tracebacks, and short lifecycle
    lines ("started", "logged in as <username>", "closed"). A traceback
    can legitimately contain a value that happened to be in a local
    variable at the point of failure, so this is a best-effort boundary,
    not a guarantee for every possible exception message - but nothing
    here deliberately logs a secret the way the old debug prints this
    session started from sometimes did.
    """
    import logging
    from logging.handlers import RotatingFileHandler
    from logic.paths import log_path

    logger = logging.getLogger("restaurant_erp")
    logger.setLevel(logging.INFO)
    # Idempotent - main() can safely be called more than once (as the test
    # suite does, constructing the app repeatedly) without stacking up a
    # new handler, and therefore a new open file descriptor, on every call.
    if not logger.handlers:
        handler = RotatingFileHandler(
            log_path(), maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
        logger.addHandler(handler)

    def log_uncaught_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
        try:
            QMessageBox.critical(
                None, "حدث خطأ غير متوقع",
                "حدث خطأ غير متوقع وسيُغلق البرنامج.\n\n"
                "بياناتك في قاعدة البيانات لم تتأثر. تفاصيل الخطأ محفوظة في ملف "
                f"سجل يمكن إرساله لمزوّد البرنامج:\n{log_path()}",
            )
        except Exception:
            pass   # the message box itself failing must never hide the original error

    sys.excepthook = log_uncaught_exception
    return logger


def pin_dpi_policy():
    """Makes window and font sizing consistent across different customer
    machines, rather than however each one's Qt build happens to default.

    Windows laptops run at a mix of display scales - 100%, 125%, 150% are all
    common on ordinary hardware, not just high-end screens. Qt has to turn that
    scale into whole logical pixels somehow, and different builds have shipped
    different defaults for how it rounds a factor like 1.25x: some snap it to
    the nearest whole number (so 125% renders as if it were 100%, or jumps
    straight to 200%), others follow it exactly. Nothing in this program set
    that policy, so two customers on two ordinary laptops could see visibly
    different proportions from the identical .exe - which is what was reported.

    Qt::HighDpiScaleFactorRoundingPolicy::PassThrough follows the OS scale
    factor exactly instead of snapping it to a whole number, which is the
    closest a pixel-styled Qt Widgets app gets to "the same size everywhere."
    Must be called before QApplication exists - Qt reads it once, at startup.
    """
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )


def main():
    logger = setup_logging()

    # Order matters: the copy is taken before DBManager exists, because
    # constructing one runs the schema migrations, and a backup taken after
    # those have rewritten the file is not a backup of anything.
    from logic.upgrade import backup_before_upgrade, record_version, APP_VERSION

    logger.info("Application starting (version %s)", APP_VERSION)
    pin_dpi_policy()

    path = database_path()
    upgrade_backup = backup_before_upgrade(path)
    db = DBManager(path)
    record_version(db)

    app = QApplication(sys.argv)
    apply_theme(app)
    apply_app_icon(app)
    install_arabic_dialog_buttons(app)

    days_left = enforce_trial(db)

    from logic.auth import AuthLogic
    from ui.login_dialog import LoginDialog

    AuthLogic(db).ensure_default_admins()
    login = LoginDialog(db)
    if login.exec() != login.DialogCode.Accepted or login.authenticated_user is None:
        sys.exit(0)

    logger.info("Logged in as role=%s", login.authenticated_user.get("role"))

    window = MainWindow(db, current_user=login.authenticated_user)
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

    exit_code = app.exec()
    logger.info("Application closing (exit code %s)", exit_code)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
