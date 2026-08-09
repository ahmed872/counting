
from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QComboBox,
    QDateEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QTabWidget,
)

from logic.accounting import AccountingLogic
from ui.formatting import money_item
from ui.common_widgets import (page_header, danger_button, fill_table, pin_height,
                              collapsible, fit_table_height)
from logic.money import parse_money

REFUND_METHOD_LABELS = [
    ("Cash", "نقدي"),
    ("POS", "شبكة (مدى / فيزا)"),
    ("Transfer", "تحويل بنكي"),
    ("Delivery", "تطبيقات التوصيل"),
]

PAYMENT_CHANNELS = [
    ("Cash", "cash_input", "كاش"),
    ("POS", "network_input", "شبكة (مدى / فيزا)"),
    ("Transfer", "transfer_input", "تحويل بنكي"),
    ("Delivery", "delivery_input", "تطبيقات التوصيل"),
]


class SalesEntryModule(QWidget):
    """Simple end-of-day sales entry: how much came in as cash / network / transfer.
    No item-level ordering - the totals are entered once and posted automatically."""

    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.accounting = AccountingLogic(db_manager)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        layout.addWidget(page_header(
            "المبيعات اليومية",
            "اكتب مبيعات اليوم شاملة الضريبة، والباقي يحسبه البرنامج لوحده."))

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        layout.addWidget(tabs, 1)

        tabs.addTab(self.build_sales_tab(), "المبيعات اليومية")
        tabs.addTab(self.build_returns_tab(), "مرتجعات المبيعات")

    def build_sales_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)

        form_box = QGroupBox("مبيعات اليوم")
        form_outer = QVBoxLayout(form_box)
        form_outer.setSpacing(10)

        self.branch_input = QComboBox()
        for branch in self.db.fetch_all("SELECT id, name FROM branches ORDER BY id"):
            self.branch_input.addItem(branch["name"], branch["id"])
        self.date_input = QDateEdit(QDate.currentDate())
        # A sale cannot happen on a day that has not arrived yet - without
        # this, a mis-set system clock or a stray click on the calendar
        # silently posted revenue and VAT into a future month's figures.
        self.date_input.setMaximumDate(QDate.currentDate())
        # Reference only, for matching this entry against the physical
        # register's Z-report - it does not change the accounting. The day is
        # still one total, one journal entry, regardless of how many
        # registers fed into it.
        self.cashier_input = QLineEdit()
        self.cashier_input.setPlaceholderText("اختياري")

        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        top_row.addWidget(self._field_label("الفرع"))
        top_row.addWidget(self.branch_input, 1)
        top_row.addSpacing(18)
        top_row.addWidget(self._field_label("التاريخ"))
        top_row.addWidget(self.date_input, 1)
        top_row.addSpacing(18)
        top_row.addWidget(self._field_label("رقم الكاشير / الجهاز"))
        top_row.addWidget(self.cashier_input, 1)
        top_row.addStretch()
        form_outer.addLayout(top_row)

        # The payment amounts sit side by side, like the end-of-day cash sheet
        # they are copied from - one glance shows all of them at once and it
        # frees a lot of vertical space for the history table underneath.
        self.cash_input = self._amount_input()
        self.network_input = self._amount_input()
        self.transfer_input = self._amount_input()
        # Delivery apps (هنقرستيشن / جاهز وغيرها) collect the money from the
        # customer themselves and settle it to the bank later, minus their
        # own commission - money never passes through the register as cash,
        # so it is entered and booked the same way a bank transfer is, just
        # tracked under its own label so the owner can see how much of his
        # revenue comes through delivery apps versus a direct transfer.
        self.delivery_input = self._amount_input()

        amounts_row = QHBoxLayout()
        amounts_row.setSpacing(14)
        for caption, field in (
            ("كاش", self.cash_input),
            ("شبكة (مدى / فيزا)", self.network_input),
            ("تحويل بنكي", self.transfer_input),
            ("تطبيقات التوصيل", self.delivery_input),
        ):
            column = QVBoxLayout()
            column.setSpacing(4)
            column.addWidget(self._field_label(caption))
            column.addWidget(field)
            wrapper = QWidget()
            wrapper.setLayout(column)
            amounts_row.addWidget(wrapper, 1)
        form_outer.addLayout(amounts_row)

        hint = QLabel("المبالغ المدخلة شاملة ضريبة القيمة المضافة (15%)")
        hint.setStyleSheet("color:#94a3b8; font-size:12px;")
        form_outer.addWidget(hint)

        # Live preview so the user can sanity-check before saving.
        self.preview_label = QLabel()
        self.preview_label.setStyleSheet(
            "background:#eef6ff; border:1px solid #cfe0f5; border-radius:10px;"
            "padding:10px; font-weight:800; color:#1f3b57;"
        )
        form_outer.addWidget(self.preview_label)
        for field in (self.cash_input, self.network_input, self.transfer_input, self.delivery_input):
            field.textChanged.connect(self.update_preview)

        save_btn = QPushButton("حفظ مبيعات اليوم")
        save_btn.setMinimumHeight(46)
        save_btn.clicked.connect(self.save_daily_sales)
        form_outer.addWidget(save_btn)

        layout.addWidget(pin_height(form_box))

        history_row = QHBoxLayout()
        history_label = QLabel("سجل المبيعات اليومية (حسب الفرع):")
        history_label.setStyleSheet("font-size: 15px; font-weight: 700; color: #334155;")
        history_row.addWidget(history_label)
        history_row.addStretch()
        history_row.addWidget(collapsible(
            form_box, "إظهار نموذج التسجيل", "إخفاء النموذج",
            start_collapsed=self._short_screen()))
        delete_btn = danger_button("حذف اليوم المحدد")
        delete_btn.clicked.connect(self.delete_selected_day)
        history_row.addWidget(delete_btn)
        layout.addLayout(history_row)

        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels(
            ["التاريخ", "الفرع", "كاش", "شبكة", "تحويل بنكي", "تطبيقات التوصيل",
             "الإجمالي", "الضريبة", "رقم الكاشير"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setMinimumHeight(90)
        layout.addWidget(self.table, 1)

        self.update_preview()
        self.load_history()
        return widget

    def build_returns_tab(self):
        """A customer refund. sales_returns already existed in the schema and
        every report already reads from it - net_sales and output VAT both
        subtract it - but nothing ever wrote a row into it, so it sat
        permanently at zero. The only way to record a refund was to reopen
        and retype the whole day's total in the sales tab, which conflates a
        genuine refund with correcting a typo and leaves no record of why the
        number changed."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)

        self.return_branch_input = QComboBox()
        for branch in self.db.fetch_all("SELECT id, name FROM branches ORDER BY id"):
            self.return_branch_input.addItem(branch["name"], branch["id"])
        self.return_date_input = QDateEdit(QDate.currentDate())
        self.return_date_input.setMaximumDate(QDate.currentDate())
        self.return_amount_input = self._amount_input()
        self.return_method_input = QComboBox()
        for code, label in REFUND_METHOD_LABELS:
            self.return_method_input.addItem(label, code)
        self.return_notes_input = QLineEdit()
        self.return_notes_input.setPlaceholderText("سبب المرتجع (اختياري)")

        form_box = QGroupBox("مرتجع مبيعات جديد")
        form_outer = QVBoxLayout(form_box)
        form_outer.setSpacing(10)

        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        top_row.addWidget(self._field_label("الفرع"))
        top_row.addWidget(self.return_branch_input, 1)
        top_row.addSpacing(18)
        top_row.addWidget(self._field_label("التاريخ"))
        top_row.addWidget(self.return_date_input, 1)
        form_outer.addLayout(top_row)

        amount_row = QHBoxLayout()
        amount_row.setSpacing(10)
        amount_row.addWidget(self._field_label("المبلغ المسترد (شامل الضريبة)"))
        amount_row.addWidget(self.return_amount_input, 1)
        amount_row.addSpacing(18)
        amount_row.addWidget(self._field_label("طريقة الاسترداد"))
        amount_row.addWidget(self.return_method_input, 1)
        form_outer.addLayout(amount_row)

        notes_row = QHBoxLayout()
        notes_row.setSpacing(10)
        notes_row.addWidget(self._field_label("ملاحظات"))
        notes_row.addWidget(self.return_notes_input, 1)
        form_outer.addLayout(notes_row)

        save_return_btn = QPushButton("تسجيل مرتجع المبيعات")
        save_return_btn.setMinimumHeight(44)
        save_return_btn.clicked.connect(self.save_sales_return)
        form_outer.addWidget(save_return_btn)

        layout.addWidget(pin_height(form_box))

        returns_header = QHBoxLayout()
        returns_label = QLabel("المرتجعات المسجلة:")
        returns_label.setStyleSheet("font-size: 15px; font-weight: 700; color: #334155;")
        returns_header.addWidget(returns_label)
        returns_header.addStretch()
        delete_return_btn = danger_button("حذف المرتجع المحدد")
        delete_return_btn.clicked.connect(self.delete_selected_return)
        returns_header.addWidget(delete_return_btn)
        layout.addLayout(returns_header)

        self.returns_table = QTableWidget()
        self.returns_table.setColumnCount(6)
        self.returns_table.setHorizontalHeaderLabels(
            ["التاريخ", "الفرع", "المبلغ", "الضريبة", "طريقة الاسترداد", "ملاحظات"])
        self.returns_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.returns_table.verticalHeader().setVisible(False)
        self.returns_table.setAlternatingRowColors(True)
        self.returns_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.returns_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.returns_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.returns_table.setMinimumHeight(90)
        layout.addWidget(self.returns_table, 1)

        self.load_sales_returns()
        return widget

    def save_sales_return(self):
        try:
            branch_id = self.return_branch_input.currentData()
            total = parse_money(self.return_amount_input.text(), "المبلغ المسترد",
                                allow_blank=False, allow_zero=False)
        except ValueError as exc:
            QMessageBox.warning(self, "تنبيه", str(exc))
            return

        method = self.return_method_input.currentData()
        notes = self.return_notes_input.text().strip()
        date_str = self.return_date_input.date().toString("yyyy-MM-dd")
        # The refunded total is what the customer was actually handed back,
        # tax included - the same way the original sale itself is entered -
        # so it is split the same way rather than asking for a pre-tax figure
        # nobody reads off a receipt.
        net, vat = self.accounting.reverse_vat(total)

        # Mirrors the sale's own journal entry in reverse: that one credited
        # revenue and output VAT and debited cash/bank; a return debits
        # revenue and output VAT back down and credits the cash/bank that
        # actually paid the customer back.
        cash_account = "1000" if method == "Cash" else "1001"
        items = [
            {"account_code": "4000", "debit": net, "credit": 0},
            {"account_code": "2100", "debit": vat, "credit": 0},
            {"account_code": cash_account, "debit": 0, "credit": total},
        ]

        with self.db.transaction() as cursor:
            entry_id = self.db.insert_journal_entry(
                cursor, date_str, f"مرتجع مبيعات - {notes or ''}", branch_id, items)
            cursor.execute(
                """INSERT INTO sales_returns
                   (branch_id, date, amount, vat_amount, refund_method, notes, journal_entry_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (branch_id, date_str, net, vat, method, notes, entry_id),
            )

        QMessageBox.information(self, "تم", "تم تسجيل مرتجع المبيعات")
        self.return_amount_input.clear()
        self.return_notes_input.clear()
        self.load_sales_returns()

    def delete_selected_return(self):
        row = self.returns_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "تنبيه", "اختر مرتجعاً من الجدول أولاً")
            return
        return_id, entry_id = self.returns_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        answer = QMessageBox.question(
            self, "حذف مرتجع",
            "سيتم حذف هذا المرتجع وقيده المحاسبي نهائياً.\n\nمتابعة؟",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.db.execute_query("DELETE FROM sales_returns WHERE id = ?", (return_id,))
        if entry_id:
            self.db.delete_journal_entry(entry_id)
        QMessageBox.information(self, "تم", "تم حذف المرتجع وقيده المحاسبي")
        self.load_sales_returns()

    def load_sales_returns(self):
        rows = self.db.fetch_all("""
            SELECT sr.id, sr.date, b.name as branch_name, sr.amount, sr.vat_amount,
                   sr.refund_method, sr.notes, sr.journal_entry_id
            FROM sales_returns sr
            JOIN branches b ON sr.branch_id = b.id
            ORDER BY sr.date DESC, sr.id DESC
        """)
        if not fill_table(self.returns_table, len(rows), "لا يوجد مرتجعات مبيعات مسجلة"):
            fit_table_height(self.returns_table)
            return
        method_labels = dict(REFUND_METHOD_LABELS)
        for row, r in enumerate(rows):
            date_item = QTableWidgetItem(r["date"])
            date_item.setData(Qt.ItemDataRole.UserRole, (r["id"], r["journal_entry_id"]))
            self.returns_table.setItem(row, 0, date_item)
            self.returns_table.setItem(row, 1, QTableWidgetItem(r["branch_name"]))
            self.returns_table.setItem(row, 2, money_item(r["amount"], bold=True))
            self.returns_table.setItem(row, 3, money_item(r["vat_amount"]))
            self.returns_table.setItem(row, 4, QTableWidgetItem(method_labels.get(r["refund_method"], r["refund_method"])))
            self.returns_table.setItem(row, 5, QTableWidgetItem(r["notes"] or ""))
        fit_table_height(self.returns_table)

    def _short_screen(self):
        screen = self.screen() or (self.window().screen() if self.window() else None)
        return bool(screen and screen.availableGeometry().height() < 800)

    def _field_label(self, text):
        label = QLabel(text)
        label.setStyleSheet("font-weight:700; color:#334155;")
        return label

    def _amount_input(self):
        field = QLineEdit()
        field.setPlaceholderText("0.00")
        field.setMinimumHeight(40)
        field.setAlignment(Qt.AlignmentFlag.AlignCenter)
        field.setStyleSheet("font-size:17px; font-weight:700;")
        return field

    def update_preview(self):
        total = 0.0
        for field in (self.cash_input, self.network_input, self.transfer_input, self.delivery_input):
            try:
                total += parse_money(field.text())
            except ValueError:
                pass
        net, vat = self.accounting.reverse_vat(total) if total else (0.0, 0.0)
        self.preview_label.setText(
            f"إجمالي اليوم: {total:,.2f} ريال     |     قبل الضريبة: {net:,.2f}     |     الضريبة: {vat:,.2f}"
        )

    def _parse_amount(self, line_edit):
        text = line_edit.text().strip()
        if not text:
            return 0.0
        return parse_money(text, label=line_edit.property("moneyLabel") or "المبلغ")

    def existing_day(self, branch_id, date_str):
        return self.db.fetch_all(
            "SELECT id, journal_entry_id FROM sales WHERE branch_id = ? AND date = ?",
            (branch_id, date_str),
        )

    def clear_day(self, branch_id, date_str):
        """Removes a day's sales rows together with the journal entry they
        produced, so replacing a day cannot leave a stale entry in the ledger."""
        rows = self.existing_day(branch_id, date_str)
        entry_ids = {r["journal_entry_id"] for r in rows if r["journal_entry_id"]}
        self.db.execute_query(
            "DELETE FROM sales WHERE branch_id = ? AND date = ?", (branch_id, date_str)
        )
        for entry_id in entry_ids:
            self.db.delete_journal_entry(entry_id)

    def save_daily_sales(self):
        try:
            branch_id = self.branch_input.currentData()
            date_str = self.date_input.date().toString("yyyy-MM-dd")

            channel_totals = {
                "Cash": self._parse_amount(self.cash_input),
                "POS": self._parse_amount(self.network_input),
                "Transfer": self._parse_amount(self.transfer_input),
                "Delivery": self._parse_amount(self.delivery_input),
            }
        except ValueError as e:
            QMessageBox.warning(self, "تنبيه", str(e) if str(e) else "المبالغ المدخلة غير صحيحة")
            return

        if all(v <= 0 for v in channel_totals.values()):
            QMessageBox.warning(self, "تنبيه", "ادخل مبلغاً واحداً على الأقل")
            return

        branch_name = self.branch_input.currentText()
        cashier_number = self.cashier_input.text().strip() or None

        # Saving the same day twice used to double that day's revenue and VAT.
        # Now it asks, and replaces the day rather than adding to it.
        if self.existing_day(branch_id, date_str):
            answer = QMessageBox.question(
                self,
                "هذا اليوم مسجل من قبل",
                f"يوجد تسجيل مبيعات بالفعل ليوم {date_str} - {branch_name}.\n\n"
                "هل تريد استبداله بالمبالغ الجديدة؟",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            self.clear_day(branch_id, date_str)

        cash_debit = 0.0
        bank_debit = 0.0
        revenue_credit = 0.0
        vat_credit = 0.0
        saved_methods = []

        for method, total in channel_totals.items():
            if total <= 0:
                continue
            amount, vat = self.accounting.reverse_vat(total)
            saved_methods.append((method, total, vat))
            revenue_credit += amount
            vat_credit += vat
            if method == "Cash":
                cash_debit += total
            else:
                bank_debit += total

        journal_items = []
        if cash_debit:
            journal_items.append({"account_code": "1000", "debit": cash_debit, "credit": 0})
        if bank_debit:
            journal_items.append({"account_code": "1001", "debit": bank_debit, "credit": 0})
        journal_items.append({"account_code": "4000", "debit": 0, "credit": revenue_credit})
        journal_items.append({"account_code": "2100", "debit": 0, "credit": vat_credit})

        # One transaction: a crash between posting the journal entry and
        # writing the sales rows used to be able to leave the day's revenue
        # in the accounts with no sales record behind it to explain it.
        with self.db.transaction() as cursor:
            entry_id = self.db.insert_journal_entry(
                cursor, date_str, f"مبيعات يومية - {branch_name} - {date_str}", branch_id, journal_items)
            for method, total, vat in saved_methods:
                cursor.execute(
                    """INSERT INTO sales
                       (branch_id, date, total_amount, vat_amount, payment_method, journal_entry_id, cashier_number)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (branch_id, date_str, total, vat, method, entry_id, cashier_number),
                )

        QMessageBox.information(self, "تم", "تم تسجيل مبيعات اليوم وترحيلها للمحاسبة")
        self.cash_input.clear()
        self.network_input.clear()
        self.transfer_input.clear()
        self.delivery_input.clear()
        self.update_preview()
        self.load_history()

    def delete_selected_day(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "تنبيه", "اختر يوماً من الجدول أولاً")
            return
        day = self.table.item(row, 0).text()
        branch_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        branch_name = self.table.item(row, 1).text()
        answer = QMessageBox.question(
            self, "حذف مبيعات يوم",
            f"سيتم حذف مبيعات يوم {day} - {branch_name} وقيدها المحاسبي نهائياً.\nمتابعة؟",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.clear_day(branch_id, day)
        QMessageBox.information(self, "تم", "تم حذف مبيعات اليوم وقيدها المحاسبي")
        self.load_history()

    def load_history(self):
        query = """
            SELECT
                date(s.date) as day,
                s.branch_id as branch_id,
                b.name as branch_name,
                SUM(CASE WHEN s.payment_method = 'Cash' THEN s.total_amount ELSE 0 END) as cash_total,
                SUM(CASE WHEN s.payment_method = 'POS' THEN s.total_amount ELSE 0 END) as pos_total,
                SUM(CASE WHEN s.payment_method = 'Transfer' THEN s.total_amount ELSE 0 END) as transfer_total,
                SUM(CASE WHEN s.payment_method = 'Delivery' THEN s.total_amount ELSE 0 END) as delivery_total,
                SUM(s.total_amount) as grand_total,
                SUM(s.vat_amount) as vat_total,
                MAX(s.cashier_number) as cashier_number
            FROM sales s
            JOIN branches b ON s.branch_id = b.id
            GROUP BY date(s.date), s.branch_id
            ORDER BY day DESC
        """
        rows = self.db.fetch_all(query)
        if not fill_table(self.table, len(rows), "لم تُسجَّل مبيعات بعد — اكتب مبالغ اليوم بالأعلى واضغط حفظ"):
            fit_table_height(self.table)
            return
        for row, r in enumerate(rows):
            day_item = QTableWidgetItem(r["day"])
            day_item.setData(Qt.ItemDataRole.UserRole, r["branch_id"])
            self.table.setItem(row, 0, day_item)
            self.table.setItem(row, 1, QTableWidgetItem(r["branch_name"]))
            self.table.setItem(row, 2, money_item(r['cash_total'], bold=False))
            self.table.setItem(row, 3, money_item(r['pos_total'], bold=False))
            self.table.setItem(row, 4, money_item(r['transfer_total'], bold=False))
            self.table.setItem(row, 5, money_item(r['delivery_total'], bold=False))
            self.table.setItem(row, 6, money_item(r['grand_total'], bold=True))
            self.table.setItem(row, 7, money_item(r['vat_total'], bold=False))
            self.table.setItem(row, 8, QTableWidgetItem(r['cashier_number'] or ""))
        fit_table_height(self.table)

    def refresh_on_show(self):
        selected_branch = self.branch_input.currentData()
        self.branch_input.clear()
        for branch in self.db.fetch_all("SELECT id, name FROM branches ORDER BY id"):
            self.branch_input.addItem(branch["name"], branch["id"])
        if selected_branch is not None:
            idx = self.branch_input.findData(selected_branch)
            if idx >= 0:
                self.branch_input.setCurrentIndex(idx)
        self.load_history()
