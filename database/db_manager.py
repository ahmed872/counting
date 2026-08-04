import sqlite3
import os

class DBManager:
    def __init__(self, db_path='restaurant_erp.db'):
        self.db_path = db_path
        self.init_db()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
        with open(schema_path, 'r', encoding='utf-8') as f:
            schema_sql = f.read()
        
        conn = self.get_connection()
        conn.executescript(schema_sql)
        self.ensure_schema_migrations(conn)
        conn.commit()
        conn.close()

    def ensure_schema_migrations(self, conn):
        cursor = conn.cursor()

        def table_columns(table_name):
            cursor.execute(f"PRAGMA table_info({table_name})")
            return {row[1] for row in cursor.fetchall()}

        employee_columns = table_columns('employees')
        employee_additions = {
            'work_permit_no': 'TEXT',
            'work_permit_expiry': 'DATE',
            'work_card_no': 'TEXT',
            'work_card_expiry': 'DATE'
        }
        for column_name, column_type in employee_additions.items():
            if column_name not in employee_columns:
                cursor.execute(f"ALTER TABLE employees ADD COLUMN {column_name} {column_type}")

        attendance_columns = table_columns('attendance')
        if 'notes' not in attendance_columns:
            cursor.execute("ALTER TABLE attendance ADD COLUMN notes TEXT")

        menu_categories_columns = table_columns('menu_categories') if self.table_exists(cursor, 'menu_categories') else set()
        if 'menu_categories' in self.get_existing_tables(cursor):
            if 'sort_order' not in menu_categories_columns:
                cursor.execute("ALTER TABLE menu_categories ADD COLUMN sort_order INTEGER DEFAULT 0")
            if 'is_active' not in menu_categories_columns:
                cursor.execute("ALTER TABLE menu_categories ADD COLUMN is_active INTEGER DEFAULT 1")

        menu_items_columns = table_columns('menu_items') if self.table_exists(cursor, 'menu_items') else set()
        if 'menu_items' in self.get_existing_tables(cursor):
            if 'image_path' not in menu_items_columns:
                cursor.execute("ALTER TABLE menu_items ADD COLUMN image_path TEXT")
            if 'is_active' not in menu_items_columns:
                cursor.execute("ALTER TABLE menu_items ADD COLUMN is_active INTEGER DEFAULT 1")
            if 'sort_order' not in menu_items_columns:
                cursor.execute("ALTER TABLE menu_items ADD COLUMN sort_order INTEGER DEFAULT 0")

        sales_orders_columns = table_columns('sales_orders') if self.table_exists(cursor, 'sales_orders') else set()
        if 'sales_orders' in self.get_existing_tables(cursor):
            if 'order_no' not in sales_orders_columns:
                cursor.execute("ALTER TABLE sales_orders ADD COLUMN order_no TEXT")
            if 'cashier_name' not in sales_orders_columns:
                cursor.execute("ALTER TABLE sales_orders ADD COLUMN cashier_name TEXT")
            if 'qr_code' not in sales_orders_columns:
                cursor.execute("ALTER TABLE sales_orders ADD COLUMN qr_code TEXT")

        sales_order_items_columns = table_columns('sales_order_items') if self.table_exists(cursor, 'sales_order_items') else set()
        if 'sales_order_items' in self.get_existing_tables(cursor):
            if 'item_name' not in sales_order_items_columns:
                cursor.execute("ALTER TABLE sales_order_items ADD COLUMN item_name TEXT")
            if 'unit_price' not in sales_order_items_columns:
                cursor.execute("ALTER TABLE sales_order_items ADD COLUMN unit_price REAL DEFAULT 0")
            if 'quantity' not in sales_order_items_columns:
                cursor.execute("ALTER TABLE sales_order_items ADD COLUMN quantity INTEGER DEFAULT 1")
            if 'line_total' not in sales_order_items_columns:
                cursor.execute("ALTER TABLE sales_order_items ADD COLUMN line_total REAL DEFAULT 0")

        purchases_columns = table_columns('purchases') if self.table_exists(cursor, 'purchases') else set()
        if 'purchases' in self.get_existing_tables(cursor):
            if 'category' not in purchases_columns:
                cursor.execute("ALTER TABLE purchases ADD COLUMN category TEXT DEFAULT 'raw_material'")
            if 'description' not in purchases_columns:
                cursor.execute("ALTER TABLE purchases ADD COLUMN description TEXT")
            if 'amount' not in purchases_columns:
                cursor.execute("ALTER TABLE purchases ADD COLUMN amount REAL DEFAULT 0")
                cursor.execute("UPDATE purchases SET amount = COALESCE(total_amount, 0) - COALESCE(vat_amount, 0) WHERE amount = 0")

        employee_deductions_columns = table_columns('employee_deductions') if self.table_exists(cursor, 'employee_deductions') else set()
        if 'employee_deductions' in self.get_existing_tables(cursor):
            if 'settled_run_id' not in employee_deductions_columns:
                cursor.execute("ALTER TABLE employee_deductions ADD COLUMN settled_run_id INTEGER")

        if 'is_active' not in employee_columns:
            # Employees who leave are deactivated, never deleted - deleting one
            # would orphan their attendance, payroll and journal history.
            cursor.execute("ALTER TABLE employees ADD COLUMN is_active INTEGER DEFAULT 1")
            cursor.execute("UPDATE employees SET is_active = 1 WHERE is_active IS NULL")

        if 'journal_entry_id' not in purchases_columns and self.table_exists(cursor, 'purchases'):
            cursor.execute("ALTER TABLE purchases ADD COLUMN journal_entry_id INTEGER")

        sales_columns = table_columns('sales')
        if 'journal_entry_id' not in sales_columns:
            # Links a day's sales rows to the journal entry they produced, so a
            # mis-typed day can be corrected without orphaning its ledger entry.
            cursor.execute("ALTER TABLE sales ADD COLUMN journal_entry_id INTEGER")

        supplier_columns = table_columns('suppliers')
        if 'is_active' not in supplier_columns:
            cursor.execute("ALTER TABLE suppliers ADD COLUMN is_active INTEGER DEFAULT 1")
            cursor.execute("UPDATE suppliers SET is_active = 1 WHERE is_active IS NULL")

        self.arabise_account_names(cursor)
        self.enforce_uniqueness(cursor)

    def arabise_account_names(self, cursor):
        """schema.sql seeds accounts with INSERT OR IGNORE, so renaming them there
        only affects new databases. Existing ones are updated here - the code is
        the key, the name is only ever a label."""
        renames = {
            '1200': 'ضريبة المشتريات (مدخلات)',
            '2000': 'الموردون (ذمم دائنة)',
            '2100': 'ضريبة المبيعات (مخرجات)',
            '5000': 'تكلفة البضاعة المباعة',
        }
        for code, name in renames.items():
            cursor.execute(
                "UPDATE chart_of_accounts SET name = ? WHERE code = ? AND name <> ?",
                (name, code, name),
            )

    def enforce_uniqueness(self, cursor):
        """De-duplicate then add the unique indexes.

        Recording the same absence twice used to deduct the daily rate twice,
        and saving a day's sales twice doubled that day's revenue and VAT.
        Existing databases may already hold such duplicates, so they are
        collapsed to the newest row before the index is created - otherwise
        CREATE UNIQUE INDEX aborts and the app will not start."""
        # Daily sales are stored per-day; drop any time component so that
        # "the same day" is actually comparable.
        cursor.execute(
            "UPDATE sales SET date = date(date) WHERE date <> date(date)"
        )
        cursor.execute("""
            DELETE FROM sales WHERE id NOT IN (
                SELECT MAX(id) FROM sales GROUP BY branch_id, date, payment_method
            )
        """)
        cursor.execute("""
            DELETE FROM attendance WHERE id NOT IN (
                SELECT MAX(id) FROM attendance GROUP BY employee_id, date
            )
        """)
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_attendance_employee_day "
            "ON attendance(employee_id, date)"
        )
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_sales_branch_day_method "
            "ON sales(branch_id, date, payment_method)"
        )

    def get_existing_tables(self, cursor):
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        return {row[0] for row in cursor.fetchall()}

    def table_exists(self, cursor, table_name):
        return table_name in self.get_existing_tables(cursor)

    def execute_query(self, query, params=()):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        conn.close()

    def insert_and_return_id(self, query, params=()):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        new_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return new_id

    def fetch_all(self, query, params=()):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        results = cursor.fetchall()
        conn.close()
        return results

    def fetch_one(self, query, params=()):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        result = cursor.fetchone()
        conn.close()
        return result

    def get_setting(self, key, default=None):
        row = self.fetch_one("SELECT value FROM app_settings WHERE key = ?", (key,))
        return row['value'] if row else default

    def set_setting(self, key, value):
        self.execute_query(
            "INSERT INTO app_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )

    def delete_journal_entry(self, entry_id):
        """Removes a journal entry and its lines together, so the ledger can
        never be left holding half of a reversed transaction."""
        if not entry_id:
            return
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM journal_items WHERE entry_id = ?", (entry_id,))
            cursor.execute("DELETE FROM journal_entries WHERE id = ?", (entry_id,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def add_journal_entry(self, date, description, branch_id, items):
        """
        items: list of dicts [{'account_code': '1000', 'debit': 100, 'credit': 0}, ...]
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO journal_entries (date, description, branch_id) VALUES (?, ?, ?)", 
                           (date, description, branch_id))
            entry_id = cursor.lastrowid
            for item in items:
                cursor.execute("INSERT INTO journal_items (entry_id, account_code, debit, credit) VALUES (?, ?, ?, ?)",
                               (entry_id, item['account_code'], item['debit'], item['credit']))
            conn.commit()
            return entry_id
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
