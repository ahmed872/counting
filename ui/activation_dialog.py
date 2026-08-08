"""The screen the customer sees when the evaluation period runs out.

This is the only screen in the program that a non-technical person meets while
already annoyed, so it does one thing at a time and says what to do in the order
he has to do it: here is your number, send it, paste what comes back.

It matters that activation lives *here*. Blocking startup with a plain message
and exiting leaves nowhere to type a key - the customer would have to be told to
find some other screen in a program that will not open. The box that stops him
is the same box that lets him in.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QApplication,
    QMessageBox,
)

from logic.licence import activate, device_code


class ActivationDialog(QDialog):
    def __init__(self, db, message, parent=None):
        super().__init__(parent)
        self.db = db
        self.activated = False
        self.setWindowTitle("تفعيل البرنامج")
        from logic.paths import set_window_icon
        set_window_icon(self)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setMinimumWidth(560)
        self.build(message)

    def build(self, message):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)

        title = QLabel("انتهت مدة النسخة التجريبية")
        title.setStyleSheet("font-size: 21px; font-weight: 800; color: #1f3b57;")
        layout.addWidget(title)

        body = QLabel(message)
        body.setWordWrap(True)
        body.setStyleSheet("color: #334155; font-size: 14px;")
        layout.addWidget(body)

        reassurance = QLabel(
            "بياناتك كلها محفوظة ولم يُحذف منها شيء.\n"
            "بمجرد إدخال مفتاح التفعيل يكمل البرنامج من حيث توقّف بالضبط."
        )
        reassurance.setWordWrap(True)
        reassurance.setStyleSheet(
            "color:#15803d; background:#f0fdf4; border:1px solid #bbf7d0;"
            "border-radius:8px; padding:10px 12px; font-weight:700;")
        layout.addWidget(reassurance)

        step_one = QLabel("١ — أرسل رقم الجهاز هذا لمزوّد البرنامج:")
        step_one.setStyleSheet("font-weight:800; color:#1f3b57; font-size:14px;")
        layout.addWidget(step_one)

        code_row = QHBoxLayout()
        code_row.setSpacing(8)
        self.code_field = QLineEdit(device_code(self.db))
        self.code_field.setReadOnly(True)
        self.code_field.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.code_field.setStyleSheet(
            "font-size:22px; font-weight:800; letter-spacing:3px; color:#1f3b57;"
            "background:#eef6ff; border:1px solid #cfe0f5; border-radius:8px; padding:10px;")
        copy_btn = QPushButton("نسخ الرقم")
        copy_btn.clicked.connect(self.copy_code)
        code_row.addWidget(self.code_field, 1)
        code_row.addWidget(copy_btn)
        layout.addLayout(code_row)

        step_two = QLabel("٢ — اكتب المفتاح الذي وصلك هنا:")
        step_two.setStyleSheet("font-weight:800; color:#1f3b57; font-size:14px;")
        layout.addWidget(step_two)

        self.key_field = QLineEdit()
        self.key_field.setPlaceholderText("XXXX-XXXX-XXXX-XXXX")
        self.key_field.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.key_field.setStyleSheet(
            "font-size:19px; font-weight:700; letter-spacing:2px; padding:10px;")
        self.key_field.returnPressed.connect(self.try_activate)
        layout.addWidget(self.key_field)

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setVisible(False)
        layout.addWidget(self.status)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        activate_btn = QPushButton("تفعيل البرنامج")
        activate_btn.setMinimumHeight(44)
        activate_btn.clicked.connect(self.try_activate)
        close_btn = QPushButton("إغلاق")
        close_btn.setMinimumHeight(44)
        close_btn.setStyleSheet(
            "QPushButton { background-color:#64748b; border:1px solid #475569; }"
            "QPushButton:hover { background-color:#475569; border:1px solid #334155; }")
        close_btn.clicked.connect(self.reject)
        buttons.addWidget(activate_btn, 2)
        buttons.addWidget(close_btn, 1)
        layout.addLayout(buttons)

    def copy_code(self):
        QApplication.clipboard().setText(self.code_field.text())
        self.show_status("تم نسخ الرقم. أرسله عبر الواتساب.", ok=True)

    def show_status(self, text, ok):
        self.status.setText(text)
        self.status.setStyleSheet(
            f"font-weight:800; padding:9px 11px; border-radius:8px;"
            f"color:{'#15803d' if ok else '#b91c1c'};"
            f"background:{'#f0fdf4' if ok else '#fef2f2'};"
            f"border:1px solid {'#bbf7d0' if ok else '#fecaca'};")
        self.status.setVisible(True)

    def try_activate(self):
        typed = self.key_field.text().strip()
        if not typed:
            self.show_status("اكتب مفتاح التفعيل أولاً.", ok=False)
            return

        if activate(self.db, typed):
            self.activated = True
            QMessageBox.information(
                self, "تم التفعيل",
                "تم تفعيل البرنامج بنجاح.\n\n"
                "كل بياناتك كما هي، والبرنامج يعمل الآن بلا مدة.",
            )
            self.accept()
            return

        self.show_status(
            "المفتاح غير صحيح لهذا الجهاز.\n"
            "تأكد أنك أرسلت رقم الجهاز الظاهر أعلاه، وأن المفتاح كما وصلك تماماً.",
            ok=False,
        )
