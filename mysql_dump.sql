-- ====================================================================
-- Delhi Technological University (DTU)
-- Dept. Applied Mathematics | CS209 - Database Management System
-- Project: Bank Management System
-- Submitted by: Arnav Gupta (24/CS/087), Lavya Yadav (24/MC/104)
-- ====================================================================

CREATE DATABASE IF NOT EXISTS bank_system;
USE bank_system;

-- 1. companies
DROP TABLE IF EXISTS loans;
DROP TABLE IF EXISTS cards;
DROP TABLE IF EXISTS transactions;
DROP TABLE IF EXISTS accounts;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS employees;
DROP TABLE IF EXISTS branches;
DROP TABLE IF EXISTS transaction_categories;
DROP TABLE IF EXISTS account_types;
DROP TABLE IF EXISTS companies;

CREATE TABLE companies (
    company_code VARCHAR(10) PRIMARY KEY,
    company_name VARCHAR(100) NOT NULL,
    headquarters_address TEXT,
    phone VARCHAR(20),
    established_date DATE,
    total_assets DECIMAL(15,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. branches
CREATE TABLE branches (
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

-- 3. employees
CREATE TABLE employees (
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

-- 4. account_types
CREATE TABLE account_types (
    account_type_code VARCHAR(10) PRIMARY KEY,
    type_name VARCHAR(50) NOT NULL,
    description TEXT,
    minimum_balance DECIMAL(10,2) DEFAULT 0.00,
    interest_rate DECIMAL(5,4) DEFAULT 0.0000,
    allows_overdraft TINYINT(1) DEFAULT 0
);

-- 5. transaction_categories
CREATE TABLE transaction_categories (
    category_code VARCHAR(10) PRIMARY KEY,
    category_name VARCHAR(50) NOT NULL,
    description TEXT,
    category_type ENUM('income', 'expense') NOT NULL
);

-- 6. customers
CREATE TABLE customers (
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

-- 7. accounts
CREATE TABLE accounts (
    account_number VARCHAR(20) PRIMARY KEY,
    customer_id VARCHAR(10) NOT NULL,
    account_type_code VARCHAR(10) NOT NULL,
    balance DECIMAL(15,2) DEFAULT 0.00,
    opening_date DATE NOT NULL,
    status ENUM('active', 'closed', 'frozen') NOT NULL DEFAULT 'active',
    overdraft_limit DECIMAL(10,2) DEFAULT 0.00,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (account_type_code) REFERENCES account_types(account_type_code) ON DELETE RESTRICT ON UPDATE CASCADE
);

-- 8. transactions
CREATE TABLE transactions (
    transaction_reference VARCHAR(20) PRIMARY KEY,
    account_number VARCHAR(20) NOT NULL,
    category_code VARCHAR(10),
    transaction_type ENUM('credit', 'debit') NOT NULL,
    amount DECIMAL(15,2) NOT NULL,
    description TEXT,
    transaction_date DATETIME NOT NULL,
    running_balance DECIMAL(15,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_number) REFERENCES accounts(account_number) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (category_code) REFERENCES transaction_categories(category_code) ON DELETE SET NULL ON UPDATE CASCADE
);

-- 9. cards
CREATE TABLE cards (
    card_id VARCHAR(20) PRIMARY KEY,
    customer_id VARCHAR(10) NOT NULL,
    linked_account_number VARCHAR(20) NOT NULL,
    card_number_masked VARCHAR(255) NOT NULL,
    card_type ENUM('debit', 'credit', 'prepaid') NOT NULL,
    issue_date DATE NOT NULL,
    expiry_date DATE NOT NULL,
    credit_limit DECIMAL(10,2) DEFAULT 0.00,
    pin_hash VARCHAR(255),
    status ENUM('active', 'blocked', 'expired') NOT NULL DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (linked_account_number) REFERENCES accounts(account_number) ON DELETE CASCADE ON UPDATE CASCADE
);

-- 10. loans
CREATE TABLE loans (
    loan_number VARCHAR(20) PRIMARY KEY,
    customer_id VARCHAR(10) NOT NULL,
    loan_type ENUM('home', 'personal', 'education', 'car', 'business') NOT NULL,
    principal_amount DECIMAL(15,2) NOT NULL,
    interest_rate DECIMAL(5,4) NOT NULL,
    term_months INT NOT NULL,
    monthly_payment DECIMAL(10,2) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    status ENUM('running', 'closed', 'defaulted') NOT NULL DEFAULT 'running',
    outstanding_balance DECIMAL(15,2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id) ON DELETE CASCADE ON UPDATE CASCADE
);

-- Seed Data (from report page 16-18)
INSERT INTO companies VALUES
('COMP001', 'National Bank of India', 'Tower A, BKC, Mumbai, Maharashtra 400051', '+91-22-66801234', '1990-01-15', 5000000000.00, NOW()),
('COMP002', 'Global Finance Corp', 'Sector 62, Noida, Uttar Pradesh 201301', '+91-120-4567890', '1995-03-20', 3500000000.00, NOW()),
('COMP003', 'Metro Banking Group', 'MG Road, Bangalore, Karnataka 560001', '+91-80-25591234', '2000-07-10', 2800000000.00, NOW());

INSERT INTO branches VALUES
('BR001', 'COMP001', 'Connaught Place Main', 'Block B, Connaught Place, New Delhi 110001', '+91-11-23340001', 'Rajesh Sharma', '09:30:00', '16:30:00', NOW()),
('BR002', 'COMP001', 'Rohini Sector 14', 'Plot 12, Sector 14, Rohini, Delhi 110085', '+91-11-27050002', 'Pooja Verma', '09:30:00', '16:30:00', NOW()),
('BR003', 'COMP001', 'BKC Corporate Hub', 'G-Block, BKC, Bandra East, Mumbai 400051', '+91-22-26590003', 'Vikramaditya Rao', '09:00:00', '17:00:00', NOW()),
('BR004', 'COMP002', 'Indirapuram Tech Park', 'Ahinsa Khand, Indirapuram, Ghaziabad 201014', '+91-120-2890004', 'Ananya Gupta', '10:00:00', '16:00:00', NOW()),
('BR005', 'COMP003', 'Koramangala Fintech Hub', '80 Feet Road, 4th Block, Koramangala, Bangalore 560034', '+91-80-41230005', 'Karthik Nambiar', '09:30:00', '17:30:00', NOW());

INSERT INTO employees VALUES
('EMP001', 'BR001', 'Rajesh', 'Sharma', 'rajesh.sharma@nbi-bank.in', '+91-9811000001', 'Branch Manager', 145000.00, '2012-04-10', 'Branch Operations', NOW()),
('EMP002', 'BR001', 'Sneha', 'Kapoor', 'sneha.kapoor@nbi-bank.in', '+91-9811000002', 'Senior Relationship Manager', 98000.00, '2016-08-15', 'Retail Banking', NOW()),
('EMP003', 'BR001', 'Amit', 'Trivedi', 'amit.trivedi@nbi-bank.in', '+91-9811000003', 'Cash & Vault Officer', 62000.00, '2019-01-20', 'Cash Management', NOW()),
('EMP004', 'BR002', 'Pooja', 'Verma', 'pooja.verma@nbi-bank.in', '+91-9811000004', 'Branch Manager', 135000.00, '2014-06-01', 'Branch Operations', NOW()),
('EMP005', 'BR002', 'Naveen', 'Chawla', 'naveen.chawla@nbi-bank.in', '+91-9811000005', 'Relationship Manager', 75000.00, '2020-03-12', 'Retail Banking', NOW()),
('EMP006', 'BR003', 'Vikramaditya', 'Rao', 'vikram.rao@nbi-bank.in', '+91-9811000006', 'Corporate General Manager', 190000.00, '2010-11-05', 'Corporate Banking', NOW()),
('EMP007', 'BR003', 'Deepika', 'Menon', 'deepika.menon@nbi-bank.in', '+91-9811000007', 'Senior Credit Analyst', 105000.00, '2018-09-17', 'Credit Risk', NOW()),
('EMP008', 'BR004', 'Ananya', 'Gupta', 'ananya.gupta@gfc-bank.in', '+91-9811000008', 'Branch Manager', 128000.00, '2015-05-22', 'Branch Operations', NOW()),
('EMP009', 'BR005', 'Karthik', 'Nambiar', 'karthik.n@mbg-bank.in', '+91-9811000009', 'AVP Digital Banking', 160000.00, '2013-02-14', 'Digital Products', NOW()),
('EMP010', 'BR005', 'Ritu', 'Kaur', 'ritu.kaur@mbg-bank.in', '+91-9811000010', 'Customer Relationship Exec', 54000.00, '2021-10-01', 'Retail Banking', NOW());

INSERT INTO account_types VALUES
('SAV001', 'Savings Account', 'Basic savings account with quarterly interest & debit card', 1000.00, 0.0350, 0),
('CURR001', 'Current Account', 'Business current account with high transaction limit & overdraft facility', 5000.00, 0.0000, 1),
('FD001', 'Fixed Deposit', 'Fixed tenure deposit account yielding guaranteed annual returns', 10000.00, 0.0650, 0),
('SAL001', 'Salary Account', 'Corporate zero balance salary account with lounge access', 0.00, 0.0300, 0),
('BUS001', 'Business Account', 'Tiered business account with bulk payroll and multi-currency support', 25000.00, 0.0200, 1);

INSERT INTO transaction_categories VALUES
('CAT001', 'Salary Credit', 'Monthly corporate payroll direct deposit', 'income'),
('CAT002', 'ATM Withdrawal', 'Automated teller cash withdrawal', 'expense'),
('CAT003', 'Online Transfer', 'Instant NEFT/RTGS/IMPS fund transfer', 'expense'),
('CAT004', 'Bill Payment', 'Electricity, water, broadband, or mobile utility payment', 'expense'),
('CAT005', 'Interest Credit', 'Compounded interest credited on quarterly basis', 'income'),
('CAT006', 'Deposit', 'Direct cash or cheque deposit', 'income'),
('CAT007', 'Shopping', 'POS merchant swipe or online eCommerce shopping', 'expense'),
('CAT008', 'Refund', 'Merchant reversal or dispute charge refund', 'income');

INSERT INTO customers VALUES
('CUST001', 'EMP002', 'Arnav', 'Gupta', 'arnavgupta@gmail.com', '+91-9650910304', 'B-99, Amar Colony, New Delhi', '2007-03-25', 'AADH123456789', 758.0, '2021-07-21', NOW()),
('CUST002', 'EMP002', 'Aarav', 'Malhotra', 'aarav.malhotra@gmail.com', '+91-9876543220', 'D-45, Vasant Kunj, New Delhi', '1998-05-15', 'AADH234567890', 820.0, '2020-03-10', NOW()),
('CUST003', 'EMP002', 'Diya', 'Kapoor', 'diya.kapoor@gmail.com', '+91-9876543221', 'C-78, Saket, New Delhi', '1980-11-22', 'AADH345678901', 680.0, '2019-08-15', NOW()),
('CUST004', 'EMP005', 'Rohan', 'Saxena', 'rohan.saxena@yahoo.com', '+91-9876543222', 'A-12, Lajpat Nagar, New Delhi', '1992-07-08', 'AADH456789012', 795.0, '2021-01-20', NOW()),
('CUST005', 'EMP005', 'Priyanshu', 'Nair', 'priyanshu.nair@gmail.com', '+91-9876543223', 'E-34, Dwarka, New Delhi', '1995-02-14', 'AADH567890123', 720.0, '2020-09-05', NOW()),
('CUST006', 'EMP007', 'Arjun', 'Chatterjee', 'arjun.c@gmail.com', '+91-9876543224', 'Sector 22, Noida, Uttar Pradesh', '1987-09-30', 'AADH678901234', 760.0, '2019-11-12', NOW()),
('CUST007', 'EMP007', 'Meera', 'Iyer', 'meera.iyer@hotmail.com', '+91-9876543225', 'Sector 50, Noida, Uttar Pradesh', '1993-12-05', 'AADH789012345', 810.0, '2020-06-18', NOW()),
('CUST008', 'EMP009', 'Siddharth', 'Rao', 'siddharth.rao@gmail.com', '+91-9876543226', 'Indiranagar, Bangalore, Karnataka', '1991-04-20', 'AADH890123456', 735.0, '2021-02-28', NOW()),
('CUST009', 'EMP009', 'Anjali', 'Menon', 'anjali.menon@gmail.com', '+91-9876543227', 'Koramangala, Bangalore, Karnataka', '1996-08-17', 'AADH901234567', 790.0, '2020-10-15', NOW()),
('CUST010', 'EMP010', 'Karan', 'Bhatia', 'karan.bhatia@gmail.com', '+91-9876543228', 'HSR Layout, Bangalore, Karnataka', '1994-06-11', 'AADH012345678', 664.0, '2022-05-22', NOW()),
('CUST011', 'EMP002', 'Punit', 'Gambhir', 'punit@gmail.com', '+91-9871630011', 'B-99, New Delhi', '1974-12-23', 'AADH09382', 841.0, '2004-05-19', NOW()),
('CUST012', 'EMP005', 'Lavya', 'Yadav', 'lavya.yadav@dtu.ac.in', '+91-9988776655', 'Sector 17, Rohini, New Delhi', '2006-08-14', 'AADH998877661', 775.0, '2022-08-01', NOW());

INSERT INTO accounts VALUES
('ACC100001', 'CUST001', 'SAV001', 45250.75, '2021-07-21', 'active', 0.00, NOW()),
('ACC100002', 'CUST001', 'SAL001', 128400.00, '2022-01-10', 'active', 0.00, NOW()),
('ACC100003', 'CUST002', 'CURR001', 340000.50, '2020-03-10', 'active', 100000.00, NOW()),
('ACC100004', 'CUST002', 'FD001', 500000.00, '2021-04-01', 'active', 0.00, NOW()),
('ACC100005', 'CUST003', 'SAV001', 15400.20, '2019-08-15', 'active', 0.00, NOW()),
('ACC100006', 'CUST004', 'SAL001', 92500.00, '2021-01-20', 'active', 0.00, NOW()),
('ACC100007', 'CUST005', 'SAV001', 31200.00, '2020-09-05', 'active', 0.00, NOW()),
('ACC100008', 'CUST006', 'BUS001', 890450.00, '2019-11-12', 'active', 250000.00, NOW()),
('ACC100009', 'CUST007', 'SAV001', 64800.90, '2020-06-18', 'active', 0.00, NOW()),
('ACC100010', 'CUST008', 'SAV001', 18350.00, '2021-02-28', 'active', 0.00, NOW()),
('ACC100011', 'CUST009', 'SAL001', 145000.00, '2020-10-15', 'active', 0.00, NOW()),
('ACC100012', 'CUST010', 'SAV001', 8200.00, '2022-05-22', 'frozen', 0.00, NOW()),
('ACC100013', 'CUST011', 'SAV001', 684200.00, '2004-05-19', 'active', 50000.00, NOW()),
('ACC100014', 'CUST012', 'SAV001', 25000.00, '2022-08-01', 'active', 0.00, NOW());

INSERT INTO transactions VALUES
('TXN100001', 'ACC100001', 'CAT006', 'credit', 25000.00, 'Initial branch cash deposit', '2026-09-01 10:15:00', 25000.00, NOW()),
('TXN100002', 'ACC100001', 'CAT001', 'credit', 35000.00, 'September Stipend / Salary', '2026-09-05 09:00:00', 60000.00, NOW()),
('TXN100003', 'ACC100001', 'CAT002', 'debit', 5000.00, 'ATM cash withdrawal Connaught Place', '2026-09-10 16:45:00', 55000.00, NOW()),
('TXN100004', 'ACC100001', 'CAT007', 'debit', 3549.25, 'Electronics retail purchase', '2026-09-15 19:20:00', 51450.75, NOW()),
('TXN100005', 'ACC100001', 'CAT004', 'debit', 6200.00, 'Airtel Broadband & Electricity Bill', '2026-09-20 14:10:00', 45250.75, NOW()),
('TXN100006', 'ACC100002', 'CAT001', 'credit', 128400.00, 'Infosys monthly payroll deposit', '2026-09-30 08:00:00', 128400.00, NOW()),
('TXN100007', 'ACC100003', 'CAT006', 'credit', 150000.00, 'Client invoice payment', '2026-09-12 11:30:00', 360000.50, NOW()),
('TXN100008', 'ACC100003', 'CAT003', 'debit', 20000.00, 'Vendor raw materials payment', '2026-09-18 15:00:00', 340000.50, NOW()),
('TXN100009', 'ACC100006', 'CAT001', 'credit', 95000.00, 'Monthly Corporate Salary', '2026-09-30 09:30:00', 95000.00, NOW()),
('TXN100010', 'ACC100006', 'CAT004', 'debit', 2500.00, 'Mobile bill payment', '2026-10-02 11:22:00', 92500.00, NOW()),
('TXN100011', 'ACC100008', 'CAT006', 'credit', 450000.00, 'Contract milestone settlement', '2026-09-25 17:15:00', 890450.00, NOW()),
('TXN100012', 'ACC100009', 'CAT005', 'credit', 840.90, 'Quarterly interest deposit', '2026-09-30 23:59:00', 64800.90, NOW()),
('TXN100013', 'ACC100011', 'CAT001', 'credit', 145000.00, 'Google India payroll salary credit', '2026-10-01 07:00:00', 145000.00, NOW()),
('TXN100014', 'ACC100013', 'CAT006', 'credit', 200000.00, 'Fixed savings transfer', '2026-08-15 12:00:00', 684200.00, NOW()),
('TXN100015', 'ACC100014', 'CAT006', 'credit', 25000.00, 'Opening initial deposit DTU branch', '2026-08-01 10:00:00', 25000.00, NOW());

INSERT INTO cards VALUES
('CRD001', 'CUST001', 'ACC100001', '4532 •••• •••• 8821', 'debit', '2021-08-01', '2028-08-31', 0.00, 'hash_pin_1', 'active', NOW()),
('CRD002', 'CUST001', 'ACC100002', '5424 •••• •••• 4190', 'credit', '2022-02-15', '2027-02-28', 150000.00, 'hash_pin_2', 'active', NOW()),
('CRD003', 'CUST002', 'ACC100003', '4111 •••• •••• 9924', 'debit', '2020-03-20', '2027-03-31', 0.00, 'hash_pin_3', 'active', NOW()),
('CRD004', 'CUST003', 'ACC100005', '5105 •••• •••• 1204', 'debit', '2019-09-01', '2024-09-30', 0.00, 'hash_pin_4', 'expired', NOW()),
('CRD005', 'CUST004', 'ACC100006', '4556 •••• •••• 7731', 'credit', '2021-02-01', '2026-02-28', 250000.00, 'hash_pin_5', 'active', NOW()),
('CRD006', 'CUST006', 'ACC100008', '4000 •••• •••• 6612', 'debit', '2019-12-01', '2025-12-31', 0.00, 'hash_pin_6', 'active', NOW()),
('CRD007', 'CUST007', 'ACC100009', '5521 •••• •••• 3341', 'debit', '2020-07-01', '2027-07-31', 0.00, 'hash_pin_7', 'active', NOW()),
('CRD008', 'CUST010', 'ACC100012', '4123 •••• •••• 0081', 'debit', '2022-06-01', '2027-06-30', 0.00, 'hash_pin_8', 'blocked', NOW()),
('CRD009', 'CUST011', 'ACC100013', '5234 •••• •••• 9999', 'credit', '2018-05-20', '2028-05-31', 500000.00, 'hash_pin_9', 'active', NOW()),
('CRD010', 'CUST012', 'ACC100014', '4242 •••• •••• 1042', 'debit', '2022-08-05', '2029-08-31', 0.00, 'hash_pin_10', 'active', NOW());

INSERT INTO loans VALUES
('LN100001', 'CUST001', 'education', 600000.00, 0.0825, 60, 12240.50, '2023-08-01', '2028-08-01', 'running', 415000.00, NOW()),
('LN100002', 'CUST002', 'home', 4500000.00, 0.0780, 240, 39750.00, '2021-05-15', '2041-05-15', 'running', 4120000.00, NOW()),
('LN100003', 'CUST004', 'car', 950000.00, 0.0890, 60, 19680.00, '2022-03-10', '2027-03-10', 'running', 430000.00, NOW()),
('LN100004', 'CUST006', 'business', 2500000.00, 0.1050, 48, 63980.00, '2020-10-01', '2024-10-01', 'closed', 0.00, NOW()),
('LN100005', 'CUST008', 'personal', 300000.00, 0.1200, 36, 9960.00, '2023-01-15', '2026-01-15', 'running', 142000.00, NOW()),
('LN100006', 'CUST010', 'personal', 200000.00, 0.1350, 24, 9550.00, '2022-09-01', '2024-09-01', 'defaulted', 128400.00, NOW()),
('LN100007', 'CUST011', 'home', 6500000.00, 0.0750, 180, 60250.00, '2015-06-01', '2030-06-01', 'running', 2150000.00, NOW());
