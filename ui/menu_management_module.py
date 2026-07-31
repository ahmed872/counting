from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QComboBox,
    QDoubleSpinBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QFileDialog,
)


class MenuManagementModule(QWidget):
    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.image_path = ""
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        header = QLabel("إدارة المنيو")
        header.setStyleSheet("font-size: 24px; font-weight: 800; color: #1f3b57;")
        subtitle = QLabel("إضافة التصنيفات والأصناف مع الأسعار والصور لتظهر مباشرة في شاشة الكاشير")
        subtitle.setStyleSheet("color:#64748b;")
        subtitle.setWordWrap(True)
        layout.addWidget(header)
        layout.addWidget(subtitle)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(10)
        self.category_count = self.make_stat_card("التصنيفات", "0")
        self.item_count = self.make_stat_card("الأصناف", "0")
        stats_row.addWidget(self.category_count)
        stats_row.addWidget(self.item_count)
        layout.addLayout(stats_row)

        form_row = QHBoxLayout()
        form_row.setSpacing(12)

        category_box = QGroupBox("إضافة تصنيف")
        category_layout = QGridLayout(category_box)
        self.category_name = QLineEdit()
        self.category_order = QDoubleSpinBox()
        self.category_order.setMaximum(9999)
        self.category_order.setDecimals(0)
        self.add_category_btn = QPushButton("حفظ التصنيف")
        self.add_category_btn.clicked.connect(self.add_category)
        category_layout.addWidget(QLabel("اسم التصنيف"), 0, 0)
        category_layout.addWidget(self.category_name, 1, 0)
        category_layout.addWidget(QLabel("الترتيب"), 0, 1)
        category_layout.addWidget(self.category_order, 1, 1)
        category_layout.addWidget(self.add_category_btn, 2, 0, 1, 2)

        item_box = QGroupBox("إضافة صنف")
        item_layout = QGridLayout(item_box)
        self.item_category = QComboBox()
        self.item_name = QLineEdit()
        self.item_price = QDoubleSpinBox()
        self.item_price.setMaximum(999999)
        self.item_price.setDecimals(2)
        self.item_price.setSingleStep(0.50)
        self.item_order = QDoubleSpinBox()
        self.item_order.setMaximum(9999)
        self.item_order.setDecimals(0)
        self.item_image = QLineEdit()
        self.item_image.setReadOnly(True)
        browse_btn = QPushButton("اختيار صورة")
        browse_btn.clicked.connect(self.pick_image)
        self.add_item_btn = QPushButton("حفظ الصنف")
        self.add_item_btn.clicked.connect(self.add_item)
        item_layout.addWidget(QLabel("التصنيف"), 0, 0)
        item_layout.addWidget(self.item_category, 1, 0)
        item_layout.addWidget(QLabel("اسم الصنف"), 0, 1)
        item_layout.addWidget(self.item_name, 1, 1)
        item_layout.addWidget(QLabel("السعر"), 2, 0)
        item_layout.addWidget(self.item_price, 3, 0)
        item_layout.addWidget(QLabel("الترتيب"), 2, 1)
        item_layout.addWidget(self.item_order, 3, 1)
        item_layout.addWidget(QLabel("الصورة"), 4, 0)
        item_layout.addWidget(self.item_image, 5, 0)
        item_layout.addWidget(browse_btn, 5, 1)
        item_layout.addWidget(self.add_item_btn, 6, 0, 1, 2)

        form_row.addWidget(category_box)
        form_row.addWidget(item_box)
        layout.addLayout(form_row)

        tables_row = QHBoxLayout()
        tables_row.setSpacing(12)

        self.categories_table = QTableWidget()
        self.categories_table.setColumnCount(3)
        self.categories_table.setHorizontalHeaderLabels(["الاسم", "الترتيب", "الحالة"])
        self.categories_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.categories_table.verticalHeader().setVisible(False)
        self.categories_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.categories_table.setAlternatingRowColors(True)

        self.items_table = QTableWidget()
        self.items_table.setColumnCount(5)
        self.items_table.setHorizontalHeaderLabels(["التصنيف", "اسم الصنف", "السعر", "الحالة", "الصورة"])
        self.items_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.items_table.verticalHeader().setVisible(False)
        self.items_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.items_table.setAlternatingRowColors(True)

        cat_box = QGroupBox("التصنيفات الحالية")
        cat_layout = QVBoxLayout(cat_box)
        cat_layout.addWidget(self.categories_table)

        item_list_box = QGroupBox("الأصناف الحالية")
        item_list_layout = QVBoxLayout(item_list_box)
        item_list_layout.addWidget(self.items_table)

        tables_row.addWidget(cat_box)
        tables_row.addWidget(item_list_box)
        layout.addLayout(tables_row)

        self.load_data()

    def make_stat_card(self, title, value):
        frame = QGroupBox()
        frame.setStyleSheet("QGroupBox { background:#f8fbff; border:1px solid #dbe3ec; border-radius:12px; padding:10px; font-weight:600; }")
        box = QVBoxLayout(frame)
        title_label = QLabel(title)
        title_label.setStyleSheet("color:#64748b;")
        value_label = QLabel(value)
        value_label.setStyleSheet("font-size:22px; font-weight:700; color:#1f3b57;")
        box.addWidget(title_label)
        box.addWidget(value_label)
        frame.value_label = value_label
        return frame

    def pick_image(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "اختيار صورة", "", "Images (*.png *.jpg *.jpeg *.webp)")
        if file_path:
            self.image_path = file_path
            self.item_image.setText(file_path)

    def add_category(self):
        name = self.category_name.text().strip()
        if not name:
            QMessageBox.warning(self, "تنبيه", "ادخل اسم التصنيف")
            return
        sort_order = int(self.category_order.value())
        try:
            self.db.execute_query(
                "INSERT INTO menu_categories (name, sort_order, is_active) VALUES (?, ?, 1)",
                (name, sort_order),
            )
            self.category_name.clear()
            self.category_order.setValue(0)
            self.load_data()
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", str(exc))

    def add_item(self):
        category_id = self.item_category.currentData()
        name = self.item_name.text().strip()
        if not name:
            QMessageBox.warning(self, "تنبيه", "ادخل اسم الصنف")
            return
        price = float(self.item_price.value())
        sort_order = int(self.item_order.value())
        try:
            self.db.execute_query(
                "INSERT INTO menu_items (category_id, name, price, image_path, is_active, sort_order) VALUES (?, ?, ?, ?, 1, ?)",
                (category_id, name, price, self.image_path, sort_order),
            )
            self.item_name.clear()
            self.item_price.setValue(0)
            self.item_order.setValue(0)
            self.item_image.clear()
            self.image_path = ""
            self.load_data()
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", str(exc))

    def load_data(self):
        categories = self.db.fetch_all("SELECT * FROM menu_categories ORDER BY sort_order, name")
        self.item_category.clear()
        self.item_category.addItem("اختر تصنيف", None)
        self.category_count.value_label.setText(str(len(categories)))
        for row, category in enumerate(categories):
            self.item_category.addItem(category["name"], category["id"])
            self.categories_table.setRowCount(len(categories))
            self.categories_table.setItem(row, 0, QTableWidgetItem(category["name"]))
            self.categories_table.setItem(row, 1, QTableWidgetItem(str(category["sort_order"] or 0)))
            self.categories_table.setItem(row, 2, QTableWidgetItem("نشط" if category["is_active"] else "موقف"))

        items = self.db.fetch_all(
            """
            SELECT mi.*, mc.name as category_name
            FROM menu_items mi
            LEFT JOIN menu_categories mc ON mi.category_id = mc.id
            ORDER BY mc.sort_order, mi.sort_order, mi.name
            """
        )
        self.item_count.value_label.setText(str(len(items)))
        self.items_table.setRowCount(len(items))
        for row, item in enumerate(items):
            self.items_table.setItem(row, 0, QTableWidgetItem(item["category_name"] or ""))
            self.items_table.setItem(row, 1, QTableWidgetItem(item["name"]))
            self.items_table.setItem(row, 2, QTableWidgetItem(f"{item['price']:.2f}"))
            self.items_table.setItem(row, 3, QTableWidgetItem("نشط" if item["is_active"] else "موقف"))
            self.items_table.setItem(row, 4, QTableWidgetItem(item["image_path"] or ""))
