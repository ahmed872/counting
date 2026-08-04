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


def enforce_trial(db):
    """Blocks startup once the evaluation period is over. Returns days left."""
    allowed, days_left, message = TrialManager(db).check()
    if allowed:
        return days_left

    box = QMessageBox()
    box.setWindowTitle("النسخة التجريبية")
    box.setIcon(QMessageBox.Icon.Warning)
    box.setText(message)
    box.exec()
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
    db = DBManager('restaurant_erp.db')

    app = QApplication(sys.argv)
    apply_theme(app)

    days_left = enforce_trial(db)

    window = MainWindow(db)
    window.set_trial_banner(days_left)
    window.show()

    show_expiry_notifications(db)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
