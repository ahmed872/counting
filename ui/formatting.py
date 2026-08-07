"""Money and table-cell formatting.

Amounts were printed as bare "13800.00" all over the app. Thousands
separators and right-aligned tabular digits are what make a column of money
readable at a glance, which matters more here than anywhere else.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QTableWidgetItem

# Bidi controls used to keep a minus sign attached to its number inside an
# Arabic line. Named rather than pasted inline: as literal characters they are
# invisible in the source, and an invisible character nobody can see is one
# nobody can maintain.
LTR_ISOLATE = "\u2066"
POP_ISOLATE = "\u2069"


def money(value, decimals=2):
    """1234.5 -> '1,234.50', and -1234.5 -> '1,234.50-' read correctly.

    The minus sign is the problem. In a right-to-left paragraph the bidi
    algorithm moves a leading "-" to the visual right of the number, so -1000
    was being displayed as "1,000.00-" - which reads at a glance as a positive
    figure with a stray dash, on the one screen where the difference between
    owing and being owed is the whole point. The number is wrapped in an
    explicit left-to-right embedding so the sign stays where it belongs.
    """
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        return "0.00"

    text = f"{amount:,.{decimals}f}"
    if amount < 0:
        # U+2066 LEFT-TO-RIGHT ISOLATE ... U+2069 POP DIRECTIONAL ISOLATE.
        # Isolates rather than the older embedding controls: an isolate cannot
        # affect how the text around it is ordered, so wrapping an amount can
        # never disturb the Arabic sentence it sits inside.
        return LTR_ISOLATE + text + POP_ISOLATE
    return text


def riyal(value):
    return f"{money(value)} ريال"


def money_item(value, bold=False, colour=None, blank_if_zero=False):
    """A right-aligned, tabular table cell for an amount."""
    amount = float(value or 0)
    text = "" if (blank_if_zero and abs(amount) < 0.005) else money(amount)
    item = QTableWidgetItem(text)
    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    if bold:
        font = item.font()
        font.setBold(True)
        item.setFont(font)
    if colour:
        item.setForeground(QColor(colour))
    return item

