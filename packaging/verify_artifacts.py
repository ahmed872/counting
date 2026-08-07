"""Refuses to let a broken manual or icon get into a build.

The manual and the icon are committed rather than generated during the build,
because both were checked by eye and a build machine cannot do that. This is
the guard on that decision: it proves the committed files are still intact
before anything is packaged around them.

The failure this exists for actually shipped. Regenerating the manual on a
headless Windows runner produced a PDF in which every Arabic glyph was an empty
box - Qt found no font with Arabic coverage and quietly substituted one. The
build was green, the artifact uploaded, and the customer opened a booklet of
rectangles.
"""

import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANUAL = os.path.join(ROOT, "docs", "دليل-الاستخدام.pdf")
ICON_ICO = os.path.join(ROOT, "packaging", "app_icon.ico")
ICON_PNG = os.path.join(ROOT, "packaging", "app_icon.png")

MIN_MANUAL_BYTES = 60_000
MIN_MANUAL_PAGES = 8


def fail(message):
    print(f"[خطأ] {message}")
    sys.exit(1)


def check_manual():
    if not os.path.exists(MANUAL):
        fail(f"الدليل غير موجود: {MANUAL}")

    size = os.path.getsize(MANUAL)
    if size < MIN_MANUAL_BYTES:
        fail(f"حجم الدليل {size:,} بايت - يبدو مبتوراً")

    with open(MANUAL, "rb") as handle:
        blob = handle.read()

    if not blob.startswith(b"%PDF-"):
        fail("الدليل ليس ملف PDF")

    pages = blob.count(b"/Type /Page") + blob.count(b"/Type/Page")
    if pages < MIN_MANUAL_PAGES:
        fail(f"الدليل {pages} صفحة فقط")

    # The real check. A PDF whose fonts are not embedded renders as boxes on any
    # machine that lacks them, which is every machine this is sent to.
    if b"FontFile2" not in blob and b"FontFile3" not in blob and b"FontFile" not in blob:
        fail("خطوط الدليل غير مضمّنة في الملف - سيظهر النص مربعات فارغة")

    print(f"  الدليل: {size:,} بايت، ~{pages} صفحة، الخطوط مضمّنة ✓")


def check_icon():
    for path in (ICON_ICO, ICON_PNG):
        if not os.path.exists(path):
            fail(f"الأيقونة غير موجودة: {path}")

    with open(ICON_ICO, "rb") as handle:
        blob = handle.read()

    reserved, kind, count = struct.unpack("<HHH", blob[:6])
    if (reserved, kind) != (0, 1) or count == 0:
        fail("ملف الأيقونة تالف")

    sizes = []
    for i in range(count):
        offset = 6 + 16 * i
        width = blob[offset] or 256
        length, data_at = struct.unpack("<II", blob[offset + 8:offset + 16])
        payload = blob[data_at:data_at + length]
        if len(payload) != length:
            fail(f"مقاس {width} في ملف الأيقونة مبتور")
        # Small entries must be BMP. As PNG they are legal but the Windows
        # taskbar ignores them and falls back to a generic icon - which is
        # exactly what shipped once already.
        is_png = payload[:4] == b"\x89PNG"
        if width <= 64 and is_png:
            fail(f"مقاس {width} مكتوب بصيغة PNG - شريط المهام لن يعرضه")
        sizes.append(width)

    for required in (16, 32, 256):
        if required not in sizes:
            fail(f"مقاس {required} غير موجود في الأيقونة")

    print(f"  الأيقونة: {len(sizes)} مقاسات {sorted(sizes)} ✓")


if __name__ == "__main__":
    print("التحقق من الملفات الجاهزة قبل البناء:")
    check_manual()
    check_icon()
    print("تمام.")
