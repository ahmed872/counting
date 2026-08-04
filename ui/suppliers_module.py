from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QScrollArea,
)

from logic.accounting import AccountingLogic
from ui.formatting import money_item, money
from ui.common_widgets import page_header, fill_table


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

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll_widget = QWidget()
        layout = QVBoxLayout(scroll_widget)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(14)

        form_box = QGroupBox("إضافة مورد جديد")
        form_layout = QFormLayout(form_box)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form_layout.setSpacing(12)
        self.name_input = QLineEdit()
        self.tax_id_input = QLineEdit()
        self.phone_input = QLineEdit()
        self.opening_balance_input = QLineEdit()
        self.opening_balance_input.setPlaceholderText("0.00")
        form_layout.addRow("اسم المورد:", self.name_input)
        form_layout.addRow("الرقم الضريبي:", self.tax_id_input)
        form_layout.addRow("رقم الجوال:", self.phone_input)
        form_layout.addRow("الرصيد الافتتاحي (دائن للمورد):", self.opening_balance_input)
        add_btn = QPushButton("حفظ المورد")
        add_btn.clicked.connect(self.add_supplier)
        add_btn.setMinimumHeight(42)
        form_layout.addRow(add_btn)
        layout.addWidget(form_box)

        list_label = QLabel("قائمة الموردين والأرصدة الحالية")
        list_label.setStyleSheet("font-weight: 700; color: #334155; margin-top: 6px;")
        layout.addWidget(list_label)

        self.suppliers_table = QTableWidget()
        self.suppliers_table.setColumnCount(4)
        self.suppliers_table.setHorizontalHeaderLabels(["المورد", "الجوال", "الرصيد الحالي", "الحالة"])
        self.suppliers_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.suppliers_table.verticalHeader().setVisible(False)
        self.suppliers_table.setAlternatingRowColors(True)
        self.suppliers_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.suppliers_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.suppliers_table.setMinimumHeight(160)
        self.suppliers_table.itemSelectionChanged.connect(self.on_supplier_selected)
        layout.addWidget(self.suppliers_table)

        total_box = QLabel("إجمالي أرصدة الموردين الدائنة: 0.00 ريال")
        total_box.setStyleSheet("font-weight: 700; color: #e67e22; padding: 6px;")
        self.total_balance_label = total_box
        layout.addWidget(total_box)

        payment_box = QGroupBox("تسجيل سداد لمورد")
        payment_layout = QFormLayout(payment_box)
        payment_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        payment_layout.setSpacing(14)
        self.payment_supplier_label = QLabel("اختر مورداً من القائمة أعلاه أولاً")
        self.payment_supplier_label.setStyleSheet("font-weight: 700; color: #1f3b57;")
        self.payment_amount = QLineEdit()
        self.payment_method = QComboBox()
        self.payment_method.addItem("نقدي", "Cash")
        self.payment_method.addItem("تحويل بنكي", "Bank")
        self.payment_notes = QLineEdit()
        pay_btn = QPushButton("تسجيل السداد")
        pay_btn.setMinimumHeight(42)
        pay_btn.clicked.connect(self.record_payment)
        payment_layout.addRow(self.payment_supplier_label)
        payment_layout.addRow("المبلغ:", self.payment_amount)
        payment_layout.addRow("طريقة السداد:", self.payment_method)
        payment_layout.addRow("ملاحظات:", self.payment_notes)
        payment_layout.addRow(pay_btn)
        layout.addWidget(payment_box)

        statement_label = QLabel("كشف حساب المورد")
        statement_label.setStyleSheet("font-weight: 700; color: #334155; margin-top: 6px;")
        layout.addWidget(statement_label)

        self.statement_table = QTableWidget()
        self.statement_table.setColumnCount(5)
        self.statement_table.setHorizontalHeaderLabels(["التاريخ", "البيان", "مدين (سداد)", "دائن (مستحق)", "الرصيد"])
        self.statement_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.statement_table.verticalHeader().setVisible(False)
        self.statement_table.setAlternatingRowColors(True)
        self.statement_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.statement_table.setMinimumHeight(160)
        layout.addWidget(self.statement_table, 1)

        scroll.setWidget(scroll_widget)
        root_layout.addWidget(scroll, 1)

        self.load_suppliers()

    def add_supplier(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "تنبيه", "ادخل اسم المورد")
            return
        tax_id = self.tax_id_input.text().strip()
        phone = self.phone_input.text().strip()
        try:
            opening_balance = float(self.opening_balance_input.text() or 0)
        except ValueError:
            QMessageBox.warning(self, "تنبيه", "الرصيد الافتتاحي غير صحيح")
            return

        supplier_id = self.db.insert_and_return_id(
            "INSERT INTO suppliers (name, tax_id, opening_balance, phone) VALUES (?, ?, ?, ?)",
            (name, tax_id, opening_balance, phone),
        )

        if opening_balance:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            items = [
                {'account_code': '3900', 'debit': opening_balance, 'credit': 0},
                {'account_code': '2000', 'debit': 0, 'credit': opening_balance},
            ]
            self.db.add_journal_entry(timestamp, f"رصيد افتتاحي لمورد - {name}", None, items)

        QMessageBox.information(self, "نجاح", "تم إضافة المورد بنجاح")
        self.name_input.clear()
        self.tax_id_input.clear()
        self.phone_input.clear()
        self.opening_balance_input.clear()
        self.load_suppliers()

    def load_suppliers(self):
        balances = self.accounting.get_all_supplier_balances()
        total = 0
        if not fill_table(self.suppliers_table, len(balances), "لا يوجد موردون مسجلون بعد"):
            self.total_balance_label.setText("")
            return
        for row, s in enumerate(balances):
            total += s['balance']
            self.suppliers_table.setItem(row, 0, QTableWidgetItem(s['name']))
            self.suppliers_table.setItem(row, 1, QTableWidgetItem(s['phone'] or ""))
            self.suppliers_table.setItem(row, 2, money_item(s['balance'], bold=True))
            status = "له رصيد مستحق" if s['balance'] > 0.01 else ("مسدد بالكامل" if s['balance'] > -0.01 else "رصيد لصالحنا")
            item = QTableWidgetItem(status)
            self.suppliers_table.setItem(row, 3, item)
            self.suppliers_table.item(row, 0).setData(Qt.ItemDataRole.UserRole, s['id'])
        self.total_balance_label.setText(f"إجمالي أرصدة الموردين الدائنة: {money(total)} ريال")

    def on_supplier_selected(self):
        rows = self.suppliers_table.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        supplier_id = self.suppliers_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        name = self.suppliers_table.item(row, 0).text()
        self.selected_supplier_id = supplier_id
        self.payment_supplier_label.setText(f"المورد المحدد: {name}")
        self.refresh_statement()

    def refresh_statement(self):
        if not self.selected_supplier_id:
            self.statement_table.setRowCount(0)
            return
        statement = self.accounting.get_supplier_statement(self.selected_supplier_id)
        entries = statement['entries']
        if not fill_table(self.statement_table, len(entries), "لا توجد حركات على هذا المورد"):
            return
        for row, e in enumerate(entries):
            self.statement_table.setItem(row, 0, QTableWidgetItem(str(e['date'] or "")))
            self.statement_table.setItem(row, 1, QTableWidgetItem(e['type']))
            self.statement_table.setItem(row, 2, money_item(e['debit'], blank_if_zero=True))
            self.statement_table.setItem(row, 3, money_item(e['credit'], blank_if_zero=True))
            self.statement_table.setItem(row, 4, money_item(e['balance'], bold=True))

    def record_payment(self):
        if not self.selected_supplier_id:
            QMessageBox.warning(self, "تنبيه", "اختر مورداً من القائمة أولاً")
            return
        try:
            amount = float(self.payment_amount.text())
            if amount <= 0:
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, "تنبيه", "ادخل مبلغاً صحيحاً")
            return

        method = self.payment_method.currentData()
        notes = self.payment_notes.text().strip()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.db.execute_query(
            "INSERT INTO supplier_payments (supplier_id, date, amount, method, notes) VALUES (?, ?, ?, ?, ?)",
            (self.selected_supplier_id, timestamp, amount, method, notes),
        )

        cash_account = '1000' if method == 'Cash' else '1001'
        items = [
            {'account_code': '2000', 'debit': amount, 'credit': 0},
            {'account_code': cash_account, 'debit': 0, 'credit': amount},
        ]
        self.db.add_journal_entry(timestamp, "سداد لمورد", None, items)

        QMessageBox.information(self, "نجاح", "تم تسجيل السداد وتحديث رصيد المورد")
        self.payment_amount.clear()
        self.payment_notes.clear()
        self.load_suppliers()
        self.refresh_statement()

    def refresh_on_show(self):
        self.load_suppliers()
        self.refresh_statement()
