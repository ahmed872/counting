import sys
import os

# Add current directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import Qt
from database.db_manager import DBManager
from ui.main_window import MainWindow
from logic.hr import HRLogic

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
    # Initialize Database
    db = DBManager('restaurant_erp.db')
    
    # Start Application
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    app.setStyleSheet("""
        QWidget {
            font-family: 'Segoe UI', 'Tahoma', sans-serif;
            font-size: 13px;
            color: #1f2937;
        }
        QLineEdit, QComboBox, QDateEdit, QTextEdit, QSpinBox, QDoubleSpinBox {
            background-color: white;
            border: 1px solid #d6dbe3;
            border-radius: 10px;
            padding: 8px 10px;
            min-height: 28px;
        }
        QComboBox::drop-down {
            border: 0px;
            width: 28px;
        }
        QComboBox QAbstractItemView {
            background-color: white;
            selection-background-color: #d7e7f7;
            outline: 0;
        }
        QPushButton {
            background-color: #4f78a8;
            color: white;
            border: none;
            border-radius: 10px;
            padding: 10px 14px;
            font-weight: 600;
        }
        QPushButton:hover {
            background-color: #3f6996;
        }
        QPushButton:pressed {
            background-color: #36577d;
        }
        QTableWidget {
            background-color: white;
            border: 1px solid #dde3ea;
            border-radius: 12px;
            gridline-color: #e5eaf1;
            alternate-background-color: #f7f9fc;
        }
        QTableWidget::item {
            padding: 6px;
        }
        QHeaderView::section {
            background-color: #1f3b57;
            color: white;
            padding: 8px;
            border: 0px;
            font-weight: 600;
        }
        QTableCornerButton::section {
            background-color: #1f3b57;
            border: 0px;
        }
    """)
    
    window = MainWindow(db)
    window.show()

    show_expiry_notifications(db)

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
