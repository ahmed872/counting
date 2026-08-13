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

# One spacing scale, used everywhere below instead of ad-hoc numbers -
# a login screen assembled from whatever margin "looked about right" in
# each spot is exactly what read as "بدائي" (amateurish): the gap under
# the header, the gap between a label and its field, and the gap between
# one field group and the next were all different sizes with no reason
# for any of them to differ.
_XS, _SM, _MD, _LG, _XL = 4, 8, 16, 24, 36


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
        self.setMinimumWidth(440)
        self.setFixedWidth(440)
        # A soft off-white, not stark white - the input fields below stay
        # pure white on top of it, which is what actually gives the form
        # its own sense of depth (a card sitting on a surface) instead of
        # everything - dialog, fields, background - being the identical
        # shade of white with only thin borders to tell them apart.
        self.setStyleSheet("QDialog { background-color: #eef1f6; }")
        self.build()

    def build(self):
        # A dark header band (logo, title, subtitle) over the body, instead
        # of everything sitting flat on one plain background - reported
        # live as looking too basic. Only the header gets its own
        # background colour: it holds nothing but labels (styled
        # explicitly below, not relying on the app-wide QSS), so it cannot
        # be the container that stops that QSS from cascading down to a
        # button - see the dialog-stylesheet test this file ships with,
        # and the QScrollArea case in add_page (main_window.py) that test
        # guards against.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget()
        header.setStyleSheet("background-color: #1f3b57;")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(_XL, _LG + _XS, _XL, _LG)
        header_layout.setSpacing(_SM)

        from logic.paths import icon_path
        logo_frame = QLabel()
        logo_frame.setFixedSize(64, 64)
        logo_frame.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_frame.setStyleSheet(
            "background: transparent;")
        pixmap = QPixmap(icon_path())
        if not pixmap.isNull():
            logo_frame.setPixmap(pixmap.scaled(
                36, 36, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
        header_layout.addWidget(logo_frame, 0, Qt.AlignmentFlag.AlignHCenter)
        header_layout.addSpacing(_XS)

        title = QLabel("نظام إدارة المطعم")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: 800; color: #ffffff;")
        header_layout.addWidget(title)

        subtitle = QLabel("سجّل دخولك للمتابعة")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color:#a9bcd0; font-size:13px;")
        header_layout.addWidget(subtitle)

        outer.addWidget(header)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(_XL, _LG, _XL, _MD)
        body_layout.setSpacing(0)

        self.stack = QStackedWidget()
        body_layout.addWidget(self.stack)
        self.stack.addWidget(self._build_login_page())
        self.stack.addWidget(self._build_change_password_page())

        signature = QLabel("تطوير: أحمد  •  01093033884")
        signature.setAlignment(Qt.AlignmentFlag.AlignCenter)
        signature.setStyleSheet(
            f"color:#9aa7b8; font-size:11px; margin-top:{_MD}px;")
        body_layout.addWidget(signature)

        outer.addWidget(body)

    def _field(self, layout, caption, placeholder, password=False, on_enter=None):
        """One label+input pair, spaced as a single tight unit (the label
        sits right against its own field) with a uniform gap before the
        next pair - the two different jobs a gap can do here (inside a
        pair vs between pairs) had the same size before, which is what
        made the form read as an undifferentiated stack of lines instead
        of grouped fields."""
        label = QLabel(caption)
        label.setStyleSheet(
            f"font-weight:600; color:#475569; font-size:12.5px; "
            f"margin-bottom:{_XS}px;")
        layout.addWidget(label)

        field = QLineEdit()
        field.setPlaceholderText(placeholder)
        field.setMinimumHeight(44)
        field.setStyleSheet(
            "QLineEdit {"
            "  border: 1.5px solid #dbe2ea; border-radius: 10px;"
            "  padding: 0 14px; font-size: 14px; background: #ffffff;"
            "}"
            "QLineEdit:focus { border: 1.5px solid #2c5a82; }")
        if password:
            field.setEchoMode(QLineEdit.EchoMode.Password)
        if on_enter:
            field.returnPressed.connect(on_enter)
        layout.addWidget(field)
        layout.addSpacing(_MD)
        return field

    def _primary_button(self, layout, text, on_click):
        btn = QPushButton(text)
        btn.setMinimumHeight(46)
        btn.setStyleSheet(
            "QPushButton {"
            "  background-color: #1f3b57; color: #ffffff; border: none;"
            "  border-radius: 10px; font-size: 14px; font-weight: 700;"
            "}"
            "QPushButton:hover { background-color: #2c4d6d; }"
            "QPushButton:pressed { background-color: #17293c; }")
        btn.clicked.connect(on_click)
        layout.addWidget(btn)
        return btn

    def _build_login_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.username_field = self._field(
            layout, "اسم المستخدم", "اكتب اسم المستخدم", on_enter=self.try_login)
        self.password_field = self._field(
            layout, "كلمة المرور", "اكتب كلمة المرور", password=True, on_enter=self.try_login)

        self.login_status = QLabel()
        self.login_status.setWordWrap(True)
        self.login_status.setVisible(False)
        layout.addWidget(self.login_status)

        layout.addSpacing(_XS)
        self._primary_button(layout, "دخول", self.try_login)

        return page

    def _build_change_password_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        notice = QLabel(
            "هذه كلمة مرور مؤقتة - اختر كلمة مرور جديدة خاصة بك لإكمال الدخول."
        )
        notice.setWordWrap(True)
        notice.setStyleSheet(
            "color:#9a5a06; background:#fdf3e2; border:1px solid #f0d4a3;"
            f"border-radius:10px; padding:{_SM+2}px {_MD}px; font-weight:600;"
            f"font-size:12.5px;")
        layout.addWidget(notice)
        layout.addSpacing(_MD)

        self.new_password_field = self._field(
            layout, "كلمة المرور الجديدة", "6 خانات على الأقل", password=True)
        self.confirm_password_field = self._field(
            layout, "تأكيد كلمة المرور الجديدة", "اكتبها مرة أخرى",
            password=True, on_enter=self.try_change_password)

        self.change_status = QLabel()
        self.change_status.setWordWrap(True)
        self.change_status.setVisible(False)
        layout.addWidget(self.change_status)

        layout.addSpacing(_XS)
        self._primary_button(layout, "حفظ كلمة المرور والدخول", self.try_change_password)

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
            # A locked account gets a specific, honest message; a plain
            # wrong password still shows the deliberately generic one (see
            # AuthLogic.authenticate) so a login attempt cannot be used to
            # probe which usernames exist.
            minutes = self.auth.lockout_status(username)
            if minutes is not None:
                self._show_status(
                    self.login_status,
                    f"محاولات كثيرة خاطئة. حاول مرة أخرى بعد {minutes} دقيقة تقريباً.",
                    ok=False)
            else:
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
