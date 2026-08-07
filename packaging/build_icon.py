"""Draws the application icon and writes packaging/app_icon.ico.

Kept as a script rather than a checked-in binary blob so the icon can be
adjusted without hunting for whatever tool produced it.

Design notes, because they are the whole job here:

  - The icon is read at 16x16 in the taskbar and in Explorer's detail view far
    more often than at 256. Everything is therefore a solid filled shape; there
    is no outline, no thin stroke and no small detail, because all three turn to
    grey mush at that size.

  - A cloche (serving dome) reads as "restaurant" instantly and survives being
    shrunk to a thumbnail, which is more than can be said for a fork and knife -
    at 16px those become two grey specks.

  - Drawn fresh at every size rather than rendered once and downscaled, so the
    geometry can be nudged where a size needs it: below 32px the dome is widened
    and the plate thickened, otherwise they thin out and the silhouette breaks.

  - The .ico is assembled by hand, because Qt ships the ICO plugin read-only in
    most builds. The small entries are written as BMP/DIB rather than PNG: the
    PNG-in-ICO form is legal but not honoured everywhere, and the taskbar was
    silently falling back to a generic icon because of it.
"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import QApplication

HERE = os.path.dirname(os.path.abspath(__file__))
ICO_PATH = os.path.join(HERE, "app_icon.ico")
PNG_PATH = os.path.join(HERE, "app_icon.png")

SIZES = [16, 24, 32, 48, 64, 128, 256]

NAVY_TOP = QColor("#2c4a6b")
NAVY_BOTTOM = QColor("#1b2f47")
DOME = QColor("#ffffff")
PLATE = QColor("#ffffff")
KNOB = QColor("#e8b64c")          # a warm accent so it is not a grey blob


def draw(size):
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    s = float(size)
    small = size < 32

    # --- rounded-square badge ---------------------------------------------
    gradient = QLinearGradient(0, 0, 0, s)
    gradient.setColorAt(0.0, NAVY_TOP)
    gradient.setColorAt(1.0, NAVY_BOTTOM)
    radius = s * (0.16 if small else 0.22)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(gradient))
    painter.drawRoundedRect(QRectF(0, 0, s, s), radius, radius)

    # --- cloche: the restaurant half of the idea --------------------------
    dome_w = s * (0.74 if small else 0.66)
    dome_h = dome_w * 0.54
    cx = s / 2
    base_y = s * (0.66 if small else 0.65)

    dome = QPainterPath()
    dome.moveTo(cx - dome_w / 2, base_y)
    dome.arcTo(QRectF(cx - dome_w / 2, base_y - dome_h, dome_w, dome_h * 2), 180, -180)
    dome.closeSubpath()
    painter.setBrush(DOME)
    painter.drawPath(dome)

    knob_r = s * (0.075 if small else 0.055)
    painter.setBrush(KNOB)
    painter.drawEllipse(QPointF(cx, base_y - dome_h - knob_r * 0.55), knob_r, knob_r)

    # --- rising bars inside the dome: the accounting half -----------------
    # Dropped entirely below 32px. Three bars in eleven pixels is not a chart,
    # it is noise, and it eats the dome that carries the whole silhouette.
    if not small:
        bar_w = dome_w * 0.13
        gap = bar_w * 0.55
        heights = (0.30, 0.52, 0.74)
        total_w = 3 * bar_w + 2 * gap
        x = cx - total_w / 2
        painter.setBrush(NAVY_BOTTOM)
        for factor in heights:
            bar_h = dome_h * factor
            painter.drawRoundedRect(
                QRectF(x, base_y - bar_h - dome_h * 0.06, bar_w, bar_h),
                bar_w * 0.3, bar_w * 0.3,
            )
            x += bar_w + gap

    # --- plate -------------------------------------------------------------
    plate_w = s * (0.86 if small else 0.78)
    plate_h = s * (0.11 if small else 0.085)
    painter.setBrush(PLATE)
    painter.drawRoundedRect(
        QRectF(cx - plate_w / 2, base_y + plate_h * 0.35, plate_w, plate_h),
        plate_h / 2, plate_h / 2,
    )

    painter.end()
    return pixmap


def png_bytes(pixmap):
    # The QByteArray must be held in a local: QBuffer keeps only a pointer to
    # it, so passing a temporary lets Python free it mid-write and Qt crashes.
    storage = QByteArray()
    buffer = QBuffer(storage)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    buffer.close()
    return bytes(storage)


def dib_bytes(image):
    """The classic ICO payload: a BITMAPINFOHEADER, bottom-up BGRA pixels, then
    a 1-bit AND mask.

    Windows has accepted PNG payloads inside .ico since Vista, but only
    reliably for the large sizes. Several shell surfaces - the taskbar among
    them - still expect the small entries in this format, and quietly fall back
    to a default icon when they are PNG. That is exactly what happened: the
    executable carried the icon and the taskbar showed a generic one.
    """
    width, height = image.width(), image.height()

    header = struct.pack(
        "<IiiHHIIiiII",
        40,                 # header size
        width,
        height * 2,         # colour data plus the mask, per the ICO convention
        1,                  # planes
        32,                 # bits per pixel
        0,                  # BI_RGB, uncompressed
        width * height * 4,
        0, 0, 0, 0,
    )

    pixels = bytearray()
    for y in range(height - 1, -1, -1):          # bottom-up
        for x in range(width):
            colour = image.pixelColor(x, y)
            pixels += bytes((colour.blue(), colour.green(),
                             colour.red(), colour.alpha()))

    # AND mask: one bit per pixel, rows padded to four bytes. With a real alpha
    # channel it is ignored, but a missing or misaligned mask makes some
    # versions of the shell reject the entry outright.
    row_bytes = ((width + 31) // 32) * 4
    mask = bytearray(row_bytes * height)

    return bytes(header) + bytes(pixels) + bytes(mask)


def write_ico(path, entries):
    """entries: list of (size, payload_bytes)."""
    count = len(entries)
    header = struct.pack("<HHH", 0, 1, count)          # reserved, type=icon, count
    directory = b""
    payload = b""
    offset = 6 + 16 * count
    for size, data in entries:
        directory += struct.pack(
            "<BBBBHHII",
            0 if size >= 256 else size,                # width  (0 means 256)
            0 if size >= 256 else size,                # height
            0,                                         # palette colours
            0,                                         # reserved
            1,                                         # colour planes
            32,                                        # bits per pixel
            len(data),
            offset,
        )
        payload += data
        offset += len(data)
    with open(path, "wb") as handle:
        handle.write(header + directory + payload)


def build():
    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
    entries = []
    for size in SIZES:
        pixmap = draw(size)
        # PNG only for the big entries, where it saves real space; BMP for
        # everything the shell draws small.
        if size >= 128:
            entries.append((size, png_bytes(pixmap)))
        else:
            entries.append((size, dib_bytes(pixmap.toImage())))
        if size == 256:
            pixmap.save(PNG_PATH, "PNG")
    write_ico(ICO_PATH, entries)
    print(f"تم إنشاء الأيقونة: {ICO_PATH} ({os.path.getsize(ICO_PATH):,} بايت)")
    print(f"المقاسات: {', '.join(str(s) for s in SIZES)}")
    return ICO_PATH


if __name__ == "__main__":
    build()
