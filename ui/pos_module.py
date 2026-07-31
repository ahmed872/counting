from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from logic.accounting import AccountingLogic


class POSModule(QWidget):
    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.accounting = AccountingLogic(db_manager)
        self.cart = {}
        self.current_category_id = None
        self.init_ui()

    def init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        header = QLabel("نقطة البيع - POS")
        header.setStyleSheet("font-size: 24px; font-weight: 800; color: #1f3b57;")
        subtitle = QLabel("واجهة لمس سريعة لإضافة الأصناف، تجميع الطلب، وطباعة فاتورة مبسطة")
        subtitle.setStyleSheet("color: #64748b;")
        subtitle.setWordWrap(True)
        root.addWidget(header)
        root.addWidget(subtitle)

        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        self.branch_input = QComboBox()
        self.branch_input.addItem("فرع الرياض", 1)
        self.branch_input.addItem("فرع جدة", 2)
        self.branch_input.setCurrentIndex(0)
        
        self.cashier_input = QComboBox()
        self.cashier_input.addItems(["الكاشير", "مشرف الصالة", "مدير الفرع"])
        self.cashier_input.setCurrentIndex(0)
        
        self.payment_method = QComboBox()
        self.payment_method.addItems(["نقد - Cash", "بطاقة - POS", "تحويل - Transfer"])
        self.payment_method.setCurrentIndex(0)
        
        for widget in (self.branch_input, self.cashier_input, self.payment_method):
            widget.setMinimumHeight(42)
            widget.setMinimumWidth(160)
            widget.setStyleSheet(
                "QComboBox { padding: 8px; border-radius: 8px; background: white; border: 2px solid #d6dbe3; }"
                "QComboBox:hover { border: 2px solid #4f78a8; }"
                "QComboBox::drop-down { border: none; width: 30px; }"
            )

        top_row.addWidget(QLabel("الفرع:"))
        top_row.addWidget(self.branch_input)
        top_row.addWidget(QLabel("المستخدم:"))
        top_row.addWidget(self.cashier_input)
        top_row.addWidget(QLabel("الدفع:"))
        top_row.addWidget(self.payment_method)
        top_row.addStretch()
        root.addLayout(top_row)

        body = QHBoxLayout()
        body.setSpacing(12)

        left_panel = QFrame()
        left_panel.setStyleSheet("background: white; border: 1px solid #dde3ea; border-radius: 16px;")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(14, 14, 14, 14)
        left_layout.setSpacing(10)

        category_row = QHBoxLayout()
        category_row.setSpacing(8)
        self.category_buttons = []
        all_btn = QPushButton("الكل")
        all_btn.setMinimumHeight(42)
        all_btn.setStyleSheet(
            "QPushButton { background-color: #6366f1; color: white; border: none; border-radius: 8px; font-weight: 600; }"
            "QPushButton:hover { background-color: #4f46e5; }"
            "QPushButton:pressed { background-color: #4338ca; }"
        )
        all_btn.clicked.connect(lambda: self.apply_category_filter(None))
        self.category_buttons.append(all_btn)
        category_row.addWidget(all_btn)
        self.categories_holder = QHBoxLayout()
        self.categories_holder.setSpacing(8)
        category_wrap = QWidget()
        category_wrap.setLayout(self.categories_holder)
        category_row.addWidget(category_wrap)
        left_layout.addLayout(category_row)

        self.menu_scroll = QScrollArea()
        self.menu_scroll.setWidgetResizable(True)
        self.menu_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.menu_container = QWidget()
        self.menu_grid = QGridLayout(self.menu_container)
        self.menu_grid.setHorizontalSpacing(10)
        self.menu_grid.setVerticalSpacing(10)
        self.menu_scroll.setWidget(self.menu_container)
        left_layout.addWidget(self.menu_scroll, 1)

        right_panel = QFrame()
        right_panel.setStyleSheet("background: white; border: 1px solid #dde3ea; border-radius: 16px;")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(14, 14, 14, 14)
        right_layout.setSpacing(10)

        cart_header = QLabel("سلة الطلب")
        cart_header.setStyleSheet("font-size: 18px; font-weight: 800; color: #1f3b57;")
        right_layout.addWidget(cart_header)

        self.cart_table = QTableWidget()
        self.cart_table.setColumnCount(4)
        self.cart_table.setHorizontalHeaderLabels(["الصنف", "سعر", "كمية", "الإجمالي"])
        self.cart_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.cart_table.horizontalHeader().setStyleSheet(
            "QHeaderView::section { background-color: #f3f4f6; color: #1f3b57; font-weight: 700; padding: 8px; border: 1px solid #e5e7eb; }"
        )
        self.cart_table.verticalHeader().setVisible(False)
        self.cart_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.cart_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.cart_table.setAlternatingRowColors(True)
        self.cart_table.setStyleSheet(
            "QTableWidget { border: 1px solid #dde3ea; border-radius: 8px; background: white; }"
            "QTableWidget::item { padding: 8px; color: #1f3b57; }"
            "QTableWidget::item:selected { background-color: #dbeafe; }"
        )
        self.cart_table.setMinimumHeight(320)
        right_layout.addWidget(self.cart_table, 1)

        summary_box = QFrame()
        summary_box.setStyleSheet(
            "background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%); "
            "border: 2px solid #0284c7; border-radius: 14px; padding: 12px;"
        )
        summary_layout = QVBoxLayout(summary_box)
        summary_layout.setContentsMargins(12, 12, 12, 12)
        summary_layout.setSpacing(8)
        
        self.subtotal_label = QLabel("الإجمالي قبل الضريبة: 0.00 ريال")
        self.vat_label = QLabel("ضريبة 15%: 0.00 ريال")
        self.total_label = QLabel("الإجمالي النهائي: 0.00 ريال")
        
        for label in (self.subtotal_label, self.vat_label, self.total_label):
            label.setStyleSheet("font-size: 15px; font-weight: 700; color: #0c4a6e;")
            summary_layout.addWidget(label)
        
        right_layout.addWidget(summary_box)

        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(10)
        
        self.remove_btn = QPushButton("حذف المحدد")
        self.clear_btn = QPushButton("تفريغ السلة")
        self.finish_btn = QPushButton("✓ إنهاء الطلب وطباعة فاتورة")
        
        self.remove_btn.clicked.connect(self.remove_selected_item)
        self.clear_btn.clicked.connect(self.clear_cart)
        self.finish_btn.clicked.connect(self.finish_order)
        
        # Style removal and clear buttons
        for btn in [self.remove_btn, self.clear_btn]:
            btn.setMinimumHeight(42)
            btn.setStyleSheet(
                "QPushButton { background-color: #f87171; color: white; border: none; border-radius: 8px; font-weight: 600; }"
                "QPushButton:hover { background-color: #ef4444; }"
                "QPushButton:pressed { background-color: #dc2626; }"
            )
        
        # Style finish button
        self.finish_btn.setMinimumHeight(52)
        self.finish_btn.setStyleSheet(
            "QPushButton { background-color: #10b981; color: white; border: none; border-radius: 8px; font-weight: 700; font-size: 14px; }"
            "QPushButton:hover { background-color: #059669; }"
            "QPushButton:pressed { background-color: #047857; }"
        )
        
        buttons_row.addWidget(self.remove_btn)
        buttons_row.addWidget(self.clear_btn)
        right_layout.addLayout(buttons_row)
        right_layout.addWidget(self.finish_btn)

        body.addWidget(left_panel, 3)
        body.addWidget(right_panel, 2)
        root.addLayout(body, 1)

        self.load_categories()
        self.load_menu_items()

    def load_categories(self):
        while self.categories_holder.count():
            item = self.categories_holder.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        categories = self.db.fetch_all("SELECT id, name FROM menu_categories WHERE is_active = 1 ORDER BY sort_order, name")
        self.category_buttons = self.category_buttons[:1]
        for category in categories:
            button = QPushButton(category["name"])
            button.setProperty("category_id", category["id"])
            button.setMinimumHeight(42)
            button.setMinimumWidth(120)
            button.setStyleSheet(
                "QPushButton { background-color: #8b5cf6; color: white; border: none; border-radius: 8px; font-weight: 600; }"
                "QPushButton:hover { background-color: #7c3aed; }"
                "QPushButton:pressed { background-color: #6d28d9; }"
            )
            button.clicked.connect(lambda checked=False, cid=category["id"]: self.apply_category_filter(cid))
            self.categories_holder.addWidget(button)
            self.category_buttons.append(button)

    def apply_category_filter(self, category_id):
        self.current_category_id = category_id
        self.load_menu_items()

    def load_menu_items(self):
        while self.menu_grid.count():
            item = self.menu_grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        query = """
            SELECT mi.id, mi.name, mi.price, mi.image_path, mc.name as category_name
            FROM menu_items mi
            LEFT JOIN menu_categories mc ON mi.category_id = mc.id
            WHERE mi.is_active = 1
        """
        params = ()
        if self.current_category_id:
            query += " AND mi.category_id = ?"
            params = (self.current_category_id,)
        query += " ORDER BY mc.sort_order, mi.sort_order, mi.name"
        items = self.db.fetch_all(query, params)

        columns = 3
        for index, item in enumerate(items):
            button = self.create_menu_button(item)
            row = index // columns
            col = index % columns
            self.menu_grid.addWidget(button, row, col)

    def create_menu_button(self, item):
        button = QPushButton()
        button.setMinimumSize(180, 110)
        button.setMaximumHeight(120)
        image_path = item["image_path"] or ""
        text = f"{item['name']}\n\n{item['price']:.2f} ريال"
        if image_path:
            text = f"{item['name']}\n\n{item['price']:.2f} ريال"
        button.setText(text)
        button.setStyleSheet(
            "QPushButton { "
            "text-align: right; padding: 14px; border-radius: 12px; "
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #eef4fb, stop:1 #dbeafe); "
            "color: #0f172a; border: 2px solid #cfd8e3; font-weight: 700; "
            "} "
            "QPushButton:hover { "
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #dbeafe, stop:1 #bfdbfe); "
            "border: 2px solid #0284c7; "
            "} "
            "QPushButton:pressed { background: #bfdbfe; }"
        )
        if image_path:
            button.setToolTip(image_path)
        button.clicked.connect(lambda checked=False, item_id=item["id"]: self.add_to_cart(item_id))
        return button

    def add_to_cart(self, item_id):
        item = self.db.fetch_one("SELECT id, name, price FROM menu_items WHERE id = ?", (item_id,))
        if not item:
            return
        if item_id in self.cart:
            self.cart[item_id]["quantity"] += 1
        else:
            self.cart[item_id] = {
                "item_id": item["id"],
                "name": item["name"],
                "price": float(item["price"]),
                "quantity": 1,
            }
        self.refresh_cart()

    def refresh_cart(self):
        self.cart_table.setRowCount(len(self.cart))
        subtotal = 0
        for row, data in enumerate(self.cart.values()):
            line_total = data["price"] * data["quantity"]
            subtotal += line_total
            self.cart_table.setItem(row, 0, QTableWidgetItem(data["name"]))
            self.cart_table.setItem(row, 1, QTableWidgetItem(f"{data['price']:.2f}"))
            self.cart_table.setItem(row, 2, QTableWidgetItem(str(data["quantity"])))
            self.cart_table.setItem(row, 3, QTableWidgetItem(f"{line_total:.2f}"))
        
        vat, total = self.accounting.calculate_vat(subtotal)
        self.subtotal_label.setText(f"الإجمالي قبل الضريبة: {subtotal:.2f} ريال")
        self.vat_label.setText(f"ضريبة 15%: {vat:.2f} ريال")
        self.total_label.setText(f"الإجمالي النهائي: {total:.2f} ريال")

    def remove_selected_item(self):
        row = self.cart_table.currentRow()
        if row < 0:
            return
        cart_items = list(self.cart.keys())
        if row < len(cart_items):
            del self.cart[cart_items[row]]
        self.refresh_cart()

    def clear_cart(self):
        self.cart.clear()
        self.refresh_cart()

    def finish_order(self):
        if not self.cart:
            QMessageBox.warning(self, "تنبيه", "السلة فارغة")
            return

        branch_id = self.branch_input.currentData()
        cashier_name = self.cashier_input.currentText()
        payment_method = self.payment_method.currentText()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        order_no = datetime.now().strftime("POS-%Y%m%d-%H%M%S")

        subtotal = sum(data["price"] * data["quantity"] for data in self.cart.values())
        vat, total = self.accounting.calculate_vat(subtotal)
        qr_code = self.accounting.generate_zatca_qr("مطعم الفرعين", "300000000000003", timestamp, total, vat)

        order_id = self.db.insert_and_return_id(
            "INSERT INTO sales_orders (branch_id, order_no, cashier_name, payment_method, subtotal, vat_amount, total_amount, qr_code, date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (branch_id, order_no, cashier_name, payment_method, subtotal, vat, total, qr_code, timestamp),
        )

        for data in self.cart.values():
            self.db.execute_query(
                "INSERT INTO sales_order_items (order_id, item_id, item_name, unit_price, quantity, line_total) VALUES (?, ?, ?, ?, ?, ?)",
                (order_id, data["item_id"], data["name"], data["price"], data["quantity"], data["price"] * data["quantity"]),
            )

        self.db.execute_query(
            "INSERT INTO sales (branch_id, total_amount, vat_amount, payment_method, date) VALUES (?, ?, ?, ?, ?)",
            (branch_id, total, vat, payment_method, timestamp),
        )

        account_debit = "1000" if payment_method == "Cash" else "1001"
        journal_items = [
            {"account_code": account_debit, "debit": total, "credit": 0},
            {"account_code": "4000", "debit": 0, "credit": subtotal},
            {"account_code": "2100", "debit": 0, "credit": vat},
        ]
        self.db.add_journal_entry(timestamp, f"مبيعات POS - {order_no}", branch_id, journal_items)

        receipt = self.build_receipt(order_no, timestamp, payment_method, subtotal, vat, total, qr_code)
        self.show_receipt(receipt)
        self.clear_cart()
        QMessageBox.information(self, "تم", "تم إتمام الطلب وترحيل المبيعات للمحاسبة")

    def build_receipt(self, order_no, timestamp, payment_method, subtotal, vat, total, qr_code):
        lines = [
            "فاتورة مبسطة",
            f"رقم الطلب: {order_no}",
            f"التاريخ: {timestamp}",
            f"طريقة الدفع: {payment_method}",
            "",
        ]
        for data in self.cart.values():
            lines.append(f"{data['name']} x{data['quantity']} = {data['price'] * data['quantity']:.2f}")
        lines.extend([
            "",
            f"الإجمالي قبل الضريبة: {subtotal:.2f}",
            f"الضريبة 15%: {vat:.2f}",
            f"الإجمالي النهائي: {total:.2f}",
            "",
            f"QR: {qr_code}",
        ])
        return "\n".join(lines)

    def show_receipt(self, receipt_text):
        dialog = QDialog(self)
        dialog.setWindowTitle("فاتورة البيع")
        dialog.resize(520, 620)
        layout = QVBoxLayout(dialog)
        viewer = QTextEdit()
        viewer.setReadOnly(True)
        viewer.setPlainText(receipt_text)
        layout.addWidget(viewer)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)
        dialog.exec()
