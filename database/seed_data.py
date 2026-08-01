import sqlite3
import os
import sys
from datetime import datetime, timedelta

# Add parent directory to path to import database module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db_manager import DBManager

def seed():
    db = DBManager('restaurant_erp.db')
    conn = db.get_connection()
    cursor = conn.cursor()

    # Add Suppliers
    suppliers = [
        ('شركة الموارد الغذائية', '310123456700003', 5000, '0501234567'),
        ('مؤسسة التجهيزات الحديثة', '310987654300003', 0, '0507654321')
    ]
    for name, tax_id, opening_balance, phone in suppliers:
        cursor.execute(
            "INSERT OR IGNORE INTO suppliers (name, tax_id, opening_balance, phone) VALUES (?, ?, ?, ?)",
            (name, tax_id, opening_balance, phone),
        )
        if cursor.rowcount and opening_balance:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                "INSERT INTO journal_entries (date, description, branch_id) VALUES (?, ?, ?)",
                (timestamp, f"رصيد افتتاحي لمورد - {name}", None),
            )
            entry_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO journal_items (entry_id, account_code, debit, credit) VALUES (?, ?, ?, ?)",
                (entry_id, '3900', opening_balance, 0),
            )
            cursor.execute(
                "INSERT INTO journal_items (entry_id, account_code, debit, credit) VALUES (?, ?, ?, ?)",
                (entry_id, '2000', 0, opening_balance),
            )

    # Add Employees
    employees = [
        (1, 'أحمد علي', 'مدير فرع', 8000, 2000, '2345678901', '2026-08-15', 'P1234567', '2026-10-01', 'WP-1001', '2026-11-01', 'WC-5001', '2026-09-15'),
        (2, 'محمد حسن', 'شيف عمومي', 6000, 1500, '2456789012', '2026-09-20', 'P7654321', '2026-12-01', 'WP-1002', '2026-10-20', 'WC-5002', '2026-08-20')
    ]
    cursor.executemany("INSERT OR IGNORE INTO employees (branch_id, name, job_title, base_salary, allowances, iqama_no, iqama_expiry, passport_no, passport_expiry, work_permit_no, work_permit_expiry, work_card_no, work_card_expiry) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", employees)

    conn.commit()
    conn.close()

if __name__ == "__main__":
    seed()
