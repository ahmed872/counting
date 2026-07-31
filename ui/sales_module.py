from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, 
                             QTableWidgetItem, QPushButton, QFormLayout, QLineEdit, 
                             QComboBox, QLabel, QHeaderView, QMessageBox)
from datetime import datetime
from logic.accounting import AccountingLogic

class SalesModule(QWidget):
    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.accounting = AccountingLogic(db_manager)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        header = QLabel("إدارة المبيعات")
        header.setStyleSheet("font-size: 22px; font-weight: bold; color: #1f3b57; margin-bottom: 8px;")
        layout.addWidget(header)

        # Sales Form
        form_layout = QFormLayout()
        self.branch_input = QComboBox()
        self.branch_input.addItem("فرع الرياض", 1)
        self.branch_input.addItem("فرع جدة", 2)
        self.amount_input = QLineEdit()
        self.payment_method = QComboBox()
        self.payment_method.addItems(["Cash", "POS", "Transfer"])
        
        form_layout.addRow("الفرع:", self.branch_input)
        form_layout.addRow("المبلغ (قبل الضريبة):", self.amount_input)
        form_layout.addRow("طريقة الدفع:", self.payment_method)

        save_btn = QPushButton("تسجيل مبيعات وإصدار فاتورة")
        save_btn.clicked.connect(self.save_sale)
        form_layout.addRow(save_btn)

        layout.addLayout(form_layout)

        # Sales Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["التاريخ", "الفرع", "المبلغ الإجمالي", "الضريبة", "طريقة الدفع"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        self.load_sales()

    def save_sale(self):
        try:
            branch_id = self.branch_input.currentData()
            amount = float(self.amount_input.text())
            vat, total = self.accounting.calculate_vat(amount)
            method = self.payment_method.currentText()
            timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

            # Save to DB
            self.db.execute_query(
                "INSERT INTO sales (branch_id, total_amount, vat_amount, payment_method, date) VALUES (?, ?, ?, ?, ?)",
                (branch_id, total, vat, method, timestamp)
            )

            # Generate ZATCA QR
            qr_code = self.accounting.generate_zatca_qr("مطعم الفرعين", "300000000000003", timestamp, total, vat)
            
            # Double Entry: Debit Cash/Bank, Credit Sales, Credit VAT Output
            account_debit = '1000' if method == 'Cash' else '1001'
            items = [
                {'account_code': account_debit, 'debit': total, 'credit': 0},
                {'account_code': '4000', 'debit': 0, 'credit': amount},
                {'account_code': '2100', 'debit': 0, 'credit': vat}
            ]
            self.db.add_journal_entry(timestamp, f"مبيعات فاتورة - {method}", branch_id, items)

            QMessageBox.information(self, "فاتورة ضريبية", f"تم التسجيل بنجاح.\nQR Code: {qr_code[:30]}...")
            self.load_sales()
        except Exception as e:
            QMessageBox.critical(self, "خطأ", str(e))

    def load_sales(self):
        sales = self.db.fetch_all("SELECT s.*, b.name as branch_name FROM sales s JOIN branches b ON s.branch_id = b.id ORDER BY s.date DESC")
        self.table.setRowCount(len(sales))
        for row, s in enumerate(sales):
            self.table.setItem(row, 0, QTableWidgetItem(s['date']))
            self.table.setItem(row, 1, QTableWidgetItem(s['branch_name']))
            self.table.setItem(row, 2, QTableWidgetItem(str(s['total_amount'])))
            self.table.setItem(row, 3, QTableWidgetItem(str(s['vat_amount'])))
            self.table.setItem(row, 4, QTableWidgetItem(s['payment_method']))
