from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QWidget, QPushButton,
    QTableWidget, QSizePolicy,
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


def compact_form(pairs, columns=2, field_min_width=200):
    """A form laid out in N columns instead of one field per row.

    A seven-field form stacked vertically is ~330px tall, which on a 720p
    screen leaves almost nothing for the table underneath. The same fields in
    two columns are half that, and they fill the width instead of leaving a
    dead gap beside them.

    pairs: list of (label_text, widget). Pass (None, widget) to span a cell
    without a label.
    """
    wrapper = QWidget()
    # Vertically Fixed: left at the default policy the form stretches to absorb
    # spare height (measured 480px for a 299px form) and starves the table
    # underneath it, which is what limited the invoice list to a single row.
    wrapper.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    grid = QGridLayout(wrapper)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(18)
    grid.setVerticalSpacing(10)

    for index, (caption, field) in enumerate(pairs):
        row, column = divmod(index, columns)
        cell = QHBoxLayout()
        cell.setSpacing(8)
        if caption:
            label = QLabel(caption)
            label.setMinimumWidth(92)
            label.setStyleSheet("color:#334155; font-weight:600;")
            cell.addWidget(label)
        field.setMinimumWidth(field_min_width)
        cell.addWidget(field, 1)
        holder = QWidget()
        holder.setLayout(cell)
        grid.addWidget(holder, row, column)

    for column in range(columns):
        grid.setColumnStretch(column, 1)
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


def pin_height(widget):
    """Stop a form container from stretching into the space a table needs."""
    widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return widget


def collapsible(form_widget, show_text, hide_text, start_collapsed=False):
    """Returns (toggle_button, form_widget) where the button hides/shows the form.

    On a short screen a form and a table cannot both have a usable height. Rather
    than shrink the table to a couple of rows, the form can be folded away and
    the table takes the whole page. Starts collapsed automatically when the
    screen is too short to fit both.
    """
    button = QPushButton()
    button.setCheckable(True)
    button.setStyleSheet(
        "QPushButton { background-color: transparent; color: #1f3b57;"
        "  border: 1px solid #c9d6e4; border-radius: 8px; padding: 6px 14px; font-weight: 700; }"
        "QPushButton:hover { background-color: #eef4fa; border-color: #4f78a8; }"
    )

    def apply_state():
        collapsed = button.isChecked()
        form_widget.setVisible(not collapsed)
        button.setText(show_text if collapsed else hide_text)

    button.toggled.connect(lambda _checked: apply_state())
    button.setChecked(start_collapsed)
    apply_state()
    return button


def hide_when_short(page, widgets, min_height=660):
    """Hide decorative widgets while the page is too short to afford them.

    A page built around a table has a fixed budget of vertical pixels. Headers,
    summary cards and hint boxes take theirs first and the table gets whatever
    is left - which on a 1024x600 laptop was 78 pixels, about one visible row.

    The signal is the page's own height, not the size of the monitor. Someone on
    a large screen can still drag the window small, and a check against
    screen().availableGeometry() never notices. This reacts to the actual
    resize, in both directions, so the cards come back when there is room.
    """
    original_resize = page.resizeEvent

    def resizeEvent(event):
        original_resize(event)
        roomy = event.size().height() >= min_height
        for widget in widgets:
            if widget is not None:
                widget.setVisible(roomy)

    page.resizeEvent = resizeEvent
    return page


def collapse_when_short(page, toggle_button, min_height=660):
    """Fold a collapsible form away while the page is too short for it.

    Deliberately fires only when the page crosses the threshold, not on every
    resize: if the user opens the form on a short window they mean it, and
    slamming it shut on the next stray resize event would be infuriating. Their
    choice stands until the window actually changes between short and roomy.
    """
    original_resize = page.resizeEvent
    state = {"short": None}

    def resizeEvent(event):
        original_resize(event)
        short = event.size().height() < min_height
        if short != state["short"]:
            state["short"] = short
            toggle_button.setChecked(short)

    page.resizeEvent = resizeEvent
    return page
