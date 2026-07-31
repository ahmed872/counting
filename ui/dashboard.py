from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, 
                             QTableWidgetItem, QLabel, QHeaderView, QFrame)
from PyQt6.QtCore import Qt
from logic.hr import HRLogic

class DashboardModule(QWidget):
    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.hr_logic = HRLogic(db_manager)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QLabel("لوحة التحكم - ملخص الأداء والتنبيهات")
        header.setStyleSheet("font-size: 24px; font-weight: bold; color: #1f3b57;")
        layout.addWidget(header)

        # Stats Cards
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(12)
        self.sales_card = self.create_card("إجمالي المبيعات اليوم", "0.00 ريال", "#27ae60")
        self.vat_card = self.create_card("الضريبة المستحقة", "0.00 ريال", "#e67e22")
        self.emp_card = self.create_card("عدد الموظفين", "0", "#2980b9")
        
        stats_layout.addWidget(self.sales_card)
        stats_layout.addWidget(self.vat_card)
        stats_layout.addWidget(self.emp_card)
        layout.addLayout(stats_layout)

        # Alerts Section
        alerts_header = QLabel("تنبيهات انتهاء الوثائق (خلال 30 يوم):")
        alerts_header.setStyleSheet("font-size: 15px; font-weight: 600; color: #334155;")
        layout.addWidget(alerts_header)

        self.alerts_empty = QLabel("لا توجد تنبيهات حالياً")
        self.alerts_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.alerts_empty.setStyleSheet("background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 12px; padding: 24px; color: #64748b;")
        layout.addWidget(self.alerts_empty)

        self.alerts_table = QTableWidget()
        self.alerts_table.setColumnCount(3)
        self.alerts_table.setHorizontalHeaderLabels(["اسم الموظف", "نوع الوثيقة", "تاريخ الانتهاء"])
        self.alerts_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.alerts_table.verticalHeader().setVisible(False)
        self.alerts_table.setAlternatingRowColors(True)
        self.alerts_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.alerts_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.alerts_table.setMinimumHeight(210)
        layout.addWidget(self.alerts_table)

        self.refresh_dashboard()

    def create_card(self, title, value, color):
        frame = QFrame()
        frame.setMinimumHeight(130)
        frame.setStyleSheet(f"background-color: {color}; color: white; border-radius: 16px; padding: 18px;")
        lay = QVBoxLayout(frame)
        lay.setSpacing(8)
        t_label = QLabel(title)
        v_label = QLabel(value)
        t_label.setStyleSheet("font-size: 14px; font-weight: 600; color: rgba(255, 255, 255, 0.95);")
        v_label.setStyleSheet("font-size: 24px; font-weight: bold; color: white;")
        lay.addStretch()
        lay.addWidget(t_label)
        lay.addWidget(v_label)
        lay.addStretch()
        return frame

    def refresh_dashboard(self):
        # Update Stats
        sales_today = self.db.fetch_one("SELECT SUM(total_amount) as total FROM sales WHERE date >= date('now')")['total'] or 0
        self.sales_card.findChildren(QLabel)[1].setText(f"{sales_today:.2f} ريال")
        
        emp_count = self.db.fetch_one("SELECT COUNT(*) as count FROM employees")['count']
        self.emp_card.findChildren(QLabel)[1].setText(str(emp_count))

        # Update Alerts
        alerts = self.hr_logic.get_document_alerts()
        self.alerts_table.setVisible(bool(alerts))
        self.alerts_empty.setVisible(not alerts)
        self.alerts_table.setRowCount(len(alerts))
        for row, alert in enumerate(alerts):
            self.alerts_table.setItem(row, 0, QTableWidgetItem(alert['name']))
            self.alerts_table.setItem(row, 1, QTableWidgetItem(alert['doc_type']))
            self.alerts_table.setItem(row, 2, QTableWidgetItem(alert['expiry_date']))
