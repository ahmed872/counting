"""Single source of truth for the application's look.

Kept out of main.py so that the exact same theme can be applied in tests and
screenshot tooling - otherwise rendered output does not match the real app.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette, QColor

APP_STYLESHEET = """
    QWidget {
        font-family: 'Segoe UI', 'Tahoma', sans-serif;
        font-size: 13px;
        color: #1f2937;
    }
    QLineEdit, QComboBox, QDateEdit, QTextEdit, QSpinBox, QDoubleSpinBox {
        background-color: white;
        border: 1px solid #d6dbe3;
        border-radius: 8px;
        padding: 5px 10px;
        min-height: 24px;
    }
    QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTextEdit:focus,
    QSpinBox:focus, QDoubleSpinBox:focus {
        border: 1px solid #4f78a8;
    }
    QComboBox::drop-down {
        border: 0px;
        width: 28px;
    }
    /* Reported live as "looks suspicious, is this even a dropdown?" - once
       ::drop-down carries its own rule, Qt stops drawing its native arrow
       glyph unless ::down-arrow is styled too, leaving an empty 28px gap
       that reads as a plain text box with dead space, not a selector. Drawn
       with plain borders (a CSS triangle) rather than an image so it never
       depends on an icon file being found or bundled. */
    QComboBox::down-arrow {
        image: none;
        width: 0px;
        height: 0px;
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 6px solid #64748b;
    }
    QComboBox::down-arrow:on {
        border-top-color: #334155;
    }
    QComboBox QAbstractItemView {
        background-color: white;
        color: #1f2937;
        selection-background-color: #d7e7f7;
        selection-color: #1f2937;
        outline: 0;
    }
    QGroupBox {
        font-weight: 700;
        border: 1px solid #d8e0ea;
        border-radius: 12px;
        margin-top: 14px;
        padding: 16px 10px 10px 10px;
        background-color: #fbfcfe;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top right;
        right: 14px;
        padding: 2px 8px;
        color: #1f3b57;
        background-color: #ffffff;
        border: 1px solid #d8e0ea;
        border-radius: 6px;
    }
    /* NOTE: use an explicit solid border, never `border: none`. With no border
       set, Qt can leave the button frame to the native style and then never
       paints `background-color` - the button falls back to the palette's light
       button colour while `color: white` still applies, i.e. white-on-white
       and effectively invisible. */
    QPushButton {
        background-color: #4f78a8;
        color: #ffffff;
        border: 1px solid #3f6996;
        border-radius: 10px;
        padding: 10px 18px;
        min-height: 22px;
        font-weight: 700;
    }
    QPushButton:hover {
        background-color: #3f6996;
        border: 1px solid #36577d;
    }
    QPushButton:pressed {
        background-color: #36577d;
        border: 1px solid #2c4763;
    }
    QPushButton:disabled {
        background-color: #cbd5e1;
        color: #64748b;
        border: 1px solid #b6c2d1;
    }
    QTabWidget::pane {
        border: 0;
    }
    QTabBar::tab {
        padding: 10px 18px;
        margin-left: 4px;
        border-radius: 8px;
        color: #475569;
    }
    QTabBar::tab:selected {
        font-weight: 700;
        background-color: #e6eef7;
        color: #1f3b57;
    }
    QTableWidget {
        background-color: white;
        border: 1px solid #dde3ea;
        border-radius: 12px;
        gridline-color: #e5eaf1;
        alternate-background-color: #f7f9fc;
    }
    QTableWidget::item {
        padding: 6px;
    }
    QHeaderView::section {
        background-color: #1f3b57;
        color: white;
        padding: 8px;
        border: 0px;
        font-weight: 600;
    }
    QTableCornerButton::section {
        background-color: #1f3b57;
        border: 0px;
    }
    /* Scrollbars are deliberately wide and high-contrast: the people using this
       app need an obvious signal that there is more content below the fold.

       The groove itself is transparent rather than a filled, rounded
       rectangle - Qt's native Windows style does not reliably round the
       *track* background the way it rounds the smaller handle sub-control,
       so a filled groove rendered as a hard-edged block that looked cut off
       sitting against the page's rounded corners. Nothing painted there
       means nothing to look cut off; the rounded handle alone is still
       exactly as wide and high-contrast as before. */
    QScrollBar:vertical {
        background: transparent;
        width: 16px;
        margin: 0;
    }
    QScrollBar::handle:vertical {
        background: #90a4bd;
        min-height: 40px;
        border-radius: 8px;
        border: 2px solid transparent;
    }
    QScrollBar::handle:vertical:hover {
        background: #6b83a3;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
        background: transparent;
    }
    QScrollBar:horizontal {
        background: transparent;
        height: 16px;
        margin: 0;
    }
    QScrollBar::handle:horizontal {
        background: #90a4bd;
        min-width: 40px;
        border-radius: 8px;
        border: 2px solid transparent;
    }
    QScrollBar::handle:horizontal:hover {
        background: #6b83a3;
    }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        width: 0px;
    }
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
        background: transparent;
    }
"""


def _force_light_palette(app):
    """On Windows, Qt6 auto-detects the OS dark/light theme and silently applies a dark
    QPalette underneath our light QSS. Anything the stylesheet doesn't explicitly cover
    (like combo-box popups) then renders as unreadable dark-on-dark. Force light mode
    explicitly so the app looks the same regardless of the user's Windows theme."""
    try:
        app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    except AttributeError:
        pass  # older Qt without colour-scheme hints; the palette below still fixes it

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#edf1f5"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#1f2937"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#f7f9fc"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#1f2937"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#1f2937"))
    # Button/ButtonText deliberately mirror the stylesheet's primary button
    # colours. If a platform ever fails to paint the QSS background, the palette
    # still yields white-on-blue rather than white-on-light-grey (an invisible
    # button). Inputs are unaffected: the stylesheet sets their background
    # explicitly, so they stay white.
    palette.setColor(QPalette.ColorRole.Button, QColor("#4f78a8"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#dc2626"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#4f78a8"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#94a3b8"))
    app.setPalette(palette)


def apply_theme(app):
    """Apply style, light palette, RTL direction and the app stylesheet."""
    app.setStyle("Fusion")
    _force_light_palette(app)
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    app.setStyleSheet(APP_STYLESHEET)
