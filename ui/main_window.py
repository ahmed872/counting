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
    QLineEdit,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QPalette, QColor

class MainWindow(QMainWindow):
    def __init__(self, db_manager, current_user=None):
        super().__init__()
        self.db = db_manager
        # Callers that never heard of login (every existing test, and any
        # future one-off script) get full admin behaviour by default rather
        # than being forced to construct a user just to open the window.
        self.current_user = current_user or {
            "id": None, "username": "admin", "role": "admin",
            "display_name": "أدمن", "must_change_password": False,
        }
        self.nav_entries = []
        self.setWindowTitle("نظام إدارة المطعم")
        from logic.paths import set_window_icon
        set_window_icon(self)
        self.setMinimumSize(1040, 640)
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

        self.btn_dashboard = self.create_nav_btn("لوحة التحكم")
        self.btn_sales = self.create_nav_btn("المبيعات اليومية")
        self.btn_customers = self.create_nav_btn("العملاء")
        self.btn_purchases = self.create_nav_btn("المشتريات")
        self.btn_suppliers = self.create_nav_btn("الموردون")
        self.btn_hr = self.create_nav_btn("الموارد البشرية")
        self.btn_reports = self.create_nav_btn("التقارير")
        self.btn_accounting = self.create_nav_btn("المحاسبة")
        self.btn_other_balances = self.create_nav_btn("القروض والمقدّمة")
        self.btn_settings = self.create_nav_btn("الإعدادات")

        # The nav list kept growing (8 buttons, now 9, plus group labels) with
        # no scroll of its own - on a normal-height window it simply ran out
        # of room, and Qt does not show an overflowing QVBoxLayout, it
        # compresses it: the trial countdown ended up overlapping the last
        # nav button instead of either being visible. The nav list scrolls
        # internally now; the trial banner and Settings stay pinned outside
        # it, since those two must always be reachable regardless of how
        # many pages get added later.
        nav_scroll = QScrollArea()
        nav_scroll.setWidgetResizable(True)
        nav_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        nav_scroll.setStyleSheet("QScrollArea { background: transparent; }")
        nav_list_widget = QWidget()
        nav_list_widget.setStyleSheet("background: transparent;")
        nav_list = QVBoxLayout(nav_list_widget)
        nav_list.setContentsMargins(0, 0, 0, 0)
        nav_list.setSpacing(10)

        # Grouped by what the owner is doing, with the daily work first: the flat
        # list of eight gave no clue which page he needs at the end of a shift.
        nav_list.addWidget(self.btn_dashboard)
        nav_list.addWidget(self.nav_group_label("العمل اليومي"))
        nav_list.addWidget(self.btn_sales)
        nav_list.addWidget(self.btn_customers)
        nav_list.addWidget(self.btn_purchases)
        nav_list.addWidget(self.btn_suppliers)
        nav_list.addWidget(self.nav_group_label("الموظفون"))
        nav_list.addWidget(self.btn_hr)
        nav_list.addWidget(self.nav_group_label("التقارير والحسابات"))
        nav_list.addWidget(self.btn_reports)
        nav_list.addWidget(self.btn_accounting)
        nav_list.addWidget(self.btn_other_balances)
        nav_list.addStretch()
        nav_scroll.setWidget(nav_list_widget)
        sidebar_layout.addWidget(nav_scroll, 1)

        self.trial_banner = QLabel()
        self.trial_banner.setWordWrap(True)
        self.trial_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.trial_banner.setVisible(False)
        sidebar_layout.addWidget(self.trial_banner)
        # Reachable regardless of role - unlike everything else about an
        # account, which lives inside Settings and is admin-only (see
        # apply_role_restrictions). A manager or viewer still needs a way to
        # change their own password later, not just the one forced change a
        # temporary password triggers at login.
        self.btn_change_password = QPushButton("تغيير كلمة المرور")
        self.btn_change_password.setFixedHeight(38)
        self.btn_change_password.setStyleSheet(
            "QPushButton { background-color: transparent; color: rgba(255,255,255,0.75);"
            "  border: 1px solid rgba(255,255,255,0.2); border-radius: 10px; font-size: 12px; }"
            "QPushButton:hover { background-color: rgba(255,255,255,0.10); color: #ffffff; }"
        )
        self.btn_change_password.clicked.connect(self.open_change_password_dialog)
        sidebar_layout.addWidget(self.btn_change_password)
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
        self.apply_role_restrictions()

        self.set_active_page(0)

    def open_change_password_dialog(self):
        from ui.change_password_dialog import ChangePasswordDialog
        user_id = self.current_user.get("id")
        if user_id is None:
            return
        ChangePasswordDialog(self.db, user_id, parent=self).exec()

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

    def set_trial_banner(self, days_left):
        """Show how much of the evaluation period is left, so the expiry is
        never a surprise on the day it happens."""
        if days_left is None:
            self.trial_banner.setVisible(False)
            return
        from logic.trial import arabic_days
        urgent = days_left <= 2
        self.trial_banner.setText(
            "نسخة تجريبية\nينتهي غداً" if days_left == 1
            else f"نسخة تجريبية\nمتبقٍ {arabic_days(days_left)}"
        )
        self.trial_banner.setStyleSheet(
            f"color: {'#ffd8d4' if urgent else 'rgba(255,255,255,0.72)'};"
            f"background: {'rgba(220,38,38,0.28)' if urgent else 'rgba(255,255,255,0.07)'};"
            "border-radius: 8px; padding: 8px 6px; font-size: 12px; font-weight: 700;"
        )
        self.trial_banner.setVisible(True)

    def nav_group_label(self, text):
        label = QLabel(text)
        label.setStyleSheet(
            "color: rgba(255,255,255,0.42); font-size: 11px; font-weight: 800;"
            "padding: 10px 16px 2px 0;"
        )
        return label

    def create_nav_btn(self, text):
        btn = QPushButton(text)
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
            # Both the QScrollArea's own viewport AND the page widget it wraps
            # paint the palette's plain grey Window colour wherever nothing
            # else covers a pixel - a label's own background is transparent,
            # so it is the page widget behind it that actually shows through
            # its padding and the gaps between widgets. Every page lives
            # inside the white, rounded content card, so any such gap showed
            # as a hard-edged grey patch against it - most visible right at
            # the top corner next to the page title, where the scrollbar
            # starts. Fixed through the palette, not setStyleSheet(): giving
            # *any* widget its own stylesheet - even a one-line "background:
            # transparent" - makes Qt stop cascading the app-wide QSS to
            # everything below it in that subtree, which silently strips
            # every button inside the page back to an unstyled, textless
            # outline (found rendering the delivery-apps sales field this
            # way). The palette has no such side effect.
            white = QPalette(container.viewport().palette())
            white.setColor(QPalette.ColorRole.Window, QColor("#ffffff"))
            container.viewport().setPalette(white)
            container.setPalette(white)
            widget.setPalette(white)
            widget.setAutoFillBackground(True)
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
        from ui.customers_module import CustomersModule
        from ui.reports_module import ReportsModule
        from ui.settings_module import SettingsModule
        from ui.accounting_module import AccountingModule
        from ui.other_balances_module import OtherBalancesModule
        from logic.hr import HRLogic

        self.hr_logic = HRLogic(self.db)

        self.dashboard = DashboardModule(self.db)
        self.sales = SalesEntryModule(self.db)
        self.hr = HRModule(self.db, self.hr_logic)
        self.purchases = PurchaseModule(self.db)
        self.suppliers = SuppliersModule(self.db)
        self.customers = CustomersModule(self.db)
        self.reports = ReportsModule(self.db)
        self.settings = SettingsModule(self.db, current_user=self.current_user)
        self.accounting = AccountingModule(self.db)
        self.other_balances = OtherBalancesModule(self.db)

        # Every table on every page now sizes itself to fit all of its own
        # rows (see fit_table_height in common_widgets.py) instead of being
        # boxed into a fixed height with its own small, easy-to-miss
        # scrollbar - that is what let a payroll table show two of three
        # employees with the third one simply gone from view. With that in
        # place, every page can scroll as a whole - the same big,
        # high-contrast scrollbar used throughout the app (see the note in
        # theme.py), one consistent way to reach anything that does not fit,
        # instead of a different rule on every screen. "التقارير" is the one
        # exception: its QTextBrowser already scrolls its own long report
        # content, and wrapping that in a second, outer scroll area produces
        # exactly the nested-scroll confusion this change is fixing everywhere
        # else - see the dashboard alerts-table fix earlier for what that
        # looked like in practice.
        self.add_page("dashboard", self.dashboard)
        self.add_page("sales", self.sales)
        self.add_page("hr", self.hr)
        self.add_page("purchases", self.purchases)
        self.add_page("suppliers", self.suppliers)
        self.add_page("customers", self.customers)
        self.add_page("reports", self.reports, scrollable=False)
        self.add_page("accounting", self.accounting)
        self.add_page("other_balances", self.other_balances)
        self.add_page("settings", self.settings)

    def apply_role_restrictions(self):
        """Settings - company info, backup, the licence, and the user list
        itself - is an admin-only area: a manager or viewer never sees the
        nav button at all, let alone what is behind it. A viewer additionally
        cannot change anything anywhere else either - every button, text
        field, dropdown and date picker on every other page is disabled,
        leaving tables and labels exactly as readable as before. Dashboard
        and reports are exempt: neither has anything that mutates data in
        the first place - a dropdown that only changes what a filter shows,
        or a report/print button, are not something a viewer needs blocked
        from using."""
        role = self.current_user.get("role")
        if role != "admin":
            self.btn_settings.setVisible(False)
        if role == "viewer":
            for entry in self.nav_entries:
                if entry["label"] in ("dashboard", "reports"):
                    continue
                self._lock_page_for_viewing(entry["page"])

    def _lock_page_for_viewing(self, page):
        # A handful of verbs that only ever look at data, never change it -
        # printing or exporting a report, refreshing a list, searching it.
        safe_keywords = ("طباعة", "تصدير", "تحديث", "نسخ", "بحث")
        for button in page.findChildren(QPushButton):
            if any(word in button.text() for word in safe_keywords):
                continue
            button.setEnabled(False)
        for field in page.findChildren(QLineEdit):
            if not field.isReadOnly():
                field.setEnabled(False)
        for combo in page.findChildren(QComboBox):
            combo.setEnabled(False)
        for date_edit in page.findChildren(QDateEdit):
            date_edit.setEnabled(False)
        for spin in page.findChildren(QSpinBox):
            spin.setEnabled(False)
        for spin in page.findChildren(QDoubleSpinBox):
            spin.setEnabled(False)
