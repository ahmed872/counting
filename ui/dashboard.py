from datetime import datetime

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QTableWidget,
                             QTableWidgetItem, QLabel, QHeaderView, QComboBox)
from PyQt6.QtGui import QColor
from logic.hr import HRLogic
from logic.accounting import AccountingLogic
from ui.common_widgets import create_stat_card, page_header, fill_table
from ui.formatting import riyal, money


class DashboardModule(QWidget):
    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.hr_logic = HRLogic(db_manager)
        self.accounting = AccountingLogic(db_manager)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(page_header(
            "لوحة التحكم",
            "ملخص سريع لليوم وللشهر الحالي، وتنبيهات وثائق العمال."
        ))

        # A status strip that says in words whether today has been recorded yet.
        # Previously the whole dashboard showed 0.00 on any day before the sales
        # were entered, which reads as "my data is gone" rather than "not yet".
        self.today_banner = QLabel()
        self.today_banner.setWordWrap(True)
        layout.addWidget(self.today_banner)

        layout.addWidget(self._group_label("اليوم"))
        today_row = QGridLayout()
        today_row.setHorizontalSpacing(12)
        today_row.setVerticalSpacing(12)
        self.sales_card = create_stat_card("مبيعات اليوم", "0.00 ريال", "#27ae60")
        self.purchases_card = create_stat_card("مشتريات ومصروفات اليوم", "0.00 ريال", "#8e44ad")
        self.profit_card = create_stat_card("صافي ربح اليوم", "0.00 ريال", "#2c7be5")
        for index, card in enumerate((self.sales_card, self.purchases_card, self.profit_card)):
            today_row.addWidget(card, 0, index)
        layout.addLayout(today_row)

        layout.addWidget(self._group_label("الشهر الحالي"))
        month_row = QGridLayout()
        month_row.setHorizontalSpacing(12)
        month_row.setVerticalSpacing(12)
        self.month_sales_card = create_stat_card("مبيعات الشهر", "0.00 ريال", "#27ae60")
        self.month_profit_card = create_stat_card("صافي ربح الشهر", "0.00 ريال", "#2c7be5")
        self.month_vat_card = create_stat_card("ضريبة الشهر المستحقة", "0.00 ريال", "#e67e22")
        self.emp_card = create_stat_card("عدد الموظفين", "0", "#2980b9")
        for index, card in enumerate((self.month_sales_card, self.month_profit_card,
                                      self.month_vat_card, self.emp_card)):
            month_row.addWidget(card, 0, index)
        layout.addLayout(month_row)

        alerts_header_row = QHBoxLayout()
        alerts_header = QLabel("وثائق العمال التي تقترب من الانتهاء")
        alerts_header.setStyleSheet("font-size: 15px; font-weight: 700; color: #334155;")
        alerts_header_row.addWidget(alerts_header)
        self.threshold_input = QComboBox()
        self.threshold_input.addItem("خلال 7 أيام", 7)
        self.threshold_input.addItem("خلال 15 يوم", 15)
        self.threshold_input.addItem("خلال 30 يوم", 30)
        self.threshold_input.addItem("خلال 60 يوم", 60)
        self.threshold_input.addItem("خلال 90 يوم", 90)
        self.threshold_input.setCurrentIndex(2)
        self.threshold_input.setMaximumWidth(160)
        self.threshold_input.currentIndexChanged.connect(self.refresh_dashboard)
        alerts_header_row.addWidget(self.threshold_input)
        alerts_header_row.addStretch()
        layout.addLayout(alerts_header_row)

        self.alerts_table = QTableWidget()
        self.alerts_table.setColumnCount(4)
        self.alerts_table.setHorizontalHeaderLabels(["اسم الموظف", "نوع الوثيقة", "تاريخ الانتهاء", "الأيام المتبقية"])
        self.alerts_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.alerts_table.verticalHeader().setVisible(False)
        self.alerts_table.setAlternatingRowColors(True)
        self.alerts_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.alerts_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.alerts_table.setMinimumHeight(180)
        layout.addWidget(self.alerts_table, 1)

        self.refresh_dashboard()

    def _group_label(self, text):
        label = QLabel(text)
        label.setStyleSheet(
            "font-size: 13px; font-weight: 800; color: #64748b; padding-top: 4px;"
        )
        return label

    def refresh_dashboard(self):
        today = datetime.now().strftime("%Y-%m-%d")
        month_start = datetime.now().strftime("%Y-%m-01")

        day = self.accounting.get_period_report(today, today, None)
        month = self.accounting.get_period_report(month_start, today, None)

        self.sales_card.value_label.setText(riyal(day["net_sales"]))
        self.purchases_card.value_label.setText(
            riyal(day["cost_of_sales"] + day["operating_expenses"]))
        self.profit_card.value_label.setText(riyal(day["net_profit"]))

        self.month_sales_card.value_label.setText(riyal(month["net_sales"]))
        self.month_profit_card.value_label.setText(riyal(month["net_profit"]))
        self.month_vat_card.value_label.setText(riyal(month["net_vat"]))

        emp_count = self.db.fetch_one(
            "SELECT COUNT(*) as count FROM employees WHERE is_active = 1")['count']
        self.emp_card.value_label.setText(str(emp_count))

        recorded_today = self.db.fetch_one(
            "SELECT COUNT(*) c FROM sales WHERE date(date) = date(?)", (today,))['c']
        if recorded_today:
            self._set_banner(
                f"مبيعات اليوم ({today}) مسجلة ✓ — إجمالي التحصيل "
                f"{money(day['sales']['grand_total'])} ريال",
                "#14714a", "#e6f5ee", "#a9dcc4")
        else:
            self._set_banner(
                f"لم تُسجَّل مبيعات اليوم ({today}) بعد. افتح صفحة «المبيعات اليومية» وسجّلها.",
                "#9a5a06", "#fdf3e2", "#f0d4a3")

        threshold_days = self.threshold_input.currentData() or 30
        alerts = self.hr_logic.get_document_alerts(days=threshold_days)
        today_date = datetime.now().date()

        if not fill_table(self.alerts_table, len(alerts),
                          "لا توجد وثائق تقترب من الانتهاء خلال هذه المدة"):
            return

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
            if days_left is None:
                days_text = "-"
            elif days_left < 0:
                days_text = f"منتهية منذ {abs(days_left)} يوم"
            else:
                days_text = f"{days_left} يوم"
            self.alerts_table.setItem(row, 3, QTableWidgetItem(days_text))

            if days_left is not None:
                if days_left < 0:
                    colour = QColor("#fecaca")
                elif days_left <= 7:
                    colour = QColor("#fed7aa")
                else:
                    colour = QColor("#fef9c3")
                for col in range(4):
                    item = self.alerts_table.item(row, col)
                    if item:
                        item.setBackground(colour)

    def _set_banner(self, text, fg, bg, border):
        self.today_banner.setText(text)
        self.today_banner.setStyleSheet(
            f"color:{fg}; background:{bg}; border:1px solid {border};"
            "border-radius:10px; padding:11px 14px; font-weight:700;"
        )

    def refresh_on_show(self):
        self.refresh_dashboard()
