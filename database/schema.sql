-- Branches Table
CREATE TABLE IF NOT EXISTS branches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    location TEXT
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

-- Menu Categories
CREATE TABLE IF NOT EXISTS menu_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    sort_order INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1
);

-- Menu Items
CREATE TABLE IF NOT EXISTS menu_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER,
    name TEXT NOT NULL,
    price REAL NOT NULL DEFAULT 0,
    image_path TEXT,
    is_active INTEGER DEFAULT 1,
    sort_order INTEGER DEFAULT 0,
    FOREIGN KEY (category_id) REFERENCES menu_categories(id)
);

-- Sales Orders (POS)
CREATE TABLE IF NOT EXISTS sales_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    branch_id INTEGER,
    order_no TEXT,
    cashier_name TEXT,
    payment_method TEXT CHECK(payment_method IN ('Cash', 'POS', 'Transfer')),
    subtotal REAL DEFAULT 0,
    vat_amount REAL DEFAULT 0,
    total_amount REAL DEFAULT 0,
    qr_code TEXT,
    date DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (branch_id) REFERENCES branches(id)
);

CREATE TABLE IF NOT EXISTS sales_order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER,
    item_id INTEGER,
    item_name TEXT,
    unit_price REAL DEFAULT 0,
    quantity INTEGER DEFAULT 1,
    line_total REAL DEFAULT 0,
    FOREIGN KEY (order_id) REFERENCES sales_orders(id),
    FOREIGN KEY (item_id) REFERENCES menu_items(id)
);

-- Sales Table
CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    branch_id INTEGER,
    date DATETIME DEFAULT CURRENT_TIMESTAMP,
    total_amount REAL,
    vat_amount REAL,
    payment_method TEXT CHECK(payment_method IN ('Cash', 'POS', 'Transfer')),
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
    refund_method TEXT CHECK(refund_method IN ('Cash', 'POS', 'Transfer')),
    notes TEXT,
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

-- Initial Data for Branches
INSERT OR IGNORE INTO branches (id, name, location) VALUES (1, 'فرع الرياض', 'الرياض - العليا');
INSERT OR IGNORE INTO branches (id, name, location) VALUES (2, 'فرع جدة', 'جدة - الروضة');

-- Initial Chart of Accounts
INSERT OR IGNORE INTO chart_of_accounts (code, name, type) VALUES ('1000', 'النقدية', 'Asset');
INSERT OR IGNORE INTO chart_of_accounts (code, name, type) VALUES ('1001', 'البنك', 'Asset');
INSERT OR IGNORE INTO chart_of_accounts (code, name, type) VALUES ('1100', 'المخزون', 'Asset');
INSERT OR IGNORE INTO chart_of_accounts (code, name, type) VALUES ('1200', 'ضريبة المشتريات (Input VAT)', 'Asset');
INSERT OR IGNORE INTO chart_of_accounts (code, name, type) VALUES ('1300', 'سلف الموظفين', 'Asset');
INSERT OR IGNORE INTO chart_of_accounts (code, name, type) VALUES ('2000', 'الموردون (AP)', 'Liability');
INSERT OR IGNORE INTO chart_of_accounts (code, name, type) VALUES ('2100', 'ضريبة المبيعات (Output VAT)', 'Liability');
INSERT OR IGNORE INTO chart_of_accounts (code, name, type) VALUES ('3000', 'رأس المال', 'Equity');
INSERT OR IGNORE INTO chart_of_accounts (code, name, type) VALUES ('3900', 'الأرصدة الافتتاحية', 'Equity');
INSERT OR IGNORE INTO chart_of_accounts (code, name, type) VALUES ('4000', 'المبيعات', 'Revenue');
INSERT OR IGNORE INTO chart_of_accounts (code, name, type) VALUES ('5000', 'تكلفة البضاعة المباعة (COGS)', 'Expense');
INSERT OR IGNORE INTO chart_of_accounts (code, name, type) VALUES ('5100', 'الرواتب والأجور', 'Expense');
INSERT OR IGNORE INTO chart_of_accounts (code, name, type) VALUES ('5150', 'مصروفات مرتبطة بالمشتريات', 'Expense');
INSERT OR IGNORE INTO chart_of_accounts (code, name, type) VALUES ('5200', 'المصاريف التشغيلية', 'Expense');

-- Initial Menu Categories
INSERT OR IGNORE INTO menu_categories (id, name, sort_order, is_active) VALUES (1, 'وجبات', 1, 1);
INSERT OR IGNORE INTO menu_categories (id, name, sort_order, is_active) VALUES (2, 'مشروبات', 2, 1);
INSERT OR IGNORE INTO menu_categories (id, name, sort_order, is_active) VALUES (3, 'وجبات خفيفة', 3, 1);

-- Initial Menu Items
INSERT OR IGNORE INTO menu_items (id, category_id, name, price, image_path, is_active, sort_order) VALUES (1, 1, 'برجر دجاج', 24.00, '', 1, 1);
INSERT OR IGNORE INTO menu_items (id, category_id, name, price, image_path, is_active, sort_order) VALUES (2, 1, 'شاورما دجاج', 18.00, '', 1, 2);
INSERT OR IGNORE INTO menu_items (id, category_id, name, price, image_path, is_active, sort_order) VALUES (3, 2, 'ماء', 2.00, '', 1, 1);
INSERT OR IGNORE INTO menu_items (id, category_id, name, price, image_path, is_active, sort_order) VALUES (4, 2, 'مشروب غازي', 5.00, '', 1, 2);
INSERT OR IGNORE INTO menu_items (id, category_id, name, price, image_path, is_active, sort_order) VALUES (5, 3, 'بطاطس', 8.00, '', 1, 1);
