"""Arabic display labels for values stored in English.

The database deliberately stores English codes ('Cash', 'Absent', 'Asset'...):
they are referenced by CHECK constraints and by every reporting query, so
renaming them would be a data migration. Only the label the user reads is
translated here, in one place, so no screen can drift back to English.
"""

ACCOUNT_TYPE_LABELS = {
    'Asset': 'أصول',
    'Liability': 'التزامات',
    'Equity': 'حقوق ملكية',
    'Revenue': 'إيرادات',
    'Expense': 'مصروفات',
}

PAYMENT_STATUS_LABELS = {
    'Cash': 'نقدي',
    'Credit': 'آجل (على الحساب)',
}

PAYMENT_METHOD_LABELS = {
    'Cash': 'نقدي',
    'Bank': 'تحويل بنكي',
    'POS': 'شبكة (مدى / فيزا)',
    'Transfer': 'تحويل بنكي',
    'Delivery': 'تطبيقات التوصيل',
}

ATTENDANCE_STATUS_LABELS = {
    'Present': 'حاضر',
    'Absent': 'غائب',
}

DEDUCTION_TYPE_LABELS = {
    'Deduction': 'خصم',
    'Advance': 'سلفة',
    'Bonus': 'مكافأة',
}

REFUND_METHOD_LABELS = {
    'Cash': 'استرداد نقدي',
    'CreditNote': 'خصم من رصيد المورد',
    'POS': 'شبكة (مدى / فيزا)',
    'Transfer': 'تحويل بنكي',
    'Delivery': 'تطبيقات التوصيل',
}


def label_for(mapping, value, fallback=None):
    """Arabic label for a stored value, falling back to the value itself so a
    new code shows up visibly rather than silently rendering blank."""
    if value is None:
        return fallback if fallback is not None else ""
    return mapping.get(value, fallback if fallback is not None else str(value))
