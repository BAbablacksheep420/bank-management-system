import os
import json
import sqlite3
import datetime
import urllib.parse
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import mimetypes
import traceback

DB_PATH = os.path.join(os.path.dirname(__file__), "bank_system.db")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn

class BankingRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def send_json(self, data, status=200):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, message, status=400):
        self.send_json({"success": False, "error": message}, status=status)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def read_json_body(self):
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        body = self.rfile.read(content_length).decode("utf-8")
        return json.loads(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        try:
            if path == "/api/dashboard/stats":
                self.handle_dashboard_stats()
            elif path == "/api/customers":
                self.handle_get_customers(query)
            elif path.startswith("/api/customers/"):
                cust_id = path.replace("/api/customers/", "").strip()
                self.handle_get_customer_detail(cust_id)
            elif path == "/api/accounts":
                self.handle_get_accounts(query)
            elif path == "/api/transactions":
                self.handle_get_transactions(query)
            elif path == "/api/cards":
                self.handle_get_cards(query)
            elif path == "/api/loans":
                self.handle_get_loans(query)
            elif path == "/api/branches":
                self.handle_get_branches()
            elif path == "/api/employees":
                self.handle_get_employees()
            elif path == "/api/metadata":
                self.handle_get_metadata()
            elif path == "/api/export/sql":
                self.handle_export_sql()
            else:
                # Fallback to static files
                if path == "/" or not os.path.exists(os.path.join(STATIC_DIR, path.lstrip("/"))):
                    self.path = "/index.html"
                super().do_GET()
        except Exception as e:
            traceback.print_exc()
            self.send_error_json(str(e), status=500)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        try:
            body = self.read_json_body()
            if path == "/api/customers":
                self.handle_create_customer(body)
            elif path == "/api/accounts":
                self.handle_create_account(body)
            elif path == "/api/transact":
                self.handle_transaction_action(body)
            elif path == "/api/cards":
                self.handle_create_card(body)
            elif path == "/api/loans":
                self.handle_create_loan(body)
            elif path == "/api/loans/repay":
                self.handle_loan_repayment(body)
            elif path == "/api/sql":
                self.handle_run_sql(body)
            else:
                self.send_error_json("Endpoint not found", status=404)
        except Exception as e:
            traceback.print_exc()
            self.send_error_json(str(e), status=500)

    def do_PUT(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        try:
            body = self.read_json_body()
            if path.startswith("/api/accounts/") and path.endswith("/status"):
                acc_no = path.split("/")[3]
                self.handle_update_account_status(acc_no, body)
            elif path.startswith("/api/cards/") and path.endswith("/status"):
                card_id = path.split("/")[3]
                self.handle_update_card_status(card_id, body)
            else:
                self.send_error_json("Endpoint not found", status=404)
        except Exception as e:
            traceback.print_exc()
            self.send_error_json(str(e), status=500)

    # ---------------- HANDLERS ---------------- #

    def handle_dashboard_stats(self):
        conn = get_db()
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM customers")
        total_customers = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*), COALESCE(SUM(balance), 0) FROM accounts WHERE status = 'active'")
        active_accounts, total_balance = cur.fetchone()

        cur.execute("SELECT COUNT(*), COALESCE(SUM(outstanding_balance), 0) FROM loans WHERE status = 'running'")
        active_loans, outstanding_loans = cur.fetchone()

        cur.execute("SELECT COUNT(*) FROM cards WHERE status = 'active'")
        active_cards = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM transactions")
        total_transactions, total_txn_volume = cur.fetchone()

        # Account Types Distribution
        cur.execute("""
            SELECT at.type_name, COUNT(a.account_number) as count, COALESCE(SUM(a.balance), 0) as total_balance
            FROM account_types at
            LEFT JOIN accounts a ON at.account_type_code = a.account_type_code
            GROUP BY at.account_type_code, at.type_name
        """)
        account_dist = [dict(row) for row in cur.fetchall()]

        # Recent 8 transactions
        cur.execute("""
            SELECT t.transaction_reference, t.account_number, t.category_code, t.transaction_type, 
                   t.amount, t.description, t.transaction_date, t.running_balance,
                   c.first_name || ' ' || c.last_name as customer_name,
                   tc.category_name
            FROM transactions t
            JOIN accounts a ON t.account_number = a.account_number
            JOIN customers c ON a.customer_id = c.customer_id
            LEFT JOIN transaction_categories tc ON t.category_code = tc.category_code
            ORDER BY t.transaction_date DESC, t.created_at DESC
            LIMIT 8
        """)
        recent_txns = [dict(row) for row in cur.fetchall()]

        # Branch overview
        cur.execute("""
            SELECT b.branch_name, b.branch_code, COUNT(e.employee_id) as employee_count,
                   (SELECT COUNT(a.account_number) FROM accounts a 
                    JOIN customers c ON a.customer_id = c.customer_id 
                    JOIN employees em ON c.relationship_manager_id = em.employee_id 
                    WHERE em.branch_code = b.branch_code) as customer_accounts_managed
            FROM branches b
            LEFT JOIN employees e ON b.branch_code = e.branch_code
            GROUP BY b.branch_code
        """)
        branch_stats = [dict(row) for row in cur.fetchall()]

        conn.close()
        self.send_json({
            "success": True,
            "data": {
                "total_customers": total_customers,
                "active_accounts": active_accounts,
                "total_balance": total_balance,
                "active_loans": active_loans,
                "outstanding_loans": outstanding_loans,
                "active_cards": active_cards,
                "total_transactions": total_transactions,
                "total_txn_volume": total_txn_volume,
                "account_distribution": account_dist,
                "recent_transactions": recent_txns,
                "branch_stats": branch_stats
            }
        })

    def handle_get_customers(self, query):
        conn = get_db()
        cur = conn.cursor()
        search = query.get("q", [""])[0].strip()

        sql = """
            SELECT c.*, 
                   e.first_name || ' ' || e.last_name as rm_name,
                   COUNT(DISTINCT a.account_number) as accounts_count,
                   COALESCE(SUM(a.balance), 0) as total_customer_balance,
                   COUNT(DISTINCT l.loan_number) as loans_count,
                   COUNT(DISTINCT cd.card_id) as cards_count
            FROM customers c
            LEFT JOIN employees e ON c.relationship_manager_id = e.employee_id
            LEFT JOIN accounts a ON c.customer_id = a.customer_id
            LEFT JOIN loans l ON c.customer_id = l.customer_id AND l.status = 'running'
            LEFT JOIN cards cd ON c.customer_id = cd.customer_id
        """
        params = []
        if search:
            sql += """
                WHERE c.customer_id LIKE ? OR c.first_name LIKE ? OR c.last_name LIKE ? 
                   OR c.email LIKE ? OR c.phone LIKE ?
            """
            wildcard = f"%{search}%"
            params = [wildcard, wildcard, wildcard, wildcard, wildcard]

        sql += " GROUP BY c.customer_id ORDER BY c.customer_id DESC"
        cur.execute(sql, params)
        customers = [dict(row) for row in cur.fetchall()]
        conn.close()
        self.send_json({"success": True, "data": customers})

    def handle_get_customer_detail(self, cust_id):
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT c.*, e.first_name || ' ' || e.last_name as rm_name, e.email as rm_email, b.branch_name
            FROM customers c
            LEFT JOIN employees e ON c.relationship_manager_id = e.employee_id
            LEFT JOIN branches b ON e.branch_code = b.branch_code
            WHERE c.customer_id = ?
        """, (cust_id,))
        cust = cur.fetchone()
        if not cust:
            conn.close()
            return self.send_error_json("Customer not found", status=404)

        customer_data = dict(cust)

        # Accounts
        cur.execute("""
            SELECT a.*, at.type_name, at.interest_rate, at.allows_overdraft
            FROM accounts a
            JOIN account_types at ON a.account_type_code = at.account_type_code
            WHERE a.customer_id = ?
        """, (cust_id,))
        customer_data["accounts"] = [dict(row) for row in cur.fetchall()]

        # Cards
        cur.execute("SELECT * FROM cards WHERE customer_id = ?", (cust_id,))
        customer_data["cards"] = [dict(row) for row in cur.fetchall()]

        # Loans
        cur.execute("SELECT * FROM loans WHERE customer_id = ?", (cust_id,))
        customer_data["loans"] = [dict(row) for row in cur.fetchall()]

        # Recent transactions across all accounts of this customer
        cur.execute("""
            SELECT t.*, tc.category_name
            FROM transactions t
            JOIN accounts a ON t.account_number = a.account_number
            LEFT JOIN transaction_categories tc ON t.category_code = tc.category_code
            WHERE a.customer_id = ?
            ORDER BY t.transaction_date DESC
            LIMIT 15
        """, (cust_id,))
        customer_data["transactions"] = [dict(row) for row in cur.fetchall()]

        conn.close()
        self.send_json({"success": True, "data": customer_data})

    def handle_create_customer(self, body):
        conn = get_db()
        cur = conn.cursor()

        # Generate next CUST id
        cur.execute("SELECT customer_id FROM customers ORDER BY customer_id DESC LIMIT 1")
        last_row = cur.fetchone()
        if last_row and last_row[0].startswith("CUST"):
            num = int(last_row[0][4:]) + 1
            new_id = f"CUST{num:03d}"
        else:
            new_id = "CUST001"

        first_name = body.get("first_name", "").strip()
        last_name = body.get("last_name", "").strip()
        email = body.get("email", "").strip()
        phone = body.get("phone", "").strip()
        address = body.get("address", "").strip()
        dob = body.get("date_of_birth", "")
        id_number = body.get("id_number", "").strip()
        credit_score = float(body.get("credit_score", 700))
        rm_id = body.get("relationship_manager_id") or "EMP002"
        reg_date = body.get("registration_date") or datetime.date.today().isoformat()

        if not first_name or not last_name or not email or not dob:
            conn.close()
            return self.send_error_json("first_name, last_name, email, and date_of_birth are required")

        cur.execute("""
            INSERT INTO customers (customer_id, relationship_manager_id, first_name, last_name, email, phone, address, date_of_birth, id_number, credit_score, registration_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (new_id, rm_id, first_name, last_name, email, phone, address, dob, id_number, credit_score, reg_date))

        conn.commit()
        conn.close()
        self.send_json({"success": True, "customer_id": new_id, "message": "Customer created successfully"})

    def handle_get_accounts(self, query):
        conn = get_db()
        cur = conn.cursor()
        search = query.get("q", [""])[0].strip()

        sql = """
            SELECT a.*, at.type_name, at.interest_rate,
                   c.first_name || ' ' || c.last_name as customer_name,
                   c.email as customer_email,
                   (SELECT COUNT(*) FROM cards cd WHERE cd.linked_account_number = a.account_number) as linked_cards_count
            FROM accounts a
            JOIN customers c ON a.customer_id = c.customer_id
            JOIN account_types at ON a.account_type_code = at.account_type_code
        """
        params = []
        if search:
            sql += " WHERE a.account_number LIKE ? OR c.first_name LIKE ? OR c.last_name LIKE ?"
            w = f"%{search}%"
            params = [w, w, w]

        sql += " ORDER BY a.created_at DESC"
        cur.execute(sql, params)
        accounts = [dict(row) for row in cur.fetchall()]
        conn.close()
        self.send_json({"success": True, "data": accounts})

    def handle_create_account(self, body):
        conn = get_db()
        cur = conn.cursor()

        # Generate next ACC number
        cur.execute("SELECT account_number FROM accounts ORDER BY account_number DESC LIMIT 1")
        last_row = cur.fetchone()
        if last_row and last_row[0].startswith("ACC"):
            num = int(last_row[0][3:]) + 1
            new_acc = f"ACC{num:06d}"
        else:
            new_acc = "ACC100001"

        customer_id = body.get("customer_id")
        account_type_code = body.get("account_type_code")
        initial_balance = float(body.get("initial_deposit", 0.0))
        overdraft_limit = float(body.get("overdraft_limit", 0.0))
        opening_date = datetime.date.today().isoformat()

        if not customer_id or not account_type_code:
            conn.close()
            return self.send_error_json("customer_id and account_type_code are required")

        # Verify customer exists
        cur.execute("SELECT customer_id FROM customers WHERE customer_id = ?", (customer_id,))
        if not cur.fetchone():
            conn.close()
            return self.send_error_json("Customer not found")

        cur.execute("""
            INSERT INTO accounts (account_number, customer_id, account_type_code, balance, opening_date, status, overdraft_limit)
            VALUES (?, ?, ?, ?, ?, 'active', ?)
        """, (new_acc, customer_id, account_type_code, initial_balance, opening_date, overdraft_limit))

        # If opening balance > 0, log opening transaction
        if initial_balance > 0:
            cur.execute("SELECT transaction_reference FROM transactions ORDER BY transaction_reference DESC LIMIT 1")
            txn_row = cur.fetchone()
            if txn_row and txn_row[0].startswith("TXN"):
                tnum = int(txn_row[0][3:]) + 1
                txn_ref = f"TXN{tnum:06d}"
            else:
                txn_ref = "TXN100001"

            cur.execute("""
                INSERT INTO transactions (transaction_reference, account_number, category_code, transaction_type, amount, description, transaction_date, running_balance)
                VALUES (?, ?, 'CAT006', 'credit', ?, 'Account Opening Initial Deposit', datetime('now'), ?)
            """, (txn_ref, new_acc, initial_balance, initial_balance))

        conn.commit()
        conn.close()
        self.send_json({"success": True, "account_number": new_acc, "message": "Account opened successfully"})

    def handle_update_account_status(self, acc_no, body):
        new_status = body.get("status")
        if new_status not in ['active', 'closed', 'frozen']:
            return self.send_error_json("Invalid status. Must be active, closed, or frozen")

        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE accounts SET status = ? WHERE account_number = ?", (new_status, acc_no))
        if cur.rowcount == 0:
            conn.close()
            return self.send_error_json("Account not found")

        conn.commit()
        conn.close()
        self.send_json({"success": True, "message": f"Account status updated to {new_status}"})

    def handle_transaction_action(self, body):
        action = body.get("action") # 'deposit', 'withdraw', 'transfer'
        amount = float(body.get("amount", 0))
        if amount <= 0:
            return self.send_error_json("Amount must be greater than zero")

        conn = get_db()
        cur = conn.cursor()

        try:
            cur.execute("BEGIN TRANSACTION")

            def get_next_txn_ref():
                cur.execute("SELECT transaction_reference FROM transactions ORDER BY transaction_reference DESC LIMIT 1")
                row = cur.fetchone()
                if row and row[0].startswith("TXN"):
                    num = int(row[0][3:]) + 1
                    return f"TXN{num:06d}"
                return "TXN100001"

            if action == "deposit":
                acc_no = body.get("account_number")
                cur.execute("SELECT balance, status FROM accounts WHERE account_number = ?", (acc_no,))
                row = cur.fetchone()
                if not row:
                    raise Exception(f"Account {acc_no} not found")
                if row["status"] != "active":
                    raise Exception(f"Cannot deposit: Account is {row['status']}")

                new_balance = round(row["balance"] + amount, 2)
                cur.execute("UPDATE accounts SET balance = ? WHERE account_number = ?", (new_balance, acc_no))

                txn_ref = get_next_txn_ref()
                cat_code = body.get("category_code") or "CAT006"
                desc = body.get("description") or "Cash/Cheque Deposit"
                cur.execute("""
                    INSERT INTO transactions (transaction_reference, account_number, category_code, transaction_type, amount, description, transaction_date, running_balance)
                    VALUES (?, ?, ?, 'credit', ?, ?, datetime('now'), ?)
                """, (txn_ref, acc_no, cat_code, amount, desc, new_balance))

                conn.commit()
                conn.close()
                return self.send_json({"success": True, "transaction_reference": txn_ref, "new_balance": new_balance, "message": "Deposit completed successfully"})

            elif action == "withdraw":
                acc_no = body.get("account_number")
                cur.execute("SELECT balance, status, overdraft_limit FROM accounts WHERE account_number = ?", (acc_no,))
                row = cur.fetchone()
                if not row:
                    raise Exception(f"Account {acc_no} not found")
                if row["status"] != "active":
                    raise Exception(f"Cannot withdraw: Account is {row['status']}")

                max_available = row["balance"] + row["overdraft_limit"]
                if amount > max_available:
                    raise Exception(f"Insufficient funds: Available balance including overdraft is ₹{max_available:,.2f}")

                new_balance = round(row["balance"] - amount, 2)
                cur.execute("UPDATE accounts SET balance = ? WHERE account_number = ?", (new_balance, acc_no))

                txn_ref = get_next_txn_ref()
                cat_code = body.get("category_code") or "CAT002"
                desc = body.get("description") or "Cash Withdrawal"
                cur.execute("""
                    INSERT INTO transactions (transaction_reference, account_number, category_code, transaction_type, amount, description, transaction_date, running_balance)
                    VALUES (?, ?, ?, 'debit', ?, ?, datetime('now'), ?)
                """, (txn_ref, acc_no, cat_code, amount, desc, new_balance))

                conn.commit()
                conn.close()
                return self.send_json({"success": True, "transaction_reference": txn_ref, "new_balance": new_balance, "message": "Withdrawal completed successfully"})

            elif action == "transfer":
                src_acc = body.get("from_account")
                dst_acc = body.get("to_account")

                if src_acc == dst_acc:
                    raise Exception("Source and destination accounts cannot be identical")

                # Fetch source
                cur.execute("SELECT balance, status, overdraft_limit FROM accounts WHERE account_number = ?", (src_acc,))
                src = cur.fetchone()
                if not src:
                    raise Exception(f"Source account {src_acc} not found")
                if src["status"] != "active":
                    raise Exception(f"Source account {src_acc} is {src['status']}")

                if amount > (src["balance"] + src["overdraft_limit"]):
                    raise Exception(f"Insufficient funds in source account {src_acc}")

                # Fetch dest
                cur.execute("SELECT balance, status FROM accounts WHERE account_number = ?", (dst_acc,))
                dst = cur.fetchone()
                if not dst:
                    raise Exception(f"Destination account {dst_acc} not found")
                if dst["status"] != "active":
                    raise Exception(f"Destination account {dst_acc} is {dst['status']}")

                src_new_bal = round(src["balance"] - amount, 2)
                dst_new_bal = round(dst["balance"] + amount, 2)

                cur.execute("UPDATE accounts SET balance = ? WHERE account_number = ?", (src_new_bal, src_acc))
                cur.execute("UPDATE accounts SET balance = ? WHERE account_number = ?", (dst_new_bal, dst_acc))

                # Log debit from source
                ref1 = get_next_txn_ref()
                cur.execute("""
                    INSERT INTO transactions (transaction_reference, account_number, category_code, transaction_type, amount, description, transaction_date, running_balance)
                    VALUES (?, ?, 'CAT003', 'debit', ?, ?, datetime('now'), ?)
                """, (ref1, src_acc, amount, f"Transfer to {dst_acc}: {body.get('description', 'Fund Transfer')}", src_new_bal))

                # Log credit to dest
                ref2 = get_next_txn_ref()
                cur.execute("""
                    INSERT INTO transactions (transaction_reference, account_number, category_code, transaction_type, amount, description, transaction_date, running_balance)
                    VALUES (?, ?, 'CAT003', 'credit', ?, ?, datetime('now'), ?)
                """, (ref2, dst_acc, amount, f"Transfer from {src_acc}: {body.get('description', 'Fund Transfer')}", dst_new_bal))

                conn.commit()
                conn.close()
                return self.send_json({
                    "success": True,
                    "debit_reference": ref1,
                    "credit_reference": ref2,
                    "from_balance": src_new_bal,
                    "to_balance": dst_new_bal,
                    "message": f"Successfully transferred ₹{amount:,.2f} from {src_acc} to {dst_acc}"
                })
            else:
                raise Exception("Invalid action. Must be deposit, withdraw, or transfer")

        except Exception as e:
            conn.rollback()
            conn.close()
            return self.send_error_json(str(e))

    def handle_get_transactions(self, query):
        conn = get_db()
        cur = conn.cursor()
        acc = query.get("account_number", [""])[0].strip()
        txn_type = query.get("type", [""])[0].strip()
        cat = query.get("category", [""])[0].strip()

        sql = """
            SELECT t.*, tc.category_name, c.first_name || ' ' || c.last_name as customer_name, a.customer_id
            FROM transactions t
            JOIN accounts a ON t.account_number = a.account_number
            JOIN customers c ON a.customer_id = c.customer_id
            LEFT JOIN transaction_categories tc ON t.category_code = tc.category_code
            WHERE 1=1
        """
        params = []
        if acc:
            sql += " AND t.account_number = ?"
            params.append(acc)
        if txn_type:
            sql += " AND t.transaction_type = ?"
            params.append(txn_type)
        if cat:
            sql += " AND t.category_code = ?"
            params.append(cat)

        sql += " ORDER BY t.transaction_date DESC, t.created_at DESC LIMIT 100"
        cur.execute(sql, params)
        txns = [dict(row) for row in cur.fetchall()]
        conn.close()
        self.send_json({"success": True, "data": txns})

    def handle_get_cards(self, query):
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT cd.*, c.first_name || ' ' || c.last_name as customer_name, a.balance, at.type_name as account_type
            FROM cards cd
            JOIN customers c ON cd.customer_id = c.customer_id
            JOIN accounts a ON cd.linked_account_number = a.account_number
            JOIN account_types at ON a.account_type_code = at.account_type_code
            ORDER BY cd.created_at DESC
        """)
        cards = [dict(row) for row in cur.fetchall()]
        conn.close()
        self.send_json({"success": True, "data": cards})

    def handle_create_card(self, body):
        conn = get_db()
        cur = conn.cursor()

        customer_id = body.get("customer_id")
        linked_account = body.get("linked_account_number")
        card_type = body.get("card_type", "debit")
        credit_limit = float(body.get("credit_limit", 0))

        # Check account
        cur.execute("SELECT customer_id FROM accounts WHERE account_number = ?", (linked_account,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return self.send_error_json("Linked account not found")

        # Next card ID
        cur.execute("SELECT card_id FROM cards ORDER BY card_id DESC LIMIT 1")
        last_card = cur.fetchone()
        if last_card and last_card[0].startswith("CRD"):
            num = int(last_card[0][3:]) + 1
            card_id = f"CRD{num:03d}"
        else:
            card_id = "CRD001"

        import random
        rand4 = f"{random.randint(1000, 9999)}"
        card_num_masked = f"4219 •••• •••• {rand4}"
        issue_date = datetime.date.today().isoformat()
        expiry_date = (datetime.date.today() + datetime.timedelta(days=365*5)).isoformat()

        cur.execute("""
            INSERT INTO cards (card_id, customer_id, linked_account_number, card_number_masked, card_type, issue_date, expiry_date, credit_limit, pin_hash, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'hash_dummy_pin', 'active')
        """, (card_id, customer_id, linked_account, card_num_masked, card_type, issue_date, expiry_date, credit_limit))

        conn.commit()
        conn.close()
        self.send_json({"success": True, "card_id": card_id, "message": "Card issued successfully"})

    def handle_update_card_status(self, card_id, body):
        status = body.get("status")
        if status not in ["active", "blocked", "expired"]:
            return self.send_error_json("Invalid card status")

        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE cards SET status = ? WHERE card_id = ?", (status, card_id))
        conn.commit()
        conn.close()
        self.send_json({"success": True, "message": f"Card status updated to {status}"})

    def handle_get_loans(self, query):
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT l.*, c.first_name || ' ' || c.last_name as customer_name, c.credit_score, c.phone
            FROM loans l
            JOIN customers c ON l.customer_id = c.customer_id
            ORDER BY l.created_at DESC
        """)
        loans = [dict(row) for row in cur.fetchall()]
        conn.close()
        self.send_json({"success": True, "data": loans})

    def handle_create_loan(self, body):
        conn = get_db()
        cur = conn.cursor()

        customer_id = body.get("customer_id")
        loan_type = body.get("loan_type", "personal")
        principal = float(body.get("principal_amount", 0))
        rate = float(body.get("interest_rate", 0.085))
        term = int(body.get("term_months", 12))

        if principal <= 0 or term <= 0:
            conn.close()
            return self.send_error_json("Principal and term must be greater than zero")

        # Calculate monthly EMI: P * r * (1+r)^n / ((1+r)^n - 1)
        r = rate / 12.0
        if r > 0:
            emi = round(principal * r * ((1 + r) ** term) / (((1 + r) ** term) - 1), 2)
        else:
            emi = round(principal / term, 2)

        cur.execute("SELECT loan_number FROM loans ORDER BY loan_number DESC LIMIT 1")
        last_loan = cur.fetchone()
        if last_loan and last_loan[0].startswith("LN"):
            num = int(last_loan[0][2:]) + 1
            loan_num = f"LN{num:06d}"
        else:
            loan_num = "LN100001"

        start_date = datetime.date.today().isoformat()
        end_date = (datetime.date.today() + datetime.timedelta(days=int(term * 30.4))).isoformat()

        cur.execute("""
            INSERT INTO loans (loan_number, customer_id, loan_type, principal_amount, interest_rate, term_months, monthly_payment, start_date, end_date, status, outstanding_balance)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'running', ?)
        """, (loan_num, customer_id, loan_type, principal, rate, term, emi, start_date, end_date, principal))

        conn.commit()
        conn.close()
        self.send_json({"success": True, "loan_number": loan_num, "monthly_payment": emi, "message": "Loan sanctioned successfully"})

    def handle_loan_repayment(self, body):
        loan_number = body.get("loan_number")
        repay_amount = float(body.get("amount", 0))

        if repay_amount <= 0:
            return self.send_error_json("Repayment amount must be positive")

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT outstanding_balance, status FROM loans WHERE loan_number = ?", (loan_number,))
        loan = cur.fetchone()
        if not loan:
            conn.close()
            return self.send_error_json("Loan not found")

        new_bal = round(max(0.0, loan["outstanding_balance"] - repay_amount), 2)
        new_status = "closed" if new_bal == 0.0 else loan["status"]

        cur.execute("UPDATE loans SET outstanding_balance = ?, status = ? WHERE loan_number = ?", (new_bal, new_status, loan_number))
        conn.commit()
        conn.close()
        self.send_json({"success": True, "new_balance": new_bal, "status": new_status, "message": f"Repayment of ₹{repay_amount:,.2f} recorded. Remaining: ₹{new_bal:,.2f}"})

    def handle_get_branches(self):
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT b.*, c.company_name, COUNT(e.employee_id) as employee_count
            FROM branches b
            JOIN companies c ON b.company_code = c.company_code
            LEFT JOIN employees e ON b.branch_code = e.branch_code
            GROUP BY b.branch_code
        """)
        branches = [dict(row) for row in cur.fetchall()]
        conn.close()
        self.send_json({"success": True, "data": branches})

    def handle_get_employees(self):
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT e.*, b.branch_name
            FROM employees e
            LEFT JOIN branches b ON e.branch_code = b.branch_code
            ORDER BY e.employee_id ASC
        """)
        employees = [dict(row) for row in cur.fetchall()]
        conn.close()
        self.send_json({"success": True, "data": employees})

    def handle_get_metadata(self):
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM account_types")
        account_types = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT * FROM transaction_categories")
        categories = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT company_code, company_name FROM companies")
        companies = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT employee_id, first_name || ' ' || last_name || ' (' || position || ')' as name FROM employees")
        employees = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT customer_id, customer_id || ' - ' || first_name || ' ' || last_name as name FROM customers")
        customers = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT account_number, account_number || ' (' || customer_id || ' - ₹' || balance || ')' as label FROM accounts WHERE status = 'active'")
        accounts = [dict(r) for r in cur.fetchall()]
        conn.close()

        self.send_json({
            "success": True,
            "data": {
                "account_types": account_types,
                "categories": categories,
                "companies": companies,
                "employees": employees,
                "customers": customers,
                "accounts": accounts
            }
        })

    def handle_run_sql(self, body):
        import time
        raw_sql = body.get("query", "").strip()
        if not raw_sql:
            return self.send_error_json("No SQL query provided")

        # Disallow hazardous system table drops
        upper = raw_sql.upper()
        if "DROP DATABASE" in upper:
            return self.send_error_json("Drop database operation is prohibited")

        start = time.time()
        conn = get_db()
        cur = conn.cursor()

        try:
            # Check if multiple statements or single
            cur.execute(raw_sql)
            duration_ms = round((time.time() - start) * 1000, 2)

            if cur.description:
                columns = [col[0] for col in cur.description]
                rows = [list(row) for row in cur.fetchall()]
                conn.commit()
                conn.close()
                return self.send_json({
                    "success": True,
                    "columns": columns,
                    "rows": rows,
                    "row_count": len(rows),
                    "execution_time_ms": duration_ms
                })
            else:
                affected = cur.rowcount
                conn.commit()
                conn.close()
                return self.send_json({
                    "success": True,
                    "columns": ["Result"],
                    "rows": [[f"Query executed successfully. Rows affected: {affected}"]],
                    "row_count": affected,
                    "execution_time_ms": duration_ms
                })
        except Exception as e:
            conn.close()
            return self.send_error_json(f"SQL Error: {str(e)}")

    def handle_export_sql(self):
        dump_path = os.path.join(os.path.dirname(__file__), "mysql_dump.sql")
        if not os.path.exists(dump_path):
            return self.send_error_json("Dump file not found", 404)
        with open(dump_path, "rb") as f:
            content = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "application/sql")
        self.send_header("Content-Disposition", 'attachment; filename="dtu_bank_system_mysql.sql"')
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

def run_server(port=8080):
    server_address = ("0.0.0.0", port)
    httpd = ThreadingHTTPServer(server_address, BankingRequestHandler)
    print(f"Bank Management System API & Frontend Server running at http://localhost:{port}")
    httpd.serve_forever()

if __name__ == "__main__":
    run_server()
