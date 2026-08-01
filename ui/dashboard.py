from datetime import datetime

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
                             QTableWidgetItem, QLabel, QHeaderView, QFrame, QComboBox)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from logic.hr import HRLogic
from logic.accounting import AccountingLogic


class DashboardModule(QWidget):
    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.hr_logic = HRLogic(db_manager)
        self.accounting = AccountingLogic(db_manager)
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
        self.purchases_card = self.create_card("إجمالي المشتريات اليوم", "0.00 ريال", "#8e44ad")
        self.profit_card = self.create_card("صافي الربح اليوم", "0.00 ريال", "#2c7be5")
        self.vat_card = self.create_card("صافي الضريبة المستحقة اليوم", "0.00 ريال", "#e67e22")
        self.emp_card = self.create_card("عدد الموظفين", "0", "#2980b9")

        stats_layout.addWidget(self.sales_card)
        stats_layout.addWidget(self.purchases_card)
        stats_layout.addWidget(self.profit_card)
        stats_layout.addWidget(self.vat_card)
        stats_layout.addWidget(self.emp_card)
        layout.addLayout(stats_layout)

        # Alerts Section
        alerts_header_row = QHBoxLayout()
        alerts_header = QLabel("تنبيهات انتهاء الوثائق (إقامة / جواز / تصريح عمل / كرت عمل):")
        alerts_header.setStyleSheet("font-size: 15px; font-weight: 600; color: #334155;")
        alerts_header_row.addWidget(alerts_header)
        self.threshold_input = QComboBox()
        self.threshold_input.addItem("خلال 7 أيام", 7)
        self.threshold_input.addItem("خلال 15 يوم", 15)
        self.threshold_input.addItem("خلال 30 يوم", 30)
        self.threshold_input.addItem("خلال 60 يوم", 60)
        self.threshold_input.addItem("خلال 90 يوم", 90)
        self.threshold_input.setCurrentIndex(2)
        self.threshold_input.currentIndexChanged.connect(self.refresh_dashboard)
        alerts_header_row.addWidget(self.threshold_input)
        alerts_header_row.addStretch()
        layout.addLayout(alerts_header_row)

        self.alerts_empty = QLabel("لا توجد تنبيهات حالياً")
        self.alerts_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.alerts_empty.setStyleSheet("background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 12px; padding: 24px; color: #64748b;")
        layout.addWidget(self.alerts_empty)

        self.alerts_table = QTableWidget()
        self.alerts_table.setColumnCount(4)
        self.alerts_table.setHorizontalHeaderLabels(["اسم الموظف", "نوع الوثيقة", "تاريخ الانتهاء", "الأيام المتبقية"])
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
        v_label.setStyleSheet("font-size: 22px; font-weight: bold; color: white;")
        lay.addStretch()
        lay.addWidget(t_label)
        lay.addWidget(v_label)
        lay.addStretch()
        frame.value_label = v_label
        return frame

    def refresh_dashboard(self):
        today = datetime.now().strftime("%Y-%m-%d")
        summary = self.accounting.get_financial_summary(today, today)

        self.sales_card.value_label.setText(f"{summary['revenue']:.2f} ريال")
        self.purchases_card.value_label.setText(f"{summary['cogs'] + summary['operating_expenses']:.2f} ريال")
        self.profit_card.value_label.setText(f"{summary['net_profit']:.2f} ريال")
        self.vat_card.value_label.setText(f"{summary['net_vat']:.2f} ريال")

        emp_count = self.db.fetch_one("SELECT COUNT(*) as count FROM employees")['count']
        self.emp_card.value_label.setText(str(emp_count))

        threshold_days = self.threshold_input.currentData() or 30
        alerts = self.hr_logic.get_document_alerts(days=threshold_days)
        self.alerts_table.setVisible(bool(alerts))
        self.alerts_empty.setVisible(not alerts)
        self.alerts_table.setRowCount(len(alerts))
        today_date = datetime.now().date()
        for row, alert in enumerate(alerts):
            days_left = None
            try:
                expiry = datetime.strptime(alert['expiry_date'], "%Y-%m-%d").date()
                days_left = (expiry - today_date).days
            except (TypeError, ValueError):
                pass

            self.alerts_table.setItem(row, 0, QTableWidgetItem(alert['name']))
            self.alerts_table.setItem(row, 1, QTableWidgetItem(alert['doc_type']))
            self.alerts_table.setItem(row, 2, QTableWidgetItem(alert['expiry_date']))
            days_text = str(days_left) if days_left is not None else "-"
            days_item = QTableWidgetItem(days_text)
            self.alerts_table.setItem(row, 3, days_item)

            if days_left is not None:
                if days_left < 0:
                    color = QColor("#fecaca")
                elif days_left <= 7:
                    color = QColor("#fed7aa")
                else:
                    color = QColor("#fef9c3")
                for col in range(4):
                    item = self.alerts_table.item(row, col)
                    if item:
                        item.setBackground(color)

    def get_urgent_alerts(self, days=30):
        return self.hr_logic.get_document_alerts(days=days)

    def refresh_on_show(self):
        self.refresh_dashboard()
