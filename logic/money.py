"""One place that turns what the user typed into a number.

Every money field in the app used to do its own float(text). That let a
held-down key put 99,999,999,999,999 into a day's sales: the entry was
perfectly balanced, so the trial balance still said "متوازن" and nothing
anywhere complained, while every report and the balance sheet were quietly
ruined. Silent corruption of the books is the worst failure this program can
have, so the guard belongs in one place that every screen goes through.

It also does the small kindnesses the audience needs:

  - Arabic-Indic digits (١٢٣) are accepted. An Arabic keyboard produces them,
    and rejecting them looks like the program is broken.
  - Thousands separators are accepted, because "1,500" is how people write it.
  - The Arabic decimal separator (٫) is understood.
"""

MAX_AMOUNT = 10_000_000        # 10 million riyals in a single field

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def round_money(value):
    """P1-3: the one rounding policy every monetary amount in the app goes
    through - halalas, always round-half-up, computed via Decimal rather
    than Python's built-in round().

    Python's round() uses round-half-to-even ("banker's rounding") on top
    of a binary float that frequently cannot represent a decimal amount
    exactly in the first place - round(2.675, 2) returns 2.67, not 2.68,
    because 2.675 is actually stored as something microscopically below
    it. That is invisible on any single number and silently wrong on
    every accountant's or cashier's expectation of ordinary rounding.
    Going through str(value) first (not Decimal(value) directly) is what
    avoids inheriting that same binary imprecision into the Decimal.

    Returns a float, not a Decimal - every caller, every SQLite REAL
    column, and every existing calculation in this app already expects a
    plain float; only the rounding step itself needed to change."""
    from decimal import Decimal, ROUND_HALF_UP
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def normalise(text):
    """The raw text, with Arabic digits and separators turned into something
    float() understands. Does not validate."""
    if text is None:
        return ""
    cleaned = str(text).strip().translate(_ARABIC_DIGITS)
    cleaned = cleaned.replace("٫", ".").replace("٬", "").replace(",", "")
    cleaned = cleaned.replace("‏", "").replace("‎", "")   # bidi marks
    return cleaned.strip()


def parse_money(text, label="المبلغ", allow_blank=True, allow_zero=True):
    """Returns a float, or raises ValueError carrying an Arabic message that is
    safe to show the user directly."""
    cleaned = normalise(text)

    if not cleaned:
        if allow_blank:
            return 0.0
        raise ValueError(f"يرجى إدخال {label}")

    try:
        value = float(cleaned)
    except ValueError:
        raise ValueError(f"{label}: اكتب رقماً فقط، بدون حروف")

    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError(f"{label}: القيمة غير صحيحة")

    if value < 0:
        raise ValueError(f"{label}: لا يمكن إدخال مبلغ سالب")

    if not allow_zero and value == 0:
        raise ValueError(f"{label}: يجب أن يكون أكبر من صفر")

    if value > MAX_AMOUNT:
        raise ValueError(
            f"{label}: الرقم كبير بشكل غير معقول ({value:,.0f} ريال).\n"
            f"الحد الأقصى للخانة الواحدة هو {MAX_AMOUNT:,} ريال.\n"
            "تأكد من الرقم - غالباً ضغطت على زر بالخطأ."
        )

    # Riyals and halalas. Anything finer is a typo, and unrounded floats
    # accumulate a drift that shows up later as a trial balance off by 0.01.
    return round_money(value)
