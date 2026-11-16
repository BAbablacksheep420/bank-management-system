# Bank Management System (CS209 DBMS)

Full-stack banking database management system built with Python's standard-library `ThreadingHTTPServer`, SQLite (`bank_system.db`), a relational MySQL export (`mysql_dump.sql`), and a vanilla HTML/CSS/JS dashboard (`static/`).

## Schema

10 normalized tables initialized in `db_setup.py` with foreign-key constraints (`PRAGMA foreign_keys = ON`):

- `companies` — institution metadata and total assets
- `branches` — branch codes, managers, addresses, and operating hours
- `employees` — branch staff records
- `account_types` — account tier definitions
- `transaction_categories` — transaction classification lookup
- `customers` — customer profiles
- `accounts` — customer bank accounts and balances
- `transactions` — deposits, withdrawals, and transfers
- `cards` — debit/credit cards linked to customers and accounts
- `loans` — loan principals, rates, terms, EMIs, and repayment balances

## Run Locally

```bash
# Optional: re-initialize and seed bank_system.db
python3 db_setup.py

# Start the API and frontend server on port 8080
python3 server.py
```

Open `http://localhost:8080` in a browser.

## API Endpoints

- `GET /api/dashboard/stats` — aggregate metrics
- `GET/POST /api/customers`, `GET /api/customers/<id>` — customer directory and details
- `GET/POST /api/accounts`, `PUT /api/accounts/<acc_no>/status` — account management
- `GET /api/transactions`, `POST /api/transact` — ledger queries and transactions
- `GET/POST /api/cards`, `PUT /api/cards/<card_id>/status` — card issuance and status updates
- `GET/POST /api/loans`, `POST /api/loans/repay` — loan origination and repayments
- `GET /api/branches`, `GET /api/employees`, `GET /api/metadata` — reference data
- `POST /api/sql` — interactive SQL query runner
- `GET /api/export/sql` — download `mysql_dump.sql`
