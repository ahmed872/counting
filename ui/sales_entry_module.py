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

        header = QLabel("تسجيل المبيعات اليومية")
        header.setStyleSheet("font-size: 22px; font-weight: 800; color: #1f3b57;")
        layout.addWidget(header)

        subtitle = QLabel("اكتب مبيعات اليوم شاملة الضريبة، والباقي يحسبه البرنامج لوحده.")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #64748b;")
        layout.addWidget(subtitle)

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

        layout.addWidget(form_box)

        history_label = QLabel("سجل المبيعات اليومية (حسب الفرع):")
        history_label.setStyleSheet("font-size: 15px; font-weight: 700; color: #334155;")
        layout.addWidget(history_label)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["التاريخ", "الفرع", "كاش", "شبكة", "تحويل بنكي", "الإجمالي", "الضريبة"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setMinimumHeight(240)
        layout.addWidget(self.table, 1)

        self.update_preview()
        self.load_history()

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

    def save_daily_sales(self):
        try:
            branch_id = self.branch_input.currentData()
            date_str = self.date_input.date().toString("yyyy-MM-dd")
            timestamp = f"{date_str} {datetime.now().strftime('%H:%M:%S')}"

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

        cash_debit = 0.0
        bank_debit = 0.0
        revenue_credit = 0.0
        vat_credit = 0.0

        for method, total in channel_totals.items():
            if total <= 0:
                continue
            amount, vat = self.accounting.reverse_vat(total)
            self.db.execute_query(
                "INSERT INTO sales (branch_id, date, total_amount, vat_amount, payment_method) VALUES (?, ?, ?, ?, ?)",
                (branch_id, timestamp, total, vat, method),
            )
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

        branch_name = self.branch_input.currentText()
        self.db.add_journal_entry(timestamp, f"مبيعات يومية - {branch_name} - {date_str}", branch_id, journal_items)

        QMessageBox.information(self, "تم", "تم تسجيل مبيعات اليوم وترحيلها للمحاسبة")
        self.cash_input.clear()
        self.network_input.clear()
        self.transfer_input.clear()
        self.load_history()

    def load_history(self):
        query = """
            SELECT
                date(s.date) as day,
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
        self.table.setRowCount(len(rows))
        for row, r in enumerate(rows):
            self.table.setItem(row, 0, QTableWidgetItem(r["day"]))
            self.table.setItem(row, 1, QTableWidgetItem(r["branch_name"]))
            self.table.setItem(row, 2, QTableWidgetItem(f"{r['cash_total']:.2f}"))
            self.table.setItem(row, 3, QTableWidgetItem(f"{r['pos_total']:.2f}"))
            self.table.setItem(row, 4, QTableWidgetItem(f"{r['transfer_total']:.2f}"))
            self.table.setItem(row, 5, QTableWidgetItem(f"{r['grand_total']:.2f}"))
            self.table.setItem(row, 6, QTableWidgetItem(f"{r['vat_total']:.2f}"))

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
