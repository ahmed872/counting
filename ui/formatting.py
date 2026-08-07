"""Money and table-cell formatting.

Amounts were printed as bare "13800.00" all over the app. Thousands
separators and right-aligned tabular digits are what make a column of money
readable at a glance, which matters more here than anywhere else.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QTableWidgetItem


def money(value, decimals=2):
    """1234.5 -> '1,234.50'"""
    try:
        return f"{float(value or 0):,.{decimals}f}"
    except (TypeError, ValueError):
        return "0.00"


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

