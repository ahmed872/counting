import os
import shutil
from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QFileDialog,
)

OPENING_ENTRY_KEY = "opening_balance_entry_id"


class SettingsModule(QWidget):
    """Company details, opening balances, branches, and backup/restore."""

    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
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
        layout.addStretch()

        self.load_all()

    # ---------------- company ----------------

    def build_company_box(self):
        box = QGroupBox("بيانات المنشأة (تظهر في التقارير)")
        form = QFormLayout(box)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.company_name = QLineEdit()
        self.company_tax = QLineEdit()
        save = QPushButton("حفظ بيانات المنشأة")
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
        save.clicked.connect(self.save_opening_balances)
        outer.addWidget(save)
        return box

    def save_opening_balances(self):
        try:
            cash = float(self.opening_cash.text().strip() or 0)
            bank = float(self.opening_bank.text().strip() or 0)
            inventory = float(self.opening_inventory.text().strip() or 0)
        except ValueError:
            QMessageBox.warning(self, "تنبيه", "المبالغ المدخلة غير صحيحة")
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
            self.db.delete_journal_entry(int(existing))

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
        entry_id = self.db.add_journal_entry(
            timestamp, "الأرصدة الافتتاحية للمنشأة", None, items
        )
        self.db.set_setting(OPENING_ENTRY_KEY, entry_id)
        self.db.set_setting("opening_cash", cash)
        self.db.set_setting("opening_bank", bank)
        self.db.set_setting("opening_inventory", inventory)

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
            "كل البيانات موجودة في ملف واحد. احفظ نسخة احتياطية بشكل دوري على "
            "فلاشة أو على الجهاز، حتى لا تفقد بياناتك."
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

    def backup(self):
        default = f"backup-{datetime.now().strftime('%Y-%m-%d-%H%M')}.db"
        path, _ = QFileDialog.getSaveFileName(self, "حفظ نسخة احتياطية", default, "قاعدة بيانات (*.db)")
        if not path:
            return
        try:
            shutil.copyfile(self.db.db_path, path)
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
        self.company_name.setText(self.db.get_setting("company_name", "") or "")
        self.company_tax.setText(self.db.get_setting("company_tax_number", "") or "")
        self.load_opening()
        self.load_branches()

    def refresh_on_show(self):
        self.load_all()
