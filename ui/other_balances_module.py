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

PREPAID_TARGET_LABELS = [
    ('5200', 'مصروفات تشغيلية'),
    ('5150', 'مصروفات مرتبطة بالمشتريات'),
    ('5100', 'رواتب وأجور'),
]


class OtherBalancesModule(QWidget):
    """Two items the accountant's balance-sheet message asked for that had
    nowhere to live: money borrowed (قروض) and money paid now for an expense
    that belongs to later months (مصروفات مقدمة). Both are occasional,
    setup-style entries rather than daily work, so they get one shared
    screen instead of their own place in the sidebar."""

    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.accounting = AccountingLogic(db_manager)
        self.selected_loan_id = None
        self.init_ui()

    def init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(12)

        root_layout.addWidget(page_header(
            "القروض والمصروفات المقدمة",
            "سجّل القروض وسدادها، والمصروفات المدفوعة مقدماً وتوزيعها على شهورها."))

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        root_layout.addWidget(tabs, 1)

        tabs.addTab(self.build_loans_tab(), "القروض")
        tabs.addTab(self.build_prepaid_tab(), "المصروفات المقدمة")

        self.load_loans()
        self.load_prepaid()

    # ---------------- Loans ----------------

    def build_loans_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)

        self.lender_input = QLineEdit()
        self.loan_amount_input = QLineEdit()
        self.loan_amount_input.setPlaceholderText("0.00")
        self.loan_method_input = QComboBox()
        self.loan_method_input.addItem("نقدي", "Cash")
        self.loan_method_input.addItem("تحويل بنكي", "Bank")
        self.loan_notes_input = QLineEdit()

        new_loan_box = QGroupBox("تسجيل قرض جديد")
        new_loan_outer = QVBoxLayout(new_loan_box)
        new_loan_btn = QPushButton("تسجيل القرض")
        new_loan_btn.setMinimumHeight(38)
        new_loan_btn.clicked.connect(self.record_new_loan)
        new_loan_outer.addWidget(compact_form([
            ("اسم المُقرض (بنك / فرد)", self.lender_input),
            ("المبلغ", self.loan_amount_input),
            ("طريقة الاستلام", self.loan_method_input),
            ("ملاحظات", self.loan_notes_input),
            (None, new_loan_btn),
        ], columns=3, field_min_width=150))
        layout.addWidget(pin_height(new_loan_box))

        loans_label = QLabel("القروض المسجّلة")
        loans_label.setStyleSheet("font-weight: 700; color: #334155;")
        layout.addWidget(loans_label)

        self.loans_table = QTableWidget()
        self.loans_table.setColumnCount(4)
        self.loans_table.setHorizontalHeaderLabels(["المُقرض", "التاريخ", "المبلغ الأصلي", "المتبقي"])
        self.loans_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.loans_table.verticalHeader().setVisible(False)
        self.loans_table.setAlternatingRowColors(True)
        self.loans_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.loans_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.loans_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.loans_table.setMinimumHeight(90)
        self.loans_table.itemSelectionChanged.connect(self.on_loan_selected)
        layout.addWidget(self.loans_table, 1)

        self.loan_payment_amount = QLineEdit()
        self.loan_payment_amount.setPlaceholderText("0.00")
        self.loan_payment_method = QComboBox()
        self.loan_payment_method.addItem("نقدي", "Cash")
        self.loan_payment_method.addItem("تحويل بنكي", "Bank")

        pay_loan_box = QGroupBox("تسجيل سداد للقرض المحدد أعلاه")
        pay_loan_outer = QVBoxLayout(pay_loan_box)
        pay_loan_btn = QPushButton("تسجيل السداد")
        pay_loan_btn.setMinimumHeight(38)
        pay_loan_btn.clicked.connect(self.record_loan_payment)
        pay_loan_outer.addWidget(compact_form([
            ("المبلغ", self.loan_payment_amount),
            ("طريقة السداد", self.loan_payment_method),
            (None, pay_loan_btn),
        ], columns=3, field_min_width=150))
        layout.addWidget(pin_height(pay_loan_box))

        return widget

    def record_new_loan(self):
        lender = self.lender_input.text().strip()
        if not lender:
            QMessageBox.warning(self, "تنبيه", "ادخل اسم المُقرض")
            return
        try:
            amount = parse_money(self.loan_amount_input.text(), "مبلغ القرض",
                                 allow_blank=False, allow_zero=False)
            if amount <= 0:
                raise ValueError
        except ValueError as exc:
            QMessageBox.warning(self, "تنبيه", str(exc))
            return

        method = self.loan_method_input.currentData()
        notes = self.loan_notes_input.text().strip()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cash_account = '1000' if method == 'Cash' else '1001'

        items = [
            {'account_code': cash_account, 'debit': amount, 'credit': 0},
            {'account_code': '2300', 'debit': 0, 'credit': amount},
        ]
        with self.db.transaction() as cursor:
            entry_id = self.db.insert_journal_entry(cursor, timestamp, f"قرض جديد - {lender}", None, items)
            cursor.execute(
                "INSERT INTO loans (lender_name, amount, date, notes, journal_entry_id) VALUES (?, ?, ?, ?, ?)",
                (lender, amount, timestamp, notes, entry_id),
            )

        QMessageBox.information(self, "نجاح", "تم تسجيل القرض")
        self.lender_input.clear()
        self.loan_amount_input.clear()
        self.loan_notes_input.clear()
        self.load_loans()

    def load_loans(self):
        loans = self.accounting.get_all_loans_with_balances()
        if not fill_table(self.loans_table, len(loans), "لا يوجد قروض مسجّلة"):
            return
        for row, loan in enumerate(loans):
            name_item = QTableWidgetItem(loan['lender_name'])
            self.loans_table.setItem(row, 0, name_item)
            self.loans_table.setItem(row, 1, QTableWidgetItem(str(loan['date'] or "")))
            self.loans_table.setItem(row, 2, money_item(loan['amount']))
            self.loans_table.setItem(row, 3, money_item(loan['balance'], bold=True))
            name_item.setData(Qt.ItemDataRole.UserRole, loan['id'])

    def on_loan_selected(self):
        rows = self.loans_table.selectionModel().selectedRows()
        if not rows:
            return
        self.selected_loan_id = self.loans_table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)

    def record_loan_payment(self):
        if not self.selected_loan_id:
            QMessageBox.warning(self, "تنبيه", "اختر قرضاً من الجدول أولاً")
            return
        try:
            amount = parse_money(self.loan_payment_amount.text(), "مبلغ السداد",
                                 allow_blank=False, allow_zero=False)
            if amount <= 0:
                raise ValueError
        except ValueError as exc:
            QMessageBox.warning(self, "تنبيه", str(exc))
            return

        outstanding = self.accounting.get_loan_statement(self.selected_loan_id)["balance"]
        if amount > outstanding + 0.01:
            answer = QMessageBox.question(
                self, "المبلغ أكبر من المتبقي",
                f"المتبقي من القرض {money(outstanding)} ريال فقط، وأنت تسجّل سداد {money(amount)} ريال.\n\n"
                "متابعة؟",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        method = self.loan_payment_method.currentData()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cash_account = '1000' if method == 'Cash' else '1001'

        items = [
            {'account_code': '2300', 'debit': amount, 'credit': 0},
            {'account_code': cash_account, 'debit': 0, 'credit': amount},
        ]
        with self.db.transaction() as cursor:
            entry_id = self.db.insert_journal_entry(cursor, timestamp, "سداد قرض", None, items)
            cursor.execute(
                "INSERT INTO loan_payments (loan_id, date, amount, method, journal_entry_id) VALUES (?, ?, ?, ?, ?)",
                (self.selected_loan_id, timestamp, amount, method, entry_id),
            )

        QMessageBox.information(self, "نجاح", "تم تسجيل سداد القرض")
        self.loan_payment_amount.clear()
        self.load_loans()

    # ---------------- Prepaid expenses ----------------

    def build_prepaid_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)

        self.prepaid_desc_input = QLineEdit()
        self.prepaid_desc_input.setPlaceholderText("مثال: إيجار سنة كاملة مقدماً")
        self.prepaid_amount_input = QLineEdit()
        self.prepaid_amount_input.setPlaceholderText("0.00")
        self.prepaid_method_input = QComboBox()
        self.prepaid_method_input.addItem("نقدي", "Cash")
        self.prepaid_method_input.addItem("تحويل بنكي", "Bank")
        self.prepaid_target_input = QComboBox()
        for code, label in PREPAID_TARGET_LABELS:
            self.prepaid_target_input.addItem(label, code)

        new_prepaid_box = QGroupBox("تسجيل مصروف مقدم جديد")
        new_prepaid_outer = QVBoxLayout(new_prepaid_box)
        new_prepaid_btn = QPushButton("تسجيل المصروف المقدم")
        new_prepaid_btn.setMinimumHeight(38)
        new_prepaid_btn.clicked.connect(self.record_new_prepaid)
        new_prepaid_outer.addWidget(compact_form([
            ("البيان", self.prepaid_desc_input),
            ("المبلغ المدفوع", self.prepaid_amount_input),
            ("طريقة الدفع", self.prepaid_method_input),
            ("نوع المصروف عند التوزيع", self.prepaid_target_input),
            (None, new_prepaid_btn),
        ], columns=3, field_min_width=160))
        layout.addWidget(pin_height(new_prepaid_box))

        prepaid_label = QLabel("المصروفات المقدمة المسجّلة")
        prepaid_label.setStyleSheet("font-weight: 700; color: #334155;")
        layout.addWidget(prepaid_label)

        self.prepaid_table = QTableWidget()
        self.prepaid_table.setColumnCount(5)
        self.prepaid_table.setHorizontalHeaderLabels(
            ["البيان", "التاريخ", "المبلغ الكلي", "تم توزيعه", "المتبقي"])
        self.prepaid_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.prepaid_table.verticalHeader().setVisible(False)
        self.prepaid_table.setAlternatingRowColors(True)
        self.prepaid_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.prepaid_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.prepaid_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.prepaid_table.setMinimumHeight(90)
        self.prepaid_table.itemSelectionChanged.connect(self.on_prepaid_selected)
        layout.addWidget(self.prepaid_table, 1)

        self.release_amount_input = QLineEdit()
        self.release_amount_input.setPlaceholderText("0.00")

        release_box = QGroupBox("توزيع جزء من المصروف المقدم المحدد أعلاه على الشهر الحالي")
        release_outer = QVBoxLayout(release_box)
        release_btn = QPushButton("توزيع هذا الشهر")
        release_btn.setMinimumHeight(38)
        release_btn.clicked.connect(self.release_prepaid)
        release_outer.addWidget(compact_form([
            ("المبلغ", self.release_amount_input),
            (None, release_btn),
        ], columns=2, field_min_width=150))
        layout.addWidget(pin_height(release_box))

        return widget

    def record_new_prepaid(self):
        description = self.prepaid_desc_input.text().strip()
        if not description:
            QMessageBox.warning(self, "تنبيه", "ادخل بيان المصروف")
            return
        try:
            amount = parse_money(self.prepaid_amount_input.text(), "المبلغ",
                                 allow_blank=False, allow_zero=False)
            if amount <= 0:
                raise ValueError
        except ValueError as exc:
            QMessageBox.warning(self, "تنبيه", str(exc))
            return

        method = self.prepaid_method_input.currentData()
        target_code = self.prepaid_target_input.currentData()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cash_account = '1000' if method == 'Cash' else '1001'

        items = [
            {'account_code': '1500', 'debit': amount, 'credit': 0},
            {'account_code': cash_account, 'debit': 0, 'credit': amount},
        ]
        with self.db.transaction() as cursor:
            entry_id = self.db.insert_journal_entry(cursor, timestamp, f"مصروف مقدم - {description}", None, items)
            cursor.execute(
                """INSERT INTO prepaid_expenses (description, amount, date, target_account_code, journal_entry_id)
                   VALUES (?, ?, ?, ?, ?)""",
                (description, amount, timestamp, target_code, entry_id),
            )

        QMessageBox.information(self, "نجاح", "تم تسجيل المصروف المقدم")
        self.prepaid_desc_input.clear()
        self.prepaid_amount_input.clear()
        self.load_prepaid()

    def load_prepaid(self):
        rows = self.accounting.get_prepaid_expenses_with_balances()
        if not fill_table(self.prepaid_table, len(rows), "لا يوجد مصروفات مقدمة مسجّلة"):
            return
        for row, r in enumerate(rows):
            desc_item = QTableWidgetItem(r['description'])
            self.prepaid_table.setItem(row, 0, desc_item)
            self.prepaid_table.setItem(row, 1, QTableWidgetItem(str(r['date'] or "")))
            self.prepaid_table.setItem(row, 2, money_item(r['amount']))
            self.prepaid_table.setItem(row, 3, money_item(r['released_amount']))
            self.prepaid_table.setItem(row, 4, money_item(r['remaining'], bold=True))
            desc_item.setData(Qt.ItemDataRole.UserRole, r['id'])

    def on_prepaid_selected(self):
        rows = self.prepaid_table.selectionModel().selectedRows()
        if not rows:
            self.selected_prepaid_id = None
            return
        self.selected_prepaid_id = self.prepaid_table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)

    def release_prepaid(self):
        prepaid_id = getattr(self, 'selected_prepaid_id', None)
        if not prepaid_id:
            QMessageBox.warning(self, "تنبيه", "اختر مصروفاً مقدماً من الجدول أولاً")
            return
        row = self.db.fetch_one("SELECT * FROM prepaid_expenses WHERE id = ?", (prepaid_id,))
        if not row:
            return
        try:
            amount = parse_money(self.release_amount_input.text(), "المبلغ",
                                 allow_blank=False, allow_zero=False)
            if amount <= 0:
                raise ValueError
        except ValueError as exc:
            QMessageBox.warning(self, "تنبيه", str(exc))
            return

        remaining = (row['amount'] or 0) - (row['released_amount'] or 0)
        if amount > remaining + 0.01:
            QMessageBox.warning(self, "تنبيه",
                                f"المتبقي من هذا المصروف {money(remaining)} ريال فقط، لا يمكن توزيع أكثر منه.")
            return

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        items = [
            {'account_code': row['target_account_code'], 'debit': amount, 'credit': 0},
            {'account_code': '1500', 'debit': 0, 'credit': amount},
        ]
        with self.db.transaction() as cursor:
            entry_id = self.db.insert_journal_entry(
                cursor, timestamp, f"توزيع مصروف مقدم - {row['description']}", None, items)
            cursor.execute(
                "INSERT INTO prepaid_expense_releases (prepaid_expense_id, date, amount, journal_entry_id) "
                "VALUES (?, ?, ?, ?)",
                (prepaid_id, timestamp, amount, entry_id),
            )
            cursor.execute(
                "UPDATE prepaid_expenses SET released_amount = COALESCE(released_amount, 0) + ? WHERE id = ?",
                (amount, prepaid_id),
            )

        QMessageBox.information(self, "نجاح", "تم توزيع المبلغ على المصروف")
        self.release_amount_input.clear()
        self.load_prepaid()

    def refresh_on_show(self):
        self.load_loans()
        self.load_prepaid()
