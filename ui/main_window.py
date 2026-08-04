from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QStackedWidget,
    QLabel,
    QFrame,
    QDateEdit,
    QScrollArea,
    QSizePolicy,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

class MainWindow(QMainWindow):
    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.nav_entries = []
        self.setWindowTitle("نظام إدارة المطعم")
        self.setMinimumSize(1200, 760)
        self.resize(1440, 900)

        # Main Layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QHBoxLayout(main_widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)
        # Scope every container rule by objectName. A bare "background: ...;
        # border-radius: ...;" stylesheet is inherited by *all* descendants,
        # which paints stray borders/rounded corners onto the widgets inside.
        main_widget.setObjectName("appRoot")
        main_widget.setStyleSheet("QWidget#appRoot { background-color: #edf1f5; }")

        # Sidebar
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(230)
        self.sidebar.setStyleSheet(
            "QFrame#sidebar { background-color: #243447; border-radius: 18px; }"
        )
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(16, 20, 16, 16)
        sidebar_layout.setSpacing(10)

        title_label = QLabel("إدارة المطعم")
        title_label.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("padding: 8px 0; color: white;")
        sidebar_layout.addWidget(title_label)
        sidebar_layout.addWidget(self.create_divider())
        sidebar_layout.addSpacing(6)

        self.btn_dashboard = self.create_nav_btn("لوحة التحكم", "🏠")
        self.btn_sales = self.create_nav_btn("المبيعات اليومية", "💰")
        self.btn_purchases = self.create_nav_btn("المشتريات", "🧾")
        self.btn_suppliers = self.create_nav_btn("الموردون", "🚚")
        self.btn_hr = self.create_nav_btn("الموارد البشرية", "👥")
        self.btn_reports = self.create_nav_btn("التقارير", "📊")
        self.btn_accounting = self.create_nav_btn("المحاسبة", "📒")
        self.btn_settings = self.create_nav_btn("الإعدادات", "⚙️")

        # Grouped by what the owner is doing, with the daily work first: the flat
        # list of eight gave no clue which page he needs at the end of a shift.
        sidebar_layout.addWidget(self.btn_dashboard)
        sidebar_layout.addWidget(self.nav_group_label("العمل اليومي"))
        sidebar_layout.addWidget(self.btn_sales)
        sidebar_layout.addWidget(self.btn_purchases)
        sidebar_layout.addWidget(self.btn_suppliers)
        sidebar_layout.addWidget(self.nav_group_label("الموظفون"))
        sidebar_layout.addWidget(self.btn_hr)
        sidebar_layout.addWidget(self.nav_group_label("التقارير والحسابات"))
        sidebar_layout.addWidget(self.btn_reports)
        sidebar_layout.addWidget(self.btn_accounting)
        sidebar_layout.addStretch()
        sidebar_layout.addWidget(self.btn_settings)

        layout.addWidget(self.sidebar)

        # Content Area
        self.content_wrapper = QFrame()
        self.content_wrapper.setObjectName("contentWrapper")
        self.content_wrapper.setStyleSheet(
            "QFrame#contentWrapper { background-color: white; border-radius: 18px; }"
        )
        content_layout = QVBoxLayout(self.content_wrapper)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(0)

        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName("contentStack")
        self.content_stack.setStyleSheet("QStackedWidget#contentStack { background: transparent; }")
        self.content_stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        content_layout.addWidget(self.content_stack)
        layout.addWidget(self.content_wrapper)

        # Initialize Modules
        self.init_modules()
        self.normalize_date_fields()

        self.set_active_page(0)

    def normalize_date_fields(self):
        """Qt's default short-date display is locale-dependent and renders as an
        ambiguous "2026 08 1" here. Pin every date field to ISO format in one
        place instead of at each call site.

        The fields are also forced LTR: under RTL the bidi algorithm reorders
        the hyphen-separated parts, so 2026-08-01 visually reads "01-08-2026",
        which invites real data-entry mistakes on expiry dates."""
        for date_edit in self.findChildren(QDateEdit):
            # Order matters: QDateTimeEdit reverses the section order of the
            # display format for RTL widgets, so the direction must be set to
            # LTR *before* the format, otherwise 2026-08-01 comes out 01-08-2026.
            date_edit.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            date_edit.setDisplayFormat("yyyy-MM-dd")
            date_edit.setCalendarPopup(True)

    def nav_group_label(self, text):
        label = QLabel(text)
        label.setStyleSheet(
            "color: rgba(255,255,255,0.42); font-size: 11px; font-weight: 800;"
            "padding: 10px 16px 2px 0;"
        )
        return label

    def create_nav_btn(self, text, icon=None):
        btn = QPushButton(f"{icon}   {text}" if icon else text)
        btn.setCheckable(True)
        btn.setAutoExclusive(True)
        btn.setFixedHeight(44)
        # Explicit transparent border rather than `border: none` - see the note
        # on QPushButton in ui/theme.py.
        btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #ffffff;
                border: 1px solid transparent;
                border-radius: 10px;
                text-align: right;
                padding-right: 16px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.10);
                border: 1px solid rgba(255, 255, 255, 0.10);
            }
            QPushButton:checked {
                background-color: #4f78a8;
                border: 1px solid #4f78a8;
                font-weight: bold;
            }
        """)
        return btn

    def create_divider(self):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: rgba(255, 255, 255, 0.15);")
        return line

    def add_page(self, label, widget, scrollable=True):
        """Pages are wrapped in a scroll area so content can never be cut off at
        the bottom of the window - on a short screen the user would otherwise
        have no way to reach it, and no hint that it exists. Pages that already
        manage their own scrolling internally pass scrollable=False."""
        if scrollable:
            container = QScrollArea()
            container.setWidgetResizable(True)
            container.setFrameShape(QScrollArea.Shape.NoFrame)
            container.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            container.setWidget(widget)
        else:
            container = widget

        index = self.content_stack.addWidget(container)
        button = getattr(self, f"btn_{label}", None)
        if button is None:
            button = self.create_nav_btn(label)
        button.clicked.connect(lambda checked=False, page_index=index: self.set_active_page(page_index))
        self.nav_entries.append({"label": label, "button": button, "index": index, "page": widget})
        return index

    def set_active_page(self, index):
        self.content_stack.setCurrentIndex(index)
        entry = None
        for item in self.nav_entries:
            item["button"].setChecked(item["index"] == index)
            if item["index"] == index:
                entry = item
        if entry is None:
            return
        refresh = getattr(entry["page"], "refresh_on_show", None)
        if callable(refresh):
            refresh()

    def init_modules(self):
        from ui.dashboard import DashboardModule
        from ui.hr_module import HRModule
        from ui.sales_entry_module import SalesEntryModule
        from ui.purchase_module import PurchaseModule
        from ui.suppliers_module import SuppliersModule
        from ui.reports_module import ReportsModule
        from ui.settings_module import SettingsModule
        from ui.accounting_module import AccountingModule
        from logic.hr import HRLogic

        self.hr_logic = HRLogic(self.db)

        self.dashboard = DashboardModule(self.db)
        self.sales = SalesEntryModule(self.db)
        self.hr = HRModule(self.db, self.hr_logic)
        self.purchases = PurchaseModule(self.db)
        self.suppliers = SuppliersModule(self.db)
        self.reports = ReportsModule(self.db)
        self.settings = SettingsModule(self.db)
        self.accounting = AccountingModule(self.db)

        self.add_page("dashboard", self.dashboard)
        self.add_page("sales", self.sales)
        # HR and Suppliers scroll internally already - wrapping them again would
        # produce two nested scrollbars on the same page.
        self.add_page("hr", self.hr, scrollable=False)
        self.add_page("purchases", self.purchases)
        self.add_page("suppliers", self.suppliers, scrollable=False)
        self.add_page("reports", self.reports)
        self.add_page("accounting", self.accounting)
        self.add_page("settings", self.settings)
