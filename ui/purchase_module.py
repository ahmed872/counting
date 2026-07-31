from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, 
                             QTableWidgetItem, QPushButton, QFormLayout, QLineEdit, 
                             QComboBox, QLabel, QHeaderView, QMessageBox)
from datetime import datetime
from logic.accounting import AccountingLogic

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

        # Purchase Form
        form_layout = QFormLayout()
        self.branch_input = QComboBox()
        self.branch_input.addItem("فرع الرياض", 1)
        self.branch_input.addItem("فرع جدة", 2)
        
        self.supplier_input = QComboBox()
        self.load_suppliers()
        
        self.amount_input = QLineEdit()
        self.payment_status = QComboBox()
        self.payment_status.addItems(["Cash", "Credit"])
        
        form_layout.addRow("الفرع:", self.branch_input)
        form_layout.addRow("المورد:", self.supplier_input)
        form_layout.addRow("المبلغ (قبل الضريبة):", self.amount_input)
        form_layout.addRow("حالة الدفع:", self.payment_status)

        save_btn = QPushButton("تسجيل مشتريات")
        save_btn.clicked.connect(self.save_purchase)
        form_layout.addRow(save_btn)

        layout.addLayout(form_layout)

        # Purchases Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["التاريخ", "المورد", "المبلغ الإجمالي", "الضريبة", "الحالة"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        self.load_purchases()

    def load_suppliers(self):
        suppliers = self.db.fetch_all("SELECT * FROM suppliers")
        for s in suppliers:
            self.supplier_input.addItem(s['name'], s['id'])

    def save_purchase(self):
        try:
            branch_id = self.branch_input.currentData()
            supplier_id = self.supplier_input.currentData()
            amount_text = self.amount_input.text().strip()
            if not amount_text:
                raise ValueError("يرجى إدخال مبلغ الشراء قبل الضريبة")

            amount = float(amount_text)
            vat, total = self.accounting.calculate_vat(amount)
            status = self.payment_status.currentText()
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Save to DB
            self.db.execute_query(
                "INSERT INTO purchases (branch_id, supplier_id, total_amount, vat_amount, payment_status, date) VALUES (?, ?, ?, ?, ?, ?)",
                (branch_id, supplier_id, total, vat, status, timestamp)
            )

            # Double Entry: 
            # Debit Inventory (1100), Debit Input VAT (1200)
            # Credit Cash (1000) or AP (2000)
            account_credit = '1000' if status == 'Cash' else '2000'
            items = [
                {'account_code': '1100', 'debit': amount, 'credit': 0},
                {'account_code': '1200', 'debit': vat, 'credit': 0},
                {'account_code': account_credit, 'debit': 0, 'credit': total}
            ]
            self.db.add_journal_entry(timestamp, f"مشتريات من مورد - {status}", branch_id, items)

            QMessageBox.information(self, "نجاح", "تم تسجيل المشتريات بنجاح")
            self.load_purchases()
        except Exception as e:
            QMessageBox.critical(self, "خطأ", str(e))

    def load_purchases(self):
        query = """
            SELECT p.*, s.name as supplier_name 
            FROM purchases p 
            LEFT JOIN suppliers s ON p.supplier_id = s.id 
            ORDER BY p.date DESC
        """
        purchases = self.db.fetch_all(query)
        self.table.setRowCount(len(purchases))
        for row, p in enumerate(purchases):
            self.table.setItem(row, 0, QTableWidgetItem(p['date']))
            self.table.setItem(row, 1, QTableWidgetItem(p['supplier_name'] or "مصروف عام"))
            self.table.setItem(row, 2, QTableWidgetItem(str(p['total_amount'])))
            self.table.setItem(row, 3, QTableWidgetItem(str(p['vat_amount'])))
            self.table.setItem(row, 4, QTableWidgetItem(p['payment_status']))
