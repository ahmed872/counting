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

  - The .ico is assembled by hand. Qt ships the ICO plugin read-only in most
    builds, and the format is simply a header, a directory, and PNG payloads.
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

    # --- cloche ------------------------------------------------------------
    # Widened and dropped slightly at small sizes; the default proportions
    # leave too little ink and the dome reads as a smudge.
    dome_w = s * (0.72 if small else 0.64)
    dome_h = dome_w * 0.52
    cx = s / 2
    base_y = s * (0.66 if small else 0.64)

    dome = QPainterPath()
    dome.moveTo(cx - dome_w / 2, base_y)
    dome.arcTo(QRectF(cx - dome_w / 2, base_y - dome_h, dome_w, dome_h * 2), 180, -180)
    dome.closeSubpath()
    painter.setBrush(DOME)
    painter.drawPath(dome)

    # knob on top of the dome
    knob_r = s * (0.075 if small else 0.055)
    painter.setBrush(KNOB)
    painter.drawEllipse(QPointF(cx, base_y - dome_h - knob_r * 0.55), knob_r, knob_r)

    # --- plate -------------------------------------------------------------
    plate_w = s * (0.84 if small else 0.76)
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


def write_ico(path, images):
    """images: list of (size, png_bytes). Windows accepts PNG payloads inside
    an .ico for Vista and later, which every target machine is."""
    count = len(images)
    header = struct.pack("<HHH", 0, 1, count)          # reserved, type=icon, count
    directory = b""
    payload = b""
    offset = 6 + 16 * count
    for size, data in images:
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
    images = []
    for size in SIZES:
        pixmap = draw(size)
        images.append((size, png_bytes(pixmap)))
        if size == 256:
            pixmap.save(PNG_PATH, "PNG")
    write_ico(ICO_PATH, images)
    print(f"تم إنشاء الأيقونة: {ICO_PATH} ({os.path.getsize(ICO_PATH):,} بايت)")
    print(f"المقاسات: {', '.join(str(s) for s in SIZES)}")
    return ICO_PATH


if __name__ == "__main__":
    build()
