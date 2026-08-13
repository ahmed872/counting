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
    QGroupBox,
    QGridLayout,
    QTabWidget,
    QMessageBox,
)
from PyQt6.QtCore import QDate, Qt
from logic.accounting import AccountingLogic
from ui.common_widgets import create_stat_card
from ui.labels import ACCOUNT_TYPE_LABELS, label_for
from ui.formatting import money_item, money
from ui.common_widgets import page_header, hide_when_short, fill_table, fit_table_height


class AccountingModule(QWidget):
    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.accounting = AccountingLogic(db_manager)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        layout.addWidget(page_header(
            "المحاسبة",
            "ميزان المراجعة، قائمة الدخل، حساب المتاجرة، وقائمة المركز المالي."))

        controls_box = QGroupBox("تحديد الفترة")
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

        # Two rows, not one crammed with all three field-pairs plus a
        # button - a single unbroken row of that many minimum-150px fields
        # had nowhere to wrap to and forced the whole page wider than the
        # window at a modest size (reported live via screenshot, and
        # confirmed by measuring a real 57px overflow at the app's own
        # documented minimum window size, 1040x640).
        controls.addWidget(QLabel("الفترة:"), 0, 0)
        controls.addWidget(self.period_input, 0, 1)
        controls.addWidget(QLabel("من:"), 0, 2)
        controls.addWidget(self.start_date, 0, 3)
        controls.addWidget(QLabel("إلى:"), 1, 0)
        controls.addWidget(self.end_date, 1, 1)
        controls.addWidget(self.refresh_btn, 1, 2, 1, 2)
        layout.addWidget(controls_box)

        self.summary_container = QWidget()
        summary_row = QHBoxLayout(self.summary_container)
        summary_row.setContentsMargins(0, 0, 0, 0)
        summary_row.setSpacing(10)
        self.sales_card = create_stat_card("المبيعات", "0.00", "#27ae60")
        self.purchases_card = create_stat_card("المشتريات", "0.00", "#8e44ad")
        self.profit_card = create_stat_card("صافي الربح", "0.00", "#2c7be5")
        self.vat_card = create_stat_card("صافي الضريبة", "0.00", "#e67e22")
        summary_row.addWidget(self.sales_card)
        summary_row.addWidget(self.purchases_card)
        summary_row.addWidget(self.profit_card)
        summary_row.addWidget(self.vat_card)
        layout.addWidget(self.summary_container)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        layout.addWidget(tabs, 1)
        self.tabs = tabs

        tabs.addTab(self.build_trial_balance_tab(), "ميزان المراجعة")
        tabs.addTab(self.build_income_tab(), "قائمة الدخل")
        tabs.addTab(self.build_trading_tab(), "حساب المتاجرة")
        tabs.addTab(self.build_balance_sheet_tab(), "المركز المالي")
        tabs.addTab(self.build_ledger_tab(), "كشف حساب")

        # On a short window the four summary cards left the trial balance table
        # 78 pixels - one row. The numbers on the cards are all repeated inside
        # the tabs, so they are the right thing to drop when space is tight.
        hide_when_short(self, [self.summary_container])

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
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        v.addWidget(self.table)

        self.tb_totals_label = QLabel("إجمالي مدين: 0.00   |   إجمالي دائن: 0.00")
        self.tb_totals_label.setStyleSheet("font-weight: 700; padding: 6px;")
        v.addWidget(self.tb_totals_label)
        v.addStretch()
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
        # No scroll area of its own - the whole accounting page already
        # scrolls as a single unit (see add_page in main_window.py). Giving
        # this box its own nested one on top of that produced two separate
        # scrollbars for the same content, one inside the other.
        v.addWidget(self.income_box)
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
        # Two rows, not one - both label+field pairs plus the button used
        # to sit on a single unbroken row with nowhere to wrap, which made
        # this the single widest element on the whole page (measured wider
        # than the page's own container at the app's documented minimum
        # window size) and forced a horizontal scrollbar the rest of the
        # page never needed.
        inv_layout.addWidget(QLabel("رصيد أول المدة (المخزون):"), 0, 0)
        inv_layout.addWidget(self.opening_inventory_input, 0, 1)
        inv_layout.addWidget(QLabel("رصيد آخر المدة (المخزون):"), 1, 0)
        inv_layout.addWidget(self.closing_inventory_input, 1, 1)
        calc_btn = QPushButton("احتساب حساب المتاجرة")
        calc_btn.clicked.connect(self.refresh_trading_account)
        inv_layout.addWidget(calc_btn, 2, 0, 1, 2)
        v.addWidget(inv_box)

        self.trading_box = QLabel()
        self.trading_box.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        self.trading_box.setStyleSheet(
            "background:#f8fafc; border:1px solid #dbe3ec; border-radius:12px; padding:14px;"
        )
        self.trading_box.setWordWrap(True)
        # No scroll area of its own - see the note in build_income_tab above.
        v.addWidget(self.trading_box)

        close_box = QGroupBox("إقفال المخزون (ترحيل فعلي إلى الحسابات)")
        close_layout = QVBoxLayout(close_box)
        close_note = QLabel(
            "الحساب أعلاه تقديري فقط ولا يُسجَّل في الحسابات. زر الإقفال هنا ينشئ قيدًا "
            "محاسبيًا فعليًا (مدين تكلفة البضاعة المباعة / دائن المخزون) بالفترة المحددة أعلاه "
            "ورصيد آخر المدة المُدخل، بحيث يقل رصيد حساب المخزون فعلاً بما تم استهلاكه. "
            "رصيد أول المدة يُؤخذ تلقائيًا من آخر إقفال سابق، ولا يمكن إقفال نفس الفترة مرتين."
        )
        close_note.setWordWrap(True)
        close_note.setStyleSheet("color:#64748b;")
        close_layout.addWidget(close_note)

        self.close_period_btn = QPushButton("إقفال هذه الفترة الآن")
        self.close_period_btn.clicked.connect(self.close_inventory_period)
        close_layout.addWidget(self.close_period_btn)

        self.inventory_periods_table = QTableWidget()
        self.inventory_periods_table.setColumnCount(6)
        self.inventory_periods_table.setHorizontalHeaderLabels(
            ["من", "إلى", "أول المدة", "آخر المدة", "تكلفة البضاعة المباعة", "الحالة"])
        self.inventory_periods_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.inventory_periods_table.verticalHeader().setVisible(False)
        self.inventory_periods_table.setAlternatingRowColors(True)
        self.inventory_periods_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.inventory_periods_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.inventory_periods_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        close_layout.addWidget(self.inventory_periods_table)

        self.reverse_period_btn = QPushButton("عكس الإقفال المحدد (لإعادة فتح الفترة)")
        self.reverse_period_btn.clicked.connect(self.reverse_selected_inventory_period)
        close_layout.addWidget(self.reverse_period_btn)

        v.addWidget(close_box)
        return widget

    def close_inventory_period(self):
        start_date, end_date = self.resolve_period()
        closing = self.closing_inventory_input.value()
        try:
            self.accounting.close_inventory_period(start_date, end_date, closing)
        except ValueError as e:
            QMessageBox.warning(self, "تعذر الإقفال", str(e))
            return
        QMessageBox.information(self, "تم", "تم إقفال الفترة وترحيل تكلفة البضاعة المباعة إلى الحسابات")
        self.refresh_inventory_periods()
        self.refresh_data()

    def reverse_selected_inventory_period(self):
        rows = self.inventory_periods_table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(self, "لم يتم التحديد", "يرجى تحديد إقفال من الجدول أولاً")
            return
        period_id = self.inventory_periods_table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        try:
            self.accounting.reverse_inventory_period(period_id)
        except ValueError as e:
            QMessageBox.warning(self, "تعذر العكس", str(e))
            return
        QMessageBox.information(self, "تم", "تم عكس الإقفال، والفترة متاحة الآن لإعادة الإقفال بأرقام مصححة")
        self.refresh_inventory_periods()
        self.refresh_data()

    def refresh_inventory_periods(self):
        periods = self.accounting.get_inventory_periods()
        self.inventory_periods_table.setRowCount(len(periods))
        for row, p in enumerate(periods):
            status = "تم عكسه" if p['reversed_at'] else "مرحّل"
            from_item = QTableWidgetItem(p['start_date'])
            from_item.setData(Qt.ItemDataRole.UserRole, p['id'])
            self.inventory_periods_table.setItem(row, 0, from_item)
            self.inventory_periods_table.setItem(row, 1, QTableWidgetItem(p['end_date']))
            self.inventory_periods_table.setItem(row, 2, money_item(p['opening_inventory']))
            self.inventory_periods_table.setItem(row, 3, money_item(p['closing_inventory']))
            self.inventory_periods_table.setItem(row, 4, money_item(p['cogs']))
            self.inventory_periods_table.setItem(row, 5, QTableWidgetItem(status))
        fit_table_height(self.inventory_periods_table)

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
        self.bs_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        v.addWidget(self.bs_table)
        v.addStretch()
        return widget

    def build_ledger_tab(self):
        """Every movement on any one account (cash, inventory, a specific
        expense...), not just its final total the way ميزان المراجعة shows
        it - the same "كشف حساب" idea already used for a supplier or
        customer, just pointed at a whole account instead of one person.
        The owner does not know accounting terms and should never have to;
        this stays "كشف حساب" everywhere, on screen and in conversation."""
        widget = QWidget()
        v = QVBoxLayout(widget)

        picker_row = QHBoxLayout()
        picker_row.setSpacing(8)
        picker_label = QLabel("الحساب:")
        picker_label.setStyleSheet("font-weight:700; color:#334155;")
        self.ledger_account_input = QComboBox()
        self.ledger_account_input.setMinimumWidth(260)
        self.ledger_account_input.currentIndexChanged.connect(self.load_ledger)
        picker_row.addWidget(picker_label)
        picker_row.addWidget(self.ledger_account_input)
        picker_row.addStretch()
        v.addLayout(picker_row)

        self.ledger_balance_label = QLabel()
        self.ledger_balance_label.setStyleSheet(
            "font-weight: 800; color: #1f3b57; background:#eef6ff;"
            "border:1px solid #cfe0f5; border-radius:8px; padding:9px 12px;")
        v.addWidget(self.ledger_balance_label)

        self.ledger_table = QTableWidget()
        self.ledger_table.setColumnCount(4)
        self.ledger_table.setHorizontalHeaderLabels(["التاريخ", "البيان", "مدين", "دائن"])
        self.ledger_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.ledger_table.verticalHeader().setVisible(False)
        self.ledger_table.setAlternatingRowColors(True)
        self.ledger_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.ledger_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        v.addWidget(self.ledger_table)
        v.addStretch()

        for account in self.accounting.get_all_accounts():
            self.ledger_account_input.addItem(f"{account['code']} - {account['name']}", account['code'])
        return widget

    def load_ledger(self):
        code = self.ledger_account_input.currentData()
        if not code:
            return
        ledger = self.accounting.get_account_ledger(code)
        if not fill_table(self.ledger_table, len(ledger['entries']), "لا توجد حركات على هذا الحساب"):
            self.ledger_balance_label.setText(f"الرصيد: {money(ledger['balance'])} ريال")
            fit_table_height(self.ledger_table)
            return
        for row, e in enumerate(ledger['entries']):
            self.ledger_table.setItem(row, 0, QTableWidgetItem(str(e['date'] or "")))
            self.ledger_table.setItem(row, 1, QTableWidgetItem(e['description'] or ""))
            self.ledger_table.setItem(row, 2, money_item(e['debit'], blank_if_zero=True))
            self.ledger_table.setItem(row, 3, money_item(e['credit'], blank_if_zero=True))
        self.ledger_balance_label.setText(f"الرصيد: {money(ledger['balance'])} ريال")
        fit_table_height(self.ledger_table)

    # ---------- Behaviour ----------

    def on_period_changed(self, _text=None):
        is_custom = self.period_input.currentText() == "مخصص"
        self.start_date.setEnabled(is_custom)
        self.end_date.setEnabled(is_custom)
        if not is_custom:
            self.start_date.setDate(QDate.currentDate())
            self.end_date.setDate(QDate.currentDate())
        self.refresh_data()

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
        self.sales_card.value_label.setText(f"{money(summary['revenue'])}")
        self.purchases_card.value_label.setText(f"{money(summary['cogs'] + summary['operating_expenses'])}")
        self.profit_card.value_label.setText(f"{money(summary['net_profit'])}")
        self.vat_card.value_label.setText(f"{money(net_vat)}")
        self.vat_label.setText(f"صافي الضريبة المستحقة للهيئة (مبيعات - مشتريات): {money(net_vat)} ريال")

        self.income_box.setText(
            f"<b>قائمة الدخل ({start_date} إلى {end_date})</b><br><br>"
            f"الإيرادات (صافي المبيعات): {money(summary['revenue'])}<br>"
            f"تكلفة البضاعة المباعة: {money(summary['cogs'])}<br>"
            f"<b>مجمل الربح: {money(summary['revenue'] - summary['cogs'])}</b><br>"
            f"الرواتب والأجور: {money(summary['salaries_expense'])}<br>"
            f"المصروفات التشغيلية: {money(summary['operating_expenses'])}<br>"
            f"<b>صافي الربح: {money(summary['net_profit'])}</b>"
        )

        balance = self.accounting.get_balance_sheet()
        self.balance_box.setText(
            f"<b>قائمة المركز المالي</b><br><br>"
            f"إجمالي الأصول: {money(balance['assets'])}<br>"
            f"إجمالي الالتزامات: {money(balance['liabilities'])}<br>"
            f"حقوق الملكية (شامل الأرباح المرحّلة): {money(balance['equity'])}<br>"
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
            self.table.setItem(row, 2, QTableWidgetItem(label_for(ACCOUNT_TYPE_LABELS, item['type'])))
            self.table.setItem(row, 3, money_item(debit, blank_if_zero=True))
            self.table.setItem(row, 4, money_item(credit, blank_if_zero=True))

        # Show the balanced/unbalanced state on the totals label rather than as a
        # border on the table: a bare "border: ..." stylesheet on a QTableWidget
        # also leaks onto its header and scrollbars.
        balanced = abs(total_debit - total_credit) < 0.01
        status = "متوازن ✓" if balanced else "غير متوازن ✗"
        color = "#16a34a" if balanced else "#dc2626"
        self.tb_totals_label.setText(
            f"إجمالي مدين: {money(total_debit)}   |   إجمالي دائن: {money(total_credit)}   |   {status}"
        )
        self.tb_totals_label.setStyleSheet(
            f"font-weight: 800; padding: 8px; color: {color}; background: transparent; border: none;"
        )
        fit_table_height(self.table)

        self.refresh_trading_account()
        self.refresh_inventory_periods()

    def refresh_balance_sheet_table(self):
        rows = self.accounting.get_balance_sheet_detail()
        self.bs_table.setRowCount(len(rows))
        for row, item in enumerate(rows):
            self.bs_table.setItem(row, 0, QTableWidgetItem(item['section']))
            self.bs_table.setItem(row, 1, QTableWidgetItem(item['name']))
            self.bs_table.setItem(row, 2, money_item(item['debit'], blank_if_zero=True))
            self.bs_table.setItem(row, 3, money_item(item['credit'], blank_if_zero=True))
        fit_table_height(self.bs_table)

    def refresh_trading_account(self):
        start_date, end_date = self.resolve_period()
        opening = self.opening_inventory_input.value()
        closing = self.closing_inventory_input.value()
        result = self.accounting.get_trading_account(start_date, end_date, opening, closing)
        self.trading_box.setText(
            f"<b>حساب المتاجرة ({start_date} إلى {end_date})</b><br><br>"
            f"رصيد أول المدة (المخزون): {money(result['opening_inventory'])}<br>"
            f"(+) المشتريات (مواد خام): {money(result['purchases'])}<br>"
            f"(+) المصروفات المرتبطة بالمشتريات: {money(result['purchase_related_expenses'])}<br>"
            f"(-) مرتجعات المشتريات: {money(result['purchase_returns'])}<br>"
            f"<b>= تكلفة البضاعة المتاحة للبيع: {money(result['cogs_available'])}</b><br>"
            f"(-) رصيد آخر المدة (المخزون): {money(result['closing_inventory'])}<br>"
            f"<b>= تكلفة البضاعة المباعة: {money(result['cost_of_goods_sold'])}</b><br><br>"
            f"صافي المبيعات: {money(result['net_sales'])}<br>"
            f"(-) مرتجعات المبيعات: {money(result['sales_returns'])}<br>"
            f"<b>= مجمل الربح (حساب المتاجرة): {money(result['gross_profit'])}</b>"
        )

    def refresh_on_show(self):
        self.refresh_data()
        self.load_ledger()
