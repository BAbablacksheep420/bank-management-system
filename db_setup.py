import datetime
import hashlib
import os
import secrets
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "bank_system.db")


def hash_password(password: str, salt_hex: str | None = None) -> str:
    """Hash a password using PBKDF2-HMAC-SHA256 with a per-user salt."""
    if not salt_hex:
        salt_hex = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), 100_000
    )
    return f"pbkdf2_sha256${salt_hex}${dk.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a plaintext password against a stored PBKDF2-HMAC-SHA256 hash."""
    if not stored_hash or "$" not in stored_hash:
        return False
    parts = stored_hash.split("$")
    if len(parts) != 3 or parts[0] != "pbkdf2_sha256":
        return False
    _, salt_hex, expected_hex = parts
    candidate = hash_password(password, salt_hex)
    return secrets.compare_digest(candidate.split("$")[2], expected_hex)


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

-- 1. Companies (Multi-Bank Tenants)
CREATE TABLE IF NOT EXISTS companies (
    company_code VARCHAR(10) PRIMARY KEY,
    company_name VARCHAR(100) NOT NULL,
    short_code VARCHAR(10) NOT NULL DEFAULT 'BANK',
    swift_code VARCHAR(20),
    currency_code VARCHAR(10) NOT NULL DEFAULT 'INR',
    currency_symbol VARCHAR(5) NOT NULL DEFAULT '₹',
    brand_color VARCHAR(20) NOT NULL DEFAULT '#10b981',
    headquarters_address TEXT,
    phone VARCHAR(20),
    established_date DATE,
    total_assets DECIMAL(15,2) DEFAULT 0.0,
    status VARCHAR(15) NOT NULL CHECK(status IN ('active', 'inactive')) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Roles (RBAC Permission Matrix)
CREATE TABLE IF NOT EXISTS roles (
    role_code VARCHAR(20) PRIMARY KEY,
    role_name VARCHAR(60) NOT NULL,
    description TEXT,
    hierarchy_level INT NOT NULL,
    can_manage_banks TINYINT NOT NULL DEFAULT 0,
    can_manage_staff TINYINT NOT NULL DEFAULT 0,
    can_manage_customers TINYINT NOT NULL DEFAULT 0,
    can_manage_accounts TINYINT NOT NULL DEFAULT 0,
    can_freeze_accounts TINYINT NOT NULL DEFAULT 0,
    can_transact TINYINT NOT NULL DEFAULT 0,
    can_manage_cards TINYINT NOT NULL DEFAULT 0,
    can_sanction_loans TINYINT NOT NULL DEFAULT 0,
    can_repay_loans TINYINT NOT NULL DEFAULT 0,
    can_run_sql_read TINYINT NOT NULL DEFAULT 0,
    can_run_sql_write TINYINT NOT NULL DEFAULT 0,
    can_view_audit TINYINT NOT NULL DEFAULT 0
);

-- 3. Branches Table
CREATE TABLE IF NOT EXISTS branches (
    branch_code VARCHAR(15) PRIMARY KEY,
    company_code VARCHAR(10) NOT NULL,
    branch_name VARCHAR(100) NOT NULL,
    address TEXT,
    phone VARCHAR(20),
    manager_name VARCHAR(100),
    opening_hours TIME,
    closing_hours TIME,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_code) REFERENCES companies(company_code) ON DELETE CASCADE ON UPDATE CASCADE
);

-- 4. Employees Table
CREATE TABLE IF NOT EXISTS employees (
    employee_id VARCHAR(10) PRIMARY KEY,
    company_code VARCHAR(10),
    branch_code VARCHAR(15),
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    phone VARCHAR(20) UNIQUE,
    position VARCHAR(50),
    salary DECIMAL(10,2),
    hire_date DATE,
    department VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_code) REFERENCES companies(company_code) ON DELETE SET NULL ON UPDATE CASCADE,
    FOREIGN KEY (branch_code) REFERENCES branches(branch_code) ON DELETE SET NULL ON UPDATE CASCADE
);

-- 5. Operators Table (Non-Manager & Manager DB Access Accounts)
CREATE TABLE IF NOT EXISTS operators (
    operator_id VARCHAR(12) PRIMARY KEY,
    employee_id VARCHAR(10),
    company_code VARCHAR(10),
    branch_code VARCHAR(15),
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    role_code VARCHAR(20) NOT NULL,
    is_active TINYINT NOT NULL DEFAULT 1,
    last_login TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE SET NULL ON UPDATE CASCADE,
    FOREIGN KEY (company_code) REFERENCES companies(company_code) ON DELETE SET NULL ON UPDATE CASCADE,
    FOREIGN KEY (branch_code) REFERENCES branches(branch_code) ON DELETE SET NULL ON UPDATE CASCADE,
    FOREIGN KEY (role_code) REFERENCES roles(role_code) ON DELETE RESTRICT ON UPDATE CASCADE
);

-- 6. Account Types (Global Templates or Bank-Specific Products)
CREATE TABLE IF NOT EXISTS account_types (
    account_type_code VARCHAR(10) PRIMARY KEY,
    company_code VARCHAR(10),
    type_name VARCHAR(50) NOT NULL,
    description TEXT,
    minimum_balance DECIMAL(10,2) DEFAULT 0.0,
    interest_rate DECIMAL(5,4) DEFAULT 0.0,
    allows_overdraft TINYINT DEFAULT 0,
    FOREIGN KEY (company_code) REFERENCES companies(company_code) ON DELETE CASCADE ON UPDATE CASCADE
);

-- 7. Transaction Categories
CREATE TABLE IF NOT EXISTS transaction_categories (
    category_code VARCHAR(10) PRIMARY KEY,
    category_name VARCHAR(50) NOT NULL,
    description TEXT,
    category_type VARCHAR(10) CHECK(category_type IN ('income', 'expense'))
);

-- 8. Customers Table
CREATE TABLE IF NOT EXISTS customers (
    customer_id VARCHAR(10) PRIMARY KEY,
    company_code VARCHAR(10),
    branch_code VARCHAR(15),
    relationship_manager_id VARCHAR(10),
    created_by_operator_id VARCHAR(12),
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    phone VARCHAR(20) UNIQUE,
    address TEXT,
    date_of_birth DATE NOT NULL,
    id_number VARCHAR(50) UNIQUE,
    credit_score DECIMAL(4,0),
    registration_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_code) REFERENCES companies(company_code) ON DELETE SET NULL ON UPDATE CASCADE,
    FOREIGN KEY (branch_code) REFERENCES branches(branch_code) ON DELETE SET NULL ON UPDATE CASCADE,
    FOREIGN KEY (relationship_manager_id) REFERENCES employees(employee_id) ON DELETE SET NULL ON UPDATE CASCADE,
    FOREIGN KEY (created_by_operator_id) REFERENCES operators(operator_id) ON DELETE SET NULL ON UPDATE CASCADE
);

-- 9. Accounts Table
CREATE TABLE IF NOT EXISTS accounts (
    account_number VARCHAR(20) PRIMARY KEY,
    company_code VARCHAR(10),
    branch_code VARCHAR(15),
    customer_id VARCHAR(10) NOT NULL,
    account_type_code VARCHAR(10) NOT NULL,
    opened_by_operator_id VARCHAR(12),
    balance DECIMAL(15,2) DEFAULT 0.0,
    opening_date DATE NOT NULL,
    status VARCHAR(10) NOT NULL CHECK(status IN ('active', 'closed', 'frozen')) DEFAULT 'active',
    overdraft_limit DECIMAL(10,2) DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_code) REFERENCES companies(company_code) ON DELETE SET NULL ON UPDATE CASCADE,
    FOREIGN KEY (branch_code) REFERENCES branches(branch_code) ON DELETE SET NULL ON UPDATE CASCADE,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (account_type_code) REFERENCES account_types(account_type_code) ON DELETE RESTRICT ON UPDATE CASCADE,
    FOREIGN KEY (opened_by_operator_id) REFERENCES operators(operator_id) ON DELETE SET NULL ON UPDATE CASCADE
);

-- 10. Transactions Table
CREATE TABLE IF NOT EXISTS transactions (
    transaction_reference VARCHAR(20) PRIMARY KEY,
    company_code VARCHAR(10),
    account_number VARCHAR(20) NOT NULL,
    category_code VARCHAR(10),
    performed_by_operator_id VARCHAR(12),
    transaction_type VARCHAR(10) NOT NULL CHECK(transaction_type IN ('credit', 'debit')),
    amount DECIMAL(15,2) NOT NULL CHECK(amount > 0),
    description TEXT,
    transaction_date DATETIME NOT NULL,
    running_balance DECIMAL(15,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_code) REFERENCES companies(company_code) ON DELETE SET NULL ON UPDATE CASCADE,
    FOREIGN KEY (account_number) REFERENCES accounts(account_number) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (category_code) REFERENCES transaction_categories(category_code) ON DELETE SET NULL ON UPDATE CASCADE,
    FOREIGN KEY (performed_by_operator_id) REFERENCES operators(operator_id) ON DELETE SET NULL ON UPDATE CASCADE
);

-- 11. Cards Table
CREATE TABLE IF NOT EXISTS cards (
    card_id VARCHAR(20) PRIMARY KEY,
    company_code VARCHAR(10),
    customer_id VARCHAR(10) NOT NULL,
    linked_account_number VARCHAR(20) NOT NULL,
    issued_by_operator_id VARCHAR(12),
    card_number_masked VARCHAR(255) NOT NULL,
    card_type VARCHAR(10) NOT NULL CHECK(card_type IN ('debit', 'credit', 'prepaid')),
    issue_date DATE NOT NULL,
    expiry_date DATE NOT NULL,
    credit_limit DECIMAL(10,2) DEFAULT 0.0,
    pin_hash VARCHAR(255),
    status VARCHAR(10) NOT NULL CHECK(status IN ('active', 'blocked', 'expired')) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_code) REFERENCES companies(company_code) ON DELETE SET NULL ON UPDATE CASCADE,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (linked_account_number) REFERENCES accounts(account_number) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (issued_by_operator_id) REFERENCES operators(operator_id) ON DELETE SET NULL ON UPDATE CASCADE
);

-- 12. Loans Table
CREATE TABLE IF NOT EXISTS loans (
    loan_number VARCHAR(20) PRIMARY KEY,
    company_code VARCHAR(10),
    customer_id VARCHAR(10) NOT NULL,
    approved_by_operator_id VARCHAR(12),
    loan_type VARCHAR(20) NOT NULL CHECK(loan_type IN ('home', 'personal', 'education', 'car', 'business')),
    principal_amount DECIMAL(15,2) NOT NULL CHECK(principal_amount > 0),
    interest_rate DECIMAL(5,4) NOT NULL,
    term_months INT NOT NULL CHECK(term_months > 0),
    monthly_payment DECIMAL(10,2) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    status VARCHAR(10) NOT NULL CHECK(status IN ('running', 'closed', 'defaulted')) DEFAULT 'running',
    outstanding_balance DECIMAL(15,2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_code) REFERENCES companies(company_code) ON DELETE SET NULL ON UPDATE CASCADE,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (approved_by_operator_id) REFERENCES operators(operator_id) ON DELETE SET NULL ON UPDATE CASCADE
);

-- 13. Audit Logs Table (Accountability for All Operators & Multi-Bank Mutations)
CREATE TABLE IF NOT EXISTS audit_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    operator_id VARCHAR(12),
    operator_username VARCHAR(50),
    role_code VARCHAR(20),
    company_code VARCHAR(10),
    action VARCHAR(50) NOT NULL,
    target_table VARCHAR(50),
    target_id VARCHAR(40),
    status VARCHAR(15) NOT NULL CHECK(status IN ('SUCCESS', 'DENIED', 'ERROR')) DEFAULT 'SUCCESS',
    details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (operator_id) REFERENCES operators(operator_id) ON DELETE SET NULL ON UPDATE CASCADE,
    FOREIGN KEY (company_code) REFERENCES companies(company_code) ON DELETE SET NULL ON UPDATE CASCADE
);
"""

INDEXES_SQL = """
-- Performance Indexes
CREATE INDEX IF NOT EXISTS idx_branches_company ON branches(company_code);
CREATE INDEX IF NOT EXISTS idx_employees_branch ON employees(branch_code);
CREATE INDEX IF NOT EXISTS idx_employees_company ON employees(company_code);
CREATE INDEX IF NOT EXISTS idx_operators_company ON operators(company_code);
CREATE INDEX IF NOT EXISTS idx_operators_role ON operators(role_code);
CREATE INDEX IF NOT EXISTS idx_customers_company ON customers(company_code);
CREATE INDEX IF NOT EXISTS idx_accounts_customer ON accounts(customer_id);
CREATE INDEX IF NOT EXISTS idx_accounts_company ON accounts(company_code);
CREATE INDEX IF NOT EXISTS idx_transactions_account ON transactions(account_number);
CREATE INDEX IF NOT EXISTS idx_transactions_company ON transactions(company_code);
CREATE INDEX IF NOT EXISTS idx_cards_account ON cards(linked_account_number);
CREATE INDEX IF NOT EXISTS idx_cards_company ON cards(company_code);
CREATE INDEX IF NOT EXISTS idx_loans_customer ON loans(customer_id);
CREATE INDEX IF NOT EXISTS idx_loans_company ON loans(company_code);
CREATE INDEX IF NOT EXISTS idx_audit_company ON audit_logs(company_code);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at);
"""


DEFAULT_ROLES = [
    # code, name, desc, level, banks, staff, cust, acc, freeze, txn, cards, loan_sanc, loan_repay, sql_r, sql_w, audit
    (
        "SUPER_ADMIN",
        "Consortium Super Admin",
        "System-wide database administrator across all onboarded banks with full SQL write and bank provisioning rights.",
        100,
        1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
    ),
    (
        "BANK_ADMIN",
        "Bank Administrator",
        "Tenant administrator for a single bank: manages its branches, staff, operators, products, and full bank operations.",
        85,
        0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1,
    ),
    (
        "BRANCH_MANAGER",
        "Branch Manager",
        "Oversees daily branch operations: accounts, freezing/closing, loans, cards, staff visibility, and read-only SQL.",
        70,
        0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1,
    ),
    (
        "TELLER",
        "Cash & Vault Teller",
        "Front-desk non-manager operator: executes deposits, withdrawals, transfers, and customer/account lookups.",
        40,
        0, 0, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0,
    ),
    (
        "RELATIONSHIP_MGR",
        "Relationship Manager",
        "Customer onboarding specialist: registers KYC profiles, opens accounts, and issues debit/credit cards.",
        50,
        0, 0, 1, 1, 0, 0, 1, 0, 0, 0, 0, 0,
    ),
    (
        "CREDIT_ANALYST",
        "Credit & Loan Analyst",
        "Lending & risk operator: evaluates credit scores, sanctions new loans, and processes EMI repayments.",
        55,
        0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 0, 0,
    ),
    (
        "AUDITOR",
        "Compliance Auditor",
        "Read-only oversight role across banks, ledgers, audit logs, and SELECT-only SQL analytics.",
        60,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 1,
    ),
]


def _table_columns(cursor: sqlite3.Cursor, table_name: str) -> set[str]:
    cursor.execute(f"PRAGMA table_info({table_name})")
    return {row[1] for row in cursor.fetchall()}


def _add_column_if_missing(
    cursor: sqlite3.Cursor, table_name: str, col_name: str, col_def: str
) -> None:
    if col_name not in _table_columns(cursor, table_name):
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def}")


def _seed_roles_and_operators(cursor: sqlite3.Cursor) -> None:
    for role in DEFAULT_ROLES:
        cursor.execute(
            """
            INSERT OR IGNORE INTO roles (
                role_code, role_name, description, hierarchy_level,
                can_manage_banks, can_manage_staff, can_manage_customers,
                can_manage_accounts, can_freeze_accounts, can_transact,
                can_manage_cards, can_sanction_loans, can_repay_loans,
                can_run_sql_read, can_run_sql_write, can_view_audit
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            role,
        )

    cursor.execute("SELECT COUNT(*) FROM operators")
    if cursor.fetchone()[0] == 0:
        demo_operators = [
            ("OP001", None, None, None, "sysadmin", hash_password("Admin@123"), "Consortium System Admin", "SUPER_ADMIN", 1),
            ("OP002", "EMP001", "COMP001", "BR001", "rajesh.mgr", hash_password("Bank@123"), "Rajesh Sharma", "BRANCH_MANAGER", 1),
            ("OP003", "EMP003", "COMP001", "BR001", "amit.teller", hash_password("Bank@123"), "Amit Trivedi", "TELLER", 1),
            ("OP004", "EMP002", "COMP001", "BR001", "sneha.rm", hash_password("Bank@123"), "Sneha Kapoor", "RELATIONSHIP_MGR", 1),
            ("OP005", "EMP007", "COMP001", "BR003", "deepika.credit", hash_password("Bank@123"), "Deepika Menon", "CREDIT_ANALYST", 1),
            ("OP006", "EMP008", "COMP002", "BR004", "ananya.gfc", hash_password("Bank@123"), "Ananya Gupta", "BANK_ADMIN", 1),
            ("OP007", "EMP009", "COMP003", "BR005", "karthik.mbg", hash_password("Bank@123"), "Karthik Nambiar", "BANK_ADMIN", 1),
            ("OP008", "EMP010", "COMP003", "BR005", "ritu.teller", hash_password("Bank@123"), "Ritu Kaur", "TELLER", 1),
            ("OP009", None, None, None, "compliance.audit", hash_password("Audit@123"), "Central Compliance Auditor", "AUDITOR", 1),
        ]
        cursor.executemany(
            """
            INSERT INTO operators (
                operator_id, employee_id, company_code, branch_code,
                username, password_hash, full_name, role_code, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            demo_operators,
        )


def ensure_schema_and_seed(db_path: str = DB_PATH) -> None:
    """Create or migrate the database to the multi-bank RBAC schema and ensure seed data."""
    conn = sqlite3.connect(db_path, timeout=15.0)
    conn.execute("PRAGMA foreign_keys = OFF;")
    cursor = conn.cursor()

    # Create any missing tables first
    cursor.executescript(SCHEMA_SQL)

    # Backfill new columns on pre-existing 10-table databases
    _add_column_if_missing(cursor, "companies", "short_code", "VARCHAR(10) NOT NULL DEFAULT 'BANK'")
    _add_column_if_missing(cursor, "companies", "swift_code", "VARCHAR(20)")
    _add_column_if_missing(cursor, "companies", "currency_code", "VARCHAR(10) NOT NULL DEFAULT 'INR'")
    _add_column_if_missing(cursor, "companies", "currency_symbol", "VARCHAR(5) NOT NULL DEFAULT '₹'")
    _add_column_if_missing(cursor, "companies", "brand_color", "VARCHAR(20) NOT NULL DEFAULT '#10b981'")
    _add_column_if_missing(cursor, "companies", "status", "VARCHAR(15) NOT NULL DEFAULT 'active'")

    _add_column_if_missing(cursor, "employees", "company_code", "VARCHAR(10)")
    _add_column_if_missing(cursor, "account_types", "company_code", "VARCHAR(10)")

    _add_column_if_missing(cursor, "customers", "company_code", "VARCHAR(10)")
    _add_column_if_missing(cursor, "customers", "branch_code", "VARCHAR(15)")
    _add_column_if_missing(cursor, "customers", "created_by_operator_id", "VARCHAR(12)")

    _add_column_if_missing(cursor, "accounts", "company_code", "VARCHAR(10)")
    _add_column_if_missing(cursor, "accounts", "branch_code", "VARCHAR(15)")
    _add_column_if_missing(cursor, "accounts", "opened_by_operator_id", "VARCHAR(12)")

    _add_column_if_missing(cursor, "transactions", "company_code", "VARCHAR(10)")
    _add_column_if_missing(cursor, "transactions", "performed_by_operator_id", "VARCHAR(12)")

    _add_column_if_missing(cursor, "cards", "company_code", "VARCHAR(10)")
    _add_column_if_missing(cursor, "cards", "issued_by_operator_id", "VARCHAR(12)")

    _add_column_if_missing(cursor, "loans", "company_code", "VARCHAR(10)")
    _add_column_if_missing(cursor, "loans", "approved_by_operator_id", "VARCHAR(12)")

    # Ensure indexes exist even on migrated databases
    cursor.executescript(INDEXES_SQL)

    cursor.execute("SELECT COUNT(*) FROM companies")
    is_fresh = cursor.fetchone()[0] == 0

    if is_fresh:
        _seed_core_data(cursor)
    else:
        # Backfill tenant company_code & branding metadata on migrated rows
        company_defaults = [
            ("NBI", "NBIINBBXXX", "INR", "₹", "#10b981", "COMP001"),
            ("GFC", "GFCFINBBXXX", "INR", "₹", "#6366f1", "COMP002"),
            ("MBG", "MBGBINBBXXX", "INR", "₹", "#06b6d4", "COMP003"),
        ]
        cursor.executemany(
            """
            UPDATE companies
            SET short_code = COALESCE(NULLIF(short_code, 'BANK'), ?),
                swift_code = COALESCE(swift_code, ?),
                currency_code = COALESCE(currency_code, ?),
                currency_symbol = COALESCE(currency_symbol, ?),
                brand_color = COALESCE(brand_color, ?)
            WHERE company_code = ?
            """,
            company_defaults,
        )
        cursor.execute(
            """
            UPDATE employees
            SET company_code = (SELECT b.company_code FROM branches b WHERE b.branch_code = employees.branch_code)
            WHERE company_code IS NULL AND branch_code IS NOT NULL
            """
        )
        cursor.execute(
            """
            UPDATE customers
            SET branch_code = COALESCE(branch_code, (SELECT e.branch_code FROM employees e WHERE e.employee_id = customers.relationship_manager_id)),
                company_code = COALESCE(company_code, (SELECT e.company_code FROM employees e WHERE e.employee_id = customers.relationship_manager_id), 'COMP001')
            WHERE company_code IS NULL
            """
        )
        cursor.execute(
            """
            UPDATE accounts
            SET company_code = COALESCE(company_code, (SELECT c.company_code FROM customers c WHERE c.customer_id = accounts.customer_id), 'COMP001'),
                branch_code = COALESCE(branch_code, (SELECT c.branch_code FROM customers c WHERE c.customer_id = accounts.customer_id))
            WHERE company_code IS NULL
            """
        )
        cursor.execute(
            """
            UPDATE transactions
            SET company_code = COALESCE(company_code, (SELECT a.company_code FROM accounts a WHERE a.account_number = transactions.account_number), 'COMP001')
            WHERE company_code IS NULL
            """
        )
        cursor.execute(
            """
            UPDATE cards
            SET company_code = COALESCE(company_code, (SELECT a.company_code FROM accounts a WHERE a.account_number = cards.linked_account_number), 'COMP001')
            WHERE company_code IS NULL
            """
        )
        cursor.execute(
            """
            UPDATE loans
            SET company_code = COALESCE(company_code, (SELECT c.company_code FROM customers c WHERE c.customer_id = loans.customer_id), 'COMP001')
            WHERE company_code IS NULL
            """
        )

    _seed_roles_and_operators(cursor)

    # Seed an initial audit record if audit_logs is empty
    cursor.execute("SELECT COUNT(*) FROM audit_logs")
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            """
            INSERT INTO audit_logs (operator_id, operator_username, role_code, company_code, action, target_table, target_id, status, details)
            VALUES ('OP001', 'sysadmin', 'SUPER_ADMIN', NULL, 'SYSTEM_INIT', 'schema', 'v2_multibank_rbac', 'SUCCESS', 'Initialized multi-bank RBAC schema and operator accounts')
            """
        )

    conn.commit()
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.close()


def _seed_core_data(cursor: sqlite3.Cursor) -> None:
    print("Seeding initial DTU CS209 Multi-Bank RBAC Banking Data...")

    # 1. Companies (Multiple Banks)
    companies = [
        ("COMP001", "National Bank of India", "NBI", "NBIINBBXXX", "INR", "₹", "#10b981", "Tower A, BKC, Mumbai, Maharashtra 400051", "+91-22-66801234", "1990-01-15", 5000000000.00, "active"),
        ("COMP002", "Global Finance Corp", "GFC", "GFCFINBBXXX", "INR", "₹", "#6366f1", "Sector 62, Noida, Uttar Pradesh 201301", "+91-120-4567890", "1995-03-20", 3500000000.00, "active"),
        ("COMP003", "Metro Banking Group", "MBG", "MBGBINBBXXX", "INR", "₹", "#06b6d4", "MG Road, Bangalore, Karnataka 560001", "+91-80-25591234", "2000-07-10", 2800000000.00, "active"),
    ]
    cursor.executemany(
        """
        INSERT INTO companies (
            company_code, company_name, short_code, swift_code, currency_code, currency_symbol,
            brand_color, headquarters_address, phone, established_date, total_assets, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        companies,
    )

    # 2. Branches
    branches = [
        ("BR001", "COMP001", "Connaught Place Main", "Block B, Connaught Place, New Delhi 110001", "+91-11-23340001", "Rajesh Sharma", "09:30:00", "16:30:00"),
        ("BR002", "COMP001", "Rohini Sector 14", "Plot 12, Sector 14, Rohini, Delhi 110085", "+91-11-27050002", "Pooja Verma", "09:30:00", "16:30:00"),
        ("BR003", "COMP001", "BKC Corporate Hub", "G-Block, BKC, Bandra East, Mumbai 400051", "+91-22-26590003", "Vikramaditya Rao", "09:00:00", "17:00:00"),
        ("BR004", "COMP002", "Indirapuram Tech Park", "Ahinsa Khand, Indirapuram, Ghaziabad 201014", "+91-120-2890004", "Ananya Gupta", "10:00:00", "16:00:00"),
        ("BR005", "COMP003", "Koramangala Fintech Hub", "80 Feet Road, 4th Block, Koramangala, Bangalore 560034", "+91-80-41230005", "Karthik Nambiar", "09:30:00", "17:30:00"),
    ]
    cursor.executemany(
        "INSERT INTO branches (branch_code, company_code, branch_name, address, phone, manager_name, opening_hours, closing_hours) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        branches,
    )

    # 3. Employees
    employees = [
        ("EMP001", "COMP001", "BR001", "Rajesh", "Sharma", "rajesh.sharma@nbi-bank.in", "+91-9811000001", "Branch Manager", 145000.00, "2012-04-10", "Branch Operations"),
        ("EMP002", "COMP001", "BR001", "Sneha", "Kapoor", "sneha.kapoor@nbi-bank.in", "+91-9811000002", "Senior Relationship Manager", 98000.00, "2016-08-15", "Retail Banking"),
        ("EMP003", "COMP001", "BR001", "Amit", "Trivedi", "amit.trivedi@nbi-bank.in", "+91-9811000003", "Cash & Vault Officer", 62000.00, "2019-01-20", "Cash Management"),
        ("EMP004", "COMP001", "BR002", "Pooja", "Verma", "pooja.verma@nbi-bank.in", "+91-9811000004", "Branch Manager", 135000.00, "2014-06-01", "Branch Operations"),
        ("EMP005", "COMP001", "BR002", "Naveen", "Chawla", "naveen.chawla@nbi-bank.in", "+91-9811000005", "Relationship Manager", 75000.00, "2020-03-12", "Retail Banking"),
        ("EMP006", "COMP001", "BR003", "Vikramaditya", "Rao", "vikram.rao@nbi-bank.in", "+91-9811000006", "Corporate General Manager", 190000.00, "2010-11-05", "Corporate Banking"),
        ("EMP007", "COMP001", "BR003", "Deepika", "Menon", "deepika.menon@nbi-bank.in", "+91-9811000007", "Senior Credit Analyst", 105000.00, "2018-09-17", "Credit Risk"),
        ("EMP008", "COMP002", "BR004", "Ananya", "Gupta", "ananya.gupta@gfc-bank.in", "+91-9811000008", "Branch Manager", 128000.00, "2015-05-22", "Branch Operations"),
        ("EMP009", "COMP003", "BR005", "Karthik", "Nambiar", "karthik.n@mbg-bank.in", "+91-9811000009", "AVP Digital Banking", 160000.00, "2013-02-14", "Digital Products"),
        ("EMP010", "COMP003", "BR005", "Ritu", "Kaur", "ritu.kaur@mbg-bank.in", "+91-9811000010", "Customer Relationship Exec", 54000.00, "2021-10-01", "Retail Banking"),
    ]
    cursor.executemany(
        "INSERT INTO employees (employee_id, company_code, branch_code, first_name, last_name, email, phone, position, salary, hire_date, department) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        employees,
    )

    # 4. Roles & Operators (needed before FK references on customers/accounts/txns/cards/loans)
    _seed_roles_and_operators(cursor)

    # 5. Account Types (Global standards + bank-specific product showcase)
    account_types = [
        ("SAV001", None, "Savings Account", "Standard savings account with quarterly interest & debit card", 1000.00, 0.0350, 0),
        ("CURR001", None, "Current Account", "Business current account with high transaction limit & overdraft facility", 5000.00, 0.0000, 1),
        ("FD001", None, "Fixed Deposit", "Fixed tenure deposit account yielding guaranteed annual returns", 10000.00, 0.0650, 0),
        ("SAL001", None, "Salary Account", "Corporate zero balance salary account with lounge access", 0.00, 0.0300, 0),
        ("BUS001", None, "Business Account", "Tiered business account with bulk payroll and multi-currency support", 25000.00, 0.0200, 1),
        ("GFC_HY", "COMP002", "GFC High-Yield Wealth", "Global Finance Corp exclusive wealth savings tier", 50000.00, 0.0525, 0),
        ("MBG_DIGI", "COMP003", "MBG Zero-Fee Neo", "Metro Banking Group instant digital checking product", 0.00, 0.0400, 1),
    ]
    cursor.executemany("INSERT INTO account_types VALUES (?, ?, ?, ?, ?, ?, ?)", account_types)

    # 6. Transaction Categories
    categories = [
        ("CAT001", "Salary Credit", "Monthly corporate payroll direct deposit", "income"),
        ("CAT002", "ATM Withdrawal", "Automated teller cash withdrawal", "expense"),
        ("CAT003", "Online Transfer", "Instant NEFT/RTGS/IMPS fund transfer", "expense"),
        ("CAT004", "Bill Payment", "Electricity, water, broadband, or mobile utility payment", "expense"),
        ("CAT005", "Interest Credit", "Compounded interest credited on quarterly basis", "income"),
        ("CAT006", "Deposit", "Direct cash or cleared cheque deposit", "income"),
        ("CAT007", "Shopping", "POS merchant swipe or online eCommerce shopping", "expense"),
        ("CAT008", "Refund", "Merchant reversal or dispute charge refund", "income"),
    ]
    cursor.executemany("INSERT INTO transaction_categories VALUES (?, ?, ?, ?)", categories)

    # 7. Customers (Assigned across COMP001, COMP002, COMP003)
    customers = [
        ("CUST001", "COMP001", "BR001", "EMP002", "OP004", "Arnav", "Gupta", "arnavgupta@gmail.com", "+91-9650910304", "B-99, Amar Colony, New Delhi", "2007-03-25", "AADH123456789", 758.0, "2021-07-21"),
        ("CUST002", "COMP001", "BR001", "EMP002", "OP004", "Aarav", "Malhotra", "aarav.malhotra@gmail.com", "+91-9876543220", "D-45, Vasant Kunj, New Delhi", "1998-05-15", "AADH234567890", 820.0, "2020-03-10"),
        ("CUST003", "COMP001", "BR001", "EMP002", "OP004", "Diya", "Kapoor", "diya.kapoor@gmail.com", "+91-9876543221", "C-78, Saket, New Delhi", "1980-11-22", "AADH345678901", 680.0, "2019-08-15"),
        ("CUST004", "COMP001", "BR002", "EMP005", "OP002", "Rohan", "Saxena", "rohan.saxena@yahoo.com", "+91-9876543222", "A-12, Lajpat Nagar, New Delhi", "1992-07-08", "AADH456789012", 795.0, "2021-01-20"),
        ("CUST005", "COMP001", "BR002", "EMP005", "OP002", "Priyanshu", "Nair", "priyanshu.nair@gmail.com", "+91-9876543223", "E-34, Dwarka, New Delhi", "1995-02-14", "AADH567890123", 720.0, "2020-09-05"),
        ("CUST006", "COMP002", "BR004", "EMP008", "OP006", "Arjun", "Chatterjee", "arjun.c@gmail.com", "+91-9876543224", "Sector 22, Noida, Uttar Pradesh", "1987-09-30", "AADH678901234", 760.0, "2019-11-12"),
        ("CUST007", "COMP002", "BR004", "EMP008", "OP006", "Meera", "Iyer", "meera.iyer@hotmail.com", "+91-9876543225", "Sector 50, Noida, Uttar Pradesh", "1993-12-05", "AADH789012345", 810.0, "2020-06-18"),
        ("CUST008", "COMP003", "BR005", "EMP009", "OP007", "Siddharth", "Rao", "siddharth.rao@gmail.com", "+91-9876543226", "Indiranagar, Bangalore, Karnataka", "1991-04-20", "AADH890123456", 735.0, "2021-02-28"),
        ("CUST009", "COMP003", "BR005", "EMP009", "OP007", "Anjali", "Menon", "anjali.menon@gmail.com", "+91-9876543227", "Koramangala, Bangalore, Karnataka", "1996-08-17", "AADH901234567", 790.0, "2020-10-15"),
        ("CUST010", "COMP003", "BR005", "EMP010", "OP007", "Karan", "Bhatia", "karan.bhatia@gmail.com", "+91-9876543228", "HSR Layout, Bangalore, Karnataka", "1994-06-11", "AADH012345678", 664.0, "2022-05-22"),
        ("CUST011", "COMP001", "BR001", "EMP002", "OP004", "Punit", "Gambhir", "punit@gmail.com", "+91-9871630011", "B-99, New Delhi", "1974-12-23", "AADH09382", 841.0, "2004-05-19"),
        ("CUST012", "COMP001", "BR002", "EMP005", "OP004", "Lavya", "Yadav", "lavya.yadav@dtu.ac.in", "+91-9988776655", "Sector 17, Rohini, New Delhi", "2006-08-14", "AADH998877661", 775.0, "2022-08-01"),
    ]
    cursor.executemany(
        """
        INSERT INTO customers (
            customer_id, company_code, branch_code, relationship_manager_id, created_by_operator_id,
            first_name, last_name, email, phone, address, date_of_birth, id_number, credit_score, registration_date
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        customers,
    )

    # 8. Accounts
    accounts = [
        ("ACC100001", "COMP001", "BR001", "CUST001", "SAV001", "OP004", 45250.75, "2021-07-21", "active", 0.00),
        ("ACC100002", "COMP001", "BR001", "CUST001", "SAL001", "OP004", 128400.00, "2022-01-10", "active", 0.00),
        ("ACC100003", "COMP001", "BR001", "CUST002", "CURR001", "OP002", 340000.50, "2020-03-10", "active", 100000.00),
        ("ACC100004", "COMP001", "BR001", "CUST002", "FD001", "OP002", 500000.00, "2021-04-01", "active", 0.00),
        ("ACC100005", "COMP001", "BR001", "CUST003", "SAV001", "OP004", 15400.20, "2019-08-15", "active", 0.00),
        ("ACC100006", "COMP001", "BR002", "CUST004", "SAL001", "OP002", 92500.00, "2021-01-20", "active", 0.00),
        ("ACC100007", "COMP001", "BR002", "CUST005", "SAV001", "OP002", 31200.00, "2020-09-05", "active", 0.00),
        ("ACC100008", "COMP002", "BR004", "CUST006", "BUS001", "OP006", 890450.00, "2019-11-12", "active", 250000.00),
        ("ACC100009", "COMP002", "BR004", "CUST007", "GFC_HY", "OP006", 64800.90, "2020-06-18", "active", 0.00),
        ("ACC100010", "COMP003", "BR005", "CUST008", "SAV001", "OP007", 18350.00, "2021-02-28", "active", 0.00),
        ("ACC100011", "COMP003", "BR005", "CUST009", "MBG_DIGI", "OP007", 145000.00, "2020-10-15", "active", 0.00),
        ("ACC100012", "COMP003", "BR005", "CUST010", "SAV001", "OP007", 8200.00, "2022-05-22", "frozen", 0.00),
        ("ACC100013", "COMP001", "BR001", "CUST011", "SAV001", "OP004", 684200.00, "2004-05-19", "active", 50000.00),
        ("ACC100014", "COMP001", "BR002", "CUST012", "SAV001", "OP004", 25000.00, "2022-08-01", "active", 0.00),
    ]
    cursor.executemany(
        """
        INSERT INTO accounts (
            account_number, company_code, branch_code, customer_id, account_type_code,
            opened_by_operator_id, balance, opening_date, status, overdraft_limit
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        accounts,
    )

    # 9. Transactions
    transactions = [
        ("TXN100001", "COMP001", "ACC100001", "CAT006", "OP003", "credit", 25000.00, "Initial branch cash deposit", "2026-09-01 10:15:00", 25000.00),
        ("TXN100002", "COMP001", "ACC100001", "CAT001", "OP003", "credit", 35000.00, "September Stipend / Salary", "2026-09-05 09:00:00", 60000.00),
        ("TXN100003", "COMP001", "ACC100001", "CAT002", "OP003", "debit", 5000.00, "ATM cash withdrawal Connaught Place", "2026-09-10 16:45:00", 55000.00),
        ("TXN100004", "COMP001", "ACC100001", "CAT007", "OP003", "debit", 3549.25, "Electronics retail purchase", "2026-09-15 19:20:00", 51450.75),
        ("TXN100005", "COMP001", "ACC100001", "CAT004", "OP003", "debit", 6200.00, "Airtel Broadband & Electricity Bill", "2026-09-20 14:10:00", 45250.75),
        ("TXN100006", "COMP001", "ACC100002", "CAT001", "OP003", "credit", 128400.00, "Infosys monthly payroll deposit", "2026-09-30 08:00:00", 128400.00),
        ("TXN100007", "COMP001", "ACC100003", "CAT006", "OP003", "credit", 150000.00, "Client invoice payment", "2026-09-12 11:30:00", 360000.50),
        ("TXN100008", "COMP001", "ACC100003", "CAT003", "OP003", "debit", 20000.00, "Vendor raw materials payment", "2026-09-18 15:00:00", 340000.50),
        ("TXN100009", "COMP001", "ACC100006", "CAT001", "OP002", "credit", 95000.00, "Monthly Corporate Salary", "2026-09-30 09:30:00", 95000.00),
        ("TXN100010", "COMP001", "ACC100006", "CAT004", "OP003", "debit", 2500.00, "Mobile bill payment", "2026-10-02 11:22:00", 92500.00),
        ("TXN100011", "COMP002", "ACC100008", "CAT006", "OP006", "credit", 450000.00, "Contract milestone settlement", "2026-09-25 17:15:00", 890450.00),
        ("TXN100012", "COMP002", "ACC100009", "CAT005", "OP006", "credit", 840.90, "Quarterly interest deposit", "2026-09-30 23:59:00", 64800.90),
        ("TXN100013", "COMP003", "ACC100011", "CAT001", "OP008", "credit", 145000.00, "Google India payroll salary credit", "2026-10-01 07:00:00", 145000.00),
        ("TXN100014", "COMP001", "ACC100013", "CAT006", "OP003", "credit", 200000.00, "Fixed savings transfer", "2026-08-15 12:00:00", 684200.00),
        ("TXN100015", "COMP001", "ACC100014", "CAT006", "OP003", "credit", 25000.00, "Opening initial deposit DTU branch", "2026-08-01 10:00:00", 25000.00),
    ]
    cursor.executemany(
        """
        INSERT INTO transactions (
            transaction_reference, company_code, account_number, category_code, performed_by_operator_id,
            transaction_type, amount, description, transaction_date, running_balance
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        transactions,
    )

    # 10. Cards
    cards = [
        ("CRD001", "COMP001", "CUST001", "ACC100001", "OP004", "4532 •••• •••• 8821", "debit", "2021-08-01", "2028-08-31", 0.00, "hash_pin_1", "active"),
        ("CRD002", "COMP001", "CUST001", "ACC100002", "OP004", "5424 •••• •••• 4190", "credit", "2022-02-15", "2027-02-28", 150000.00, "hash_pin_2", "active"),
        ("CRD003", "COMP001", "CUST002", "ACC100003", "OP002", "4111 •••• •••• 9924", "debit", "2020-03-20", "2027-03-31", 0.00, "hash_pin_3", "active"),
        ("CRD004", "COMP001", "CUST003", "ACC100005", "OP004", "5105 •••• •••• 1204", "debit", "2019-09-01", "2024-09-30", 0.00, "hash_pin_4", "expired"),
        ("CRD005", "COMP001", "CUST004", "ACC100006", "OP002", "4556 •••• •••• 7731", "credit", "2021-02-01", "2026-02-28", 250000.00, "hash_pin_5", "active"),
        ("CRD006", "COMP002", "CUST006", "ACC100008", "OP006", "4000 •••• •••• 6612", "debit", "2019-12-01", "2025-12-31", 0.00, "hash_pin_6", "active"),
        ("CRD007", "COMP002", "CUST007", "ACC100009", "OP006", "5521 •••• •••• 3341", "debit", "2020-07-01", "2027-07-31", 0.00, "hash_pin_7", "active"),
        ("CRD008", "COMP003", "CUST010", "ACC100012", "OP007", "4123 •••• •••• 0081", "debit", "2022-06-01", "2027-06-30", 0.00, "hash_pin_8", "blocked"),
        ("CRD009", "COMP001", "CUST011", "ACC100013", "OP004", "5234 •••• •••• 9999", "credit", "2018-05-20", "2028-05-31", 500000.00, "hash_pin_9", "active"),
        ("CRD010", "COMP001", "CUST012", "ACC100014", "OP004", "4242 •••• •••• 1042", "debit", "2022-08-05", "2029-08-31", 0.00, "hash_pin_10", "active"),
    ]
    cursor.executemany(
        """
        INSERT INTO cards (
            card_id, company_code, customer_id, linked_account_number, issued_by_operator_id,
            card_number_masked, card_type, issue_date, expiry_date, credit_limit, pin_hash, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        cards,
    )

    # 11. Loans
    loans = [
        ("LN100001", "COMP001", "CUST001", "OP005", "education", 600000.00, 0.0825, 60, 12240.50, "2023-08-01", "2028-08-01", "running", 415000.00),
        ("LN100002", "COMP001", "CUST002", "OP005", "home", 4500000.00, 0.0780, 240, 39750.00, "2021-05-15", "2041-05-15", "running", 4120000.00),
        ("LN100003", "COMP001", "CUST004", "OP005", "car", 950000.00, 0.0890, 60, 19680.00, "2022-03-10", "2027-03-10", "running", 430000.00),
        ("LN100004", "COMP002", "CUST006", "OP006", "business", 2500000.00, 0.1050, 48, 63980.00, "2020-10-01", "2024-10-01", "closed", 0.00),
        ("LN100005", "COMP003", "CUST008", "OP007", "personal", 300000.00, 0.1200, 36, 9960.00, "2023-01-15", "2026-01-15", "running", 142000.00),
        ("LN100006", "COMP003", "CUST010", "OP007", "personal", 200000.00, 0.1350, 24, 9550.00, "2022-09-01", "2024-09-01", "defaulted", 128400.00),
        ("LN100007", "COMP001", "CUST011", "OP002", "home", 6500000.00, 0.0750, 180, 60250.00, "2015-06-01", "2030-06-01", "running", 2150000.00),
    ]
    cursor.executemany(
        """
        INSERT INTO loans (
            loan_number, company_code, customer_id, approved_by_operator_id, loan_type,
            principal_amount, interest_rate, term_months, monthly_payment, start_date, end_date, status, outstanding_balance
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        loans,
    )


def seed_database(reset: bool = False) -> None:
    if reset and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    ensure_schema_and_seed(DB_PATH)
    print("Database initialization and seed complete!")


if __name__ == "__main__":
    import sys

    seed_database(reset="--reset" in sys.argv)
