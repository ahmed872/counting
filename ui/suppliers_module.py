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


class SuppliersModule(QWidget):
    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.accounting = AccountingLogic(db_manager)
        self.selected_supplier_id = None
        self.init_ui()

    def init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(12)

        root_layout.addWidget(page_header(
            "الموردون",
            "أضف الموردين، تابع رصيد كل مورد على حدة، وسجّل السداد."))

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        root_layout.addWidget(tabs, 1)

        # ---- Tab 1: suppliers and balances ----
        list_tab = QWidget()
        list_layout = QVBoxLayout(list_tab)
        list_layout.setSpacing(10)

        self.name_input = QLineEdit()
        self.tax_id_input = QLineEdit()
        self.phone_input = QLineEdit()
        self.opening_balance_input = QLineEdit()
        self.opening_balance_input.setPlaceholderText("0.00")
        self.name_input.returnPressed.connect(self.add_supplier)

        form_box = QGroupBox("إضافة مورد جديد")
        form_outer = QVBoxLayout(form_box)
        form_outer.setSpacing(10)
        add_btn = QPushButton("حفظ المورد")
        add_btn.setMinimumHeight(38)
        add_btn.clicked.connect(self.add_supplier)
        form_outer.setContentsMargins(10, 6, 10, 8)
        form_outer.addWidget(compact_form([
            ("اسم المورد", self.name_input),
            ("الرقم الضريبي", self.tax_id_input),
            ("رقم الجوال", self.phone_input),
            ("رصيد افتتاحي", self.opening_balance_input),
            (None, add_btn),
        ], columns=2, field_min_width=130))
        list_layout.addWidget(pin_height(form_box))

        list_header_row = QHBoxLayout()
        list_label = QLabel("قائمة الموردين والأرصدة الحالية")
        list_label.setStyleSheet("font-weight: 700; color: #334155;")
        list_header_row.addWidget(list_label)
        list_header_row.addStretch()
        # There is no hard delete for a supplier - one is always linked to
        # past purchases, payments, and journal entries, and deleting it
        # would either be blocked by that history or silently orphan it.
        # "Stop dealing with" is the safe equivalent: it drops off the list
        # offered for new purchases while every past number stays intact and
        # any balance still owed can still be paid off and reversed.
        self.toggle_active_btn = QPushButton("إيقاف/إعادة تفعيل التعامل مع المورد المحدد")
        self.toggle_active_btn.clicked.connect(self.toggle_supplier_active)
        list_header_row.addWidget(self.toggle_active_btn)
        list_layout.addLayout(list_header_row)

        self.suppliers_table = QTableWidget()
        self.suppliers_table.setColumnCount(4)
        self.suppliers_table.setHorizontalHeaderLabels(["المورد", "الجوال", "الرصيد الحالي", "الحالة"])
        self.suppliers_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.suppliers_table.verticalHeader().setVisible(False)
        self.suppliers_table.setAlternatingRowColors(True)
        self.suppliers_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.suppliers_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.suppliers_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.suppliers_table.setMinimumHeight(90)
        self.suppliers_table.itemSelectionChanged.connect(self.on_supplier_selected)
        list_layout.addWidget(self.suppliers_table)

        self.total_balance_label = QLabel("إجمالي أرصدة الموردين الدائنة: 0.00 ريال")
        self.total_balance_label.setStyleSheet("font-weight: 800; color: #e67e22; padding: 4px 2px;")
        list_layout.addWidget(self.total_balance_label)
        list_layout.addStretch()
        tabs.addTab(list_tab, "الموردون والأرصدة")

        # ---- Tab 2: payment and statement ----
        pay_tab = QWidget()
        pay_layout = QVBoxLayout(pay_tab)
        pay_layout.setSpacing(10)

        # The supplier is picked here, on the screen where the payment is
        # entered. It used to be a read-only label that only filled in after
        # selecting a row on the other tab, which meant the payment screen had
        # no way to answer "who am I paying?" on its own.
        self.payment_supplier = QComboBox()
        self.payment_supplier.setMinimumWidth(240)
        self.payment_supplier.currentIndexChanged.connect(self.on_payment_supplier_changed)

        self.payment_balance_label = QLabel()
        self.payment_balance_label.setStyleSheet(
            "font-weight: 800; color: #1f3b57; background:#eef6ff;"
            "border:1px solid #cfe0f5; border-radius:8px; padding:9px 12px;")

        picker_row = QHBoxLayout()
        picker_row.setSpacing(8)
        picker_label = QLabel("المورد:")
        picker_label.setStyleSheet("font-weight:700; color:#334155;")
        picker_row.addWidget(picker_label)
        picker_row.addWidget(self.payment_supplier)
        picker_row.addWidget(self.payment_balance_label, 1)
        pay_layout.addLayout(picker_row)

        self.payment_amount = QLineEdit()
        self.payment_amount.setPlaceholderText("0.00")
        self.payment_method = QComboBox()
        self.payment_method.addItem("نقدي", "Cash")
        self.payment_method.addItem("تحويل بنكي", "Bank")
        self.payment_notes = QLineEdit()
        self.payment_amount.returnPressed.connect(self.record_payment)

        payment_box = QGroupBox("تسجيل سداد")
        payment_outer = QVBoxLayout(payment_box)
        payment_outer.setSpacing(10)
        pay_btn = QPushButton("تسجيل السداد")
        pay_btn.setMinimumHeight(38)
        pay_btn.clicked.connect(self.record_payment)
        payment_outer.setContentsMargins(10, 6, 10, 8)
        payment_outer.addWidget(compact_form([
            ("المبلغ", self.payment_amount),
            ("طريقة السداد", self.payment_method),
            ("ملاحظات", self.payment_notes),
            (None, pay_btn),
        ], columns=2, field_min_width=150))
        pay_layout.addWidget(pin_height(payment_box))

        statement_label = QLabel("كشف حساب المورد")
        statement_label.setStyleSheet("font-weight: 700; color: #334155;")
        pay_layout.addWidget(statement_label)

        self.statement_table = QTableWidget()
        self.statement_table.setColumnCount(5)
        self.statement_table.setHorizontalHeaderLabels(["التاريخ", "البيان", "مدين (سداد)", "دائن (مستحق)", "الرصيد"])
        self.statement_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.statement_table.verticalHeader().setVisible(False)
        self.statement_table.setAlternatingRowColors(True)
        self.statement_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.statement_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.statement_table.setMinimumHeight(90)
        pay_layout.addWidget(self.statement_table)
        pay_layout.addStretch()
        tabs.addTab(pay_tab, "السداد وكشف الحساب")

        self.load_suppliers()

    def add_supplier(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "تنبيه", "ادخل اسم المورد")
            return
        tax_id = self.tax_id_input.text().strip()
        phone = self.phone_input.text().strip()
        try:
            opening_balance = parse_money(self.opening_balance_input.text(),
                                          "الرصيد الافتتاحي")
        except ValueError as exc:
            QMessageBox.warning(self, "تنبيه", str(exc))
            return

        # One transaction: the supplier row and its opening-balance journal
        # entry used to be two separate commits. A failure between them
        # could leave a supplier whose own statement (which reads
        # opening_balance straight off this row) shows a balance the
        # general ledger and trial balance never received.
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.db.transaction() as cursor:
            cursor.execute(
                "INSERT INTO suppliers (name, tax_id, opening_balance, phone) VALUES (?, ?, ?, ?)",
                (name, tax_id, opening_balance, phone),
            )
            if opening_balance:
                items = [
                    {'account_code': '3900', 'debit': opening_balance, 'credit': 0},
                    {'account_code': '2000', 'debit': 0, 'credit': opening_balance},
                ]
                self.db.insert_journal_entry(
                    cursor, timestamp, f"رصيد افتتاحي لمورد - {name}", None, items)

        QMessageBox.information(self, "نجاح", "تم إضافة المورد بنجاح")
        self.name_input.clear()
        self.tax_id_input.clear()
        self.phone_input.clear()
        self.opening_balance_input.clear()
        self.load_suppliers()

    def load_suppliers(self):
        balances = self.accounting.get_all_supplier_balances()
        self.reload_payment_picker(balances)
        total = 0
        if not fill_table(self.suppliers_table, len(balances), "لا يوجد موردون مسجلون بعد"):
            self.total_balance_label.setText("")
            fit_table_height(self.suppliers_table)
            return
        for row, s in enumerate(balances):
            total += s['balance']
            name_item = QTableWidgetItem(s['name'])
            self.suppliers_table.setItem(row, 0, name_item)
            self.suppliers_table.setItem(row, 1, QTableWidgetItem(s['phone'] or ""))
            self.suppliers_table.setItem(row, 2, money_item(s['balance'], bold=True))
            status = "له رصيد مستحق" if s['balance'] > 0.01 else ("مسدد بالكامل" if s['balance'] > -0.01 else "رصيد لصالحنا")
            if not s['is_active']:
                status = "متوقف — " + status
            item = QTableWidgetItem(status)
            self.suppliers_table.setItem(row, 3, item)
            name_item.setData(Qt.ItemDataRole.UserRole, s['id'])
            if not s['is_active']:
                for col in range(4):
                    self.suppliers_table.item(row, col).setForeground(Qt.GlobalColor.gray)
        # "إجمالي الأرصدة الدائنة: -1,000" is a contradiction in terms and reads
        # as a mistake. Say which direction the money actually goes.
        if total > 0.01:
            summary = f"إجمالي المستحق للموردين: {money(total)} ريال"
        elif total < -0.01:
            summary = f"مدفوع للموردين بالزيادة: {money(abs(total))} ريال"
        else:
            summary = "لا يوجد مستحق للموردين — كل الحسابات مسددة"
        self.total_balance_label.setText(summary)
        fit_table_height(self.suppliers_table)

    def reload_payment_picker(self, balances):
        """Refill the dropdown, keeping whoever was selected still selected.

        Rebuilding a combo box fires currentIndexChanged for every item that
        goes in, so the signal is muted for the duration - otherwise adding a
        supplier would silently repoint an in-progress payment at someone else.
        """
        previous = self.selected_supplier_id
        self.payment_supplier.blockSignals(True)
        self.payment_supplier.clear()
        for s in balances:
            self.payment_supplier.addItem(s['name'], s['id'])
        index = self.payment_supplier.findData(previous) if previous else -1
        if index < 0:
            index = 0 if self.payment_supplier.count() else -1
        self.payment_supplier.setCurrentIndex(index)
        self.payment_supplier.blockSignals(False)
        self.selected_supplier_id = self.payment_supplier.currentData()
        self.update_payment_balance()

    def update_payment_balance(self):
        """Show what is owed right next to the amount being paid, so paying the
        wrong figure takes ignoring the number sitting beside the box."""
        if not self.selected_supplier_id:
            self.payment_balance_label.setText("لا يوجد موردون مسجلون")
            return
        balance = self.accounting.get_supplier_statement(self.selected_supplier_id)["balance"]
        if balance > 0.01:
            text, colour = f"المستحق عليه الآن: {money(balance)} ريال", "#1f3b57"
        elif balance < -0.01:
            text, colour = f"مدفوع بالزيادة: {money(abs(balance))} ريال", "#b45309"
        else:
            text, colour = "الحساب مسدد بالكامل", "#15803d"
        self.payment_balance_label.setText(text)
        self.payment_balance_label.setStyleSheet(
            f"font-weight: 800; color: {colour}; background:#eef6ff;"
            "border:1px solid #cfe0f5; border-radius:8px; padding:9px 12px;")

    def on_payment_supplier_changed(self):
        self.selected_supplier_id = self.payment_supplier.currentData()
        self.update_payment_balance()
        self.refresh_statement()

    def on_supplier_selected(self):
        """Selecting a row on the list tab still points the payment tab at that
        supplier - the dropdown is an addition, not a replacement, so the habit
        of clicking the row keeps working."""
        rows = self.suppliers_table.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        supplier_id = self.suppliers_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        self.selected_supplier_id = supplier_id
        index = self.payment_supplier.findData(supplier_id)
        if index >= 0:
            self.payment_supplier.blockSignals(True)
            self.payment_supplier.setCurrentIndex(index)
            self.payment_supplier.blockSignals(False)
        self.update_payment_balance()
        self.refresh_statement()

    def refresh_statement(self):
        if not self.selected_supplier_id:
            self.statement_table.setRowCount(0)
            fit_table_height(self.statement_table)
            return
        statement = self.accounting.get_supplier_statement(self.selected_supplier_id)
        entries = statement['entries']
        if not fill_table(self.statement_table, len(entries), "لا توجد حركات على هذا المورد"):
            fit_table_height(self.statement_table)
            return
        for row, e in enumerate(entries):
            self.statement_table.setItem(row, 0, QTableWidgetItem(str(e['date'] or "")))
            self.statement_table.setItem(row, 1, QTableWidgetItem(e['type']))
            self.statement_table.setItem(row, 2, money_item(e['debit'], blank_if_zero=True))
            self.statement_table.setItem(row, 3, money_item(e['credit'], blank_if_zero=True))
            self.statement_table.setItem(row, 4, money_item(e['balance'], bold=True))
        fit_table_height(self.statement_table)

    def record_payment(self):
        if not self.selected_supplier_id:
            QMessageBox.warning(self, "تنبيه", "اختر مورداً من القائمة أولاً")
            return
        try:
            amount = parse_money(self.payment_amount.text(), "مبلغ السداد",
                                 allow_blank=False, allow_zero=False)
            if amount <= 0:
                raise ValueError
        except ValueError as exc:
            QMessageBox.warning(self, "تنبيه", str(exc))
            return

        # Paying more than is owed is almost always a typo - an extra zero, or
        # the wrong supplier picked. It is legal (a deposit, an advance), so it
        # is a question and not a refusal, but it must not go through silently:
        # the balance simply went negative and nothing said a word.
        outstanding = self.accounting.get_supplier_statement(self.selected_supplier_id)["balance"]
        if amount > outstanding + 0.01:
            supplier_name = self.payment_supplier.currentText()
            owed = (f"المستحق عليه {money(outstanding)} ريال فقط"
                    if outstanding > 0.01 else "لا يوجد أي مبلغ مستحق عليه")
            answer = QMessageBox.question(
                self, "المبلغ أكبر من المستحق",
                f"أنت تسجّل سداد {money(amount)} ريال للمورد «{supplier_name}»، و{owed}.\n\n"
                "لو كان هذا مقصوداً (دفعة مقدمة) اضغط نعم.\n"
                "لو كان خطأ في الرقم أو في اختيار المورد اضغط لا.",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        method = self.payment_method.currentData()
        notes = self.payment_notes.text().strip()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cash_account = '1000' if method == 'Cash' else '1001'
        items = [
            {'account_code': '2000', 'debit': amount, 'credit': 0},
            {'account_code': cash_account, 'debit': 0, 'credit': amount},
        ]
        # One transaction: a crash between these two writes used to be able to
        # leave cash moved in the accounts with no payment record behind it.
        with self.db.transaction() as cursor:
            self.db.insert_journal_entry(cursor, timestamp, "سداد لمورد", None, items)
            cursor.execute(
                "INSERT INTO supplier_payments (supplier_id, date, amount, method, notes) VALUES (?, ?, ?, ?, ?)",
                (self.selected_supplier_id, timestamp, amount, method, notes),
            )

        QMessageBox.information(self, "نجاح", "تم تسجيل السداد وتحديث رصيد المورد")
        self.payment_amount.clear()
        self.payment_notes.clear()
        self.load_suppliers()
        self.refresh_statement()

    def toggle_supplier_active(self):
        if not self.selected_supplier_id:
            QMessageBox.warning(self, "تنبيه", "اختر مورداً من القائمة أولاً")
            return
        supplier = self.db.fetch_one(
            "SELECT name, is_active FROM suppliers WHERE id = ?", (self.selected_supplier_id,))
        if not supplier:
            return
        turning_off = bool(supplier['is_active'])
        if turning_off:
            balance = self.accounting.get_supplier_statement(self.selected_supplier_id)["balance"]
            note = (f"\n\nملاحظة: لا يزال عليه رصيد مستحق {money(balance)} ريال — "
                    "يمكنك تسجيل السداد له وهو متوقف." if balance > 0.01 else "")
            question = (
                f"هل تريد إيقاف التعامل مع المورد «{supplier['name']}»؟\n"
                "لن يظهر بعد ذلك كخيار عند تسجيل مشتريات جديدة، لكن بياناته وكل حركاته "
                "السابقة تبقى محفوظة كما هي، ويمكن إعادة تفعيله في أي وقت." + note)
        else:
            question = f"هل تريد إعادة تفعيل التعامل مع المورد «{supplier['name']}»؟"
        answer = QMessageBox.question(self, "تأكيد", question)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.db.execute_query(
            "UPDATE suppliers SET is_active = ? WHERE id = ?",
            (0 if turning_off else 1, self.selected_supplier_id))
        self.load_suppliers()
        self.refresh_statement()

    def refresh_on_show(self):
        self.load_suppliers()
        self.refresh_statement()
