from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QFormLayout,
    QLineEdit,
    QComboBox,
    QLabel,
    QHeaderView,
    QMessageBox,
    QTabWidget,
    QGroupBox,
)
from logic.accounting import AccountingLogic

CATEGORY_LABELS = {
    'raw_material': 'مواد خام',
    'purchase_expense': 'مصروفات مرتبطة بالمشتريات',
    'operating_expense': 'مصروفات تشغيلية',
}


class PurchaseModule(QWidget):
    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.accounting = AccountingLogic(db_manager)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        header = QLabel("إدارة المشتريات والمصروفات")
        header.setStyleSheet("font-size: 22px; font-weight: bold; color: #1f3b57; margin-bottom: 8px;")
        layout.addWidget(header)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        layout.addWidget(tabs, 1)

        tabs.addTab(self.build_purchase_tab(), "فاتورة مشتريات / مصروف")
        tabs.addTab(self.build_returns_tab(), "مرتجعات المشتريات")

    def build_purchase_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        form_layout = QFormLayout()
        self.branch_input = QComboBox()
        self.load_branches()

        self.category_input = QComboBox()
        for key, label in CATEGORY_LABELS.items():
            self.category_input.addItem(label, key)
        self.category_input.currentIndexChanged.connect(self.on_category_changed)

        self.supplier_input = QComboBox()
        self.load_suppliers()

        self.description_input = QLineEdit()
        self.description_input.setPlaceholderText("مثال: إيجار، كهرباء، شحن مشتريات ...")

        self.amount_input = QLineEdit()
        self.payment_status = QComboBox()
        self.payment_status.addItem("نقدي", "Cash")
        self.payment_status.addItem("آجل (على الحساب)", "Credit")

        form_layout.addRow("الفرع:", self.branch_input)
        form_layout.addRow("نوع المصروف:", self.category_input)
        form_layout.addRow("المورد:", self.supplier_input)
        form_layout.addRow("البيان:", self.description_input)
        form_layout.addRow("المبلغ (قبل الضريبة):", self.amount_input)
        form_layout.addRow("حالة الدفع:", self.payment_status)

        save_btn = QPushButton("تسجيل الفاتورة")
        save_btn.clicked.connect(self.save_purchase)
        form_layout.addRow(save_btn)

        layout.addLayout(form_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["التاريخ", "النوع", "المورد", "البيان", "المبلغ", "الضريبة", "الحالة"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        table_header = QHBoxLayout()
        table_label = QLabel("الفواتير المسجلة:")
        table_label.setStyleSheet("font-weight:700; color:#334155;")
        table_header.addWidget(table_label)
        table_header.addStretch()
        delete_btn = QPushButton("حذف الفاتورة المحددة")
        delete_btn.setStyleSheet(
            "QPushButton { background-color:#dc2626; border:1px solid #b91c1c; }"
            "QPushButton:hover { background-color:#b91c1c; border:1px solid #991b1b; }"
        )
        delete_btn.clicked.connect(self.delete_selected_purchase)
        table_header.addWidget(delete_btn)
        layout.addLayout(table_header)
        layout.addWidget(self.table, 1)

        self.on_category_changed()
        self.load_purchases()
        return widget

    def delete_selected_purchase(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "تنبيه", "اختر فاتورة من الجدول أولاً")
            return
        purchase_id, entry_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        description = self.table.item(row, 3).text() or self.table.item(row, 1).text()
        amount = self.table.item(row, 4).text()
        answer = QMessageBox.question(
            self, "حذف فاتورة",
            f"سيتم حذف الفاتورة «{description}» بمبلغ {amount} وقيدها المحاسبي نهائياً.\n\nمتابعة؟",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.db.execute_query("DELETE FROM purchases WHERE id = ?", (purchase_id,))
        self.db.delete_journal_entry(entry_id)
        QMessageBox.information(self, "تم", "تم حذف الفاتورة وقيدها المحاسبي")
        self.load_purchases()

    def build_returns_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        form_layout = QFormLayout()
        self.return_branch_input = QComboBox()
        for row in self.db.fetch_all("SELECT id, name FROM branches ORDER BY id"):
            self.return_branch_input.addItem(row['name'], row['id'])

        self.return_supplier_input = QComboBox()
        for s in self.db.fetch_all("SELECT id, name FROM suppliers ORDER BY name"):
            self.return_supplier_input.addItem(s['name'], s['id'])

        self.return_amount_input = QLineEdit()
        self.return_method_input = QComboBox()
        self.return_method_input.addItem("استرداد نقدي", "Cash")
        self.return_method_input.addItem("خصم من رصيد المورد (إشعار دائن)", "CreditNote")
        self.return_notes_input = QLineEdit()

        form_layout.addRow("الفرع:", self.return_branch_input)
        form_layout.addRow("المورد:", self.return_supplier_input)
        form_layout.addRow("المبلغ (قبل الضريبة):", self.return_amount_input)
        form_layout.addRow("طريقة الاسترداد:", self.return_method_input)
        form_layout.addRow("ملاحظات:", self.return_notes_input)

        save_return_btn = QPushButton("تسجيل مرتجع مشتريات")
        save_return_btn.clicked.connect(self.save_purchase_return)
        form_layout.addRow(save_return_btn)
        layout.addLayout(form_layout)

        self.returns_table = QTableWidget()
        self.returns_table.setColumnCount(5)
        self.returns_table.setHorizontalHeaderLabels(["التاريخ", "المورد", "المبلغ", "الضريبة", "طريقة الاسترداد"])
        self.returns_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.returns_table.verticalHeader().setVisible(False)
        self.returns_table.setAlternatingRowColors(True)
        self.returns_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.returns_table, 1)

        self.load_purchase_returns()
        return widget

    def refresh_on_show(self):
        selected_supplier = self.supplier_input.currentData()
        self.load_suppliers()
        if selected_supplier is not None:
            idx = self.supplier_input.findData(selected_supplier)
            if idx >= 0:
                self.supplier_input.setCurrentIndex(idx)

        selected_return_supplier = self.return_supplier_input.currentData()
        self.return_supplier_input.clear()
        for s in self.db.fetch_all("SELECT id, name FROM suppliers ORDER BY name"):
            self.return_supplier_input.addItem(s['name'], s['id'])
        if selected_return_supplier is not None:
            idx = self.return_supplier_input.findData(selected_return_supplier)
            if idx >= 0:
                self.return_supplier_input.setCurrentIndex(idx)

    def load_branches(self):
        self.branch_input.clear()
        for row in self.db.fetch_all("SELECT id, name FROM branches ORDER BY id"):
            self.branch_input.addItem(row['name'], row['id'])

    def load_suppliers(self):
        self.supplier_input.clear()
        self.supplier_input.addItem("بدون مورد (مصروف عام)", None)
        suppliers = self.db.fetch_all("SELECT * FROM suppliers ORDER BY name")
        for s in suppliers:
            self.supplier_input.addItem(s['name'], s['id'])

    def on_category_changed(self):
        is_operating = self.category_input.currentData() == 'operating_expense'
        # Operating expenses (rent, utilities...) are usually not tied to a specific supplier ledger.
        self.payment_status.setEnabled(True)
        self.supplier_input.setEnabled(True)

    def save_purchase(self):
        try:
            branch_id = self.branch_input.currentData()
            category = self.category_input.currentData()
            supplier_id = self.supplier_input.currentData()
            description = self.description_input.text().strip()
            amount_text = self.amount_input.text().strip()
            if not amount_text:
                raise ValueError("يرجى إدخال المبلغ قبل الضريبة")

            amount = float(amount_text)
            if amount <= 0:
                raise ValueError("يجب أن يكون المبلغ أكبر من صفر")

            status = self.payment_status.currentData()
            if status == 'Credit' and not supplier_id:
                raise ValueError("الشراء الآجل (Credit) يتطلب اختيار مورد")

            vat, total = self.accounting.calculate_vat(amount)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            account_credit = '1000' if status == 'Cash' else '2000'
            if category == 'raw_material':
                debit_account = '1100'
            elif category == 'purchase_expense':
                debit_account = '5150'
            else:
                debit_account = '5200'

            items = [
                {'account_code': debit_account, 'debit': amount, 'credit': 0},
                {'account_code': '1200', 'debit': vat, 'credit': 0},
                {'account_code': account_credit, 'debit': 0, 'credit': total},
            ]
            label = CATEGORY_LABELS.get(category, category)
            entry_id = self.db.add_journal_entry(
                timestamp, f"{label} - {description or status}", branch_id, items
            )

            self.db.execute_query(
                """INSERT INTO purchases
                   (branch_id, supplier_id, amount, total_amount, vat_amount, payment_status,
                    category, description, date, journal_entry_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (branch_id, supplier_id, amount, total, vat, status, category,
                 description, timestamp, entry_id),
            )

            QMessageBox.information(self, "نجاح", "تم تسجيل الفاتورة بنجاح")
            self.amount_input.clear()
            self.description_input.clear()
            self.load_purchases()
        except Exception as e:
            QMessageBox.critical(self, "خطأ", str(e))

    def load_purchases(self):
        query = """
            SELECT p.*, s.name as supplier_name
            FROM purchases p
            LEFT JOIN suppliers s ON p.supplier_id = s.id
            -- id breaks ties: rows saved in the same second would otherwise
            -- come back in an arbitrary order, and the user could delete
            -- a different invoice from the one highlighted in the table.
            ORDER BY p.date DESC, p.id DESC
        """
        purchases = self.db.fetch_all(query)
        self.table.setRowCount(len(purchases))
        for row, p in enumerate(purchases):
            date_item = QTableWidgetItem(str(p['date']))
            date_item.setData(Qt.ItemDataRole.UserRole, (p['id'], p['journal_entry_id']))
            self.table.setItem(row, 0, date_item)
            self.table.setItem(row, 1, QTableWidgetItem(CATEGORY_LABELS.get(p['category'] or 'raw_material', p['category'] or "")))
            self.table.setItem(row, 2, QTableWidgetItem(p['supplier_name'] or "مصروف عام"))
            self.table.setItem(row, 3, QTableWidgetItem(p['description'] or ""))
            self.table.setItem(row, 4, QTableWidgetItem(f"{p['total_amount']:.2f}"))
            self.table.setItem(row, 5, QTableWidgetItem(f"{p['vat_amount']:.2f}"))
            self.table.setItem(row, 6, QTableWidgetItem(p['payment_status']))

    def save_purchase_return(self):
        try:
            branch_id = self.return_branch_input.currentData()
            supplier_id = self.return_supplier_input.currentData()
            amount_text = self.return_amount_input.text().strip()
            if not amount_text:
                raise ValueError("يرجى إدخال مبلغ المرتجع")
            amount = float(amount_text)
            if amount <= 0:
                raise ValueError("يجب أن يكون المبلغ أكبر من صفر")

            refund_method = self.return_method_input.currentData()
            notes = self.return_notes_input.text().strip()
            vat, total = self.accounting.calculate_vat(amount)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            self.db.execute_query(
                """INSERT INTO purchase_returns (branch_id, supplier_id, date, amount, vat_amount, refund_method, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (branch_id, supplier_id, timestamp, amount, vat, refund_method, notes),
            )

            credit_account = '1000' if refund_method == 'Cash' else '2000'
            items = [
                {'account_code': credit_account, 'debit': total, 'credit': 0},
                {'account_code': '1100', 'debit': 0, 'credit': amount},
                {'account_code': '1200', 'debit': 0, 'credit': vat},
            ]
            self.db.add_journal_entry(timestamp, f"مرتجع مشتريات - {notes or ''}", branch_id, items)

            QMessageBox.information(self, "نجاح", "تم تسجيل مرتجع المشتريات")
            self.return_amount_input.clear()
            self.return_notes_input.clear()
            self.load_purchase_returns()
            self.load_purchases()
        except Exception as e:
            QMessageBox.critical(self, "خطأ", str(e))

    def load_purchase_returns(self):
        query = """
            SELECT pr.*, s.name as supplier_name
            FROM purchase_returns pr
            LEFT JOIN suppliers s ON pr.supplier_id = s.id
            ORDER BY pr.date DESC, pr.id DESC
        """
        rows = self.db.fetch_all(query)
        self.returns_table.setRowCount(len(rows))
        for row, r in enumerate(rows):
            self.returns_table.setItem(row, 0, QTableWidgetItem(str(r['date'])))
            self.returns_table.setItem(row, 1, QTableWidgetItem(r['supplier_name'] or ""))
            self.returns_table.setItem(row, 2, QTableWidgetItem(f"{r['amount']:.2f}"))
            self.returns_table.setItem(row, 3, QTableWidgetItem(f"{r['vat_amount']:.2f}"))
            method_label = "استرداد نقدي" if r['refund_method'] == 'Cash' else "إشعار دائن"
            self.returns_table.setItem(row, 4, QTableWidgetItem(method_label))
