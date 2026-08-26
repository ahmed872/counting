from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QWidget, QPushButton,
    QTableWidget, QSizePolicy, QScrollArea,
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
    # A defensive floor under the label's own natural width: Windows font
    # substitution can measure Arabic text wider than the same string does
    # on this dev machine's fallback font, and a page title is the one
    # label an owner reads before anything else on the page - it must never
    # be the thing that gets clipped.
    from PyQt6.QtGui import QFont, QFontMetrics
    heading_font = QFont()
    heading_font.setPixelSize(23)
    heading_font.setWeight(QFont.Weight.ExtraBold)
    heading.setMinimumWidth(QFontMetrics(heading_font).horizontalAdvance(title) + 12)
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
            # A flat 92px minimum, with no wrapping, silently clipped any
            # caption longer than a short word or two - "رصيد افتتاحي (مستحق
            # له علينا)" rendered as a few letters with the rest invisible,
            # not even an ellipsis to hint more was there. Sized to what the
            # text actually needs (capped so one very long caption cannot
            # push the field off to the side), and left free to wrap onto a
            # second line for whatever still does not fit.
            from PyQt6.QtGui import QFontMetrics
            natural_width = QFontMetrics(label.font()).horizontalAdvance(caption)
            label.setMinimumWidth(min(max(natural_width + 4, 92), 170))
            label.setWordWrap(True)
            label.setStyleSheet("color:#334155; font-weight:600;")
            cell.addWidget(label)
            cell.setAlignment(label, Qt.AlignmentFlag.AlignTop)
        field.setMinimumWidth(field_min_width)
        cell.addWidget(field, 1)
        holder = QWidget()
        holder.setLayout(cell)
        grid.addWidget(holder, row, column)

    for column in range(columns):
        grid.setColumnStretch(column, 1)
    return wrapper


def danger_button(text):
    """A light red fill - solid, not outlined, so it still reads as a
    clickable button at a glance - kept lighter than the blue primary
    buttons so it does not compete with them for attention."""
    btn = QPushButton(text)
    btn.setStyleSheet(
        "QPushButton { background-color: #fdeceb; color: #b91c1c;"
        "  border: 1px solid #e6b4b0; border-radius: 8px; padding: 7px 14px; font-weight: 700; }"
        "QPushButton:hover { background-color: #fbd9d6; border-color: #dc2626; }"
        "QPushButton:pressed { background-color: #f8c4bf; }"
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


def fit_table_height(table: QTableWidget, minimum=90):
    """Grow a table to fit every one of its own rows instead of being boxed
    into a fixed height with its own internal scrollbar.

    A table on a page with no scroll of its own used to get squeezed to a
    couple of rows on a short window - the fix at the time was to keep that
    page unwrapped so the table could claim all the spare space. That traded
    one problem for another: a table with more rows than fit is still boxed
    into whatever height the layout happens to give it, with a small,
    easy-to-miss internal scrollbar hiding the rest (this is exactly what
    happened to the payroll summary table - three employees, only two
    visible). Call this after populating a table on a page that scrolls as a
    whole (see add_page in main_window.py): the table always shows every row
    it has, and the page's own scrollbar - big, familiar, the same one used
    everywhere else - handles anything that does not fit on screen.
    """
    header_height = table.horizontalHeader().height()
    rows_height = table.verticalHeader().length()
    frame = table.frameWidth() * 2
    total = header_height + rows_height + frame + 2
    if table.horizontalScrollBarPolicy() != Qt.ScrollBarPolicy.ScrollBarAlwaysOff:
        total += table.horizontalScrollBar().sizeHint().height()
    table.setFixedHeight(max(total, minimum))
    # QTableWidget's own default policy wants to grow (Expanding), so a
    # parent layout with room to spare - a QTabWidget always hands its
    # current page the tab bar's own full height, regardless of what that
    # page's layout actually needs - still allocates this table more room
    # than setFixedHeight lets it use. The table cannot fill that extra
    # room, so it ends up centred inside it: a blank gap opening up above
    # the table instead of the layout collapsing tightly around it.
    table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    _forward_wheel_to_page_scroll(table)


def _forward_wheel_to_page_scroll(table):
    """A table sized to fit every row (see above) has nothing left to scroll
    on its own - but Qt does not hand a wheel event up to the parent just
    because the table's own scrollbar has nothing to do; QAbstractScrollArea
    swallows it regardless. The mouse wheel silently did nothing at all while
    the cursor happened to be over a table, on every page that scrolls as a
    whole. Installed once per table; forwards straight to the page's own
    QScrollArea (see add_page in main_window.py)."""
    if getattr(table, "_wheel_forwards_to_page", False):
        return
    table._wheel_forwards_to_page = True

    def wheel_event(event, table=table):
        node = table.parentWidget()
        while node is not None and not isinstance(node, QScrollArea):
            node = node.parentWidget()
        if node is not None:
            node.wheelEvent(event)
        else:
            QTableWidget.wheelEvent(table, event)

    table.wheelEvent = wheel_event


def create_stat_card(title, value, accent_color="#4f78a8"):
    """A plain light card with a colored top accent bar and dark text.

    NOTE: the stylesheet selector MUST be scoped by objectName. QLabel is a
    subclass of QFrame, so a bare `QFrame { ... }` rule would also style every
    label inside the card - giving each one its own border and accent bar.
    """
    frame = QFrame()
    frame.setObjectName("statCard")
    # A row of 4 at the old 200px minimum needed 836px - more than fits in
    # the content area at the app's own documented minimum window size
    # (1040px wide). Horizontal scrolling is deliberately off on every page
    # (see add_page in main_window.py), so there was no way to reach the
    # card that got pushed off the edge - confirmed live: "عدد الموظفين"
    # simply was not on screen at that size, and the title label already
    # wraps to two lines, so a narrower card still reads fine.
    frame.setMinimumWidth(150)
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
        "QPushButton { background-color: #eef4fa; color: #1f3b57;"
        "  border: 1px solid #c9d6e4; border-radius: 8px; padding: 6px 14px; font-weight: 700; }"
        "QPushButton:hover { background-color: #dbe7f4; border-color: #4f78a8; }"
        "QPushButton:pressed { background-color: #cbdbef; }"
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


CASH_BANK_LABELS = {"1000": "الخزينة (كاش)", "1001": "البنك"}


def warn_if_would_overdraw(parent, accounting, account_code, amount):
    """Asks before letting a cash/bank outflow push that account negative -
    the same "are you sure?" shape already used for paying a supplier or
    collecting from a customer more than they owe. Every cash/bank-affecting
    screen used to post straight through with no feedback at all: nothing
    anywhere stopped a purchase, a loan repayment, or a prepaid expense from
    quietly overdrawing the till or the bank account.

    Returns True to proceed (either the balance holds, or the user confirmed
    anyway - real cash on hand can be more than what has been entered so
    far), False to abort.
    """
    from PyQt6.QtWidgets import QMessageBox
    from ui.formatting import money

    # get_account_balance() reads credit-minus-debit, the natural direction
    # for a liability - 1000/1001 are Assets, so the true, debit-positive
    # balance is the negative of that.
    current = accounting.get_account_balance(account_code) * -1
    remaining = current - amount
    if remaining >= -0.01:
        return True

    label = CASH_BANK_LABELS.get(account_code, account_code)
    answer = QMessageBox.question(
        parent, "الرصيد قد لا يكفي",
        f"رصيد {label} المسجَّل حالياً {money(current)} ريال فقط، وهذه العملية بمبلغ "
        f"{money(amount)} ريال ستجعله بالسالب ({money(remaining)} ريال).\n\n"
        "لو كان المتاح فعلياً أكبر مما هو مسجَّل هنا اضغط نعم للمتابعة.\n"
        "لو كان هذا خطأ في المبلغ أو طريقة الدفع اضغط لا.",
    )
    return answer == QMessageBox.StandardButton.Yes
