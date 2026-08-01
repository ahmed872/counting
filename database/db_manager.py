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
