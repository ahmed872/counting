from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel


def create_stat_card(title, value, accent_color="#4f78a8"):
    """A plain light card with a colored top accent bar and dark text.

    NOTE: the stylesheet selector MUST be scoped by objectName. QLabel is a
    subclass of QFrame, so a bare `QFrame { ... }` rule would also style every
    label inside the card - giving each one its own border and accent bar.
    """
    frame = QFrame()
    frame.setObjectName("statCard")
    frame.setMinimumWidth(200)
    # Fixed height keeps the KPI row compact - without it the cards stretch to
    # absorb spare vertical space and leave a big gap between title and value.
    frame.setFixedHeight(104)
    frame.setStyleSheet(
        "QFrame#statCard {"
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
    title_label.setStyleSheet(
        "color:#64748b; font-size:13px; font-weight:600;"
        "background: transparent; border: none;"
    )

    value_label = QLabel(value)
    value_label.setWordWrap(True)
    value_label.setStyleSheet(
        "color:#1f2937; font-size:22px; font-weight:800;"
        "background: transparent; border: none;"
    )

    layout.addWidget(title_label)
    layout.addStretch()
    layout.addWidget(value_label)

    frame.value_label = value_label
    return frame
