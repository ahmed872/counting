from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel


def create_stat_card(title, value, accent_color="#4f78a8"):
    """A plain light card with a colored top accent bar and dark text.
    Deliberately avoids white-text-on-solid-color: that combination has
    repeatedly rendered illegible on some Windows/Qt setups."""
    frame = QFrame()
    frame.setMinimumHeight(110)
    frame.setMinimumWidth(200)
    frame.setStyleSheet(
        "QFrame {"
        "  background-color: #ffffff;"
        "  border: 1px solid #e2e8f0;"
        f"  border-top: 5px solid {accent_color};"
        "  border-radius: 12px;"
        "}"
    )
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(6)

    title_label = QLabel(title)
    title_label.setWordWrap(True)
    title_label.setStyleSheet("color:#64748b; font-size:13px; font-weight:600; background: transparent;")

    value_label = QLabel(value)
    value_label.setWordWrap(True)
    value_label.setStyleSheet("color:#1f2937; font-size:22px; font-weight:800; background: transparent;")

    layout.addWidget(title_label)
    layout.addStretch()
    layout.addWidget(value_label)

    frame.value_label = value_label
    return frame
