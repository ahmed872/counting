from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QStackedWidget,
    QLabel,
    QFrame,
    QSizePolicy,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

class MainWindow(QMainWindow):
    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.current_role = "admin"
        self.nav_entries = []
        self.setWindowTitle("نظام إدارة المطعم - Mini ERP")
        self.resize(1200, 800)
        
        # Main Layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QHBoxLayout(main_widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)
        main_widget.setStyleSheet("background-color: #edf1f5;")

        # Sidebar
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(230)
        self.sidebar.setStyleSheet("background-color: #243447; color: white; border-radius: 18px;")
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(16, 20, 16, 16)
        sidebar_layout.setSpacing(10)
        
        title_label = QLabel("إدارة المطعم")
        title_label.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("padding: 8px 0; color: white;")
        sidebar_layout.addWidget(title_label)
        sidebar_layout.addWidget(self.create_divider())

        role_row = QHBoxLayout()
        role_row.setSpacing(8)
        self.btn_admin_role = self.create_role_btn("وضع الإدارة")
        self.btn_cashier_role = self.create_role_btn("وضع الكاشير")
        self.btn_admin_role.clicked.connect(lambda: self.set_role("admin"))
        self.btn_cashier_role.clicked.connect(lambda: self.set_role("cashier"))
        role_row.addWidget(self.btn_admin_role)
        role_row.addWidget(self.btn_cashier_role)
        sidebar_layout.addLayout(role_row)

        self.role_hint = QLabel("الصفحات الإدارية مخفية في وضع الكاشير")
        self.role_hint.setWordWrap(True)
        self.role_hint.setStyleSheet("color: rgba(255,255,255,0.75); font-size: 12px; padding: 4px 2px 8px 2px;")
        sidebar_layout.addWidget(self.role_hint)

        self.btn_sales = self.create_nav_btn("المبيعات اليومية")
        self.btn_dashboard = self.create_nav_btn("لوحة التحكم")
        self.btn_hr = self.create_nav_btn("الموارد البشرية")
        self.btn_purchases = self.create_nav_btn("المشتريات")
        self.btn_suppliers = self.create_nav_btn("الموردون")
        self.btn_accounting = self.create_nav_btn("المحاسبة")

        sidebar_layout.addWidget(self.btn_dashboard)
        sidebar_layout.addWidget(self.btn_sales)
        sidebar_layout.addWidget(self.btn_hr)
        sidebar_layout.addWidget(self.btn_purchases)
        sidebar_layout.addWidget(self.btn_suppliers)
        sidebar_layout.addWidget(self.btn_accounting)
        sidebar_layout.addStretch()

        layout.addWidget(self.sidebar)

        # Content Area
        self.content_wrapper = QFrame()
        self.content_wrapper.setStyleSheet("background-color: white; border-radius: 18px;")
        content_layout = QVBoxLayout(self.content_wrapper)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(0)

        self.content_stack = QStackedWidget()
        self.content_stack.setStyleSheet("background: transparent;")
        self.content_stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        content_layout.addWidget(self.content_stack)
        layout.addWidget(self.content_wrapper)

        # Initialize Modules (Placeholders for now)
        self.init_modules()

        self.set_role("admin")

    def create_role_btn(self, text):
        btn = QPushButton(text)
        btn.setCheckable(True)
        btn.setMinimumHeight(36)
        btn.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,0.08); color: white; border: 1px solid rgba(255,255,255,0.15); border-radius: 10px; padding: 8px 10px; font-size: 12px; }"
            "QPushButton:checked { background: #4f78a8; border-color: #4f78a8; font-weight: 700; }"
            "QPushButton:hover { background: rgba(255,255,255,0.14); }"
        )
        return btn

    def create_nav_btn(self, text):
        btn = QPushButton(text)
        btn.setCheckable(True)
        btn.setAutoExclusive(True)
        btn.setFixedHeight(48)
        btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: white;
                border: none;
                border-radius: 10px;
                text-align: right;
                padding-right: 16px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.08);
            }
            QPushButton:checked {
                background-color: #4f78a8;
                font-weight: bold;
            }
        """)
        return btn

    def create_divider(self):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: rgba(255, 255, 255, 0.15);")
        return line

    def add_page(self, label, widget, roles):
        index = self.content_stack.addWidget(widget)
        button = getattr(self, f"btn_{label}", None)
        if button is None:
            button = self.create_nav_btn(label)
        button.clicked.connect(lambda checked=False, page_index=index: self.set_active_page(page_index))
        self.nav_entries.append({"label": label, "button": button, "index": index, "roles": set(roles)})
        return index

    def visible_pages(self):
        return [entry for entry in self.nav_entries if self.current_role in entry["roles"]]

    def apply_role_visibility(self):
        for entry in self.nav_entries:
            visible = self.current_role in entry["roles"]
            entry["button"].setVisible(visible)
        self.btn_admin_role.setChecked(self.current_role == "admin")
        self.btn_cashier_role.setChecked(self.current_role == "cashier")
        self.role_hint.setText("الصفحات الإدارية مخفية في وضع الكاشير" if self.current_role == "cashier" else "كل صفحات الإدارة متاحة")

        visible = self.visible_pages()
        if visible:
            current_index = self.content_stack.currentIndex()
            if not any(entry["index"] == current_index for entry in visible):
                return

    def set_role(self, role):
        self.current_role = role
        self.apply_role_visibility()
        preferred_label = "dashboard" if role == "admin" else "sales"
        preferred_page = next((entry for entry in self.nav_entries if entry["label"] == preferred_label and role in entry["roles"]), None)
        if preferred_page:
            self.set_active_page(preferred_page["index"])

    def set_active_page(self, index):
        self.content_stack.setCurrentIndex(index)
        for entry in self.nav_entries:
            entry["button"].setChecked(entry["index"] == index)
        widget = self.content_stack.widget(index)
        refresh = getattr(widget, "refresh_on_show", None)
        if callable(refresh):
            refresh()

    def init_modules(self):
        from ui.dashboard import DashboardModule
        from ui.hr_module import HRModule
        from ui.sales_entry_module import SalesEntryModule
        from ui.purchase_module import PurchaseModule
        from ui.suppliers_module import SuppliersModule
        from ui.accounting_module import AccountingModule
        from logic.hr import HRLogic

        self.hr_logic = HRLogic(self.db)

        self.dashboard = DashboardModule(self.db)
        self.sales = SalesEntryModule(self.db)
        self.hr = HRModule(self.db, self.hr_logic)
        self.purchases = PurchaseModule(self.db)
        self.suppliers = SuppliersModule(self.db)
        self.accounting = AccountingModule(self.db)

        self.add_page("dashboard", self.dashboard, roles=("admin",))
        self.add_page("sales", self.sales, roles=("admin", "cashier"))
        self.add_page("hr", self.hr, roles=("admin",))
        self.add_page("purchases", self.purchases, roles=("admin",))
        self.add_page("suppliers", self.suppliers, roles=("admin",))
        self.add_page("accounting", self.accounting, roles=("admin",))
