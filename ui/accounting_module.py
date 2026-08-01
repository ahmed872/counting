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
    QDoubleSpinBox,
    QFrame,
    QGroupBox,
    QGridLayout,
    QTabWidget,
    QScrollArea,
    QMessageBox,
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

        subtitle = QLabel("صافي الربح والضريبة، ميزان المراجعة، قائمة الدخل، حساب المتاجرة، والمركز المالي")
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

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        layout.addWidget(tabs, 1)

        tabs.addTab(self.build_trial_balance_tab(), "ميزان المراجعة")
        tabs.addTab(self.build_income_tab(), "قائمة الدخل")
        tabs.addTab(self.build_trading_tab(), "حساب المتاجرة")
        tabs.addTab(self.build_balance_sheet_tab(), "المركز المالي")

        self.refresh_data()

    # ---------- Tab builders ----------

    def build_trial_balance_tab(self):
        widget = QWidget()
        v = QVBoxLayout(widget)
        vat_box = QGroupBox("الضريبة")
        vat_layout = QVBoxLayout(vat_box)
        self.vat_label = QLabel("صافي الضريبة المستحقة: 0.00")
        self.vat_label.setStyleSheet("font-size: 16px; color: #e67e22; font-weight: bold;")
        self.vat_label.setWordWrap(True)
        vat_layout.addWidget(self.vat_label)
        v.addWidget(vat_box)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["كود الحساب", "اسم الحساب", "النوع", "مدين", "دائن"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        v.addWidget(self.table)

        self.tb_totals_label = QLabel("إجمالي مدين: 0.00   |   إجمالي دائن: 0.00")
        self.tb_totals_label.setStyleSheet("font-weight: 700; padding: 6px;")
        v.addWidget(self.tb_totals_label)
        return widget

    def build_income_tab(self):
        widget = QWidget()
        v = QVBoxLayout(widget)
        self.income_box = QLabel()
        self.income_box.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        self.income_box.setStyleSheet(
            "background:#f8fafc; border:1px solid #dbe3ec; border-radius:12px; padding:14px;"
        )
        self.income_box.setWordWrap(True)
        v.addWidget(self.income_box)
        v.addStretch()
        return widget

    def build_trading_tab(self):
        widget = QWidget()
        v = QVBoxLayout(widget)

        note = QLabel(
            "حساب المتاجرة = رصيد أول المدة (المخزون) + المشتريات + المصروفات المرتبطة بالمشتريات "
            "- مرتجعات المشتريات = تكلفة البضاعة المتاحة للبيع. وبطرح رصيد آخر المدة (المخزون) "
            "ينتج تكلفة البضاعة المباعة، ومنها يُحسب مجمل الربح = صافي المبيعات - تكلفة البضاعة المباعة."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#64748b;")
        v.addWidget(note)

        inv_box = QGroupBox("أرصدة المخزون (تُدخل يدوياً من الجرد الفعلي)")
        inv_layout = QGridLayout(inv_box)
        self.opening_inventory_input = QDoubleSpinBox()
        self.opening_inventory_input.setMaximum(999999999)
        self.opening_inventory_input.setDecimals(2)
        self.closing_inventory_input = QDoubleSpinBox()
        self.closing_inventory_input.setMaximum(999999999)
        self.closing_inventory_input.setDecimals(2)
        inv_layout.addWidget(QLabel("رصيد أول المدة (المخزون):"), 0, 0)
        inv_layout.addWidget(self.opening_inventory_input, 0, 1)
        inv_layout.addWidget(QLabel("رصيد آخر المدة (المخزون):"), 0, 2)
        inv_layout.addWidget(self.closing_inventory_input, 0, 3)
        calc_btn = QPushButton("احتساب حساب المتاجرة")
        calc_btn.clicked.connect(self.refresh_trading_account)
        inv_layout.addWidget(calc_btn, 0, 4)
        v.addWidget(inv_box)

        self.trading_box = QLabel()
        self.trading_box.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        self.trading_box.setStyleSheet(
            "background:#f8fafc; border:1px solid #dbe3ec; border-radius:12px; padding:14px;"
        )
        self.trading_box.setWordWrap(True)
        v.addWidget(self.trading_box)
        v.addStretch()
        return widget

    def build_balance_sheet_tab(self):
        widget = QWidget()
        v = QVBoxLayout(widget)
        self.balance_box = QLabel()
        self.balance_box.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        self.balance_box.setStyleSheet(
            "background:#f8fafc; border:1px solid #dbe3ec; border-radius:12px; padding:14px;"
        )
        self.balance_box.setWordWrap(True)
        v.addWidget(self.balance_box)

        self.bs_table = QTableWidget()
        self.bs_table.setColumnCount(4)
        self.bs_table.setHorizontalHeaderLabels(["القسم", "الحساب", "مدين", "دائن"])
        self.bs_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.bs_table.verticalHeader().setVisible(False)
        self.bs_table.setAlternatingRowColors(True)
        self.bs_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        v.addWidget(self.bs_table, 1)
        return widget

    # ---------- Behaviour ----------

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
        self.vat_label.setText(f"صافي الضريبة المستحقة للهيئة (مبيعات - مشتريات): {net_vat:.2f} ريال")

        self.income_box.setText(
            f"<b>قائمة الدخل ({start_date} إلى {end_date})</b><br><br>"
            f"الإيرادات (صافي المبيعات): {summary['revenue']:.2f}<br>"
            f"تكلفة البضاعة المباعة: {summary['cogs']:.2f}<br>"
            f"<b>مجمل الربح: {summary['revenue'] - summary['cogs']:.2f}</b><br>"
            f"المصروفات التشغيلية: {summary['operating_expenses']:.2f}<br>"
            f"<b>صافي الربح: {summary['net_profit']:.2f}</b>"
        )

        balance = self.accounting.get_balance_sheet()
        self.balance_box.setText(
            f"<b>قائمة المركز المالي</b><br><br>"
            f"إجمالي الأصول: {balance['assets']:.2f}<br>"
            f"إجمالي الالتزامات: {balance['liabilities']:.2f}<br>"
            f"حقوق الملكية (شامل الأرباح المرحّلة): {balance['equity']:.2f}<br>"
            f"الأصول = الالتزامات + حقوق الملكية: "
            f"{'متوازن ✓' if balance['balanced'] else 'غير متوازن ✗'}"
        )
        self.refresh_balance_sheet_table()

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
            self.table.setItem(row, 3, QTableWidgetItem(f"{debit:.2f}"))
            self.table.setItem(row, 4, QTableWidgetItem(f"{credit:.2f}"))

        self.tb_totals_label.setText(f"إجمالي مدين: {total_debit:.2f}   |   إجمالي دائن: {total_credit:.2f}")
        if abs(total_debit - total_credit) < 0.01:
            self.table.setStyleSheet("border: 2px solid green;")
        else:
            self.table.setStyleSheet("border: 2px solid red;")

        self.refresh_trading_account()

    def refresh_balance_sheet_table(self):
        rows = self.accounting.get_balance_sheet_detail()
        self.bs_table.setRowCount(len(rows))
        for row, item in enumerate(rows):
            self.bs_table.setItem(row, 0, QTableWidgetItem(item['section']))
            self.bs_table.setItem(row, 1, QTableWidgetItem(item['name']))
            self.bs_table.setItem(row, 2, QTableWidgetItem(f"{item['debit']:.2f}"))
            self.bs_table.setItem(row, 3, QTableWidgetItem(f"{item['credit']:.2f}"))

    def refresh_trading_account(self):
        start_date, end_date = self.resolve_period()
        opening = self.opening_inventory_input.value()
        closing = self.closing_inventory_input.value()
        result = self.accounting.get_trading_account(start_date, end_date, opening, closing)
        self.trading_box.setText(
            f"<b>حساب المتاجرة ({start_date} إلى {end_date})</b><br><br>"
            f"رصيد أول المدة (المخزون): {result['opening_inventory']:.2f}<br>"
            f"(+) المشتريات (مواد خام): {result['purchases']:.2f}<br>"
            f"(+) المصروفات المرتبطة بالمشتريات: {result['purchase_related_expenses']:.2f}<br>"
            f"(-) مرتجعات المشتريات: {result['purchase_returns']:.2f}<br>"
            f"<b>= تكلفة البضاعة المتاحة للبيع: {result['cogs_available']:.2f}</b><br>"
            f"(-) رصيد آخر المدة (المخزون): {result['closing_inventory']:.2f}<br>"
            f"<b>= تكلفة البضاعة المباعة: {result['cost_of_goods_sold']:.2f}</b><br><br>"
            f"صافي المبيعات: {result['net_sales']:.2f}<br>"
            f"(-) مرتجعات المبيعات: {result['sales_returns']:.2f}<br>"
            f"<b>= مجمل الربح (حساب المتاجرة): {result['gross_profit']:.2f}</b>"
        )

    def refresh_on_show(self):
        self.refresh_data()
