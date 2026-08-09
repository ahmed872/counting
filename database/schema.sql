-- Branches Table
CREATE TABLE IF NOT EXISTS branches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    location TEXT
);

-- Simple key/value store for company details and bookkeeping markers
-- (e.g. the id of the opening-balance journal entry, so it can be corrected).
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- Who can open the program and what they can do once inside - see
-- logic/auth.py. Four roles: admin (everything, including managing other
-- users), manager (day-to-day operations, no settings or user management,
-- every branch), cashier (just daily sales entry - المبيعات اليومية,
-- لوحة التحكم, العملاء - locked to the one branch_id below), viewer
-- (read-only everywhere). Passwords are never stored in the clear - only a
-- salted PBKDF2 hash.
CREATE TABLE IF NOT EXISTS users (
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
);

-- Employees Table
CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    branch_id INTEGER,
    name TEXT NOT NULL,
    job_title TEXT,
    base_salary REAL DEFAULT 0,
    allowances REAL DEFAULT 0,
    iqama_no TEXT,
    iqama_expiry DATE,
    passport_no TEXT,
    passport_expiry DATE,
    health_card_no TEXT,
    health_card_expiry DATE,
    FOREIGN KEY (branch_id) REFERENCES branches(id)
);

-- Attendance Table
CREATE TABLE IF NOT EXISTS attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER,
    date DATE,
    status TEXT CHECK(status IN ('Present', 'Absent')),
    FOREIGN KEY (employee_id) REFERENCES employees(id)
);

-- NOTE: the uniqueness constraints for attendance and daily sales are created
-- in db_manager.ensure_schema_migrations(), not here. Existing databases may
-- already contain duplicates, and CREATE UNIQUE INDEX would abort startup - the
-- migration de-duplicates first, then adds the index.

-- Chart of Accounts
CREATE TABLE IF NOT EXISTS chart_of_accounts (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT CHECK(type IN ('Asset', 'Liability', 'Equity', 'Revenue', 'Expense'))
);

-- Journal Entries
CREATE TABLE IF NOT EXISTS journal_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATETIME DEFAULT CURRENT_TIMESTAMP,
    description TEXT,
    branch_id INTEGER,
    FOREIGN KEY (branch_id) REFERENCES branches(id)
);

-- Journal Items (Double-Entry)
CREATE TABLE IF NOT EXISTS journal_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER,
    account_code TEXT,
    debit REAL DEFAULT 0,
    credit REAL DEFAULT 0,
    FOREIGN KEY (entry_id) REFERENCES journal_entries(id),
    FOREIGN KEY (account_code) REFERENCES chart_of_accounts(code)
);

-- Suppliers Table
CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    tax_id TEXT,
    opening_balance REAL DEFAULT 0,
    phone TEXT
);

-- Sales Table
CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    branch_id INTEGER,
    date DATETIME DEFAULT CURRENT_TIMESTAMP,
    total_amount REAL,
    vat_amount REAL,
    payment_method TEXT CHECK(payment_method IN ('Cash', 'POS', 'Transfer', 'Delivery')),
    cashier_number TEXT,
    FOREIGN KEY (branch_id) REFERENCES branches(id)
);

-- Purchases Table
CREATE TABLE IF NOT EXISTS purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    branch_id INTEGER,
    supplier_id INTEGER,
    date DATETIME DEFAULT CURRENT_TIMESTAMP,
    amount REAL DEFAULT 0,
    total_amount REAL,
    vat_amount REAL,
    payment_status TEXT CHECK(payment_status IN ('Cash', 'Credit')),
    category TEXT CHECK(category IN ('raw_material', 'purchase_expense', 'operating_expense')) DEFAULT 'raw_material',
    description TEXT,
    FOREIGN KEY (branch_id) REFERENCES branches(id),
    FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
);

-- Supplier Payments (settling credit purchases / opening balances)
CREATE TABLE IF NOT EXISTS supplier_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_id INTEGER,
    date DATETIME DEFAULT CURRENT_TIMESTAMP,
    amount REAL DEFAULT 0,
    method TEXT CHECK(method IN ('Cash', 'Bank')),
    notes TEXT,
    FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
);

-- Customers (مدينون / ذمم مدينة) - the mirror image of suppliers.
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    tax_id TEXT,
    opening_balance REAL DEFAULT 0,
    phone TEXT,
    is_active INTEGER DEFAULT 1
);

-- Credit sales to a customer (the mirror of "purchases" on credit from a
-- supplier): creates the receivable rather than an instant cash/POS/transfer
-- sale, which is what the daily sales screen handles.
CREATE TABLE IF NOT EXISTS customer_sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    branch_id INTEGER,
    customer_id INTEGER,
    date DATETIME DEFAULT CURRENT_TIMESTAMP,
    amount REAL DEFAULT 0,
    vat_amount REAL DEFAULT 0,
    description TEXT,
    journal_entry_id INTEGER,
    FOREIGN KEY (branch_id) REFERENCES branches(id),
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);

-- Customer Payments (collecting what a customer owes / opening balances)
CREATE TABLE IF NOT EXISTS customer_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER,
    date DATETIME DEFAULT CURRENT_TIMESTAMP,
    amount REAL DEFAULT 0,
    method TEXT CHECK(method IN ('Cash', 'Bank')),
    notes TEXT,
    journal_entry_id INTEGER,
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);

-- Loans (قروض) - money borrowed from a bank or an individual, owed back.
CREATE TABLE IF NOT EXISTS loans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lender_name TEXT NOT NULL,
    amount REAL DEFAULT 0,
    date DATETIME DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,
    journal_entry_id INTEGER
);

CREATE TABLE IF NOT EXISTS loan_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    loan_id INTEGER,
    date DATETIME DEFAULT CURRENT_TIMESTAMP,
    amount REAL DEFAULT 0,
    method TEXT CHECK(method IN ('Cash', 'Bank')),
    notes TEXT,
    journal_entry_id INTEGER,
    FOREIGN KEY (loan_id) REFERENCES loans(id)
);

-- Prepaid expenses (مصروفات مقدمة) - paid now, recognised as an expense
-- gradually over the months they actually belong to.
CREATE TABLE IF NOT EXISTS prepaid_expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    description TEXT NOT NULL,
    amount REAL DEFAULT 0,
    date DATETIME DEFAULT CURRENT_TIMESTAMP,
    target_account_code TEXT DEFAULT '5200',
    released_amount REAL DEFAULT 0,
    journal_entry_id INTEGER
);

CREATE TABLE IF NOT EXISTS prepaid_expense_releases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prepaid_expense_id INTEGER,
    date DATETIME DEFAULT CURRENT_TIMESTAMP,
    amount REAL DEFAULT 0,
    journal_entry_id INTEGER,
    FOREIGN KEY (prepaid_expense_id) REFERENCES prepaid_expenses(id)
);

-- Purchase Returns
CREATE TABLE IF NOT EXISTS purchase_returns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    branch_id INTEGER,
    supplier_id INTEGER,
    date DATETIME DEFAULT CURRENT_TIMESTAMP,
    amount REAL DEFAULT 0,
    vat_amount REAL DEFAULT 0,
    refund_method TEXT CHECK(refund_method IN ('Cash', 'CreditNote')),
    notes TEXT,
    category TEXT DEFAULT 'raw_material',
    journal_entry_id INTEGER,
    FOREIGN KEY (branch_id) REFERENCES branches(id),
    FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
);

-- Sales Returns
CREATE TABLE IF NOT EXISTS sales_returns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    branch_id INTEGER,
    date DATETIME DEFAULT CURRENT_TIMESTAMP,
    amount REAL DEFAULT 0,
    vat_amount REAL DEFAULT 0,
    refund_method TEXT CHECK(refund_method IN ('Cash', 'POS', 'Transfer', 'Delivery')),
    notes TEXT,
    journal_entry_id INTEGER,
    FOREIGN KEY (branch_id) REFERENCES branches(id)
);

-- Employee Deductions / Advances / Bonuses
CREATE TABLE IF NOT EXISTS employee_deductions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER,
    date DATE,
    type TEXT CHECK(type IN ('Deduction', 'Advance', 'Bonus')),
    amount REAL DEFAULT 0,
    notes TEXT,
    settled_run_id INTEGER,
    FOREIGN KEY (employee_id) REFERENCES employees(id)
);

-- Payroll Runs (posting payroll to the accounting journal)
CREATE TABLE IF NOT EXISTS payroll_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month INTEGER,
    year INTEGER,
    posted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    total_expense REAL DEFAULT 0,
    total_net_paid REAL DEFAULT 0,
    total_advances_recovered REAL DEFAULT 0,
    UNIQUE(month, year)
);

CREATE TABLE IF NOT EXISTS payroll_run_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER,
    employee_id INTEGER,
    gross_salary REAL DEFAULT 0,
    absence_deduction REAL DEFAULT 0,
    other_deductions REAL DEFAULT 0,
    bonuses REAL DEFAULT 0,
    advances_recovered REAL DEFAULT 0,
    net_salary REAL DEFAULT 0,
    FOREIGN KEY (run_id) REFERENCES payroll_runs(id),
    FOREIGN KEY (employee_id) REFERENCES employees(id)
);

-- Settling account 2200 (رواتب مستحقة الدفع) when a payroll run was posted
-- as owed rather than paid in cash on the spot.
CREATE TABLE IF NOT EXISTS accrued_wage_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATETIME DEFAULT CURRENT_TIMESTAMP,
    amount REAL DEFAULT 0,
    method TEXT CHECK(method IN ('Cash', 'Bank')),
    notes TEXT,
    journal_entry_id INTEGER
);

-- Initial Data for Branches
-- One neutral branch so the app is usable on first run; the owner renames it
-- and adds his own from Settings. No other data ships with the app.
INSERT OR IGNORE INTO branches (id, name, location) VALUES (1, 'الفرع الرئيسي', '');

-- Initial Chart of Accounts
INSERT OR IGNORE INTO chart_of_accounts (code, name, type) VALUES ('1000', 'النقدية', 'Asset');
INSERT OR IGNORE INTO chart_of_accounts (code, name, type) VALUES ('1001', 'البنك', 'Asset');
INSERT OR IGNORE INTO chart_of_accounts (code, name, type) VALUES ('1100', 'المخزون', 'Asset');
INSERT OR IGNORE INTO chart_of_accounts (code, name, type) VALUES ('1200', 'ضريبة المشتريات (مدخلات)', 'Asset');
INSERT OR IGNORE INTO chart_of_accounts (code, name, type) VALUES ('1300', 'سلف الموظفين', 'Asset');
INSERT OR IGNORE INTO chart_of_accounts (code, name, type) VALUES ('1400', 'العملاء (ذمم مدينة)', 'Asset');
INSERT OR IGNORE INTO chart_of_accounts (code, name, type) VALUES ('1500', 'مصروفات مدفوعة مقدماً', 'Asset');
INSERT OR IGNORE INTO chart_of_accounts (code, name, type) VALUES ('2000', 'الموردون (ذمم دائنة)', 'Liability');
INSERT OR IGNORE INTO chart_of_accounts (code, name, type) VALUES ('2100', 'ضريبة المبيعات (مخرجات)', 'Liability');
INSERT OR IGNORE INTO chart_of_accounts (code, name, type) VALUES ('2200', 'رواتب مستحقة الدفع', 'Liability');
INSERT OR IGNORE INTO chart_of_accounts (code, name, type) VALUES ('2300', 'قروض', 'Liability');
INSERT OR IGNORE INTO chart_of_accounts (code, name, type) VALUES ('3000', 'رأس المال', 'Equity');
INSERT OR IGNORE INTO chart_of_accounts (code, name, type) VALUES ('3900', 'الأرصدة الافتتاحية', 'Equity');
INSERT OR IGNORE INTO chart_of_accounts (code, name, type) VALUES ('4000', 'المبيعات', 'Revenue');
INSERT OR IGNORE INTO chart_of_accounts (code, name, type) VALUES ('5000', 'تكلفة البضاعة المباعة', 'Expense');
INSERT OR IGNORE INTO chart_of_accounts (code, name, type) VALUES ('5100', 'الرواتب والأجور', 'Expense');
INSERT OR IGNORE INTO chart_of_accounts (code, name, type) VALUES ('5150', 'مصروفات مرتبطة بالمشتريات', 'Expense');
INSERT OR IGNORE INTO chart_of_accounts (code, name, type) VALUES ('5200', 'المصاريف التشغيلية', 'Expense');


