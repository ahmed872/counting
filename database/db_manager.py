import sqlite3
from contextlib import contextmanager

class DBManager:
    def __init__(self, db_path='restaurant_erp.db'):
        self.db_path = db_path
        self.init_db()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        # SQLite ships this off by default and does not remember it in the
        # database file - every connection has to turn it on for itself, or
        # none of the FOREIGN KEY declarations in schema.sql do anything at
        # all. Off, an attendance row could be inserted against an employee_id
        # that does not exist; a journal_item could point at an account code
        # that was never created. Both are quiet corruption that nothing in
        # the app would ever notice, because nothing was ever checking.
        conn.execute("PRAGMA foreign_keys = ON")
        # Every method below already opens and closes its own connection
        # around one short statement (or one transaction), so two writes can
        # only ever overlap by a hair. Python's sqlite3 module already
        # defaults new connections to a 5-second busy timeout on its own
        # (sqlite3.connect()'s own `timeout` parameter, separate from and
        # easy to confuse with SQLite's C-level default of 0) - explicit
        # here so that stays true regardless of what Python's own default
        # happens to be on a given version, rather than depending on it
        # silently.
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def init_db(self):
        # Not dirname(__file__): inside a packaged .exe this module lives in an
        # archive, and the .sql is unpacked elsewhere.
        from logic.paths import resource_path
        schema_path = resource_path('database', 'schema.sql')
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
            'work_card_expiry': 'DATE',
            # Client request: many workers share similar names - a photo
            # tells them apart at a glance on the employee list/form.
            'photo': 'BLOB',
            # مدد: the portion of net salary the institution pays through
            # the official مدد transfer system, registered with GOSI - see
            # HRLogic.post_payroll for how this splits the monthly net pay
            # between مدد (bank) and cash.
            'madad_salary': 'REAL DEFAULT 0',
            'medical_insurance_no': 'TEXT',
            'medical_insurance_expiry': 'DATE',
            # One-time government fees recorded when the employee is added
            # - passport/iqama processing, labour office, medical
            # insurance premium, health certificate - so a later report
            # can show everything the institution has paid for this
            # person without checking another platform.
            'passport_fee': 'REAL DEFAULT 0',
            'labor_office_fee': 'REAL DEFAULT 0',
            'medical_insurance_fee': 'REAL DEFAULT 0',
            'health_certificate_fee': 'REAL DEFAULT 0',
            'fees_journal_entry_id': 'INTEGER',
        }
        for column_name, column_type in employee_additions.items():
            if column_name not in employee_columns:
                cursor.execute(f"ALTER TABLE employees ADD COLUMN {column_name} {column_type}")

        attendance_columns = table_columns('attendance')
        if 'notes' not in attendance_columns:
            cursor.execute("ALTER TABLE attendance ADD COLUMN notes TEXT")

        # Splits each posted month's net pay the same way it was actually
        # disbursed: part through مدد (bank, account 1001) and the rest in
        # cash (1000) - see HRLogic.post_payroll. A posted month is a frozen
        # snapshot, so this has to live on the item row itself, not be
        # recomputed later from the employee's *current* مدد setting.
        payroll_item_columns = table_columns('payroll_run_items')
        for column_name in ('madad_portion', 'cash_portion'):
            if column_name not in payroll_item_columns:
                cursor.execute(f"ALTER TABLE payroll_run_items ADD COLUMN {column_name} REAL DEFAULT 0")

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
        if 'sales_returns' in self.get_existing_tables(cursor):
            sales_returns_columns = table_columns('sales_returns')
            if 'journal_entry_id' not in sales_returns_columns:
                cursor.execute("ALTER TABLE sales_returns ADD COLUMN journal_entry_id INTEGER")

        purchase_returns_columns = table_columns('purchase_returns') if self.table_exists(cursor, 'purchase_returns') else set()
        if 'purchase_returns' in self.get_existing_tables(cursor):
            if 'category' not in purchase_returns_columns:
                # Every return used to credit Inventory (1100) no matter what
                # was actually being returned, so returning an operating
                # expense quietly understated the stock account instead of the
                # expense it was actually against. Existing rows are assumed
                # raw_material, which is what the account they already posted
                # against (1100) means for the ones recorded so far.
                cursor.execute(
                    "ALTER TABLE purchase_returns ADD COLUMN category TEXT DEFAULT 'raw_material'")
            if 'journal_entry_id' not in purchase_returns_columns:
                cursor.execute("ALTER TABLE purchase_returns ADD COLUMN journal_entry_id INTEGER")

        if 'employee_deductions' in self.get_existing_tables(cursor) and 'amount_recovered' not in employee_deductions_columns:
            # An advance bigger than one month's net salary used to be
            # force-recovered in a single run, driving net_salary negative
            # and marking the whole advance settled - the rest of the debt
            # simply vanished from the books. Tracking how much of each
            # advance has actually been recovered lets a run take only
            # what the salary can cover and carry the remainder forward.
            cursor.execute(
                "ALTER TABLE employee_deductions ADD COLUMN amount_recovered REAL DEFAULT 0")

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
        if 'cashier_number' not in sales_columns:
            # A reference only - which register/cashier the day's total was
            # closed out on, for matching against the physical Z-report. Not
            # part of the accounting: the day is still one journal entry
            # regardless of how many registers fed into it.
            cursor.execute("ALTER TABLE sales ADD COLUMN cashier_number TEXT")

        # Delivery-app settlements (هنقرستيشن / جاهز وغيرها) get their own
        # payment_method value now, alongside cash/network/transfer - but a
        # CHECK constraint's allowed list cannot be altered in place, SQLite
        # only lets you rebuild the table. Recreated with every column it
        # already has, all existing rows carried over untouched.
        if self.table_exists(cursor, 'sales') and not self._table_check_allows(cursor, 'sales', 'Delivery'):
            cursor.execute("ALTER TABLE sales RENAME TO sales_pre_delivery")
            cursor.execute("""
                CREATE TABLE sales (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    branch_id INTEGER,
                    date DATETIME DEFAULT CURRENT_TIMESTAMP,
                    total_amount REAL,
                    vat_amount REAL,
                    payment_method TEXT CHECK(payment_method IN ('Cash', 'POS', 'Transfer', 'Delivery')),
                    cashier_number TEXT,
                    journal_entry_id INTEGER,
                    FOREIGN KEY (branch_id) REFERENCES branches(id)
                )
            """)
            cursor.execute("""
                INSERT INTO sales (id, branch_id, date, total_amount, vat_amount,
                                    payment_method, cashier_number, journal_entry_id)
                SELECT id, branch_id, date, total_amount, vat_amount,
                       payment_method, cashier_number, journal_entry_id
                FROM sales_pre_delivery
            """)
            cursor.execute("DROP TABLE sales_pre_delivery")

        # After the rebuild above, not before it - that rebuild recreates
        # sales from a hardcoded column list of its own, which would
        # silently drop this column (and any data already in it) if it
        # existed before the rebuild ran.
        if self.table_exists(cursor, 'sales') and 'shortage_amount' not in table_columns('sales'):
            # عجز لموظف - a cash-register shortfall for the day, entered
            # alongside the payment channels and subtracted from the cash
            # actually recorded (see save_daily_sales in sales_entry_
            # module.py). Stored on every row for that day/branch, the
            # same one-value-duplicated-onto-every-row pattern
            # cashier_number already uses, so it can be read back (MAX,
            # not SUM) without a separate table.
            cursor.execute("ALTER TABLE sales ADD COLUMN shortage_amount REAL DEFAULT 0")

        if self.table_exists(cursor, 'sales_returns') and not self._table_check_allows(cursor, 'sales_returns', 'Delivery'):
            cursor.execute("ALTER TABLE sales_returns RENAME TO sales_returns_pre_delivery")
            cursor.execute("""
                CREATE TABLE sales_returns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    branch_id INTEGER,
                    date DATETIME DEFAULT CURRENT_TIMESTAMP,
                    amount REAL DEFAULT 0,
                    vat_amount REAL DEFAULT 0,
                    refund_method TEXT CHECK(refund_method IN ('Cash', 'POS', 'Transfer', 'Delivery')),
                    notes TEXT,
                    journal_entry_id INTEGER,
                    FOREIGN KEY (branch_id) REFERENCES branches(id)
                )
            """)
            cursor.execute("""
                INSERT INTO sales_returns (id, branch_id, date, amount, vat_amount,
                                            refund_method, notes, journal_entry_id)
                SELECT id, branch_id, date, amount, vat_amount,
                       refund_method, notes, journal_entry_id
                FROM sales_returns_pre_delivery
            """)
            cursor.execute("DROP TABLE sales_returns_pre_delivery")

        supplier_columns = table_columns('suppliers')
        if 'is_active' not in supplier_columns:
            cursor.execute("ALTER TABLE suppliers ADD COLUMN is_active INTEGER DEFAULT 1")
            cursor.execute("UPDATE suppliers SET is_active = 1 WHERE is_active IS NULL")

        if 'terminated_date' not in employee_columns:
            # Deactivating an employee used to drop them from payroll
            # immediately, including an unposted PAST month they had actually
            # worked - the query only ever knew "active right now", not "was
            # this person employed during the period being calculated".
            cursor.execute("ALTER TABLE employees ADD COLUMN terminated_date DATE")

        if self.table_exists(cursor, 'payroll_run_items'):
            payroll_run_items_columns = table_columns('payroll_run_items')
            for column_name in ('absent_days', 'present_days'):
                if column_name not in payroll_run_items_columns:
                    # A posted month used to have no stored record of the
                    # attendance behind its numbers, so displaying "what was
                    # posted" always meant recalculating live from current
                    # data instead - which drifts the moment attendance or a
                    # deduction is edited after the fact.
                    cursor.execute(
                        f"ALTER TABLE payroll_run_items ADD COLUMN {column_name} INTEGER DEFAULT 0")

        if self.table_exists(cursor, 'payroll_runs'):
            payroll_runs_columns = table_columns('payroll_runs')
            if 'paid_now' not in payroll_runs_columns:
                # Posting used to always assume the whole net amount left the
                # register the moment it was posted - there was no way to
                # record "earned this month, still owed" (رواتب مستحقة),
                # which is exactly what the accountant's balance-sheet
                # message asked for. Existing rows are assumed paid, which is
                # what every run before this column existed actually did.
                cursor.execute("ALTER TABLE payroll_runs ADD COLUMN paid_now INTEGER DEFAULT 1")

        # كاشير is a fourth role - day-to-day sales entry only, no purchasing,
        # HR, suppliers, loans, reports, accounting or Settings access - but
        # a CHECK constraint's allowed list cannot be altered in place, only
        # rebuilt. Recreated with every column it already has, all existing
        # accounts carried over untouched.
        if self.table_exists(cursor, 'users') and not self._table_check_allows(cursor, 'users', 'cashier'):
            cursor.execute("ALTER TABLE users RENAME TO users_pre_cashier")
            cursor.execute("""
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    password_salt TEXT NOT NULL,
                    role TEXT CHECK(role IN ('admin', 'manager', 'cashier', 'viewer')) NOT NULL,
                    branch_id INTEGER REFERENCES branches(id),
                    display_name TEXT,
                    must_change_password INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                INSERT INTO users (id, username, password_hash, password_salt, role,
                                    display_name, must_change_password, is_active, created_at)
                SELECT id, username, password_hash, password_salt, role,
                       display_name, must_change_password, is_active, created_at
                FROM users_pre_cashier
            """)
            cursor.execute("DROP TABLE users_pre_cashier")

        # A cashier is now locked to one branch (see apply_role_restrictions
        # in main_window.py) - a plain ADD COLUMN, not a CHECK constraint,
        # so no rebuild needed even for a database that already went
        # through the rebuild above in an earlier run.
        if self.table_exists(cursor, 'users') and 'branch_id' not in table_columns('users'):
            cursor.execute("ALTER TABLE users ADD COLUMN branch_id INTEGER REFERENCES branches(id)")

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

        # Which journal entries the duplicate rows point to, captured before
        # they are deleted. Removing only the duplicate sales rows and leaving
        # their journal entries behind is exactly how a customer ended up with
        # a ledger that still counted revenue for a sale that no longer
        # existed anywhere in the operational tables - the dashboard, the
        # reports and the trial balance all kept the money, the sales screen
        # did not.
        cursor.execute("""
            SELECT DISTINCT journal_entry_id FROM sales
            WHERE id NOT IN (SELECT MAX(id) FROM sales GROUP BY branch_id, date, payment_method)
              AND journal_entry_id IS NOT NULL
        """)
        orphan_candidates = [row[0] for row in cursor.fetchall()]

        cursor.execute("""
            DELETE FROM sales WHERE id NOT IN (
                SELECT MAX(id) FROM sales GROUP BY branch_id, date, payment_method
            )
        """)

        # A single day's save shares one journal entry across every payment
        # method that had an amount, so a candidate entry is only actually
        # orphaned once none of the surviving sales rows reference it either.
        for entry_id in orphan_candidates:
            cursor.execute("SELECT COUNT(*) FROM sales WHERE journal_entry_id = ?", (entry_id,))
            if cursor.fetchone()[0] == 0:
                cursor.execute("DELETE FROM journal_items WHERE entry_id = ?", (entry_id,))
                cursor.execute("DELETE FROM journal_entries WHERE id = ?", (entry_id,))
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

    def _table_check_allows(self, cursor, table_name, value):
        """Whether a table's own CREATE TABLE text already lists `value` in one
        of its CHECK(... IN (...)) constraints - the only way to tell without
        parsing SQL properly, since PRAGMA table_info does not expose CHECK
        clauses at all."""
        cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
        )
        row = cursor.fetchone()
        return bool(row and row[0] and value in row[0])

    def execute_query(self, query, params=()):
        # Every method below closes the connection in a finally block, not
        # just on the success path. A constraint violation - a foreign key
        # that no longer matches, a CHECK that rejects the row - used to leave
        # that connection open, and the next write anywhere in the app would
        # then fail with "database is locked" for a reason that had nothing
        # to do with it. That failure mode is now confirmed real: it is
        # exactly what happened here, in this file's own test cleanup, the
        # first time a delete order violated a newly-enforced foreign key.
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
        finally:
            conn.close()

    def insert_and_return_id(self, query, params=()):
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            new_id = cursor.lastrowid
            conn.commit()
            return new_id
        finally:
            conn.close()

    def fetch_all(self, query, params=()):
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()
        finally:
            conn.close()

    def fetch_one(self, query, params=()):
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            result = cursor.fetchone()
        finally:
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

    def delete_journal_entry_on_cursor(self, cursor, entry_id):
        """Same two deletes as delete_journal_entry() below, against a
        cursor the caller already holds - so removing a business row and
        reversing the journal entry it produced can be combined into one
        transaction with whatever else the caller is doing (see clear_day()
        in sales_entry_module.py). Mirrors insert_journal_entry() /
        add_journal_entry() below: this is the cursor-sharing half, and
        delete_journal_entry() is the standalone convenience wrapper for
        callers that only need to reverse a journal entry on its own."""
        if not entry_id:
            return
        cursor.execute("DELETE FROM journal_items WHERE entry_id = ?", (entry_id,))
        cursor.execute("DELETE FROM journal_entries WHERE id = ?", (entry_id,))

    def delete_journal_entry(self, entry_id):
        """Removes a journal entry and its lines together, so the ledger can
        never be left holding half of a reversed transaction."""
        if not entry_id:
            return
        with self.transaction() as cursor:
            self.delete_journal_entry_on_cursor(cursor, entry_id)

    @contextmanager
    def transaction(self):
        """Run several writes as one atomic unit: all of them land, or none do.

        Every other method here opens its own connection and commits
        immediately, which is fine for a single statement but was silently
        wrong for an operation like "record a purchase": it wrote the journal
        entry in one commit and the purchase row in a second, separate one. A
        crash or power loss in the gap between those two commits - a machine
        someone gets on and off dozens of times a day - left a journal entry
        with no purchase behind it: money moved in the accounts with no
        invoice anywhere to explain it, and no clean way to find or undo it.

        Used as `with db.transaction() as cursor:` - every statement run
        through that cursor commits together at the end of the block, or all
        of it rolls back if anything inside raises.
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def insert_journal_entry(self, cursor, date, description, branch_id, items):
        """The journal_entries + journal_items writes, against a cursor the
        caller already holds - so they can be combined into one transaction
        with whatever operational row (a purchase, a payment, a sale) the
        entry belongs to. add_journal_entry() below is the same two inserts
        for callers that only need the journal entry on its own."""
        debit = round(sum(item['debit'] for item in items), 2)
        credit = round(sum(item['credit'] for item in items), 2)
        if abs(debit - credit) > 0.01:
            # The one invariant double-entry bookkeeping cannot survive
            # without: every entry balances on its own. This was previously
            # only ever true because every caller happened to build a
            # balanced items list by hand: nothing stopped a caller with a
            # mistake in it from posting anyway and the trial balance simply
            # ceasing to balance, with no indication of which entry did it.
            raise ValueError(
                f"قيد غير متوازن: مدين {debit:,.2f} لا يساوي دائن {credit:,.2f} "
                f"({description})"
            )
        cursor.execute("INSERT INTO journal_entries (date, description, branch_id) VALUES (?, ?, ?)",
                       (date, description, branch_id))
        entry_id = cursor.lastrowid
        for item in items:
            cursor.execute("INSERT INTO journal_items (entry_id, account_code, debit, credit) VALUES (?, ?, ?, ?)",
                           (entry_id, item['account_code'], item['debit'], item['credit']))
        return entry_id

    def add_journal_entry(self, date, description, branch_id, items):
        """
        items: list of dicts [{'account_code': '1000', 'debit': 100, 'credit': 0}, ...]
        """
        with self.transaction() as cursor:
            return self.insert_journal_entry(cursor, date, description, branch_id, items)
