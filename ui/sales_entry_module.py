from datetime import datetime

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
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
)

from logic.accounting import AccountingLogic
from ui.formatting import money_item, money
from ui.common_widgets import (page_header, danger_button, fill_table, pin_height,
                              collapsible)

PAYMENT_CHANNELS = [
    ("Cash", "cash_input", "كاش"),
    ("POS", "network_input", "شبكة (مدى / فيزا)"),
    ("Transfer", "transfer_input", "تحويل بنكي"),
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

        form_box = QGroupBox("مبيعات اليوم")
        form_outer = QVBoxLayout(form_box)
        form_outer.setSpacing(10)

        self.branch_input = QComboBox()
        for branch in self.db.fetch_all("SELECT id, name FROM branches ORDER BY id"):
            self.branch_input.addItem(branch["name"], branch["id"])
        self.date_input = QDateEdit(QDate.currentDate())

        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        top_row.addWidget(self._field_label("الفرع"))
        top_row.addWidget(self.branch_input, 1)
        top_row.addSpacing(18)
        top_row.addWidget(self._field_label("التاريخ"))
        top_row.addWidget(self.date_input, 1)
        top_row.addStretch()
        form_outer.addLayout(top_row)

        # The three payment amounts sit side by side, like the end-of-day cash
        # sheet they are copied from - one glance shows all three at once and it
        # frees a lot of vertical space for the history table underneath.
        self.cash_input = self._amount_input()
        self.network_input = self._amount_input()
        self.transfer_input = self._amount_input()

        amounts_row = QHBoxLayout()
        amounts_row.setSpacing(14)
        for caption, field in (
            ("كاش", self.cash_input),
            ("شبكة (مدى / فيزا)", self.network_input),
            ("تحويل بنكي", self.transfer_input),
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
        for field in (self.cash_input, self.network_input, self.transfer_input):
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
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["التاريخ", "الفرع", "كاش", "شبكة", "تحويل بنكي", "الإجمالي", "الضريبة"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setMinimumHeight(120)
        layout.addWidget(self.table, 1)

        self.update_preview()
        self.load_history()

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
        for field in (self.cash_input, self.network_input, self.transfer_input):
            try:
                total += float(field.text().strip() or 0)
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
        value = float(text)
        if value < 0:
            raise ValueError("لا يمكن إدخال مبلغ سالب")
        return value

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
            }
        except ValueError as e:
            QMessageBox.warning(self, "تنبيه", str(e) if str(e) else "المبالغ المدخلة غير صحيحة")
            return

        if all(v <= 0 for v in channel_totals.values()):
            QMessageBox.warning(self, "تنبيه", "ادخل مبلغاً واحداً على الأقل")
            return

        branch_name = self.branch_input.currentText()

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

        entry_id = self.db.add_journal_entry(
            date_str, f"مبيعات يومية - {branch_name} - {date_str}", branch_id, journal_items
        )

        for method, total, vat in saved_methods:
            self.db.execute_query(
                """INSERT INTO sales (branch_id, date, total_amount, vat_amount, payment_method, journal_entry_id)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (branch_id, date_str, total, vat, method, entry_id),
            )

        QMessageBox.information(self, "تم", "تم تسجيل مبيعات اليوم وترحيلها للمحاسبة")
        self.cash_input.clear()
        self.network_input.clear()
        self.transfer_input.clear()
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
                SUM(s.total_amount) as grand_total,
                SUM(s.vat_amount) as vat_total
            FROM sales s
            JOIN branches b ON s.branch_id = b.id
            GROUP BY date(s.date), s.branch_id
            ORDER BY day DESC
        """
        rows = self.db.fetch_all(query)
        if not fill_table(self.table, len(rows), "لم تُسجَّل مبيعات بعد — اكتب مبالغ اليوم بالأعلى واضغط حفظ"):
            return
        for row, r in enumerate(rows):
            day_item = QTableWidgetItem(r["day"])
            day_item.setData(Qt.ItemDataRole.UserRole, r["branch_id"])
            self.table.setItem(row, 0, day_item)
            self.table.setItem(row, 1, QTableWidgetItem(r["branch_name"]))
            self.table.setItem(row, 2, money_item(r['cash_total'], bold=False))
            self.table.setItem(row, 3, money_item(r['pos_total'], bold=False))
            self.table.setItem(row, 4, money_item(r['transfer_total'], bold=False))
            self.table.setItem(row, 5, money_item(r['grand_total'], bold=True))
            self.table.setItem(row, 6, money_item(r['vat_total'], bold=False))

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
