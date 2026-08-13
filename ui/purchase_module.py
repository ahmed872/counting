
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QLineEdit,
    QComboBox,
    QDateEdit,
    QLabel,
    QHeaderView,
    QMessageBox,
    QTabWidget,
    QGroupBox,
)
from logic.accounting import AccountingLogic
from ui.labels import PAYMENT_STATUS_LABELS, REFUND_METHOD_LABELS, label_for
from ui.formatting import money_item, money
from ui.common_widgets import (page_header, danger_button, fill_table, compact_form,
                              pin_height, collapsible,
                              collapse_when_short, fit_table_height)
from logic.money import parse_money

CATEGORY_LABELS = {
    'raw_material': 'مواد خام',
    'purchase_expense': 'مصروفات مرتبطة بالمشتريات',
    'operating_expense': 'مصروفات تشغيلية',
}


class PurchaseModule(QWidget):
    def __init__(self, db_manager, current_user=None):
        super().__init__()
        self.db = db_manager
        self.current_user = current_user or {}
        self.accounting = AccountingLogic(db_manager)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        layout.addWidget(page_header(
            "المشتريات والمصروفات",
            "سجّل فواتير المواد الخام والمصروفات التشغيلية، نقداً أو على الحساب."))

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        layout.addWidget(tabs, 1)

        tabs.addTab(self.build_purchase_tab(), "فاتورة مشتريات / مصروف")
        tabs.addTab(self.build_returns_tab(), "مرتجعات المشتريات")

    def build_purchase_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        self.branch_input = QComboBox()
        self.load_branches()

        self.category_input = QComboBox()
        for key, label in CATEGORY_LABELS.items():
            self.category_input.addItem(label, key)
        self.category_input.currentIndexChanged.connect(self.on_category_changed)

        self.supplier_input = QComboBox()
        self.load_suppliers()

        self.date_input = QDateEdit(QDate.currentDate())
        # A purchase cannot happen on a day that has not arrived yet - see
        # the same fix on the daily sales screen.
        self.date_input.setMaximumDate(QDate.currentDate())
        self.description_input = QLineEdit()
        self.description_input.setPlaceholderText("مثال: إيجار، كهرباء ...")

        self.amount_input = QLineEdit()
        self.payment_status = QComboBox()
        self.payment_status.addItem("نقدي", "Cash")
        self.payment_status.addItem("آجل (على الحساب)", "Credit")

        self.amount_input.setPlaceholderText("0.00 قبل الضريبة")
        self.amount_input.returnPressed.connect(self.save_purchase)
        self.description_input.returnPressed.connect(self.save_purchase)

        save_btn = QPushButton("تسجيل الفاتورة")
        save_btn.setMinimumHeight(38)
        save_btn.clicked.connect(self.save_purchase)

        # Three columns with the button in the last cell: eight rows of fields
        # would not leave the invoice list a usable height on a 720p screen.
        form_box = QGroupBox("فاتورة جديدة")
        form_outer = QVBoxLayout(form_box)
        form_outer.setContentsMargins(10, 6, 10, 8)
        form_outer.addWidget(compact_form([
            ("الفرع", self.branch_input),
            ("التاريخ", self.date_input),
            ("نوع المصروف", self.category_input),
            ("المورد", self.supplier_input),
            ("البيان", self.description_input),
            ("المبلغ", self.amount_input),
            ("حالة الدفع", self.payment_status),
            (None, save_btn),
        ], columns=2, field_min_width=130))

        layout.addWidget(pin_height(form_box))

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["التاريخ", "النوع", "المورد", "البيان", "المبلغ", "الضريبة", "الحالة"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setMinimumHeight(90)

        table_header = QHBoxLayout()
        table_label = QLabel("الفواتير المسجلة:")
        table_label.setStyleSheet("font-weight:700; color:#334155;")
        table_header.addWidget(table_label)
        table_header.addStretch()
        self.form_toggle = collapsible(
            form_box, "إظهار نموذج الفاتورة", "إخفاء النموذج",
            start_collapsed=self._short_screen())
        table_header.addWidget(self.form_toggle)
        delete_btn = danger_button("إلغاء الفاتورة المحددة")
        delete_btn.clicked.connect(self.delete_selected_purchase)
        table_header.addWidget(delete_btn)
        layout.addLayout(table_header)
        layout.addWidget(self.table)

        self.purchases_total_label = QLabel()
        self.purchases_total_label.setStyleSheet(
            "font-weight:800; color:#1f3b57; padding:6px 2px;")
        layout.addWidget(self.purchases_total_label)
        layout.addStretch()

        self.on_category_changed()
        self.load_purchases()
        # _short_screen() only knows about the monitor. Someone on a big screen
        # can still drag the window down to where the form and the table cannot
        # both fit, and the invoice list was left at 94px - two rows.
        collapse_when_short(self, self.form_toggle)
        return widget

    def _short_screen(self):
        """Fold the entry form away by default when the screen cannot show both
        the form and a useful number of table rows."""
        screen = self.screen() or (self.window().screen() if self.window() else None)
        return bool(screen and screen.availableGeometry().height() < 800)

    def delete_selected_purchase(self):
        """P1-2: voids rather than deletes. The invoice row and its
        original journal entry stay in place as permanent history; a new
        reversal journal entry cancels its effect, and it stops counting
        toward any report total from here on - it never disappears from
        this table or from the ledger it once posted to."""
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "تنبيه", "اختر فاتورة من الجدول أولاً")
            return
        purchase_id, entry_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        description = self.table.item(row, 3).text() or self.table.item(row, 1).text()
        amount = self.table.item(row, 4).text()
        from PyQt6.QtWidgets import QInputDialog
        reason, ok = QInputDialog.getText(
            self, "إلغاء فاتورة",
            f"سيتم إلغاء الفاتورة «{description}» بمبلغ {amount} - يبقى سجلها كاملاً، "
            f"ويُعكس أثرها المحاسبي بقيد جديد بدلاً من حذف أي شيء.\n\nسبب الإلغاء:",
        )
        if not ok or not reason.strip():
            return
        try:
            self.db.void_transaction(
                'purchases', purchase_id,
                self.current_user.get("id"), reason.strip())
        except ValueError as e:
            QMessageBox.warning(self, "تعذر الإلغاء", str(e))
            return
        QMessageBox.information(self, "تم", "تم إلغاء الفاتورة وعكس قيدها المحاسبي")
        self.load_purchases()

    def build_returns_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        self.return_branch_input = QComboBox()
        for row in self.db.fetch_all("SELECT id, name FROM branches ORDER BY id"):
            self.return_branch_input.addItem(row['name'], row['id'])

        self.return_supplier_input = QComboBox()
        for s in self.db.fetch_all("SELECT id, name FROM suppliers ORDER BY name"):
            self.return_supplier_input.addItem(s['name'], s['id'])

        self.return_date_input = QDateEdit(QDate.currentDate())
        self.return_date_input.setMaximumDate(QDate.currentDate())
        self.return_amount_input = QLineEdit()
        self.return_method_input = QComboBox()
        self.return_method_input.addItem("استرداد نقدي", "Cash")
        self.return_method_input.addItem("خصم من رصيد المورد (إشعار دائن)", "CreditNote")
        self.return_category_input = QComboBox()
        for key, label in CATEGORY_LABELS.items():
            self.return_category_input.addItem(label, key)
        self.return_notes_input = QLineEdit()

        return_box = QGroupBox("مرتجع جديد")
        return_outer = QVBoxLayout(return_box)
        return_outer.setSpacing(10)
        save_return_btn = QPushButton("تسجيل مرتجع مشتريات")
        save_return_btn.setMinimumHeight(38)
        save_return_btn.clicked.connect(self.save_purchase_return)
        return_outer.setContentsMargins(10, 6, 10, 8)
        return_outer.addWidget(compact_form([
            ("الفرع", self.return_branch_input),
            ("التاريخ", self.return_date_input),
            ("المورد", self.return_supplier_input),
            ("نوع المصروف الأصلي", self.return_category_input),
            ("المبلغ", self.return_amount_input),
            ("طريقة الاسترداد", self.return_method_input),
            ("ملاحظات", self.return_notes_input),
            (None, save_return_btn),
        ], columns=2, field_min_width=130))
        layout.addWidget(pin_height(return_box))

        returns_header = QHBoxLayout()
        returns_label = QLabel("المرتجعات المسجلة:")
        returns_label.setStyleSheet("font-weight:700; color:#334155;")
        returns_header.addWidget(returns_label)
        returns_header.addStretch()
        delete_return_btn = danger_button("إلغاء المرتجع المحدد")
        delete_return_btn.clicked.connect(self.delete_selected_return)
        returns_header.addWidget(delete_return_btn)
        layout.addLayout(returns_header)

        self.returns_table = QTableWidget()
        self.returns_table.setColumnCount(5)
        self.returns_table.setHorizontalHeaderLabels(["التاريخ", "المورد", "المبلغ", "الضريبة", "طريقة الاسترداد"])
        self.returns_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.returns_table.verticalHeader().setVisible(False)
        self.returns_table.setAlternatingRowColors(True)
        self.returns_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.returns_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.returns_table.setMinimumHeight(90)
        layout.addWidget(self.returns_table)
        layout.addStretch()

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
        self.supplier_input.addItem("بدون مورد", None)
        # Only active suppliers - a stopped supplier can still be reached to
        # settle what they're owed (payments/returns), but should not appear
        # as a choice for a brand new purchase.
        suppliers = self.db.fetch_all("SELECT * FROM suppliers WHERE is_active = 1 ORDER BY name")
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

            amount = parse_money(amount_text, "المبلغ قبل الضريبة",
                                 allow_blank=False, allow_zero=False)

            status = self.payment_status.currentData()
            if status == 'Credit' and not supplier_id:
                raise ValueError("الشراء الآجل (Credit) يتطلب اختيار مورد")

            vat, total = self.accounting.calculate_vat(amount)
            # The invoice date is chosen, not "now": invoices are often entered
            # in a batch days after they were actually received.
            timestamp = self.date_input.date().toString("yyyy-MM-dd")

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

            # One transaction, not a journal write and a separate purchase
            # write: a crash between the two used to be able to leave a
            # journal entry moving money with no invoice behind it to explain
            # it, or a purchase row with no accounting entry at all.
            with self.db.transaction() as cursor:
                fallback = label_for(PAYMENT_STATUS_LABELS, status)
                entry_id = self.db.insert_journal_entry(
                    cursor, timestamp, f"{label} - {description or fallback}", branch_id, items)
                cursor.execute(
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
        if not fill_table(self.table, len(purchases), "لا توجد فواتير مسجلة بعد"):
            self.purchases_total_label.setText("")
            fit_table_height(self.table)
            return
        for row, p in enumerate(purchases):
            date_item = QTableWidgetItem(str(p['date']))
            date_item.setData(Qt.ItemDataRole.UserRole, (p['id'], p['journal_entry_id']))
            self.table.setItem(row, 0, date_item)
            self.table.setItem(row, 1, QTableWidgetItem(CATEGORY_LABELS.get(p['category'] or 'raw_material', p['category'] or "")))
            self.table.setItem(row, 2, QTableWidgetItem(p['supplier_name'] or "مصروف عام"))
            self.table.setItem(row, 3, QTableWidgetItem(p['description'] or ""))
            self.table.setItem(row, 4, money_item(p['total_amount']))
            self.table.setItem(row, 5, money_item(p['vat_amount']))
            status_text = label_for(PAYMENT_STATUS_LABELS, p['payment_status'])
            if p['voided_at']:
                status_item = QTableWidgetItem(f"ملغاة ⛔ ({status_text})")
                status_item.setToolTip(p['void_reason'] or "")
                status_item.setForeground(Qt.GlobalColor.red)
            else:
                status_item = QTableWidgetItem(status_text)
            self.table.setItem(row, 6, status_item)

        # A voided invoice stays in the table for its own history, but its
        # amount must not count toward the total shown here - that total
        # is exactly what every accounting report reads too, and reports
        # already exclude voided rows (see logic/accounting.py).
        total = sum((p['total_amount'] or 0) for p in purchases if not p['voided_at'])
        vat = sum((p['vat_amount'] or 0) for p in purchases if not p['voided_at'])
        self.purchases_total_label.setText(
            f"عدد الفواتير: {len(purchases)}"
            f"     |     الإجمالي: {money(total)} ريال"
            f"     |     منها ضريبة: {money(vat)} ريال"
        )
        fit_table_height(self.table)

    def save_purchase_return(self):
        try:
            branch_id = self.return_branch_input.currentData()
            supplier_id = self.return_supplier_input.currentData()
            amount_text = self.return_amount_input.text().strip()
            if not amount_text:
                raise ValueError("يرجى إدخال مبلغ المرتجع")
            amount = parse_money(amount_text, "مبلغ المرتجع",
                                 allow_blank=False, allow_zero=False)

            refund_method = self.return_method_input.currentData()
            # An إشعار دائن reduces a specific supplier's balance (account
            # 2000 credited). Posting one with no supplier chosen moves the
            # general ledger total without any supplier statement reflecting
            # it, so the two stop matching - the same requirement the
            # purchase form already makes for a credit purchase.
            if refund_method == 'CreditNote' and not supplier_id:
                raise ValueError("الخصم من رصيد المورد يتطلب اختيار مورد")

            category = self.return_category_input.currentData()
            notes = self.return_notes_input.text().strip()
            vat, total = self.accounting.calculate_vat(amount)
            timestamp = self.return_date_input.date().toString("yyyy-MM-dd")

            # Mirrors save_purchase's own routing: a return has to credit the
            # same account its purchase debited, or an operating-expense
            # refund quietly shrinks the inventory account instead of the
            # expense it was actually against.
            if category == 'raw_material':
                source_account = '1100'
            elif category == 'purchase_expense':
                source_account = '5150'
            else:
                source_account = '5200'

            credit_account = '1000' if refund_method == 'Cash' else '2000'
            items = [
                {'account_code': credit_account, 'debit': total, 'credit': 0},
                {'account_code': source_account, 'debit': 0, 'credit': amount},
                {'account_code': '1200', 'debit': 0, 'credit': vat},
            ]
            label = CATEGORY_LABELS.get(category, category)

            # One transaction: a crash between these two writes used to be
            # able to leave a journal entry with no return behind it, or a
            # return with no journal entry - either way, the accounts and the
            # operational record disagreeing about whether it happened.
            with self.db.transaction() as cursor:
                entry_id = self.db.insert_journal_entry(
                    cursor, timestamp, f"مرتجع مشتريات ({label}) - {notes or ''}", branch_id, items)
                cursor.execute(
                    """INSERT INTO purchase_returns
                       (branch_id, supplier_id, date, amount, vat_amount, refund_method, notes, category, journal_entry_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (branch_id, supplier_id, timestamp, amount, vat, refund_method, notes, category, entry_id),
                )

            QMessageBox.information(self, "نجاح", "تم تسجيل مرتجع المشتريات")
            self.return_amount_input.clear()
            self.return_notes_input.clear()
            self.load_purchase_returns()
            self.load_purchases()
        except Exception as e:
            QMessageBox.critical(self, "خطأ", str(e))

    def delete_selected_return(self):
        """P1-2: voids rather than deletes - see delete_selected_purchase."""
        row = self.returns_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "تنبيه", "اختر مرتجعاً من الجدول أولاً")
            return
        return_id, entry_id = self.returns_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        from PyQt6.QtWidgets import QInputDialog
        reason, ok = QInputDialog.getText(
            self, "إلغاء مرتجع",
            "سيتم إلغاء هذا المرتجع - يبقى سجله كاملاً، ويُعكس أثره المحاسبي بقيد جديد "
            "بدلاً من حذف أي شيء.\n\nسبب الإلغاء:",
        )
        if not ok or not reason.strip():
            return
        try:
            self.db.void_transaction(
                'purchase_returns', return_id,
                self.current_user.get("id"), reason.strip())
        except ValueError as e:
            QMessageBox.warning(self, "تعذر الإلغاء", str(e))
            return
        QMessageBox.information(self, "تم", "تم إلغاء المرتجع وعكس قيده المحاسبي")
        self.load_purchase_returns()

    def load_purchase_returns(self):
        query = """
            SELECT pr.*, s.name as supplier_name
            FROM purchase_returns pr
            LEFT JOIN suppliers s ON pr.supplier_id = s.id
            ORDER BY pr.date DESC, pr.id DESC
        """
        rows = self.db.fetch_all(query)
        if not fill_table(self.returns_table, len(rows), "لا توجد مرتجعات مسجلة"):
            fit_table_height(self.returns_table)
            return
        for row, r in enumerate(rows):
            date_item = QTableWidgetItem(str(r['date']))
            date_item.setData(Qt.ItemDataRole.UserRole, (r['id'], r['journal_entry_id']))
            self.returns_table.setItem(row, 0, date_item)
            self.returns_table.setItem(row, 1, QTableWidgetItem(r['supplier_name'] or ""))
            self.returns_table.setItem(row, 2, money_item(r['amount']))
            self.returns_table.setItem(row, 3, money_item(r['vat_amount']))
            method_label = label_for(REFUND_METHOD_LABELS, r['refund_method'])
            if r['voided_at']:
                method_item = QTableWidgetItem(f"ملغى ⛔ ({method_label})")
                method_item.setToolTip(r['void_reason'] or "")
                method_item.setForeground(Qt.GlobalColor.red)
            else:
                method_item = QTableWidgetItem(method_label)
            self.returns_table.setItem(row, 4, method_item)
        fit_table_height(self.returns_table)
