"""Lets whoever is logged in change their own password later, on their own
terms - not just the one forced change a temporary password triggers at
login (see ui/login_dialog.py). Reachable from the sidebar regardless of
role, since Settings itself - where everything else about an account lives
- is admin-only and a manager or viewer never sees it.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox

from logic.auth import AuthLogic


class ChangePasswordDialog(QDialog):
    def __init__(self, db, user_id, parent=None):
        super().__init__(parent)
        self.db = db
        self.user_id = user_id
        self.auth = AuthLogic(db)

        self.setWindowTitle("تغيير كلمة المرور")
        from logic.paths import set_window_icon
        set_window_icon(self)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setMinimumWidth(420)
        # See the same fix in login_dialog.py - a QDialog otherwise paints
        # the palette's plain grey Window colour instead of a clean card.
        self.setStyleSheet("QDialog { background-color: #ffffff; }")
        self.build()

    def _field_label(self, text):
        label = QLabel(text)
        label.setStyleSheet("font-weight:700; color:#334155;")
        return label

    def build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)

        layout.addWidget(self._field_label("كلمة المرور الحالية"))
        self.old_password = QLineEdit()
        self.old_password.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.old_password)

        layout.addWidget(self._field_label("كلمة المرور الجديدة"))
        self.new_password = QLineEdit()
        self.new_password.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.new_password)

        layout.addWidget(self._field_label("تأكيد كلمة المرور الجديدة"))
        self.confirm_password = QLineEdit()
        self.confirm_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_password.returnPressed.connect(self.try_save)
        layout.addWidget(self.confirm_password)

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setVisible(False)
        layout.addWidget(self.status)

        save_btn = QPushButton("حفظ")
        save_btn.setMinimumHeight(40)
        save_btn.clicked.connect(self.try_save)
        layout.addWidget(save_btn)

    def _show_status(self, text, ok):
        self.status.setText(text)
        self.status.setStyleSheet(
            f"font-weight:700; padding:8px 10px; border-radius:8px;"
            f"color:{'#15803d' if ok else '#b91c1c'};"
            f"background:{'#f0fdf4' if ok else '#fef2f2'};"
            f"border:1px solid {'#bbf7d0' if ok else '#fecaca'};")
        self.status.setVisible(True)

    def try_save(self):
        new_password = self.new_password.text()
        if len(new_password) < 6:
            self._show_status("كلمة المرور يجب ألا تقل عن 6 خانات.", ok=False)
            return
        if new_password != self.confirm_password.text():
            self._show_status("كلمتا المرور غير متطابقتين.", ok=False)
            return
        try:
            self.auth.change_own_password(self.user_id, self.old_password.text(), new_password)
        except ValueError as exc:
            self._show_status(str(exc), ok=False)
            return
        QMessageBox.information(self, "تم", "تم تغيير كلمة المرور.")
        self.accept()
