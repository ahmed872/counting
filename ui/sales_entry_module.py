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
        layout.setSpacing(14)

        header = QLabel("تسجيل المبيعات اليومية")
        header.setStyleSheet("font-size: 24px; font-weight: 800; color: #1f3b57;")
        layout.addWidget(header)

        subtitle = QLabel(
            "أدخل إجمالي التحصيل اليومي شامل الضريبة لكل طريقة دفع، وسيتم احتساب الضريبة "
            "والترحيل المحاسبي (القيد المزدوج) تلقائياً بدون الحاجة لتسجيل كل طلب على حدة."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #64748b;")
        layout.addWidget(subtitle)

        form_box = QGroupBox("مبيعات اليوم")
        form_layout = QFormLayout(form_box)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form_layout.setSpacing(12)

        self.branch_input = QComboBox()
        for branch in self.db.fetch_all("SELECT id, name FROM branches ORDER BY id"):
            self.branch_input.addItem(branch["name"], branch["id"])

        self.date_input = QDateEdit(QDate.currentDate())
        self.date_input.setCalendarPopup(True)

        self.cash_input = QLineEdit()
        self.cash_input.setPlaceholderText("0.00")
        self.network_input = QLineEdit()
        self.network_input.setPlaceholderText("0.00")
        self.transfer_input = QLineEdit()
        self.transfer_input.setPlaceholderText("0.00")

        for field in (self.branch_input, self.date_input, self.cash_input, self.network_input, self.transfer_input):
            field.setMinimumHeight(38)
            field.setMinimumWidth(220)

        form_layout.addRow("الفرع:", self.branch_input)
        form_layout.addRow("التاريخ:", self.date_input)
        form_layout.addRow("كاش (شامل الضريبة):", self.cash_input)
        form_layout.addRow("شبكة - مدى/فيزا (شامل الضريبة):", self.network_input)
        form_layout.addRow("تحويل بنكي (شامل الضريبة):", self.transfer_input)

        save_btn = QPushButton("تسجيل مبيعات اليوم")
        save_btn.setMinimumHeight(44)
        save_btn.clicked.connect(self.save_daily_sales)
        form_layout.addRow(save_btn)

        layout.addWidget(form_box)

        history_label = QLabel("سجل المبيعات اليومية (حسب الفرع):")
        history_label.setStyleSheet("font-size: 15px; font-weight: 600; color: #334155;")
        layout.addWidget(history_label)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["التاريخ", "الفرع", "كاش", "شبكة", "تحويل بنكي", "الإجمالي", "الضريبة"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table, 1)

        self.load_history()

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
