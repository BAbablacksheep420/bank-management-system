# Bank Management System (Multi-Bank & RBAC — CS209 DBMS)

Full-stack multi-tenant banking database management system built with Python's standard-library `ThreadingHTTPServer`, SQLite (`bank_system.db`), a relational MySQL export (`mysql_dump.sql`), and a vanilla HTML/CSS/JS dashboard (`static/`).

## Key Capabilities

### 1. Multi-Bank Architecture (Multi-Tenant Isolation)
- Multiple independent banks (`companies`) with configurable short codes, SWIFT codes, currency codes/symbols (`INR ₹`, `USD $`, etc.), brand themes, and active status.
- Tenant isolation via `company_code` foreign keys across `branches`, `employees`, `operators`, `account_types`, `customers`, `accounts`, `transactions`, `cards`, `loans`, and `audit_logs`.
- Dynamic bank onboarding (`POST /api/companies`), branch creation (`POST /api/branches`), and bank-specific account products (`POST /api/account-types`) directly from the UI.
- Same-bank and same-currency inter-bank double-entry transfers with FX guard across mismatched currencies.

### 2. Non-Manager Operations & Role-Based Access Control (RBAC)
- Real operator authentication (`PBKDF2-HMAC-SHA256` password hashes + `HMAC-SHA256` signed bearer tokens).
- Normalized `roles` permission matrix supporting 7 distinct roles:
  - `SUPER_ADMIN` — Consortium-wide DBA, bank provisioning, full R/W SQL Studio
  - `BANK_ADMIN` — Single-bank admin (branches, staff, operators, custom products, read-only SQL)
  - `BRANCH_MANAGER` — Branch operations, freezing/closing accounts, loans, cards, audit view, read-only SQL
  - `TELLER` — Non-manager front-desk operator (deposits, withdrawals, transfers, loan repayments; blocked from freezing accounts, sanctioning loans, or staff/SQL writes)
  - `RELATIONSHIP_MGR` — Customer KYC registration, account opening, card issuance
  - `CREDIT_ANALYST` — Loan sanctioning, EMI repayments, credit inspection, read-only SQL
  - `AUDITOR` — Cross-bank read-only oversight (`audit_logs` + `SELECT`-only SQL)
- Engine-level SQLite `set_authorizer` guard enforcing `SELECT`-only SQL (and masking `operators.password_hash`) for non-`SUPER_ADMIN` SQL users.
- Immutable `audit_logs` tracking every `SUCCESS`, `DENIED`, and `ERROR` mutation with actor, role, and bank context.

## Schema (13 Normalized Tables)

1. `companies` — bank tenants & currency/brand metadata
2. `roles` — normalized RBAC permission flags
3. `branches` — per-bank branch network
4. `employees` — bank staff records
5. `operators` — DB operator logins linked to roles & bank/branch scope
6. `account_types` — global templates and bank-specific products
7. `transaction_categories` — transaction taxonomy
8. `customers` — bank-scoped customer KYC profiles
9. `accounts` — customer accounts with balances & overdraft limits
10. `transactions` — double-entry ledger with `performed_by_operator_id`
11. `cards` — debit/credit/prepaid instruments
12. `loans` — loan principals, rates, terms, EMIs, and `approved_by_operator_id`
13. `audit_logs` — accountability trail for allowed & denied operations

## Run Locally

```bash
# Optional: reset and seed bank_system.db from scratch
python3 db_setup.py --reset

# Start the API and frontend server on port 8080 (auto-migrates existing DB)
python3 server.py
```

Open `http://localhost:8080` and use either the sign-in form or the 1-click demo operator cards (`sysadmin`, `rajesh.mgr`, `amit.teller`, `sneha.rm`, `deepika.credit`, `ananya.gfc`, `karthik.mbg`, `ritu.teller`, `compliance.audit`).
