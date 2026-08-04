from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QWidget, QPushButton, QTableWidget,
)


def page_header(title, subtitle=None):
    """One header treatment for every page, instead of each screen inventing its
    own font sizes and margins."""
    wrapper = QWidget()
    layout = QVBoxLayout(wrapper)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)

    heading = QLabel(title)
    heading.setStyleSheet("font-size: 23px; font-weight: 800; color: #1f3b57;")
    layout.addWidget(heading)

    if subtitle:
        sub = QLabel(subtitle)
        sub.setWordWrap(True)
        sub.setStyleSheet("color: #64748b; font-size: 14px;")
        layout.addWidget(sub)
    return wrapper


def section_title(text, action_button=None):
    """A titled row above a table, optionally with a right-hand action."""
    wrapper = QWidget()
    row = QHBoxLayout(wrapper)
    row.setContentsMargins(0, 4, 0, 0)
    row.setSpacing(8)
    label = QLabel(text)
    label.setStyleSheet("font-size: 15px; font-weight: 700; color: #334155;")
    row.addWidget(label)
    row.addStretch()
    if action_button is not None:
        row.addWidget(action_button)
    return wrapper


def danger_button(text):
    """Destructive actions are outlined rather than filled: a solid red block
    sitting next to the save button reads as the primary action at a glance."""
    btn = QPushButton(text)
    btn.setStyleSheet(
        "QPushButton { background-color: transparent; color: #b91c1c;"
        "  border: 1px solid #e6b4b0; border-radius: 8px; padding: 7px 14px; font-weight: 700; }"
        "QPushButton:hover { background-color: #fdeceb; border-color: #dc2626; }"
        "QPushButton:pressed { background-color: #fbd9d6; }"
    )
    return btn


def set_empty_message(table: QTableWidget, message):
    """Show a friendly line inside an otherwise blank table. An empty grid tells
    a non-technical user nothing about whether it is broken or simply empty."""
    table.setRowCount(1)
    table.setSpan(0, 0, 1, table.columnCount())
    from PyQt6.QtWidgets import QTableWidgetItem
    item = QTableWidgetItem(message)
    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    item.setForeground(Qt.GlobalColor.gray)
    table.setItem(0, 0, item)


def fill_table(table: QTableWidget, row_count, empty_message):
    """Reset spans and size a table, or show the empty message. Returns True when
    there are real rows to populate."""
    table.clearSpans()
    if row_count == 0:
        set_empty_message(table, empty_message)
        return False
    table.setRowCount(row_count)
    return True


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
