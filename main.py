import sys
import os

# Add current directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette, QColor
from database.db_manager import DBManager
from ui.main_window import MainWindow
from logic.hr import HRLogic

def force_light_theme(app):
    """On Windows, Qt6 auto-detects the OS dark/light theme and silently applies a dark
    QPalette underneath our light QSS. Anything the stylesheet doesn't explicitly cover
    (like combo-box popups) then renders as unreadable dark-on-dark. Force light mode
    explicitly so the app looks the same regardless of the user's Windows theme."""
    try:
        app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    except AttributeError:
        pass  # older Qt without colour-scheme hints; the palette below still fixes it

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#edf1f5"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#1f2937"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#f7f9fc"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#1f2937"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#1f2937"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#f3f4f6"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#1f2937"))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#dc2626"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#4f78a8"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#94a3b8"))
    app.setPalette(palette)

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
    force_light_theme(app)
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
            color: #1f2937;
            selection-background-color: #d7e7f7;
            selection-color: #1f2937;
            outline: 0;
        }
        QGroupBox {
            font-weight: 700;
            border: 1px solid #d8e0ea;
            border-radius: 12px;
            margin-top: 14px;
            padding-top: 18px;
            background-color: #fbfcfe;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top right;
            right: 12px;
            padding: 0 6px;
            color: #1f3b57;
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
