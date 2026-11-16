import sqlite3
import os
import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "bank_system.db")

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

-- 1. Companies Table
CREATE TABLE IF NOT EXISTS companies (
    company_code VARCHAR(10) PRIMARY KEY,
    company_name VARCHAR(100) NOT NULL,
    headquarters_address TEXT,
    phone VARCHAR(20),
    established_date DATE,
    total_assets DECIMAL(15,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Branches Table
CREATE TABLE IF NOT EXISTS branches (
    branch_code VARCHAR(15) PRIMARY KEY,
    company_code VARCHAR(10),
    branch_name VARCHAR(100) NOT NULL,
    address TEXT,
    phone VARCHAR(20),
    manager_name VARCHAR(100),
    opening_hours TIME,
    closing_hours TIME,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_code) REFERENCES companies(company_code) ON DELETE SET NULL ON UPDATE CASCADE
);

-- 3. Employees Table
CREATE TABLE IF NOT EXISTS employees (
    employee_id VARCHAR(10) PRIMARY KEY,
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
    FOREIGN KEY (branch_code) REFERENCES branches(branch_code) ON DELETE SET NULL ON UPDATE CASCADE
);

-- 4. Account Types
CREATE TABLE IF NOT EXISTS account_types (
    account_type_code VARCHAR(10) PRIMARY KEY,
    type_name VARCHAR(50) NOT NULL,
    description TEXT,
    minimum_balance DECIMAL(10,2) DEFAULT 0.0,
    interest_rate DECIMAL(5,4) DEFAULT 0.0,
    allows_overdraft TINYINT DEFAULT 0
);

-- 5. Transaction Categories
CREATE TABLE IF NOT EXISTS transaction_categories (
    category_code VARCHAR(10) PRIMARY KEY,
    category_name VARCHAR(50) NOT NULL,
    description TEXT,
    category_type VARCHAR(10) CHECK(category_type IN ('income', 'expense'))
);

-- 6. Customers Table
CREATE TABLE IF NOT EXISTS customers (
    customer_id VARCHAR(10) PRIMARY KEY,
    relationship_manager_id VARCHAR(10),
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
    FOREIGN KEY (relationship_manager_id) REFERENCES employees(employee_id) ON DELETE SET NULL ON UPDATE CASCADE
);

-- 7. Accounts Table
CREATE TABLE IF NOT EXISTS accounts (
    account_number VARCHAR(20) PRIMARY KEY,
    customer_id VARCHAR(10) NOT NULL,
    account_type_code VARCHAR(10) NOT NULL,
    balance DECIMAL(15,2) DEFAULT 0.0,
    opening_date DATE NOT NULL,
    status VARCHAR(10) NOT NULL CHECK(status IN ('active', 'closed', 'frozen')) DEFAULT 'active',
    overdraft_limit DECIMAL(10,2) DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (account_type_code) REFERENCES account_types(account_type_code) ON DELETE RESTRICT ON UPDATE CASCADE
);

-- 8. Transactions Table
CREATE TABLE IF NOT EXISTS transactions (
    transaction_reference VARCHAR(20) PRIMARY KEY,
    account_number VARCHAR(20) NOT NULL,
    category_code VARCHAR(10),
    transaction_type VARCHAR(10) NOT NULL CHECK(transaction_type IN ('credit', 'debit')),
    amount DECIMAL(15,2) NOT NULL CHECK(amount > 0),
    description TEXT,
    transaction_date DATETIME NOT NULL,
    running_balance DECIMAL(15,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_number) REFERENCES accounts(account_number) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (category_code) REFERENCES transaction_categories(category_code) ON DELETE SET NULL ON UPDATE CASCADE
);

-- 9. Cards Table
CREATE TABLE IF NOT EXISTS cards (
    card_id VARCHAR(20) PRIMARY KEY,
    customer_id VARCHAR(10) NOT NULL,
    linked_account_number VARCHAR(20) NOT NULL,
    card_number_masked VARCHAR(255) NOT NULL,
    card_type VARCHAR(10) NOT NULL CHECK(card_type IN ('debit', 'credit', 'prepaid')),
    issue_date DATE NOT NULL,
    expiry_date DATE NOT NULL,
    credit_limit DECIMAL(10,2) DEFAULT 0.0,
    pin_hash VARCHAR(255),
    status VARCHAR(10) NOT NULL CHECK(status IN ('active', 'blocked', 'expired')) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (linked_account_number) REFERENCES accounts(account_number) ON DELETE CASCADE ON UPDATE CASCADE
);

-- 10. Loans Table
CREATE TABLE IF NOT EXISTS loans (
    loan_number VARCHAR(20) PRIMARY KEY,
    customer_id VARCHAR(10) NOT NULL,
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
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id) ON DELETE CASCADE ON UPDATE CASCADE
);

-- Performance Indexes
CREATE INDEX IF NOT EXISTS idx_accounts_customer ON accounts(customer_id);
CREATE INDEX IF NOT EXISTS idx_transactions_account ON transactions(account_number);
CREATE INDEX IF NOT EXISTS idx_cards_account ON cards(linked_account_number);
CREATE INDEX IF NOT EXISTS idx_loans_customer ON loans(customer_id);
CREATE INDEX IF NOT EXISTS idx_employees_branch ON employees(branch_code);
"""

def seed_database():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()
    cursor.executescript(SCHEMA_SQL)

    # Check if data already exists
    cursor.execute("SELECT COUNT(*) FROM companies")
    if cursor.fetchone()[0] > 0:
        print("Database already seeded.")
        conn.close()
        return

    print("Seeding initial DTU CS209 Banking Data...")

    # 1. Companies
    companies = [
        ('COMP001', 'National Bank of India', 'Tower A, BKC, Mumbai, Maharashtra 400051', '+91-22-66801234', '1990-01-15', 5000000000.00),
        ('COMP002', 'Global Finance Corp', 'Sector 62, Noida, Uttar Pradesh 201301', '+91-120-4567890', '1995-03-20', 3500000000.00),
        ('COMP003', 'Metro Banking Group', 'MG Road, Bangalore, Karnataka 560001', '+91-80-25591234', '2000-07-10', 2800000000.00)
    ]
    cursor.executemany("INSERT INTO companies VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)", companies)

    # 2. Branches
    branches = [
        ('BR001', 'COMP001', 'Connaught Place Main', 'Block B, Connaught Place, New Delhi 110001', '+91-11-23340001', 'Rajesh Sharma', '09:30:00', '16:30:00'),
        ('BR002', 'COMP001', 'Rohini Sector 14', 'Plot 12, Sector 14, Rohini, Delhi 110085', '+91-11-27050002', 'Pooja Verma', '09:30:00', '16:30:00'),
        ('BR003', 'COMP001', 'BKC Corporate Hub', 'G-Block, BKC, Bandra East, Mumbai 400051', '+91-22-26590003', 'Vikramaditya Rao', '09:00:00', '17:00:00'),
        ('BR004', 'COMP002', 'Indirapuram Tech Park', 'Ahinsa Khand, Indirapuram, Ghaziabad 201014', '+91-120-2890004', 'Ananya Gupta', '10:00:00', '16:00:00'),
        ('BR005', 'COMP003', 'Koramangala Fintech Hub', '80 Feet Road, 4th Block, Koramangala, Bangalore 560034', '+91-80-41230005', 'Karthik Nambiar', '09:30:00', '17:30:00')
    ]
    cursor.executemany("INSERT INTO branches VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)", branches)

    # 3. Employees
    employees = [
        ('EMP001', 'BR001', 'Rajesh', 'Sharma', 'rajesh.sharma@nbi-bank.in', '+91-9811000001', 'Branch Manager', 145000.00, '2012-04-10', 'Branch Operations'),
        ('EMP002', 'BR001', 'Sneha', 'Kapoor', 'sneha.kapoor@nbi-bank.in', '+91-9811000002', 'Senior Relationship Manager', 98000.00, '2016-08-15', 'Retail Banking'),
        ('EMP003', 'BR001', 'Amit', 'Trivedi', 'amit.trivedi@nbi-bank.in', '+91-9811000003', 'Cash & Vault Officer', 62000.00, '2019-01-20', 'Cash Management'),
        ('EMP004', 'BR002', 'Pooja', 'Verma', 'pooja.verma@nbi-bank.in', '+91-9811000004', 'Branch Manager', 135000.00, '2014-06-01', 'Branch Operations'),
        ('EMP005', 'BR002', 'Naveen', 'Chawla', 'naveen.chawla@nbi-bank.in', '+91-9811000005', 'Relationship Manager', 75000.00, '2020-03-12', 'Retail Banking'),
        ('EMP006', 'BR003', 'Vikramaditya', 'Rao', 'vikram.rao@nbi-bank.in', '+91-9811000006', 'Corporate General Manager', 190000.00, '2010-11-05', 'Corporate Banking'),
        ('EMP007', 'BR003', 'Deepika', 'Menon', 'deepika.menon@nbi-bank.in', '+91-9811000007', 'Senior Credit Analyst', 105000.00, '2018-09-17', 'Credit Risk'),
        ('EMP008', 'BR004', 'Ananya', 'Gupta', 'ananya.gupta@gfc-bank.in', '+91-9811000008', 'Branch Manager', 128000.00, '2015-05-22', 'Branch Operations'),
        ('EMP009', 'BR005', 'Karthik', 'Nambiar', 'karthik.n@mbg-bank.in', '+91-9811000009', 'AVP Digital Banking', 160000.00, '2013-02-14', 'Digital Products'),
        ('EMP010', 'BR005', 'Ritu', 'Kaur', 'ritu.kaur@mbg-bank.in', '+91-9811000010', 'Customer Relationship Exec', 54000.00, '2021-10-01', 'Retail Banking')
    ]
    cursor.executemany("INSERT INTO employees VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)", employees)

    # 4. Account Types
    account_types = [
        ('SAV001', 'Savings Account', 'Basic savings account with quarterly interest & debit card', 1000.00, 0.0350, 0),
        ('CURR001', 'Current Account', 'Business current account with high transaction limit & overdraft facility', 5000.00, 0.0000, 1),
        ('FD001', 'Fixed Deposit', 'Fixed tenure deposit account yielding guaranteed annual returns', 10000.00, 0.0650, 0),
        ('SAL001', 'Salary Account', 'Corporate zero balance salary account with lounge access', 0.00, 0.0300, 0),
        ('BUS001', 'Business Account', 'Tiered business account with bulk payroll and multi-currency support', 25000.00, 0.0200, 1)
    ]
    cursor.executemany("INSERT INTO account_types VALUES (?, ?, ?, ?, ?, ?)", account_types)

    # 5. Transaction Categories
    categories = [
        ('CAT001', 'Salary Credit', 'Monthly corporate payroll direct deposit', 'income'),
        ('CAT002', 'ATM Withdrawal', 'Automated teller cash withdrawal', 'expense'),
        ('CAT003', 'Online Transfer', 'Instant NEFT/RTGS/IMPS fund transfer', 'expense'),
        ('CAT004', 'Bill Payment', 'Electricity, water, broadband, or mobile utility payment', 'expense'),
        ('CAT005', 'Interest Credit', 'Compounded interest credited on quarterly basis', 'income'),
        ('CAT006', 'Deposit', 'Direct cash or cleared cheque deposit', 'income'),
        ('CAT007', 'Shopping', 'POS merchant swipe or online eCommerce shopping', 'expense'),
        ('CAT008', 'Refund', 'Merchant reversal or dispute charge refund', 'income')
    ]
    cursor.executemany("INSERT INTO transaction_categories VALUES (?, ?, ?, ?)", categories)

    # 6. Customers (DTU Report data + extended)
    customers = [
        ('CUST001', 'EMP002', 'Arnav', 'Gupta', 'arnavgupta@gmail.com', '+91-9650910304', 'B-99, Amar Colony, New Delhi', '2007-03-25', 'AADH123456789', 758.0, '2021-07-21'),
        ('CUST002', 'EMP002', 'Aarav', 'Malhotra', 'aarav.malhotra@gmail.com', '+91-9876543220', 'D-45, Vasant Kunj, New Delhi', '1998-05-15', 'AADH234567890', 820.0, '2020-03-10'),
        ('CUST003', 'EMP002', 'Diya', 'Kapoor', 'diya.kapoor@gmail.com', '+91-9876543221', 'C-78, Saket, New Delhi', '1980-11-22', 'AADH345678901', 680.0, '2019-08-15'),
        ('CUST004', 'EMP005', 'Rohan', 'Saxena', 'rohan.saxena@yahoo.com', '+91-9876543222', 'A-12, Lajpat Nagar, New Delhi', '1992-07-08', 'AADH456789012', 795.0, '2021-01-20'),
        ('CUST005', 'EMP005', 'Priyanshu', 'Nair', 'priyanshu.nair@gmail.com', '+91-9876543223', 'E-34, Dwarka, New Delhi', '1995-02-14', 'AADH567890123', 720.0, '2020-09-05'),
        ('CUST006', 'EMP007', 'Arjun', 'Chatterjee', 'arjun.c@gmail.com', '+91-9876543224', 'Sector 22, Noida, Uttar Pradesh', '1987-09-30', 'AADH678901234', 760.0, '2019-11-12'),
        ('CUST007', 'EMP007', 'Meera', 'Iyer', 'meera.iyer@hotmail.com', '+91-9876543225', 'Sector 50, Noida, Uttar Pradesh', '1993-12-05', 'AADH789012345', 810.0, '2020-06-18'),
        ('CUST008', 'EMP009', 'Siddharth', 'Rao', 'siddharth.rao@gmail.com', '+91-9876543226', 'Indiranagar, Bangalore, Karnataka', '1991-04-20', 'AADH890123456', 735.0, '2021-02-28'),
        ('CUST009', 'EMP009', 'Anjali', 'Menon', 'anjali.menon@gmail.com', '+91-9876543227', 'Koramangala, Bangalore, Karnataka', '1996-08-17', 'AADH901234567', 790.0, '2020-10-15'),
        ('CUST010', 'EMP010', 'Karan', 'Bhatia', 'karan.bhatia@gmail.com', '+91-9876543228', 'HSR Layout, Bangalore, Karnataka', '1994-06-11', 'AADH012345678', 664.0, '2022-05-22'),
        ('CUST011', 'EMP002', 'Punit', 'Gambhir', 'punit@gmail.com', '+91-9871630011', 'B-99, New Delhi', '1974-12-23', 'AADH09382', 841.0, '2004-05-19'),
        ('CUST012', 'EMP005', 'Lavya', 'Yadav', 'lavya.yadav@dtu.ac.in', '+91-9988776655', 'Sector 17, Rohini, New Delhi', '2006-08-14', 'AADH998877661', 775.0, '2022-08-01')
    ]
    cursor.executemany("INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)", customers)

    # 7. Accounts
    accounts = [
        ('ACC100001', 'CUST001', 'SAV001', 45250.75, '2021-07-21', 'active', 0.00),
        ('ACC100002', 'CUST001', 'SAL001', 128400.00, '2022-01-10', 'active', 0.00),
        ('ACC100003', 'CUST002', 'CURR001', 340000.50, '2020-03-10', 'active', 100000.00),
        ('ACC100004', 'CUST002', 'FD001', 500000.00, '2021-04-01', 'active', 0.00),
        ('ACC100005', 'CUST003', 'SAV001', 15400.20, '2019-08-15', 'active', 0.00),
        ('ACC100006', 'CUST004', 'SAL001', 92500.00, '2021-01-20', 'active', 0.00),
        ('ACC100007', 'CUST005', 'SAV001', 31200.00, '2020-09-05', 'active', 0.00),
        ('ACC100008', 'CUST006', 'BUS001', 890450.00, '2019-11-12', 'active', 250000.00),
        ('ACC100009', 'CUST007', 'SAV001', 64800.90, '2020-06-18', 'active', 0.00),
        ('ACC100010', 'CUST008', 'SAV001', 18350.00, '2021-02-28', 'active', 0.00),
        ('ACC100011', 'CUST009', 'SAL001', 145000.00, '2020-10-15', 'active', 0.00),
        ('ACC100012', 'CUST010', 'SAV001', 8200.00, '2022-05-22', 'frozen', 0.00),
        ('ACC100013', 'CUST011', 'SAV001', 684200.00, '2004-05-19', 'active', 50000.00),
        ('ACC100014', 'CUST012', 'SAV001', 25000.00, '2022-08-01', 'active', 0.00)
    ]
    cursor.executemany("INSERT INTO accounts VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)", accounts)

    # 8. Transactions
    transactions = [
        ('TXN100001', 'ACC100001', 'CAT006', 'credit', 25000.00, 'Initial branch cash deposit', '2026-09-01 10:15:00', 25000.00),
        ('TXN100002', 'ACC100001', 'CAT001', 'credit', 35000.00, 'September Stipend / Salary', '2026-09-05 09:00:00', 60000.00),
        ('TXN100003', 'ACC100001', 'CAT002', 'debit', 5000.00, 'ATM cash withdrawal Connaught Place', '2026-09-10 16:45:00', 55000.00),
        ('TXN100004', 'ACC100001', 'CAT007', 'debit', 3549.25, 'Electronics retail purchase', '2026-09-15 19:20:00', 51450.75),
        ('TXN100005', 'ACC100001', 'CAT004', 'debit', 6200.00, 'Airtel Broadband & Electricity Bill', '2026-09-20 14:10:00', 45250.75),
        ('TXN100006', 'ACC100002', 'CAT001', 'credit', 128400.00, 'Infosys monthly payroll deposit', '2026-09-30 08:00:00', 128400.00),
        ('TXN100007', 'ACC100003', 'CAT006', 'credit', 150000.00, 'Client invoice payment', '2026-09-12 11:30:00', 360000.50),
        ('TXN100008', 'ACC100003', 'CAT003', 'debit', 20000.00, 'Vendor raw materials payment', '2026-09-18 15:00:00', 340000.50),
        ('TXN100009', 'ACC100006', 'CAT001', 'credit', 95000.00, 'Monthly Corporate Salary', '2026-09-30 09:30:00', 95000.00),
        ('TXN100010', 'ACC100006', 'CAT004', 'debit', 2500.00, 'Mobile bill payment', '2026-10-02 11:22:00', 92500.00),
        ('TXN100011', 'ACC100008', 'CAT006', 'credit', 450000.00, 'Contract milestone settlement', '2026-09-25 17:15:00', 890450.00),
        ('TXN100012', 'ACC100009', 'CAT005', 'credit', 840.90, 'Quarterly interest deposit', '2026-09-30 23:59:00', 64800.90),
        ('TXN100013', 'ACC100011', 'CAT001', 'credit', 145000.00, 'Google India payroll salary credit', '2026-10-01 07:00:00', 145000.00),
        ('TXN100014', 'ACC100013', 'CAT006', 'credit', 200000.00, 'Fixed savings transfer', '2026-08-15 12:00:00', 684200.00),
        ('TXN100015', 'ACC100014', 'CAT006', 'credit', 25000.00, 'Opening initial deposit DTU branch', '2026-08-01 10:00:00', 25000.00)
    ]
    cursor.executemany("INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)", transactions)

    # 9. Cards
    cards = [
        ('CRD001', 'CUST001', 'ACC100001', '4532 •••• •••• 8821', 'debit', '2021-08-01', '2028-08-31', 0.00, 'hash_pin_1', 'active'),
        ('CRD002', 'CUST001', 'ACC100002', '5424 •••• •••• 4190', 'credit', '2022-02-15', '2027-02-28', 150000.00, 'hash_pin_2', 'active'),
        ('CRD003', 'CUST002', 'ACC100003', '4111 •••• •••• 9924', 'debit', '2020-03-20', '2027-03-31', 0.00, 'hash_pin_3', 'active'),
        ('CRD004', 'CUST003', 'ACC100005', '5105 •••• •••• 1204', 'debit', '2019-09-01', '2024-09-30', 0.00, 'hash_pin_4', 'expired'),
        ('CRD005', 'CUST004', 'ACC100006', '4556 •••• •••• 7731', 'credit', '2021-02-01', '2026-02-28', 250000.00, 'hash_pin_5', 'active'),
        ('CRD006', 'CUST006', 'ACC100008', '4000 •••• •••• 6612', 'debit', '2019-12-01', '2025-12-31', 0.00, 'hash_pin_6', 'active'),
        ('CRD007', 'CUST007', 'ACC100009', '5521 •••• •••• 3341', 'debit', '2020-07-01', '2027-07-31', 0.00, 'hash_pin_7', 'active'),
        ('CRD008', 'CUST010', 'ACC100012', '4123 •••• •••• 0081', 'debit', '2022-06-01', '2027-06-30', 0.00, 'hash_pin_8', 'blocked'),
        ('CRD009', 'CUST011', 'ACC100013', '5234 •••• •••• 9999', 'credit', '2018-05-20', '2028-05-31', 500000.00, 'hash_pin_9', 'active'),
        ('CRD010', 'CUST012', 'ACC100014', '4242 •••• •••• 1042', 'debit', '2022-08-05', '2029-08-31', 0.00, 'hash_pin_10', 'active')
    ]
    cursor.executemany("INSERT INTO cards VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)", cards)

    # 10. Loans
    loans = [
        ('LN100001', 'CUST001', 'education', 600000.00, 0.0825, 60, 12240.50, '2023-08-01', '2028-08-01', 'running', 415000.00),
        ('LN100002', 'CUST002', 'home', 4500000.00, 0.0780, 240, 39750.00, '2021-05-15', '2041-05-15', 'running', 4120000.00),
        ('LN100003', 'CUST004', 'car', 950000.00, 0.0890, 60, 19680.00, '2022-03-10', '2027-03-10', 'running', 430000.00),
        ('LN100004', 'CUST006', 'business', 2500000.00, 0.1050, 48, 63980.00, '2020-10-01', '2024-10-01', 'closed', 0.00),
        ('LN100005', 'CUST008', 'personal', 300000.00, 0.1200, 36, 9960.00, '2023-01-15', '2026-01-15', 'running', 142000.00),
        ('LN100006', 'CUST010', 'personal', 200000.00, 0.1350, 24, 9550.00, '2022-09-01', '2024-09-01', 'defaulted', 128400.00),
        ('LN100007', 'CUST011', 'home', 6500000.00, 0.0750, 180, 60250.00, '2015-06-01', '2030-06-01', 'running', 2150000.00)
    ]
    cursor.executemany("INSERT INTO loans VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)", loans)

    conn.commit()
    conn.close()
    print("Database initialization and seed complete!")

if __name__ == "__main__":
    seed_database()
