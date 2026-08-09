"""Who is opening the program today.

Two steps in one dialog, not two dialogs: username/password, and - only when
the account still carries a seeded or admin-reset password - a forced
"choose your own password" step before the login actually completes. A
second dialog popping up after the first already closed reads as a second,
unrelated interruption; a step inside the same window reads as one login
that is not quite finished yet.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QStackedWidget,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QLabel,
    QLineEdit,
    QPushButton,
    QMessageBox,
)

from logic.auth import AuthLogic


class LoginDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.auth = AuthLogic(db)
        self.authenticated_user = None
        self._pending_user_id = None

        self.setWindowTitle("تسجيل الدخول")
        from logic.paths import set_window_icon
        set_window_icon(self)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setMinimumWidth(500)
        # An explicit white background - a QDialog otherwise paints the
        # palette's plain grey Window colour, which read as unfinished
        # sitting on top of the desktop rather than a proper card.
        self.setStyleSheet("QDialog { background-color: #ffffff; }")
        self.build()

    def build(self):
        # A dark header band (logo, title, subtitle) over a plain white
        # form card, instead of everything sitting flat on one white
        # background - reported live as looking too basic. Only the header
        # gets its own background colour: it holds nothing but labels
        # (styled explicitly below, not relying on the app-wide QSS), so it
        # cannot be the container that stops that QSS from cascading down
        # to a button - see the dialog-stylesheet test this file ships
        # with, and the QScrollArea case in add_page (main_window.py) that
        # test guards against.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget()
        header.setStyleSheet("background-color: #1f3b57;")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(36, 34, 36, 28)
        header_layout.setSpacing(8)

        from logic.paths import icon_path
        logo = QLabel()
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap(icon_path())
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaled(
                56, 56, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
            header_layout.addWidget(logo)

        title = QLabel("نظام إدارة المطعم")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 21px; font-weight: 800; color: #ffffff;")
        header_layout.addWidget(title)

        subtitle = QLabel("سجّل دخولك للمتابعة")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color:#b9c8db; font-size:13px;")
        header_layout.addWidget(subtitle)

        outer.addWidget(header)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(36, 30, 36, 30)
        body_layout.setSpacing(18)

        self.stack = QStackedWidget()
        body_layout.addWidget(self.stack)
        self.stack.addWidget(self._build_login_page())
        self.stack.addWidget(self._build_change_password_page())

        outer.addWidget(body)

    def _field_label(self, text):
        label = QLabel(text)
        label.setStyleSheet("font-weight:700; color:#334155;")
        return label

    def _build_login_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(14)

        layout.addWidget(self._field_label("اسم المستخدم"))
        self.username_field = QLineEdit()
        self.username_field.setPlaceholderText("اكتب اسم المستخدم")
        self.username_field.returnPressed.connect(self.try_login)
        layout.addWidget(self.username_field)

        layout.addWidget(self._field_label("كلمة المرور"))
        self.password_field = QLineEdit()
        self.password_field.setPlaceholderText("اكتب كلمة المرور")
        self.password_field.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_field.returnPressed.connect(self.try_login)
        layout.addWidget(self.password_field)

        self.login_status = QLabel()
        self.login_status.setWordWrap(True)
        self.login_status.setVisible(False)
        layout.addWidget(self.login_status)

        login_btn = QPushButton("دخول")
        login_btn.setMinimumHeight(44)
        login_btn.clicked.connect(self.try_login)
        layout.addWidget(login_btn)

        return page

    def _build_change_password_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(14)

        notice = QLabel(
            "هذه كلمة مرور مؤقتة - اختر كلمة مرور جديدة خاصة بك لإكمال الدخول."
        )
        notice.setWordWrap(True)
        notice.setStyleSheet(
            "color:#9a5a06; background:#fdf3e2; border:1px solid #f0d4a3;"
            "border-radius:8px; padding:10px 12px; font-weight:700;")
        layout.addWidget(notice)

        layout.addWidget(self._field_label("كلمة المرور الجديدة"))
        self.new_password_field = QLineEdit()
        self.new_password_field.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.new_password_field)

        layout.addWidget(self._field_label("تأكيد كلمة المرور الجديدة"))
        self.confirm_password_field = QLineEdit()
        self.confirm_password_field.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_password_field.returnPressed.connect(self.try_change_password)
        layout.addWidget(self.confirm_password_field)

        self.change_status = QLabel()
        self.change_status.setWordWrap(True)
        self.change_status.setVisible(False)
        layout.addWidget(self.change_status)

        confirm_btn = QPushButton("حفظ كلمة المرور والدخول")
        confirm_btn.setMinimumHeight(44)
        confirm_btn.clicked.connect(self.try_change_password)
        layout.addWidget(confirm_btn)

        return page

    def _show_status(self, label, text, ok):
        label.setText(text)
        label.setStyleSheet(
            f"font-weight:700; padding:9px 11px; border-radius:8px;"
            f"color:{'#15803d' if ok else '#b91c1c'};"
            f"background:{'#f0fdf4' if ok else '#fef2f2'};"
            f"border:1px solid {'#bbf7d0' if ok else '#fecaca'};")
        label.setVisible(True)

    def try_login(self):
        username = self.username_field.text()
        password = self.password_field.text()
        if not username.strip() or not password:
            self._show_status(self.login_status, "اكتب اسم المستخدم وكلمة المرور.", ok=False)
            return

        user = self.auth.authenticate(username, password)
        if user is None:
            self._show_status(
                self.login_status, "اسم المستخدم أو كلمة المرور غير صحيحة.", ok=False)
            return

        if user["must_change_password"]:
            self._pending_user_id = user["id"]
            self.stack.setCurrentIndex(1)
            return

        self.authenticated_user = user
        self.accept()

    def try_change_password(self):
        new_password = self.new_password_field.text()
        confirm_password = self.confirm_password_field.text()
        if len(new_password) < 6:
            self._show_status(
                self.change_status, "كلمة المرور يجب ألا تقل عن 6 خانات.", ok=False)
            return
        if new_password != confirm_password:
            self._show_status(self.change_status, "كلمتا المرور غير متطابقتين.", ok=False)
            return

        self.auth.set_password(self._pending_user_id, new_password, must_change_password=False)
        row = self.db.fetch_one("SELECT * FROM users WHERE id = ?", (self._pending_user_id,))
        self.authenticated_user = self.auth._public(row)
        QMessageBox.information(self, "تم", "تم حفظ كلمة المرور الجديدة.")
        self.accept()
