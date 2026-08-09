from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QComboBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QTabWidget,
)

from logic.accounting import AccountingLogic
from ui.formatting import money_item, money
from ui.common_widgets import page_header, fill_table, compact_form, pin_height, fit_table_height
from logic.money import parse_money


class CustomersModule(QWidget):
    """The mirror image of SuppliersModule: a supplier is money we owe, a
    customer here is money owed to us. Same shape, opposite direction."""

    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.accounting = AccountingLogic(db_manager)
        self.selected_customer_id = None
        self.init_ui()

    def init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(12)

        root_layout.addWidget(page_header(
            "العملاء",
            "أضف العملاء اللي بتبيعلهم بالأجل، تابع رصيد كل عميل، وسجّل التحصيل."))

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        root_layout.addWidget(tabs, 1)

        # ---- Tab 1: customers and balances ----
        list_tab = QWidget()
        list_layout = QVBoxLayout(list_tab)
        list_layout.setSpacing(10)

        self.name_input = QLineEdit()
        self.tax_id_input = QLineEdit()
        self.phone_input = QLineEdit()
        self.opening_balance_input = QLineEdit()
        self.opening_balance_input.setPlaceholderText("0.00")
        self.name_input.returnPressed.connect(self.add_customer)

        form_box = QGroupBox("إضافة عميل جديد")
        form_outer = QVBoxLayout(form_box)
        form_outer.setSpacing(10)
        add_btn = QPushButton("حفظ العميل")
        add_btn.setMinimumHeight(38)
        add_btn.clicked.connect(self.add_customer)
        form_outer.setContentsMargins(10, 6, 10, 8)
        form_outer.addWidget(compact_form([
            ("اسم العميل", self.name_input),
            ("الرقم الضريبي", self.tax_id_input),
            ("رقم الجوال", self.phone_input),
            ("رصيد افتتاحي (مستحق له علينا)", self.opening_balance_input),
            (None, add_btn),
        ], columns=2, field_min_width=130))
        list_layout.addWidget(pin_height(form_box))

        list_header_row = QHBoxLayout()
        list_label = QLabel("قائمة العملاء والأرصدة الحالية")
        list_label.setStyleSheet("font-weight: 700; color: #334155;")
        list_header_row.addWidget(list_label)
        list_header_row.addStretch()
        # No hard delete here either, for the same reason as suppliers: a
        # customer is always linked to past credit sales and collections.
        self.toggle_active_btn = QPushButton("إيقاف/إعادة تفعيل التعامل مع العميل المحدد")
        self.toggle_active_btn.clicked.connect(self.toggle_customer_active)
        list_header_row.addWidget(self.toggle_active_btn)
        list_layout.addLayout(list_header_row)

        self.customers_table = QTableWidget()
        self.customers_table.setColumnCount(4)
        self.customers_table.setHorizontalHeaderLabels(["العميل", "الجوال", "المستحق له علينا", "الحالة"])
        self.customers_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.customers_table.verticalHeader().setVisible(False)
        self.customers_table.setAlternatingRowColors(True)
        self.customers_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.customers_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.customers_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.customers_table.setMinimumHeight(90)
        self.customers_table.itemSelectionChanged.connect(self.on_customer_selected)
        list_layout.addWidget(self.customers_table)

        self.total_balance_label = QLabel("إجمالي المستحق على العملاء: 0.00 ريال")
        self.total_balance_label.setStyleSheet("font-weight: 800; color: #2c7be5; padding: 4px 2px;")
        list_layout.addWidget(self.total_balance_label)
        list_layout.addStretch()
        tabs.addTab(list_tab, "العملاء والأرصدة")

        # ---- Tab 2: credit sale, collection, and statement ----
        pay_tab = QWidget()
        pay_layout = QVBoxLayout(pay_tab)
        pay_layout.setSpacing(10)

        self.active_customer = QComboBox()
        self.active_customer.setMinimumWidth(240)
        self.active_customer.currentIndexChanged.connect(self.on_active_customer_changed)

        self.balance_label = QLabel()
        self.balance_label.setStyleSheet(
            "font-weight: 800; color: #1f3b57; background:#eef6ff;"
            "border:1px solid #cfe0f5; border-radius:8px; padding:9px 12px;")

        picker_row = QHBoxLayout()
        picker_row.setSpacing(8)
        picker_label = QLabel("العميل:")
        picker_label.setStyleSheet("font-weight:700; color:#334155;")
        picker_row.addWidget(picker_label)
        picker_row.addWidget(self.active_customer)
        picker_row.addWidget(self.balance_label, 1)
        pay_layout.addLayout(picker_row)

        self.sale_amount = QLineEdit()
        self.sale_amount.setPlaceholderText("0.00 شامل الضريبة")
        self.sale_notes = QLineEdit()
        self.sale_amount.returnPressed.connect(self.record_credit_sale)

        sale_box = QGroupBox("تسجيل بيع آجل (فاتورة جديدة على حساب العميل)")
        sale_outer = QVBoxLayout(sale_box)
        sale_outer.setSpacing(10)
        sale_btn = QPushButton("تسجيل البيع الآجل")
        sale_btn.setMinimumHeight(38)
        sale_btn.clicked.connect(self.record_credit_sale)
        sale_outer.setContentsMargins(10, 6, 10, 8)
        sale_outer.addWidget(compact_form([
            ("المبلغ", self.sale_amount),
            ("البيان", self.sale_notes),
            (None, sale_btn),
        ], columns=2, field_min_width=150))
        pay_layout.addWidget(pin_height(sale_box))

        self.collect_amount = QLineEdit()
        self.collect_amount.setPlaceholderText("0.00")
        self.collect_method = QComboBox()
        self.collect_method.addItem("نقدي", "Cash")
        self.collect_method.addItem("تحويل بنكي", "Bank")
        self.collect_notes = QLineEdit()
        self.collect_amount.returnPressed.connect(self.record_collection)

        collect_box = QGroupBox("تسجيل تحصيل من العميل")
        collect_outer = QVBoxLayout(collect_box)
        collect_outer.setSpacing(10)
        collect_btn = QPushButton("تسجيل التحصيل")
        collect_btn.setMinimumHeight(38)
        collect_btn.clicked.connect(self.record_collection)
        collect_outer.setContentsMargins(10, 6, 10, 8)
        collect_outer.addWidget(compact_form([
            ("المبلغ", self.collect_amount),
            ("طريقة التحصيل", self.collect_method),
            ("ملاحظات", self.collect_notes),
            (None, collect_btn),
        ], columns=2, field_min_width=150))
        pay_layout.addWidget(pin_height(collect_box))

        statement_label = QLabel("كشف حساب العميل")
        statement_label.setStyleSheet("font-weight: 700; color: #334155;")
        pay_layout.addWidget(statement_label)

        self.statement_table = QTableWidget()
        self.statement_table.setColumnCount(5)
        self.statement_table.setHorizontalHeaderLabels(["التاريخ", "البيان", "مدين (مستحق)", "دائن (تحصيل)", "الرصيد"])
        self.statement_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.statement_table.verticalHeader().setVisible(False)
        self.statement_table.setAlternatingRowColors(True)
        self.statement_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.statement_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.statement_table.setMinimumHeight(90)
        pay_layout.addWidget(self.statement_table)
        pay_layout.addStretch()
        tabs.addTab(pay_tab, "بيع آجل وتحصيل")

        self.load_customers()

    def add_customer(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "تنبيه", "ادخل اسم العميل")
            return
        tax_id = self.tax_id_input.text().strip()
        phone = self.phone_input.text().strip()
        try:
            opening_balance = parse_money(self.opening_balance_input.text(),
                                          "الرصيد الافتتاحي")
        except ValueError as exc:
            QMessageBox.warning(self, "تنبيه", str(exc))
            return

        customer_id = self.db.insert_and_return_id(
            "INSERT INTO customers (name, tax_id, opening_balance, phone) VALUES (?, ?, ?, ?)",
            (name, tax_id, opening_balance, phone),
        )

        if opening_balance:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            items = [
                {'account_code': '1400', 'debit': opening_balance, 'credit': 0},
                {'account_code': '3900', 'debit': 0, 'credit': opening_balance},
            ]
            self.db.add_journal_entry(timestamp, f"رصيد افتتاحي لعميل - {name}", None, items)

        QMessageBox.information(self, "نجاح", "تم إضافة العميل بنجاح")
        self.name_input.clear()
        self.tax_id_input.clear()
        self.phone_input.clear()
        self.opening_balance_input.clear()
        self.load_customers()

    def load_customers(self):
        balances = self.accounting.get_all_customer_balances()
        self.reload_customer_picker(balances)
        total = 0
        if not fill_table(self.customers_table, len(balances), "لا يوجد عملاء مسجلون بعد"):
            self.total_balance_label.setText("")
            fit_table_height(self.customers_table)
            return
        for row, c in enumerate(balances):
            total += c['balance']
            name_item = QTableWidgetItem(c['name'])
            self.customers_table.setItem(row, 0, name_item)
            self.customers_table.setItem(row, 1, QTableWidgetItem(c['phone'] or ""))
            self.customers_table.setItem(row, 2, money_item(c['balance'], bold=True))
            status = "له مستحق" if c['balance'] > 0.01 else ("مسدد بالكامل" if c['balance'] > -0.01 else "دفع بالزيادة")
            if not c['is_active']:
                status = "متوقف — " + status
            item = QTableWidgetItem(status)
            self.customers_table.setItem(row, 3, item)
            name_item.setData(Qt.ItemDataRole.UserRole, c['id'])
            if not c['is_active']:
                for col in range(4):
                    self.customers_table.item(row, col).setForeground(Qt.GlobalColor.gray)
        if total > 0.01:
            summary = f"إجمالي المستحق على العملاء: {money(total)} ريال"
        elif total < -0.01:
            summary = f"دفعوا بالزيادة: {money(abs(total))} ريال"
        else:
            summary = "لا يوجد مستحق على العملاء — كل الحسابات مسددة"
        self.total_balance_label.setText(summary)
        fit_table_height(self.customers_table)

    def reload_customer_picker(self, balances):
        previous = self.selected_customer_id
        self.active_customer.blockSignals(True)
        self.active_customer.clear()
        for c in balances:
            self.active_customer.addItem(c['name'], c['id'])
        index = self.active_customer.findData(previous) if previous else -1
        if index < 0:
            index = 0 if self.active_customer.count() else -1
        self.active_customer.setCurrentIndex(index)
        self.active_customer.blockSignals(False)
        self.selected_customer_id = self.active_customer.currentData()
        self.update_balance_label()

    def update_balance_label(self):
        if not self.selected_customer_id:
            self.balance_label.setText("لا يوجد عملاء مسجلون")
            return
        balance = self.accounting.get_customer_statement(self.selected_customer_id)["balance"]
        if balance > 0.01:
            text, colour = f"المستحق له علينا الآن: {money(balance)} ريال", "#1f3b57"
        elif balance < -0.01:
            text, colour = f"دفع بالزيادة: {money(abs(balance))} ريال", "#b45309"
        else:
            text, colour = "الحساب مسدد بالكامل", "#15803d"
        self.balance_label.setText(text)
        self.balance_label.setStyleSheet(
            f"font-weight: 800; color: {colour}; background:#eef6ff;"
            "border:1px solid #cfe0f5; border-radius:8px; padding:9px 12px;")

    def on_active_customer_changed(self):
        self.selected_customer_id = self.active_customer.currentData()
        self.update_balance_label()
        self.refresh_statement()

    def on_customer_selected(self):
        rows = self.customers_table.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        customer_id = self.customers_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        self.selected_customer_id = customer_id
        index = self.active_customer.findData(customer_id)
        if index >= 0:
            self.active_customer.blockSignals(True)
            self.active_customer.setCurrentIndex(index)
            self.active_customer.blockSignals(False)
        self.update_balance_label()
        self.refresh_statement()

    def refresh_statement(self):
        if not self.selected_customer_id:
            self.statement_table.setRowCount(0)
            fit_table_height(self.statement_table)
            return
        statement = self.accounting.get_customer_statement(self.selected_customer_id)
        entries = statement['entries']
        if not fill_table(self.statement_table, len(entries), "لا توجد حركات على هذا العميل"):
            fit_table_height(self.statement_table)
            return
        for row, e in enumerate(entries):
            self.statement_table.setItem(row, 0, QTableWidgetItem(str(e['date'] or "")))
            self.statement_table.setItem(row, 1, QTableWidgetItem(e['type']))
            self.statement_table.setItem(row, 2, money_item(e['debit'], blank_if_zero=True))
            self.statement_table.setItem(row, 3, money_item(e['credit'], blank_if_zero=True))
            self.statement_table.setItem(row, 4, money_item(e['balance'], bold=True))
        fit_table_height(self.statement_table)

    def record_credit_sale(self):
        if not self.selected_customer_id:
            QMessageBox.warning(self, "تنبيه", "اختر عميلاً من القائمة أولاً")
            return
        customer = self.db.fetch_one(
            "SELECT name, is_active FROM customers WHERE id = ?", (self.selected_customer_id,))
        if customer and not customer['is_active']:
            answer = QMessageBox.question(
                self, "عميل متوقف",
                f"العميل «{customer['name']}» متوقف التعامل معه حالياً.\n\n"
                "هل تريد بالفعل تسجيل بيع آجل جديد له؟",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            total = parse_money(self.sale_amount.text(), "مبلغ الفاتورة",
                                allow_blank=False, allow_zero=False)
            if total <= 0:
                raise ValueError
        except ValueError as exc:
            QMessageBox.warning(self, "تنبيه", str(exc))
            return

        amount, vat = self.accounting.reverse_vat(total)
        notes = self.sale_notes.text().strip()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        items = [
            {'account_code': '1400', 'debit': total, 'credit': 0},
            {'account_code': '4000', 'debit': 0, 'credit': amount},
            {'account_code': '2100', 'debit': 0, 'credit': vat},
        ]
        with self.db.transaction() as cursor:
            entry_id = self.db.insert_journal_entry(cursor, timestamp, "بيع آجل لعميل", None, items)
            cursor.execute(
                """INSERT INTO customer_sales (branch_id, customer_id, date, amount, vat_amount,
                       description, journal_entry_id) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (None, self.selected_customer_id, timestamp, amount, vat, notes, entry_id),
            )

        QMessageBox.information(self, "نجاح", "تم تسجيل البيع الآجل وتحديث رصيد العميل")
        self.sale_amount.clear()
        self.sale_notes.clear()
        self.load_customers()
        self.refresh_statement()

    def record_collection(self):
        if not self.selected_customer_id:
            QMessageBox.warning(self, "تنبيه", "اختر عميلاً من القائمة أولاً")
            return
        try:
            amount = parse_money(self.collect_amount.text(), "مبلغ التحصيل",
                                 allow_blank=False, allow_zero=False)
            if amount <= 0:
                raise ValueError
        except ValueError as exc:
            QMessageBox.warning(self, "تنبيه", str(exc))
            return

        # Collecting more than is owed is almost always a typo, same
        # reasoning as overpaying a supplier - legal (an advance from the
        # customer), but must not go through silently.
        outstanding = self.accounting.get_customer_statement(self.selected_customer_id)["balance"]
        if amount > outstanding + 0.01:
            customer_name = self.active_customer.currentText()
            owed = (f"المستحق له علينا {money(outstanding)} ريال فقط"
                    if outstanding > 0.01 else "لا يوجد أي مبلغ مستحق عليه")
            answer = QMessageBox.question(
                self, "المبلغ أكبر من المستحق",
                f"أنت تسجّل تحصيل {money(amount)} ريال من العميل «{customer_name}»، و{owed}.\n\n"
                "لو كان هذا مقصوداً (دفعة مقدمة) اضغط نعم.\n"
                "لو كان خطأ في الرقم أو في اختيار العميل اضغط لا.",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        method = self.collect_method.currentData()
        notes = self.collect_notes.text().strip()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cash_account = '1000' if method == 'Cash' else '1001'
        items = [
            {'account_code': cash_account, 'debit': amount, 'credit': 0},
            {'account_code': '1400', 'debit': 0, 'credit': amount},
        ]
        with self.db.transaction() as cursor:
            entry_id = self.db.insert_journal_entry(cursor, timestamp, "تحصيل من عميل", None, items)
            cursor.execute(
                "INSERT INTO customer_payments (customer_id, date, amount, method, notes, journal_entry_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (self.selected_customer_id, timestamp, amount, method, notes, entry_id),
            )

        QMessageBox.information(self, "نجاح", "تم تسجيل التحصيل وتحديث رصيد العميل")
        self.collect_amount.clear()
        self.collect_notes.clear()
        self.load_customers()
        self.refresh_statement()

    def toggle_customer_active(self):
        if not self.selected_customer_id:
            QMessageBox.warning(self, "تنبيه", "اختر عميلاً من القائمة أولاً")
            return
        customer = self.db.fetch_one(
            "SELECT name, is_active FROM customers WHERE id = ?", (self.selected_customer_id,))
        if not customer:
            return
        turning_off = bool(customer['is_active'])
        if turning_off:
            balance = self.accounting.get_customer_statement(self.selected_customer_id)["balance"]
            note = (f"\n\nملاحظة: لا يزال له مستحق {money(balance)} ريال — "
                    "يمكنك تسجيل التحصيل منه وهو متوقف." if balance > 0.01 else "")
            question = (
                f"هل تريد إيقاف التعامل مع العميل «{customer['name']}»؟\n"
                "سيتم تنبيهك في المرة القادمة لو حاولت تسجيل بيع آجل جديد له، لكن بياناته "
                "وكل حركاته السابقة تبقى محفوظة كما هي، ويمكن إعادة تفعيله في أي وقت." + note)
        else:
            question = f"هل تريد إعادة تفعيل التعامل مع العميل «{customer['name']}»؟"
        answer = QMessageBox.question(self, "تأكيد", question)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.db.execute_query(
            "UPDATE customers SET is_active = ? WHERE id = ?",
            (0 if turning_off else 1, self.selected_customer_id))
        self.load_customers()
        self.refresh_statement()

    def refresh_on_show(self):
        self.load_customers()
        self.refresh_statement()
