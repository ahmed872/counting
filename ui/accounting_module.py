from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, 
                             QTableWidgetItem, QPushButton, QLabel, QHeaderView,
                             QComboBox, QDateEdit, QFrame, QGroupBox)
from PyQt6.QtCore import QDate, Qt
from logic.accounting import AccountingLogic

class AccountingModule(QWidget):
    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.accounting = AccountingLogic(db_manager)
        self.init_ui()

    def init_ui(self):
        from PyQt6.QtWidgets import (
            QWidget,
            QVBoxLayout,
            QHBoxLayout,
            QTableWidget,
            QTableWidgetItem,
            QPushButton,
            QLabel,
            QHeaderView,
            QComboBox,
            QDateEdit,
            QFrame,
            QGroupBox,
            QGridLayout,
        )
        from PyQt6.QtCore import QDate, Qt
        from logic.accounting import AccountingLogic


        class AccountingModule(QWidget):
            def __init__(self, db_manager):
                super().__init__()
                self.db = db_manager
                self.accounting = AccountingLogic(db_manager)
                self.init_ui()

            def init_ui(self):
                layout = QVBoxLayout(self)
                layout.setSpacing(14)

                header = QLabel("التقارير المحاسبية والضريبية")
                header.setStyleSheet("font-size: 22px; font-weight: bold; color: #1f3b57; margin-bottom: 8px;")
                layout.addWidget(header)

                subtitle = QLabel("عرض صافي الربح والضريبة وميزان المراجعة مع فترات يومية وأسبوعية وشهرية وسنوية")
                subtitle.setStyleSheet("color:#64748b; margin-bottom:4px;")
                subtitle.setWordWrap(True)
                layout.addWidget(subtitle)

                controls_box = QGroupBox("تحديد الفترة")
                controls_box.setStyleSheet(
                    "QGroupBox { font-weight: 700; border: 1px solid #d8e0ea; border-radius: 12px; margin-top: 10px; padding-top: 16px; }"
                )
                controls = QGridLayout(controls_box)
                controls.setHorizontalSpacing(10)
                controls.setVerticalSpacing(10)

                self.period_input = QComboBox()
                self.period_input.addItems(["يومي", "أسبوعي", "شهري", "سنوي", "مخصص"])
                self.period_input.currentTextChanged.connect(self.on_period_changed)
                self.end_date = QDateEdit(QDate.currentDate())
                self.end_date.setCalendarPopup(True)
                self.start_date = QDateEdit(QDate.currentDate())
                self.start_date.setCalendarPopup(True)
                self.refresh_btn = QPushButton("تحديث التقارير")
                self.refresh_btn.clicked.connect(self.refresh_data)
                for field in (self.period_input, self.start_date, self.end_date):
                    field.setMinimumWidth(150)

                controls.addWidget(QLabel("الفترة:"), 0, 0)
                controls.addWidget(self.period_input, 0, 1)
                controls.addWidget(QLabel("من:"), 0, 2)
                controls.addWidget(self.start_date, 0, 3)
                controls.addWidget(QLabel("إلى:"), 0, 4)
                controls.addWidget(self.end_date, 0, 5)
                controls.addWidget(self.refresh_btn, 0, 6)
                layout.addWidget(controls_box)

                summary_row = QHBoxLayout()
                summary_row.setSpacing(10)
                self.sales_card = self.make_summary_card("المبيعات", "0.00")
                self.purchases_card = self.make_summary_card("المشتريات", "0.00")
                self.profit_card = self.make_summary_card("صافي الربح", "0.00")
                self.vat_card = self.make_summary_card("صافي الضريبة", "0.00")
                summary_row.addWidget(self.sales_card)
                summary_row.addWidget(self.purchases_card)
                summary_row.addWidget(self.profit_card)
                summary_row.addWidget(self.vat_card)
                layout.addLayout(summary_row)

                vat_box = QGroupBox("الضريبة")
                vat_layout = QVBoxLayout(vat_box)
                self.vat_label = QLabel("صافي الضريبة المستحقة: 0.00")
                self.vat_label.setStyleSheet("font-size: 16px; color: #e67e22; font-weight: bold;")
                self.vat_label.setWordWrap(True)
                vat_layout.addWidget(self.vat_label)
                layout.addWidget(vat_box)

                tb_label = QLabel("ميزان المراجعة:")
                tb_label.setStyleSheet("font-size: 15px; font-weight: 600; color: #334155;")
                layout.addWidget(tb_label)
                self.table = QTableWidget()
                self.table.setColumnCount(5)
                self.table.setHorizontalHeaderLabels(["كود الحساب", "اسم الحساب", "النوع", "مدين", "دائن"])
                self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
                self.table.verticalHeader().setVisible(False)
                self.table.setAlternatingRowColors(True)
                self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
                self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
                layout.addWidget(self.table)

                info_row = QHBoxLayout()
                info_row.setSpacing(10)
                self.income_box = QLabel()
                self.balance_box = QLabel()
                self.income_box.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
                self.balance_box.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
                self.income_box.setStyleSheet(
                    "background:#f8fafc; border:1px solid #dbe3ec; border-radius:12px; padding:12px; min-height: 120px;"
                )
                self.balance_box.setStyleSheet(
                    "background:#f8fafc; border:1px solid #dbe3ec; border-radius:12px; padding:12px; min-height: 120px;"
                )
                self.income_box.setWordWrap(True)
                self.balance_box.setWordWrap(True)
                info_row.addWidget(self.income_box)
                info_row.addWidget(self.balance_box)
                layout.addLayout(info_row)

                self.refresh_data()

            def on_period_changed(self, _text=None):
                is_custom = self.period_input.currentText() == "مخصص"
                self.start_date.setEnabled(is_custom)
                self.end_date.setEnabled(is_custom)
                if not is_custom:
                    self.start_date.setDate(QDate.currentDate())
                    self.end_date.setDate(QDate.currentDate())
                self.refresh_data()

            def make_summary_card(self, title, value):
                frame = QFrame()
                frame.setStyleSheet("background:#1f3b57; color:white; border-radius:14px; padding:14px;")
                frame.setMinimumHeight(92)
                frame.setMinimumWidth(180)
                box = QVBoxLayout(frame)
                title_label = QLabel(title)
                title_label.setStyleSheet("color:rgba(255,255,255,0.9); font-weight:600;")
                value_label = QLabel(value)
                value_label.setStyleSheet("font-size:20px; font-weight:700; color:white;")
                box.addWidget(title_label)
                box.addWidget(value_label)
                frame.value_label = value_label
                return frame

            def resolve_period(self):
                period = self.period_input.currentText()
                today = QDate.currentDate()
                if period == "يومي":
                    return today.toString("yyyy-MM-dd"), today.toString("yyyy-MM-dd")
                if period == "أسبوعي":
                    return today.addDays(-6).toString("yyyy-MM-dd"), today.toString("yyyy-MM-dd")
                if period == "شهري":
                    return today.addMonths(-1).addDays(1).toString("yyyy-MM-dd"), today.toString("yyyy-MM-dd")
                if period == "سنوي":
                    return today.addYears(-1).addDays(1).toString("yyyy-MM-dd"), today.toString("yyyy-MM-dd")
                return self.start_date.date().toString("yyyy-MM-dd"), self.end_date.date().toString("yyyy-MM-dd")

            def refresh_data(self):
                start_date, end_date = self.resolve_period()
                summary = self.accounting.get_financial_summary(start_date, end_date)
                net_vat = summary["net_vat"]
                self.sales_card.value_label.setText(f"{summary['revenue']:.2f}")
                self.purchases_card.value_label.setText(f"{summary['cogs'] + summary['operating_expenses']:.2f}")
                self.profit_card.value_label.setText(f"{summary['net_profit']:.2f}")
                self.vat_card.value_label.setText(f"{net_vat:.2f}")
                self.vat_label.setText(f"صافي الضريبة المستحقة للهيئة: {net_vat:.2f} ريال")

                self.income_box.setText(
                    f"<b>قائمة الدخل</b><br>"
                    f"الإيرادات: {summary['revenue']:.2f}<br>"
                    f"تكلفة البضاعة / المشتريات المرتبطة: {summary['cogs']:.2f}<br>"
                    f"المصروفات التشغيلية: {summary['operating_expenses']:.2f}<br>"
                    f"صافي الربح: {summary['net_profit']:.2f}"
                )

                balance = self.accounting.get_balance_sheet()
                self.balance_box.setText(
                    f"<b>المركز المالي</b><br>"
                    f"الأصول: {balance['assets']:.2f}<br>"
                    f"الالتزامات: {balance['liabilities']:.2f}<br>"
                    f"حقوق الملكية: {balance['equity']:.2f}<br>"
                    f"متوازن: {'نعم' if balance['balanced'] else 'لا'}"
                )

                tb_data = self.accounting.get_trial_balance()
                self.table.setRowCount(len(tb_data))
                total_debit = 0
                total_credit = 0
                for row, item in enumerate(tb_data):
                    debit = item['total_debit'] or 0
                    credit = item['total_credit'] or 0
                    total_debit += debit
                    total_credit += credit
                    self.table.setItem(row, 0, QTableWidgetItem(item['code']))
                    self.table.setItem(row, 1, QTableWidgetItem(item['name']))
                    self.table.setItem(row, 2, QTableWidgetItem(item['type']))
                    self.table.setItem(row, 3, QTableWidgetItem(str(debit)))
                    self.table.setItem(row, 4, QTableWidgetItem(str(credit)))

                if abs(total_debit - total_credit) < 0.01:
                    self.table.setStyleSheet("border: 2px solid green;")
                else:
                    self.table.setStyleSheet("border: 2px solid red;")
