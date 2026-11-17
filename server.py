import base64
import datetime
import hashlib
import hmac
import json
import os
import random
import secrets
import sqlite3
import time
import traceback
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import db_setup

BASE_DIR = os.path.dirname(__file__)
DB_PATH = db_setup.DB_PATH
STATIC_DIR = os.path.join(BASE_DIR, "static")
SECRET_FILE = os.path.join(BASE_DIR, ".auth_secret")


def _load_or_create_secret() -> bytes:
    env_secret = os.environ.get("BMS_AUTH_SECRET")
    if env_secret:
        return env_secret.encode("utf-8")
    if os.path.exists(SECRET_FILE):
        with open(SECRET_FILE, "rb") as f:
            raw = f.read().strip()
            if raw:
                return raw
    new_secret = secrets.token_hex(32).encode("utf-8")
    with open(SECRET_FILE, "wb") as f:
        f.write(new_secret)
    return new_secret


AUTH_SECRET = _load_or_create_secret()
TOKEN_TTL_SECONDS = 60 * 60 * 24  # 24 hours


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * ((4 - len(s) % 4) % 4)
    return base64.urlsafe_b64decode(s + pad)


def sign_token(operator_id: str, username: str, role_code: str) -> str:
    payload = {
        "oid": operator_id,
        "usr": username,
        "role": role_code,
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    body = _b64url_encode(raw)
    sig = hmac.new(AUTH_SECRET, body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_b64url_encode(sig)}"


def verify_token(token: str) -> dict | None:
    try:
        if not token or "." not in token:
            return None
        body, sig_b64 = token.split(".", 1)
        expected_sig = hmac.new(
            AUTH_SECRET, body.encode("ascii"), hashlib.sha256
        ).digest()
        provided_sig = _b64url_decode(sig_b64)
        if not hmac.compare_digest(expected_sig, provided_sig):
            return None
        payload = json.loads(_b64url_decode(body).decode("utf-8"))
        if payload.get("exp", 0) < int(time.time()):
            return None
        return payload
    except Exception:
        return None


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=15.0)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


def generate_next_id(
    cur: sqlite3.Cursor, table: str, col: str, prefix: str, start_num: int = 1, pad: int = 3
) -> str:
    idx = len(prefix) + 1
    cur.execute(
        f"SELECT MAX(CAST(SUBSTR({col}, ?) AS INTEGER)) FROM {table} WHERE {col} GLOB ?",
        (idx, f"{prefix}[0-9]*"),
    )
    row = cur.fetchone()
    max_val = row[0] if row and row[0] is not None else (start_num - 1)
    next_num = max(start_num, int(max_val) + 1)
    return f"{prefix}{next_num:0{pad}d}"


def log_audit(
    conn: sqlite3.Connection,
    user: dict | None,
    company_code: str | None,
    action: str,
    target_table: str | None = None,
    target_id: str | None = None,
    status: str = "SUCCESS",
    details: str = "",
) -> None:
    try:
        conn.execute(
            """
            INSERT INTO audit_logs (
                operator_id, operator_username, role_code, company_code,
                action, target_table, target_id, status, details
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user["operator_id"] if user else None,
                user["username"] if user else "anonymous",
                user["role_code"] if user else None,
                company_code,
                action,
                target_table,
                target_id,
                status,
                details,
            ),
        )
        conn.commit()
    except Exception:
        traceback.print_exc()


def readonly_sqlite_authorizer(action, arg1, arg2, dbname, source):
    """Engine-level SQLite authorizer restricting non-SUPER_ADMIN SQL Studio to SELECT only."""
    if action == sqlite3.SQLITE_SELECT:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_READ:
        if arg1 == "operators" and arg2 == "password_hash":
            return sqlite3.SQLITE_IGNORE
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_FUNCTION:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_PRAGMA and arg1 in ("table_info", "index_list", "foreign_key_list"):
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


class PermissionDenied(Exception):
    pass


DEMO_PASSWORDS = {
    "sysadmin": "Admin@123",
    "compliance.audit": "Audit@123",
}


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
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Company-Code")
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, message, status=400):
        self.send_json({"success": False, "error": message}, status=status)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Company-Code")
        self.end_headers()

    def read_json_body(self):
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        body = self.rfile.read(content_length).decode("utf-8")
        return json.loads(body)

    def _extract_token(self, query: dict | None = None) -> str | None:
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:].strip()
        if query and "token" in query:
            return query["token"][0].strip()
        return None

    def authenticate_request(self, query: dict | None = None) -> dict | None:
        token = self._extract_token(query)
        payload = verify_token(token) if token else None
        if not payload:
            return None

        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT o.operator_id, o.employee_id, o.company_code, o.branch_code,
                   o.username, o.full_name, o.role_code, o.is_active,
                   c.company_name, c.short_code, c.currency_symbol, c.currency_code, c.brand_color,
                   b.branch_name,
                   r.role_name, r.description as role_description, r.hierarchy_level,
                   r.can_manage_banks, r.can_manage_staff, r.can_manage_customers,
                   r.can_manage_accounts, r.can_freeze_accounts, r.can_transact,
                   r.can_manage_cards, r.can_sanction_loans, r.can_repay_loans,
                   r.can_run_sql_read, r.can_run_sql_write, r.can_view_audit
            FROM operators o
            JOIN roles r ON o.role_code = r.role_code
            LEFT JOIN companies c ON o.company_code = c.company_code
            LEFT JOIN branches b ON o.branch_code = b.branch_code
            WHERE o.operator_id = ? AND o.is_active = 1
            """,
            (payload["oid"],),
        )
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None

    def require_auth(
        self,
        query: dict | None = None,
        perm_flag: str | None = None,
        action: str | None = None,
        target_table: str | None = None,
    ) -> dict | None:
        user = self.authenticate_request(query)
        if not user:
            self.send_error_json("Authentication required. Please sign in as an operator.", status=401)
            return None

        if perm_flag and not user.get(perm_flag):
            conn = get_db()
            log_audit(
                conn,
                user,
                user.get("company_code"),
                action or f"DENIED_{perm_flag.upper()}",
                target_table,
                None,
                status="DENIED",
                details=f"Role '{user['role_code']}' attempted action requiring '{perm_flag}'",
            )
            conn.close()
            self.send_error_json(
                f"Access denied: role '{user['role_name']}' does not have permission ({perm_flag}).",
                status=403,
            )
            return None

        return user

    def resolve_company_scope(
        self,
        user: dict,
        query: dict | None = None,
        requested_company: str | None = None,
        require_single_for_write: bool = False,
    ) -> str | None:
        raw_req = requested_company
        if raw_req is None and query:
            raw_req = query.get("company_code", [None])[0]
        if raw_req is None:
            raw_req = self.headers.get("X-Company-Code")
        if isinstance(raw_req, str):
            raw_req = raw_req.strip()

        user_company = user.get("company_code")
        if user_company:
            if raw_req and raw_req != "ALL" and raw_req != user_company:
                conn = get_db()
                log_audit(
                    conn,
                    user,
                    user_company,
                    "CROSS_BANK_ACCESS",
                    "companies",
                    raw_req,
                    status="DENIED",
                    details=f"Bank-scoped operator ({user_company}) attempted access to {raw_req}",
                )
                conn.close()
                raise PermissionDenied(
                    f"Tenant isolation denied: operator is scoped to {user_company}, cannot access {raw_req}."
                )
            return user_company

        # Global operator (SUPER_ADMIN or AUDITOR)
        if not raw_req or raw_req == "ALL":
            if require_single_for_write:
                raise ValueError("Please select a specific target bank instead of 'ALL' for this operation.")
            return None
        return raw_req

    # ---------------- HTTP DISPATCH ---------------- #

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        try:
            if path == "/api/auth/demo-accounts":
                self.handle_get_demo_accounts()
            elif path == "/api/auth/me":
                user = self.require_auth(query)
                if user:
                    self.send_json({"success": True, "data": self._format_user_payload(user)})
            elif path == "/api/roles":
                user = self.require_auth(query)
                if user:
                    self.handle_get_roles()
            elif path == "/api/companies":
                user = self.require_auth(query)
                if user:
                    self.handle_get_companies(user)
            elif path == "/api/dashboard/stats":
                user = self.require_auth(query)
                if user:
                    self.handle_dashboard_stats(user, query)
            elif path == "/api/customers":
                user = self.require_auth(query)
                if user:
                    self.handle_get_customers(user, query)
            elif path.startswith("/api/customers/"):
                user = self.require_auth(query)
                if user:
                    cust_id = path.replace("/api/customers/", "").strip()
                    self.handle_get_customer_detail(user, cust_id)
            elif path == "/api/accounts":
                user = self.require_auth(query)
                if user:
                    self.handle_get_accounts(user, query)
            elif path == "/api/account-types":
                user = self.require_auth(query)
                if user:
                    self.handle_get_account_types(user, query)
            elif path == "/api/transactions":
                user = self.require_auth(query)
                if user:
                    self.handle_get_transactions(user, query)
            elif path == "/api/cards":
                user = self.require_auth(query)
                if user:
                    self.handle_get_cards(user, query)
            elif path == "/api/loans":
                user = self.require_auth(query)
                if user:
                    self.handle_get_loans(user, query)
            elif path == "/api/branches":
                user = self.require_auth(query)
                if user:
                    self.handle_get_branches(user, query)
            elif path == "/api/employees":
                user = self.require_auth(query)
                if user:
                    self.handle_get_employees(user, query)
            elif path == "/api/operators":
                user = self.require_auth(query)
                if user:
                    if not (user.get("can_manage_staff") or user.get("can_view_audit")):
                        return self.send_error_json("Permission denied to view operators", status=403)
                    self.handle_get_operators(user, query)
            elif path == "/api/audit-logs":
                user = self.require_auth(query, perm_flag="can_view_audit", action="VIEW_AUDIT_LOGS", target_table="audit_logs")
                if user:
                    self.handle_get_audit_logs(user, query)
            elif path == "/api/metadata":
                user = self.require_auth(query)
                if user:
                    self.handle_get_metadata(user, query)
            elif path == "/api/export/sql":
                self.handle_export_sql()
            else:
                if path == "/" or not os.path.exists(os.path.join(STATIC_DIR, path.lstrip("/"))):
                    self.path = "/index.html"
                super().do_GET()
        except PermissionDenied as e:
            self.send_error_json(str(e), status=403)
        except Exception as e:
            traceback.print_exc()
            self.send_error_json(str(e), status=500)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        try:
            body = self.read_json_body()
            if path == "/api/auth/login":
                self.handle_login(body)
            elif path == "/api/companies":
                user = self.require_auth(perm_flag="can_manage_banks", action="CREATE_BANK", target_table="companies")
                if user:
                    self.handle_create_company(user, body)
            elif path == "/api/branches":
                user = self.require_auth(perm_flag="can_manage_staff", action="CREATE_BRANCH", target_table="branches")
                if user:
                    self.handle_create_branch(user, body)
            elif path == "/api/employees":
                user = self.require_auth(perm_flag="can_manage_staff", action="CREATE_EMPLOYEE", target_table="employees")
                if user:
                    self.handle_create_employee(user, body)
            elif path == "/api/operators":
                user = self.require_auth(perm_flag="can_manage_staff", action="CREATE_OPERATOR", target_table="operators")
                if user:
                    self.handle_create_operator(user, body)
            elif path == "/api/account-types":
                user = self.require_auth(perm_flag="can_manage_staff", action="CREATE_ACCOUNT_TYPE", target_table="account_types")
                if user:
                    self.handle_create_account_type(user, body)
            elif path == "/api/customers":
                user = self.require_auth(perm_flag="can_manage_customers", action="CREATE_CUSTOMER", target_table="customers")
                if user:
                    self.handle_create_customer(user, body)
            elif path == "/api/accounts":
                user = self.require_auth(perm_flag="can_manage_accounts", action="CREATE_ACCOUNT", target_table="accounts")
                if user:
                    self.handle_create_account(user, body)
            elif path == "/api/transact":
                user = self.require_auth(perm_flag="can_transact", action="TRANSACTION", target_table="transactions")
                if user:
                    self.handle_transaction_action(user, body)
            elif path == "/api/cards":
                user = self.require_auth(perm_flag="can_manage_cards", action="ISSUE_CARD", target_table="cards")
                if user:
                    self.handle_create_card(user, body)
            elif path == "/api/loans":
                user = self.require_auth(perm_flag="can_sanction_loans", action="SANCTION_LOAN", target_table="loans")
                if user:
                    self.handle_create_loan(user, body)
            elif path == "/api/loans/repay":
                user = self.require_auth(perm_flag="can_repay_loans", action="REPAY_LOAN", target_table="loans")
                if user:
                    self.handle_loan_repayment(user, body)
            elif path == "/api/sql":
                user = self.require_auth(perm_flag="can_run_sql_read", action="RUN_SQL", target_table="sql_studio")
                if user:
                    self.handle_run_sql(user, body)
            else:
                self.send_error_json("Endpoint not found", status=404)
        except PermissionDenied as e:
            self.send_error_json(str(e), status=403)
        except ValueError as e:
            self.send_error_json(str(e), status=400)
        except Exception as e:
            traceback.print_exc()
            self.send_error_json(str(e), status=500)

    def do_PUT(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        try:
            body = self.read_json_body()
            if path.startswith("/api/accounts/") and path.endswith("/status"):
                user = self.require_auth(perm_flag="can_freeze_accounts", action="UPDATE_ACCOUNT_STATUS", target_table="accounts")
                if user:
                    acc_no = path.split("/")[3]
                    self.handle_update_account_status(user, acc_no, body)
            elif path.startswith("/api/cards/") and path.endswith("/status"):
                user = self.require_auth(perm_flag="can_manage_cards", action="UPDATE_CARD_STATUS", target_table="cards")
                if user:
                    card_id = path.split("/")[3]
                    self.handle_update_card_status(user, card_id, body)
            elif path.startswith("/api/companies/") and path.endswith("/status"):
                user = self.require_auth(perm_flag="can_manage_banks", action="UPDATE_BANK_STATUS", target_table="companies")
                if user:
                    comp_code = path.split("/")[3]
                    self.handle_update_company_status(user, comp_code, body)
            elif path.startswith("/api/operators/") and path.endswith("/status"):
                user = self.require_auth(perm_flag="can_manage_staff", action="UPDATE_OPERATOR", target_table="operators")
                if user:
                    op_id = path.split("/")[3]
                    self.handle_update_operator_status(user, op_id, body)
            else:
                self.send_error_json("Endpoint not found", status=404)
        except PermissionDenied as e:
            self.send_error_json(str(e), status=403)
        except ValueError as e:
            self.send_error_json(str(e), status=400)
        except Exception as e:
            traceback.print_exc()
            self.send_error_json(str(e), status=500)

    # ---------------- AUTH & RBAC ---------------- #

    def _format_user_payload(self, user: dict) -> dict:
        perm_keys = [
            "can_manage_banks",
            "can_manage_staff",
            "can_manage_customers",
            "can_manage_accounts",
            "can_freeze_accounts",
            "can_transact",
            "can_manage_cards",
            "can_sanction_loans",
            "can_repay_loans",
            "can_run_sql_read",
            "can_run_sql_write",
            "can_view_audit",
        ]
        return {
            "operator_id": user["operator_id"],
            "employee_id": user["employee_id"],
            "username": user["username"],
            "full_name": user["full_name"],
            "role_code": user["role_code"],
            "role_name": user["role_name"],
            "role_description": user["role_description"],
            "hierarchy_level": user["hierarchy_level"],
            "company_code": user["company_code"],
            "company_name": user["company_name"] or "All Consortium Banks",
            "short_code": user["short_code"] or "ALL",
            "currency_symbol": user["currency_symbol"] or "₹",
            "currency_code": user["currency_code"] or "INR",
            "brand_color": user["brand_color"] or "#10b981",
            "branch_code": user["branch_code"],
            "branch_name": user["branch_name"],
            "is_global_scope": user["company_code"] is None,
            "permissions": {k: bool(user[k]) for k in perm_keys},
        }

    def handle_get_demo_accounts(self):
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT o.operator_id, o.username, o.full_name, o.role_code, o.company_code, o.branch_code,
                   r.role_name, r.hierarchy_level,
                   COALESCE(c.company_name, 'All Onboarded Banks') as company_name,
                   COALESCE(c.short_code, 'ALL') as short_code
            FROM operators o
            JOIN roles r ON o.role_code = r.role_code
            LEFT JOIN companies c ON o.company_code = c.company_code
            WHERE o.is_active = 1
            ORDER BY r.hierarchy_level DESC, o.operator_id ASC
            """
        )
        rows = []
        for r in cur.fetchall():
            d = dict(r)
            d["demo_password"] = DEMO_PASSWORDS.get(d["username"], "Bank@123")
            rows.append(d)
        conn.close()
        self.send_json({"success": True, "data": rows})

    def handle_login(self, body):
        username = (body.get("username") or "").strip()
        password = body.get("password") or ""
        if not username or not password:
            return self.send_error_json("Username and password are required")

        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT o.*, r.role_name, r.description as role_description, r.hierarchy_level,
                   r.can_manage_banks, r.can_manage_staff, r.can_manage_customers,
                   r.can_manage_accounts, r.can_freeze_accounts, r.can_transact,
                   r.can_manage_cards, r.can_sanction_loans, r.can_repay_loans,
                   r.can_run_sql_read, r.can_run_sql_write, r.can_view_audit,
                   c.company_name, c.short_code, c.currency_symbol, c.currency_code, c.brand_color,
                   b.branch_name
            FROM operators o
            JOIN roles r ON o.role_code = r.role_code
            LEFT JOIN companies c ON o.company_code = c.company_code
            LEFT JOIN branches b ON o.branch_code = b.branch_code
            WHERE o.username = ?
            """,
            (username,),
        )
        row = cur.fetchone()
        if not row:
            log_audit(conn, None, None, "LOGIN_FAILED", "operators", username, "DENIED", f"Unknown username '{username}'")
            conn.close()
            return self.send_error_json("Invalid username or password", status=401)

        user = dict(row)
        if not user["is_active"]:
            log_audit(conn, user, user["company_code"], "LOGIN_BLOCKED", "operators", user["operator_id"], "DENIED", "Account disabled")
            conn.close()
            return self.send_error_json("Operator account is disabled", status=403)

        if not db_setup.verify_password(password, user["password_hash"]):
            log_audit(conn, user, user["company_code"], "LOGIN_FAILED", "operators", user["operator_id"], "DENIED", "Wrong password")
            conn.close()
            return self.send_error_json("Invalid username or password", status=401)

        cur.execute("UPDATE operators SET last_login = CURRENT_TIMESTAMP WHERE operator_id = ?", (user["operator_id"],))
        log_audit(
            conn,
            user,
            user["company_code"],
            "OPERATOR_LOGIN",
            "operators",
            user["operator_id"],
            "SUCCESS",
            f"Signed in as {user['role_name']} ({user['company_code'] or 'ALL'})",
        )
        conn.close()

        token = sign_token(user["operator_id"], user["username"], user["role_code"])
        self.send_json(
            {
                "success": True,
                "token": token,
                "user": self._format_user_payload(user),
            }
        )

    def handle_get_roles(self):
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM roles ORDER BY hierarchy_level DESC")
        roles = [dict(r) for r in cur.fetchall()]
        conn.close()
        self.send_json({"success": True, "data": roles})

    # ---------------- MULTI-BANK (COMPANIES) ---------------- #

    def handle_get_companies(self, user: dict):
        conn = get_db()
        cur = conn.cursor()
        sql = """
            SELECT comp.*,
                   (SELECT COUNT(*) FROM branches b WHERE b.company_code = comp.company_code) as branch_count,
                   (SELECT COUNT(*) FROM employees e WHERE e.company_code = comp.company_code) as employee_count,
                   (SELECT COUNT(*) FROM customers cu WHERE cu.company_code = comp.company_code) as customer_count,
                   (SELECT COUNT(*) FROM accounts a WHERE a.company_code = comp.company_code AND a.status = 'active') as active_accounts,
                   (SELECT COALESCE(SUM(a.balance), 0) FROM accounts a WHERE a.company_code = comp.company_code AND a.status = 'active') as total_deposits,
                   (SELECT COALESCE(SUM(l.outstanding_balance), 0) FROM loans l WHERE l.company_code = comp.company_code AND l.status = 'running') as outstanding_loans
            FROM companies comp
        """
        params = []
        if user.get("company_code"):
            sql += " WHERE comp.company_code = ?"
            params.append(user["company_code"])
        sql += " ORDER BY comp.company_code ASC"
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        self.send_json({"success": True, "data": rows})

    def handle_create_company(self, user: dict, body: dict):
        company_name = (body.get("company_name") or "").strip()
        short_code = (body.get("short_code") or "").strip().upper()[:10]
        swift_code = (body.get("swift_code") or "").strip().upper()
        currency_code = (body.get("currency_code") or "INR").strip().upper()
        currency_symbol = (body.get("currency_symbol") or "₹").strip()
        brand_color = (body.get("brand_color") or "#10b981").strip()
        hq_address = (body.get("headquarters_address") or "").strip()
        phone = (body.get("phone") or "").strip()
        established_date = body.get("established_date") or datetime.date.today().isoformat()
        total_assets = float(body.get("total_assets") or 1000000000.0)

        if not company_name or not short_code:
            return self.send_error_json("company_name and short_code are required")

        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute("BEGIN TRANSACTION")
            comp_code = (body.get("company_code") or "").strip().upper()
            if not comp_code:
                comp_code = generate_next_id(cur, "companies", "company_code", "COMP", 1, 3)

            cur.execute(
                """
                INSERT INTO companies (
                    company_code, company_name, short_code, swift_code,
                    currency_code, currency_symbol, brand_color,
                    headquarters_address, phone, established_date, total_assets, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
                """,
                (
                    comp_code,
                    company_name,
                    short_code,
                    swift_code or f"{short_code}INBBXXX",
                    currency_code,
                    currency_symbol,
                    brand_color,
                    hq_address,
                    phone,
                    established_date,
                    total_assets,
                ),
            )

            created_branch = None
            created_operator = None

            # Optional: auto-provision initial branch + Bank Admin operator
            branch_name = (body.get("initial_branch_name") or "").strip()
            admin_username = (body.get("admin_username") or "").strip()
            admin_password = body.get("admin_password") or "Bank@123"
            admin_name = (body.get("admin_full_name") or f"{short_code} Administrator").strip()

            if branch_name or admin_username:
                br_code = generate_next_id(cur, "branches", "branch_code", "BR", 1, 3)
                cur.execute(
                    """
                    INSERT INTO branches (branch_code, company_code, branch_name, address, phone, manager_name, opening_hours, closing_hours)
                    VALUES (?, ?, ?, ?, ?, ?, '09:30:00', '16:30:00')
                    """,
                    (br_code, comp_code, branch_name or f"{short_code} Headquarters", hq_address or "Main HQ", phone or "+91-00-00000000", admin_name),
                )
                created_branch = br_code

                if admin_username:
                    name_parts = admin_name.split(" ", 1)
                    fn = name_parts[0]
                    ln = name_parts[1] if len(name_parts) > 1 else "Admin"
                    emp_id = generate_next_id(cur, "employees", "employee_id", "EMP", 1, 3)
                    cur.execute(
                        """
                        INSERT INTO employees (employee_id, company_code, branch_code, first_name, last_name, email, phone, position, salary, hire_date, department)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 'Bank Administrator', 150000.00, ?, 'Administration')
                        """,
                        (emp_id, comp_code, br_code, fn, ln, f"{admin_username}@{short_code.lower()}.bank", None, datetime.date.today().isoformat()),
                    )
                    op_id = generate_next_id(cur, "operators", "operator_id", "OP", 1, 3)
                    cur.execute(
                        """
                        INSERT INTO operators (operator_id, employee_id, company_code, branch_code, username, password_hash, full_name, role_code, is_active)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 'BANK_ADMIN', 1)
                        """,
                        (op_id, emp_id, comp_code, br_code, admin_username, db_setup.hash_password(admin_password), admin_name),
                    )
                    created_operator = admin_username

            log_audit(
                conn,
                user,
                comp_code,
                "CREATE_BANK",
                "companies",
                comp_code,
                "SUCCESS",
                f"Onboarded bank '{company_name}' ({short_code}, {currency_code}); branch={created_branch}, admin={created_operator}",
            )
            conn.close()
            self.send_json(
                {
                    "success": True,
                    "company_code": comp_code,
                    "branch_code": created_branch,
                    "admin_username": created_operator,
                    "message": f"Bank '{company_name}' ({comp_code}) onboarded successfully.",
                }
            )
        except Exception as e:
            conn.rollback()
            conn.close()
            self.send_error_json(str(e))

    def handle_update_company_status(self, user: dict, comp_code: str, body: dict):
        status = body.get("status")
        if status not in ("active", "inactive"):
            return self.send_error_json("Status must be 'active' or 'inactive'")
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE companies SET status = ? WHERE company_code = ?", (status, comp_code))
        if cur.rowcount == 0:
            conn.close()
            return self.send_error_json("Bank not found", status=404)
        log_audit(conn, user, comp_code, "UPDATE_BANK_STATUS", "companies", comp_code, "SUCCESS", f"Set status to {status}")
        conn.close()
        self.send_json({"success": True, "message": f"Bank {comp_code} set to {status}"})

    # ---------------- DASHBOARD ---------------- #

    def handle_dashboard_stats(self, user: dict, query: dict):
        scope_comp = self.resolve_company_scope(user, query)
        conn = get_db()
        cur = conn.cursor()

        comp_filter = " WHERE company_code = ?" if scope_comp else ""
        comp_params = [scope_comp] if scope_comp else []

        cur.execute(f"SELECT COUNT(*) FROM customers{comp_filter}", comp_params)
        total_customers = cur.fetchone()[0]

        if scope_comp:
            cur.execute(
                "SELECT COUNT(*), COALESCE(SUM(balance), 0) FROM accounts WHERE status = 'active' AND company_code = ?",
                (scope_comp,),
            )
        else:
            cur.execute("SELECT COUNT(*), COALESCE(SUM(balance), 0) FROM accounts WHERE status = 'active'")
        active_accounts, total_balance = cur.fetchone()

        if scope_comp:
            cur.execute(
                "SELECT COUNT(*), COALESCE(SUM(outstanding_balance), 0) FROM loans WHERE status = 'running' AND company_code = ?",
                (scope_comp,),
            )
        else:
            cur.execute("SELECT COUNT(*), COALESCE(SUM(outstanding_balance), 0) FROM loans WHERE status = 'running'")
        active_loans, outstanding_loans = cur.fetchone()

        if scope_comp:
            cur.execute("SELECT COUNT(*) FROM cards WHERE status = 'active' AND company_code = ?", (scope_comp,))
        else:
            cur.execute("SELECT COUNT(*) FROM cards WHERE status = 'active'")
        active_cards = cur.fetchone()[0]

        cur.execute(f"SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM transactions{comp_filter}", comp_params)
        total_transactions, total_txn_volume = cur.fetchone()

        cur.execute(f"SELECT COUNT(*) FROM branches{comp_filter}", comp_params)
        total_branches = cur.fetchone()[0]

        # Active company metadata
        company_info = {
            "company_code": "ALL",
            "company_name": "Multi-Bank Consortium",
            "short_code": "ALL",
            "currency_code": "INR",
            "currency_symbol": "₹",
            "brand_color": "#10b981",
        }
        if scope_comp:
            cur.execute("SELECT * FROM companies WHERE company_code = ?", (scope_comp,))
            crow = cur.fetchone()
            if crow:
                company_info = dict(crow)

        # Account Types Distribution
        if scope_comp:
            cur.execute(
                """
                SELECT at.type_name, COUNT(a.account_number) as count, COALESCE(SUM(a.balance), 0) as total_balance
                FROM account_types at
                LEFT JOIN accounts a ON at.account_type_code = a.account_type_code AND a.company_code = ?
                WHERE at.company_code IS NULL OR at.company_code = ?
                GROUP BY at.account_type_code, at.type_name
                """,
                (scope_comp, scope_comp),
            )
        else:
            cur.execute(
                """
                SELECT at.type_name, COUNT(a.account_number) as count, COALESCE(SUM(a.balance), 0) as total_balance
                FROM account_types at
                LEFT JOIN accounts a ON at.account_type_code = a.account_type_code
                GROUP BY at.account_type_code, at.type_name
                """
            )
        account_dist = [dict(row) for row in cur.fetchall()]

        # Recent 8 transactions with operator attribution
        txn_sql = """
            SELECT t.transaction_reference, t.account_number, t.category_code, t.transaction_type,
                   t.amount, t.description, t.transaction_date, t.running_balance,
                   c.first_name || ' ' || c.last_name as customer_name,
                   tc.category_name,
                   COALESCE(op.username, 'system') as performed_by,
                   comp.short_code as bank_short_code,
                   COALESCE(comp.currency_symbol, '₹') as currency_symbol
            FROM transactions t
            JOIN accounts a ON t.account_number = a.account_number
            JOIN customers c ON a.customer_id = c.customer_id
            LEFT JOIN transaction_categories tc ON t.category_code = tc.category_code
            LEFT JOIN operators op ON t.performed_by_operator_id = op.operator_id
            LEFT JOIN companies comp ON t.company_code = comp.company_code
        """
        if scope_comp:
            txn_sql += " WHERE t.company_code = ?"
        txn_sql += " ORDER BY t.transaction_date DESC, t.created_at DESC LIMIT 8"
        cur.execute(txn_sql, comp_params)
        recent_txns = [dict(row) for row in cur.fetchall()]

        # Branch overview
        br_sql = """
            SELECT b.branch_name, b.branch_code, comp.short_code as bank_short_code,
                   COUNT(DISTINCT e.employee_id) as employee_count,
                   (SELECT COUNT(a.account_number) FROM accounts a
                    WHERE a.branch_code = b.branch_code) as customer_accounts_managed
            FROM branches b
            JOIN companies comp ON b.company_code = comp.company_code
            LEFT JOIN employees e ON b.branch_code = e.branch_code
        """
        if scope_comp:
            br_sql += " WHERE b.company_code = ?"
        br_sql += " GROUP BY b.branch_code ORDER BY b.branch_code ASC"
        cur.execute(br_sql, comp_params)
        branch_stats = [dict(row) for row in cur.fetchall()]

        conn.close()
        self.send_json(
            {
                "success": True,
                "data": {
                    "company_info": company_info,
                    "total_branches": total_branches,
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
                    "branch_stats": branch_stats,
                },
            }
        )

    # ---------------- CUSTOMERS ---------------- #

    def handle_get_customers(self, user: dict, query: dict):
        scope_comp = self.resolve_company_scope(user, query)
        search = query.get("q", [""])[0].strip()

        conn = get_db()
        cur = conn.cursor()
        sql = """
            SELECT c.*,
                   comp.short_code as bank_short_code,
                   comp.company_name,
                   COALESCE(comp.currency_symbol, '₹') as currency_symbol,
                   b.branch_name,
                   e.first_name || ' ' || e.last_name as rm_name,
                   COUNT(DISTINCT a.account_number) as accounts_count,
                   COALESCE(SUM(a.balance), 0) as total_customer_balance,
                   COUNT(DISTINCT l.loan_number) as loans_count,
                   COUNT(DISTINCT cd.card_id) as cards_count
            FROM customers c
            LEFT JOIN companies comp ON c.company_code = comp.company_code
            LEFT JOIN branches b ON c.branch_code = b.branch_code
            LEFT JOIN employees e ON c.relationship_manager_id = e.employee_id
            LEFT JOIN accounts a ON c.customer_id = a.customer_id
            LEFT JOIN loans l ON c.customer_id = l.customer_id AND l.status = 'running'
            LEFT JOIN cards cd ON c.customer_id = cd.customer_id
            WHERE 1=1
        """
        params = []
        if scope_comp:
            sql += " AND c.company_code = ?"
            params.append(scope_comp)
        if search:
            sql += """
                AND (c.customer_id LIKE ? OR c.first_name LIKE ? OR c.last_name LIKE ?
                     OR c.email LIKE ? OR c.phone LIKE ?)
            """
            wildcard = f"%{search}%"
            params.extend([wildcard, wildcard, wildcard, wildcard, wildcard])

        sql += " GROUP BY c.customer_id ORDER BY c.customer_id DESC"
        cur.execute(sql, params)
        customers = [dict(row) for row in cur.fetchall()]
        conn.close()
        self.send_json({"success": True, "data": customers})

    def handle_get_customer_detail(self, user: dict, cust_id: str):
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT c.*, e.first_name || ' ' || e.last_name as rm_name, e.email as rm_email,
                   COALESCE(b.branch_name, cb.branch_name) as branch_name,
                   comp.company_name, comp.short_code as bank_short_code,
                   COALESCE(comp.currency_symbol, '₹') as currency_symbol
            FROM customers c
            LEFT JOIN employees e ON c.relationship_manager_id = e.employee_id
            LEFT JOIN branches b ON e.branch_code = b.branch_code
            LEFT JOIN branches cb ON c.branch_code = cb.branch_code
            LEFT JOIN companies comp ON c.company_code = comp.company_code
            WHERE c.customer_id = ?
            """,
            (cust_id,),
        )
        cust = cur.fetchone()
        if not cust:
            conn.close()
            return self.send_error_json("Customer not found", status=404)

        customer_data = dict(cust)
        if user.get("company_code") and customer_data["company_code"] != user["company_code"]:
            log_audit(conn, user, user["company_code"], "CROSS_BANK_READ", "customers", cust_id, "DENIED", "Cross-tenant customer dossier read")
            conn.close()
            return self.send_error_json("Access denied: customer belongs to another bank", status=403)

        cur.execute(
            """
            SELECT a.*, at.type_name, at.interest_rate, at.allows_overdraft
            FROM accounts a
            JOIN account_types at ON a.account_type_code = at.account_type_code
            WHERE a.customer_id = ?
            """,
            (cust_id,),
        )
        customer_data["accounts"] = [dict(row) for row in cur.fetchall()]

        cur.execute("SELECT * FROM cards WHERE customer_id = ?", (cust_id,))
        customer_data["cards"] = [dict(row) for row in cur.fetchall()]

        cur.execute("SELECT * FROM loans WHERE customer_id = ?", (cust_id,))
        customer_data["loans"] = [dict(row) for row in cur.fetchall()]

        cur.execute(
            """
            SELECT t.*, tc.category_name
            FROM transactions t
            JOIN accounts a ON t.account_number = a.account_number
            LEFT JOIN transaction_categories tc ON t.category_code = tc.category_code
            WHERE a.customer_id = ?
            ORDER BY t.transaction_date DESC
            LIMIT 15
            """,
            (cust_id,),
        )
        customer_data["transactions"] = [dict(row) for row in cur.fetchall()]

        conn.close()
        self.send_json({"success": True, "data": customer_data})

    def handle_create_customer(self, user: dict, body: dict):
        scope_comp = self.resolve_company_scope(user, requested_company=body.get("company_code"), require_single_for_write=False)

        first_name = (body.get("first_name") or "").strip()
        last_name = (body.get("last_name") or "").strip()
        email = (body.get("email") or "").strip()
        phone = (body.get("phone") or "").strip()
        address = (body.get("address") or "").strip()
        dob = body.get("date_of_birth") or ""
        id_number = (body.get("id_number") or "").strip()
        credit_score = float(body.get("credit_score") or 700)
        rm_id = body.get("relationship_manager_id") or None
        reg_date = body.get("registration_date") or datetime.date.today().isoformat()

        if not first_name or not last_name or not email or not dob:
            return self.send_error_json("first_name, last_name, email, and date_of_birth are required")

        conn = get_db()
        cur = conn.cursor()

        branch_code = (body.get("branch_code") or "").strip() or None
        if rm_id:
            cur.execute("SELECT employee_id, company_code, branch_code FROM employees WHERE employee_id = ?", (rm_id,))
            rm_row = cur.fetchone()
            if not rm_row:
                conn.close()
                return self.send_error_json("Assigned relationship manager not found")
            if scope_comp and rm_row["company_code"] != scope_comp:
                conn.close()
                return self.send_error_json(f"Relationship manager {rm_id} does not belong to {scope_comp}", status=403)
            scope_comp = scope_comp or rm_row["company_code"]
            branch_code = branch_code or rm_row["branch_code"]

        if not scope_comp:
            conn.close()
            return self.send_error_json("Please select a target bank before registering a customer.")

        if not branch_code:
            cur.execute("SELECT branch_code FROM branches WHERE company_code = ? ORDER BY branch_code LIMIT 1", (scope_comp,))
            br = cur.fetchone()
            branch_code = br["branch_code"] if br else None

        new_id = generate_next_id(cur, "customers", "customer_id", "CUST", 1, 3)

        cur.execute(
            """
            INSERT INTO customers (
                customer_id, company_code, branch_code, relationship_manager_id, created_by_operator_id,
                first_name, last_name, email, phone, address, date_of_birth, id_number, credit_score, registration_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id,
                scope_comp,
                branch_code,
                rm_id,
                user["operator_id"],
                first_name,
                last_name,
                email,
                phone or None,
                address,
                dob,
                id_number or None,
                credit_score,
                reg_date,
            ),
        )

        log_audit(
            conn,
            user,
            scope_comp,
            "CREATE_CUSTOMER",
            "customers",
            new_id,
            "SUCCESS",
            f"Registered {first_name} {last_name} under {scope_comp}",
        )
        conn.close()
        self.send_json({"success": True, "customer_id": new_id, "message": f"Customer {new_id} created under {scope_comp}"})

    # ---------------- ACCOUNTS & PRODUCTS ---------------- #

    def handle_get_account_types(self, user: dict, query: dict):
        scope_comp = self.resolve_company_scope(user, query)
        conn = get_db()
        cur = conn.cursor()
        if scope_comp:
            cur.execute(
                """
                SELECT at.*, COALESCE(c.short_code, 'GLOBAL') as scope_label
                FROM account_types at
                LEFT JOIN companies c ON at.company_code = c.company_code
                WHERE at.company_code IS NULL OR at.company_code = ?
                ORDER BY at.company_code IS NULL DESC, at.account_type_code ASC
                """,
                (scope_comp,),
            )
        else:
            cur.execute(
                """
                SELECT at.*, COALESCE(c.short_code, 'GLOBAL') as scope_label
                FROM account_types at
                LEFT JOIN companies c ON at.company_code = c.company_code
                ORDER BY at.company_code IS NULL DESC, at.account_type_code ASC
                """
            )
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        self.send_json({"success": True, "data": rows})

    def handle_create_account_type(self, user: dict, body: dict):
        scope_comp = self.resolve_company_scope(user, requested_company=body.get("company_code"), require_single_for_write=False)
        code = (body.get("account_type_code") or "").strip().upper()
        type_name = (body.get("type_name") or "").strip()
        description = (body.get("description") or "").strip()
        min_bal = float(body.get("minimum_balance") or 0.0)
        interest_rate = float(body.get("interest_rate") or 0.0)
        allows_overdraft = 1 if body.get("allows_overdraft") else 0

        if not code or not type_name:
            return self.send_error_json("account_type_code and type_name are required")

        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO account_types (account_type_code, company_code, type_name, description, minimum_balance, interest_rate, allows_overdraft)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (code, scope_comp, type_name, description, min_bal, interest_rate, allows_overdraft),
        )
        log_audit(
            conn,
            user,
            scope_comp,
            "CREATE_ACCOUNT_TYPE",
            "account_types",
            code,
            "SUCCESS",
            f"Added account product '{type_name}' ({code}) for {scope_comp or 'ALL'}",
        )
        conn.close()
        self.send_json({"success": True, "account_type_code": code, "message": f"Account product {type_name} created"})

    def handle_get_accounts(self, user: dict, query: dict):
        scope_comp = self.resolve_company_scope(user, query)
        search = query.get("q", [""])[0].strip()

        conn = get_db()
        cur = conn.cursor()
        sql = """
            SELECT a.*, at.type_name, at.interest_rate,
                   c.first_name || ' ' || c.last_name as customer_name,
                   c.email as customer_email,
                   comp.short_code as bank_short_code,
                   COALESCE(comp.currency_symbol, '₹') as currency_symbol,
                   b.branch_name,
                   (SELECT COUNT(*) FROM cards cd WHERE cd.linked_account_number = a.account_number) as linked_cards_count
            FROM accounts a
            JOIN customers c ON a.customer_id = c.customer_id
            JOIN account_types at ON a.account_type_code = at.account_type_code
            LEFT JOIN companies comp ON a.company_code = comp.company_code
            LEFT JOIN branches b ON a.branch_code = b.branch_code
            WHERE 1=1
        """
        params = []
        if scope_comp:
            sql += " AND a.company_code = ?"
            params.append(scope_comp)
        if search:
            sql += " AND (a.account_number LIKE ? OR c.first_name LIKE ? OR c.last_name LIKE ?)"
            w = f"%{search}%"
            params.extend([w, w, w])

        sql += " ORDER BY a.created_at DESC, a.account_number DESC"
        cur.execute(sql, params)
        accounts = [dict(row) for row in cur.fetchall()]
        conn.close()
        self.send_json({"success": True, "data": accounts})

    def handle_create_account(self, user: dict, body: dict):
        scope_comp = self.resolve_company_scope(user, requested_company=body.get("company_code"), require_single_for_write=False)

        customer_id = body.get("customer_id")
        account_type_code = body.get("account_type_code")
        initial_balance = float(body.get("initial_deposit") or 0.0)
        overdraft_limit = float(body.get("overdraft_limit") or 0.0)
        opening_date = datetime.date.today().isoformat()

        if not customer_id or not account_type_code:
            return self.send_error_json("customer_id and account_type_code are required")
        if initial_balance < 0:
            return self.send_error_json("Initial deposit cannot be negative")

        conn = get_db()
        cur = conn.cursor()

        cur.execute("SELECT customer_id, company_code, branch_code FROM customers WHERE customer_id = ?", (customer_id,))
        cust = cur.fetchone()
        if not cust:
            conn.close()
            return self.send_error_json("Customer not found", status=404)

        cust_comp = cust["company_code"]
        if scope_comp and cust_comp != scope_comp:
            log_audit(conn, user, scope_comp, "CREATE_ACCOUNT", "accounts", customer_id, "DENIED", f"Cross-bank customer {customer_id}")
            conn.close()
            return self.send_error_json(f"Access denied: customer belongs to {cust_comp}", status=403)

        cur.execute("SELECT account_type_code, company_code FROM account_types WHERE account_type_code = ?", (account_type_code,))
        atype = cur.fetchone()
        if not atype:
            conn.close()
            return self.send_error_json("Invalid account_type_code")
        if atype["company_code"] and atype["company_code"] != cust_comp:
            conn.close()
            return self.send_error_json(f"Account product {account_type_code} is exclusive to {atype['company_code']}")

        new_acc = generate_next_id(cur, "accounts", "account_number", "ACC", 100001, 6)
        branch_code = body.get("branch_code") or cust["branch_code"]

        cur.execute(
            """
            INSERT INTO accounts (
                account_number, company_code, branch_code, customer_id, account_type_code,
                opened_by_operator_id, balance, opening_date, status, overdraft_limit
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
            """,
            (new_acc, cust_comp, branch_code, customer_id, account_type_code, user["operator_id"], initial_balance, opening_date, overdraft_limit),
        )

        if initial_balance > 0:
            txn_ref = generate_next_id(cur, "transactions", "transaction_reference", "TXN", 100001, 6)
            cur.execute(
                """
                INSERT INTO transactions (
                    transaction_reference, company_code, account_number, category_code,
                    performed_by_operator_id, transaction_type, amount, description, transaction_date, running_balance
                ) VALUES (?, ?, ?, 'CAT006', ?, 'credit', ?, 'Account Opening Initial Deposit', datetime('now'), ?)
                """,
                (txn_ref, cust_comp, new_acc, user["operator_id"], initial_balance, initial_balance),
            )

        log_audit(
            conn,
            user,
            cust_comp,
            "CREATE_ACCOUNT",
            "accounts",
            new_acc,
            "SUCCESS",
            f"Opened {account_type_code} account {new_acc} for {customer_id} (bal={initial_balance})",
        )
        conn.close()
        self.send_json({"success": True, "account_number": new_acc, "message": f"Account {new_acc} opened successfully"})

    def handle_update_account_status(self, user: dict, acc_no: str, body: dict):
        new_status = body.get("status")
        if new_status not in ("active", "closed", "frozen"):
            return self.send_error_json("Invalid status. Must be active, closed, or frozen")

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT account_number, company_code, status FROM accounts WHERE account_number = ?", (acc_no,))
        acc = cur.fetchone()
        if not acc:
            conn.close()
            return self.send_error_json("Account not found", status=404)

        if user.get("company_code") and acc["company_code"] != user["company_code"]:
            log_audit(conn, user, user["company_code"], "UPDATE_ACCOUNT_STATUS", "accounts", acc_no, "DENIED", "Cross-bank account modification")
            conn.close()
            return self.send_error_json("Access denied: account belongs to another bank", status=403)

        cur.execute("UPDATE accounts SET status = ? WHERE account_number = ?", (new_status, acc_no))
        log_audit(
            conn,
            user,
            acc["company_code"],
            "UPDATE_ACCOUNT_STATUS",
            "accounts",
            acc_no,
            "SUCCESS",
            f"Changed status {acc['status']} -> {new_status}",
        )
        conn.close()
        self.send_json({"success": True, "message": f"Account {acc_no} status updated to {new_status}"})

    # ---------------- TRANSACTIONS ---------------- #

    def handle_transaction_action(self, user: dict, body: dict):
        action = body.get("action")
        amount = float(body.get("amount") or 0)
        if amount <= 0:
            return self.send_error_json("Amount must be greater than zero")

        conn = get_db()
        cur = conn.cursor()

        try:
            cur.execute("BEGIN TRANSACTION")

            if action == "deposit":
                acc_no = body.get("account_number")
                cur.execute(
                    """
                    SELECT a.balance, a.status, a.company_code, COALESCE(c.currency_symbol, '₹') as sym
                    FROM accounts a LEFT JOIN companies c ON a.company_code = c.company_code
                    WHERE a.account_number = ?
                    """,
                    (acc_no,),
                )
                row = cur.fetchone()
                if not row:
                    raise ValueError(f"Account {acc_no} not found")
                if user.get("company_code") and row["company_code"] != user["company_code"]:
                    raise PermissionDenied(f"Cross-bank deposit denied on {acc_no}")
                if row["status"] != "active":
                    raise ValueError(f"Cannot deposit: Account is {row['status']}")

                new_balance = round(row["balance"] + amount, 2)
                cur.execute("UPDATE accounts SET balance = ? WHERE account_number = ?", (new_balance, acc_no))

                txn_ref = generate_next_id(cur, "transactions", "transaction_reference", "TXN", 100001, 6)
                cat_code = body.get("category_code") or "CAT006"
                desc = body.get("description") or "Cash/Cheque Deposit"
                cur.execute(
                    """
                    INSERT INTO transactions (
                        transaction_reference, company_code, account_number, category_code,
                        performed_by_operator_id, transaction_type, amount, description, transaction_date, running_balance
                    ) VALUES (?, ?, ?, ?, ?, 'credit', ?, ?, datetime('now'), ?)
                    """,
                    (txn_ref, row["company_code"], acc_no, cat_code, user["operator_id"], amount, desc, new_balance),
                )
                log_audit(conn, user, row["company_code"], "DEPOSIT", "transactions", txn_ref, "SUCCESS", f"+{row['sym']}{amount:,.2f} to {acc_no}")
                conn.close()
                return self.send_json({"success": True, "transaction_reference": txn_ref, "new_balance": new_balance, "message": "Deposit completed successfully"})

            elif action == "withdraw":
                acc_no = body.get("account_number")
                cur.execute(
                    """
                    SELECT a.balance, a.status, a.overdraft_limit, a.company_code, COALESCE(c.currency_symbol, '₹') as sym
                    FROM accounts a LEFT JOIN companies c ON a.company_code = c.company_code
                    WHERE a.account_number = ?
                    """,
                    (acc_no,),
                )
                row = cur.fetchone()
                if not row:
                    raise ValueError(f"Account {acc_no} not found")
                if user.get("company_code") and row["company_code"] != user["company_code"]:
                    raise PermissionDenied(f"Cross-bank withdrawal denied on {acc_no}")
                if row["status"] != "active":
                    raise ValueError(f"Cannot withdraw: Account is {row['status']}")

                max_available = row["balance"] + row["overdraft_limit"]
                if amount > max_available:
                    raise ValueError(f"Insufficient funds: Available balance including overdraft is {row['sym']}{max_available:,.2f}")

                new_balance = round(row["balance"] - amount, 2)
                cur.execute("UPDATE accounts SET balance = ? WHERE account_number = ?", (new_balance, acc_no))

                txn_ref = generate_next_id(cur, "transactions", "transaction_reference", "TXN", 100001, 6)
                cat_code = body.get("category_code") or "CAT002"
                desc = body.get("description") or "Cash Withdrawal"
                cur.execute(
                    """
                    INSERT INTO transactions (
                        transaction_reference, company_code, account_number, category_code,
                        performed_by_operator_id, transaction_type, amount, description, transaction_date, running_balance
                    ) VALUES (?, ?, ?, ?, ?, 'debit', ?, ?, datetime('now'), ?)
                    """,
                    (txn_ref, row["company_code"], acc_no, cat_code, user["operator_id"], amount, desc, new_balance),
                )
                log_audit(conn, user, row["company_code"], "WITHDRAW", "transactions", txn_ref, "SUCCESS", f"-{row['sym']}{amount:,.2f} from {acc_no}")
                conn.close()
                return self.send_json({"success": True, "transaction_reference": txn_ref, "new_balance": new_balance, "message": "Withdrawal completed successfully"})

            elif action == "transfer":
                src_acc = body.get("from_account")
                dst_acc = body.get("to_account")

                if src_acc == dst_acc:
                    raise ValueError("Source and destination accounts cannot be identical")

                cur.execute(
                    """
                    SELECT a.balance, a.status, a.overdraft_limit, a.company_code,
                           COALESCE(c.currency_code, 'INR') as currency_code,
                           COALESCE(c.currency_symbol, '₹') as sym
                    FROM accounts a LEFT JOIN companies c ON a.company_code = c.company_code
                    WHERE a.account_number = ?
                    """,
                    (src_acc,),
                )
                src = cur.fetchone()
                if not src:
                    raise ValueError(f"Source account {src_acc} not found")
                if user.get("company_code") and src["company_code"] != user["company_code"]:
                    raise PermissionDenied(f"Cross-bank debit denied from {src_acc}")
                if src["status"] != "active":
                    raise ValueError(f"Source account {src_acc} is {src['status']}")
                if amount > (src["balance"] + src["overdraft_limit"]):
                    raise ValueError(f"Insufficient funds in source account {src_acc}")

                cur.execute(
                    """
                    SELECT a.balance, a.status, a.company_code,
                           COALESCE(c.currency_code, 'INR') as currency_code
                    FROM accounts a LEFT JOIN companies c ON a.company_code = c.company_code
                    WHERE a.account_number = ?
                    """,
                    (dst_acc,),
                )
                dst = cur.fetchone()
                if not dst:
                    raise ValueError(f"Destination account {dst_acc} not found")
                if dst["status"] != "active":
                    raise ValueError(f"Destination account {dst_acc} is {dst['status']}")
                if src["currency_code"] != dst["currency_code"]:
                    raise ValueError(
                        f"Cross-currency inter-bank transfer ({src['currency_code']} -> {dst['currency_code']}) requires FX settlement"
                    )

                src_new_bal = round(src["balance"] - amount, 2)
                dst_new_bal = round(dst["balance"] + amount, 2)

                cur.execute("UPDATE accounts SET balance = ? WHERE account_number = ?", (src_new_bal, src_acc))
                cur.execute("UPDATE accounts SET balance = ? WHERE account_number = ?", (dst_new_bal, dst_acc))

                remarks = body.get("description") or "Fund Transfer"
                ref1 = generate_next_id(cur, "transactions", "transaction_reference", "TXN", 100001, 6)
                cur.execute(
                    """
                    INSERT INTO transactions (
                        transaction_reference, company_code, account_number, category_code,
                        performed_by_operator_id, transaction_type, amount, description, transaction_date, running_balance
                    ) VALUES (?, ?, ?, 'CAT003', ?, 'debit', ?, ?, datetime('now'), ?)
                    """,
                    (ref1, src["company_code"], src_acc, user["operator_id"], amount, f"Transfer to {dst_acc}: {remarks}", src_new_bal),
                )

                ref2 = generate_next_id(cur, "transactions", "transaction_reference", "TXN", 100001, 6)
                cur.execute(
                    """
                    INSERT INTO transactions (
                        transaction_reference, company_code, account_number, category_code,
                        performed_by_operator_id, transaction_type, amount, description, transaction_date, running_balance
                    ) VALUES (?, ?, ?, 'CAT003', ?, 'credit', ?, ?, datetime('now'), ?)
                    """,
                    (ref2, dst["company_code"], dst_acc, user["operator_id"], amount, f"Transfer from {src_acc}: {remarks}", dst_new_bal),
                )

                interbank_note = " (Inter-Bank)" if src["company_code"] != dst["company_code"] else ""
                log_audit(
                    conn,
                    user,
                    src["company_code"],
                    "TRANSFER",
                    "transactions",
                    f"{ref1}/{ref2}",
                    "SUCCESS",
                    f"{src['sym']}{amount:,.2f} {src_acc} -> {dst_acc}{interbank_note}",
                )
                conn.close()
                return self.send_json(
                    {
                        "success": True,
                        "debit_reference": ref1,
                        "credit_reference": ref2,
                        "from_balance": src_new_bal,
                        "to_balance": dst_new_bal,
                        "message": f"Transferred {src['sym']}{amount:,.2f} from {src_acc} to {dst_acc}{interbank_note}",
                    }
                )
            else:
                raise ValueError("Invalid action. Must be deposit, withdraw, or transfer")

        except PermissionDenied as e:
            conn.rollback()
            log_audit(conn, user, user.get("company_code"), "TRANSACTION_DENIED", "transactions", None, "DENIED", str(e))
            conn.close()
            return self.send_error_json(str(e), status=403)
        except Exception as e:
            conn.rollback()
            conn.close()
            return self.send_error_json(str(e))

    def handle_get_transactions(self, user: dict, query: dict):
        scope_comp = self.resolve_company_scope(user, query)
        acc = query.get("account_number", [""])[0].strip()
        txn_type = query.get("type", [""])[0].strip()
        cat = query.get("category", [""])[0].strip()

        conn = get_db()
        cur = conn.cursor()
        sql = """
            SELECT t.*, tc.category_name,
                   c.first_name || ' ' || c.last_name as customer_name, a.customer_id,
                   COALESCE(op.username, 'system') as performed_by,
                   COALESCE(op.role_code, '-') as operator_role,
                   comp.short_code as bank_short_code,
                   COALESCE(comp.currency_symbol, '₹') as currency_symbol
            FROM transactions t
            JOIN accounts a ON t.account_number = a.account_number
            JOIN customers c ON a.customer_id = c.customer_id
            LEFT JOIN transaction_categories tc ON t.category_code = tc.category_code
            LEFT JOIN operators op ON t.performed_by_operator_id = op.operator_id
            LEFT JOIN companies comp ON t.company_code = comp.company_code
            WHERE 1=1
        """
        params = []
        if scope_comp:
            sql += " AND t.company_code = ?"
            params.append(scope_comp)
        if acc:
            sql += " AND t.account_number = ?"
            params.append(acc)
        if txn_type:
            sql += " AND t.transaction_type = ?"
            params.append(txn_type)
        if cat:
            sql += " AND t.category_code = ?"
            params.append(cat)

        sql += " ORDER BY t.transaction_date DESC, t.created_at DESC LIMIT 120"
        cur.execute(sql, params)
        txns = [dict(row) for row in cur.fetchall()]
        conn.close()
        self.send_json({"success": True, "data": txns})

    # ---------------- CARDS ---------------- #

    def handle_get_cards(self, user: dict, query: dict):
        scope_comp = self.resolve_company_scope(user, query)
        conn = get_db()
        cur = conn.cursor()
        sql = """
            SELECT cd.*, c.first_name || ' ' || c.last_name as customer_name,
                   a.balance, at.type_name as account_type,
                   comp.short_code as bank_short_code
            FROM cards cd
            JOIN customers c ON cd.customer_id = c.customer_id
            JOIN accounts a ON cd.linked_account_number = a.account_number
            JOIN account_types at ON a.account_type_code = at.account_type_code
            LEFT JOIN companies comp ON cd.company_code = comp.company_code
            WHERE 1=1
        """
        params = []
        if scope_comp:
            sql += " AND cd.company_code = ?"
            params.append(scope_comp)
        sql += " ORDER BY cd.created_at DESC, cd.card_id DESC"
        cur.execute(sql, params)
        cards = [dict(row) for row in cur.fetchall()]
        conn.close()
        self.send_json({"success": True, "data": cards})

    def handle_create_card(self, user: dict, body: dict):
        linked_account = body.get("linked_account_number")
        card_type = body.get("card_type", "debit")
        credit_limit = float(body.get("credit_limit") or 0)

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT customer_id, company_code FROM accounts WHERE account_number = ?", (linked_account,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return self.send_error_json("Linked account not found")

        if user.get("company_code") and row["company_code"] != user["company_code"]:
            log_audit(conn, user, user["company_code"], "ISSUE_CARD", "cards", linked_account, "DENIED", "Cross-bank card issuance")
            conn.close()
            return self.send_error_json("Access denied: linked account belongs to another bank", status=403)

        customer_id = row["customer_id"]
        card_id = generate_next_id(cur, "cards", "card_id", "CRD", 1, 3)
        rand4 = f"{random.randint(1000, 9999)}"
        card_num_masked = f"4219 •••• •••• {rand4}"
        issue_date = datetime.date.today().isoformat()
        expiry_date = (datetime.date.today() + datetime.timedelta(days=365 * 5)).isoformat()

        cur.execute(
            """
            INSERT INTO cards (
                card_id, company_code, customer_id, linked_account_number, issued_by_operator_id,
                card_number_masked, card_type, issue_date, expiry_date, credit_limit, pin_hash, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'hash_dummy_pin', 'active')
            """,
            (card_id, row["company_code"], customer_id, linked_account, user["operator_id"], card_num_masked, card_type, issue_date, expiry_date, credit_limit),
        )
        log_audit(conn, user, row["company_code"], "ISSUE_CARD", "cards", card_id, "SUCCESS", f"Issued {card_type} card on {linked_account}")
        conn.close()
        self.send_json({"success": True, "card_id": card_id, "message": f"Card {card_id} issued successfully"})

    def handle_update_card_status(self, user: dict, card_id: str, body: dict):
        status = body.get("status")
        if status not in ("active", "blocked", "expired"):
            return self.send_error_json("Invalid card status")

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT card_id, company_code FROM cards WHERE card_id = ?", (card_id,))
        card = cur.fetchone()
        if not card:
            conn.close()
            return self.send_error_json("Card not found", status=404)

        if user.get("company_code") and card["company_code"] != user["company_code"]:
            log_audit(conn, user, user["company_code"], "UPDATE_CARD_STATUS", "cards", card_id, "DENIED", "Cross-bank card status change")
            conn.close()
            return self.send_error_json("Access denied: card belongs to another bank", status=403)

        cur.execute("UPDATE cards SET status = ? WHERE card_id = ?", (status, card_id))
        log_audit(conn, user, card["company_code"], "UPDATE_CARD_STATUS", "cards", card_id, "SUCCESS", f"Set card status to {status}")
        conn.close()
        self.send_json({"success": True, "message": f"Card status updated to {status}"})

    # ---------------- LOANS ---------------- #

    def handle_get_loans(self, user: dict, query: dict):
        scope_comp = self.resolve_company_scope(user, query)
        conn = get_db()
        cur = conn.cursor()
        sql = """
            SELECT l.*, c.first_name || ' ' || c.last_name as customer_name, c.credit_score, c.phone,
                   comp.short_code as bank_short_code,
                   COALESCE(comp.currency_symbol, '₹') as currency_symbol,
                   COALESCE(op.username, 'system') as approved_by
            FROM loans l
            JOIN customers c ON l.customer_id = c.customer_id
            LEFT JOIN companies comp ON l.company_code = comp.company_code
            LEFT JOIN operators op ON l.approved_by_operator_id = op.operator_id
            WHERE 1=1
        """
        params = []
        if scope_comp:
            sql += " AND l.company_code = ?"
            params.append(scope_comp)
        sql += " ORDER BY l.created_at DESC, l.loan_number DESC"
        cur.execute(sql, params)
        loans = [dict(row) for row in cur.fetchall()]
        conn.close()
        self.send_json({"success": True, "data": loans})

    def handle_create_loan(self, user: dict, body: dict):
        customer_id = body.get("customer_id")
        loan_type = body.get("loan_type", "personal")
        principal = float(body.get("principal_amount") or 0)
        rate = float(body.get("interest_rate") or 0.085)
        term = int(body.get("term_months") or 12)

        if principal <= 0 or term <= 0:
            return self.send_error_json("Principal and term must be greater than zero")

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT customer_id, company_code FROM customers WHERE customer_id = ?", (customer_id,))
        cust = cur.fetchone()
        if not cust:
            conn.close()
            return self.send_error_json("Customer not found", status=404)

        if user.get("company_code") and cust["company_code"] != user["company_code"]:
            log_audit(conn, user, user["company_code"], "SANCTION_LOAN", "loans", customer_id, "DENIED", "Cross-bank loan sanction attempt")
            conn.close()
            return self.send_error_json("Access denied: customer belongs to another bank", status=403)

        r = rate / 12.0
        if r > 0:
            emi = round(principal * r * ((1 + r) ** term) / (((1 + r) ** term) - 1), 2)
        else:
            emi = round(principal / term, 2)

        loan_num = generate_next_id(cur, "loans", "loan_number", "LN", 100001, 6)
        start_date = datetime.date.today().isoformat()
        end_date = (datetime.date.today() + datetime.timedelta(days=int(term * 30.4))).isoformat()

        cur.execute(
            """
            INSERT INTO loans (
                loan_number, company_code, customer_id, approved_by_operator_id, loan_type,
                principal_amount, interest_rate, term_months, monthly_payment, start_date, end_date, status, outstanding_balance
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'running', ?)
            """,
            (loan_num, cust["company_code"], customer_id, user["operator_id"], loan_type, principal, rate, term, emi, start_date, end_date, principal),
        )
        log_audit(conn, user, cust["company_code"], "SANCTION_LOAN", "loans", loan_num, "SUCCESS", f"Sanctioned {loan_type} loan {principal:,.2f} for {customer_id}")
        conn.close()
        self.send_json({"success": True, "loan_number": loan_num, "monthly_payment": emi, "message": f"Loan {loan_num} sanctioned successfully"})

    def handle_loan_repayment(self, user: dict, body: dict):
        loan_number = body.get("loan_number")
        repay_amount = float(body.get("amount") or 0)

        if repay_amount <= 0:
            return self.send_error_json("Repayment amount must be positive")

        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT l.outstanding_balance, l.status, l.company_code, COALESCE(c.currency_symbol, '₹') as sym
            FROM loans l LEFT JOIN companies c ON l.company_code = c.company_code
            WHERE l.loan_number = ?
            """,
            (loan_number,),
        )
        loan = cur.fetchone()
        if not loan:
            conn.close()
            return self.send_error_json("Loan not found", status=404)

        if user.get("company_code") and loan["company_code"] != user["company_code"]:
            log_audit(conn, user, user["company_code"], "REPAY_LOAN", "loans", loan_number, "DENIED", "Cross-bank loan repayment attempt")
            conn.close()
            return self.send_error_json("Access denied: loan belongs to another bank", status=403)

        new_bal = round(max(0.0, loan["outstanding_balance"] - repay_amount), 2)
        new_status = "closed" if new_bal == 0.0 else loan["status"]

        cur.execute("UPDATE loans SET outstanding_balance = ?, status = ? WHERE loan_number = ?", (new_bal, new_status, loan_number))
        log_audit(conn, user, loan["company_code"], "REPAY_LOAN", "loans", loan_number, "SUCCESS", f"Repaid {loan['sym']}{repay_amount:,.2f}, remaining={new_bal:,.2f}")
        conn.close()
        self.send_json(
            {
                "success": True,
                "new_balance": new_bal,
                "status": new_status,
                "message": f"Repayment of {loan['sym']}{repay_amount:,.2f} recorded. Remaining: {loan['sym']}{new_bal:,.2f}",
            }
        )

    # ---------------- BRANCHES, EMPLOYEES & OPERATORS ---------------- #

    def handle_get_branches(self, user: dict, query: dict):
        scope_comp = self.resolve_company_scope(user, query)
        conn = get_db()
        cur = conn.cursor()
        sql = """
            SELECT b.*, c.company_name, c.short_code as bank_short_code, COUNT(e.employee_id) as employee_count
            FROM branches b
            JOIN companies c ON b.company_code = c.company_code
            LEFT JOIN employees e ON b.branch_code = e.branch_code
        """
        params = []
        if scope_comp:
            sql += " WHERE b.company_code = ?"
            params.append(scope_comp)
        sql += " GROUP BY b.branch_code ORDER BY b.branch_code ASC"
        cur.execute(sql, params)
        branches = [dict(row) for row in cur.fetchall()]
        conn.close()
        self.send_json({"success": True, "data": branches})

    def handle_create_branch(self, user: dict, body: dict):
        scope_comp = self.resolve_company_scope(user, requested_company=body.get("company_code"), require_single_for_write=True)
        branch_name = (body.get("branch_name") or "").strip()
        address = (body.get("address") or "").strip()
        phone = (body.get("phone") or "").strip()
        manager_name = (body.get("manager_name") or "").strip()
        opening_hours = body.get("opening_hours") or "09:30:00"
        closing_hours = body.get("closing_hours") or "16:30:00"

        if not branch_name:
            return self.send_error_json("branch_name is required")

        conn = get_db()
        cur = conn.cursor()
        br_code = generate_next_id(cur, "branches", "branch_code", "BR", 1, 3)
        cur.execute(
            """
            INSERT INTO branches (branch_code, company_code, branch_name, address, phone, manager_name, opening_hours, closing_hours)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (br_code, scope_comp, branch_name, address, phone, manager_name, opening_hours, closing_hours),
        )
        log_audit(conn, user, scope_comp, "CREATE_BRANCH", "branches", br_code, "SUCCESS", f"Created branch '{branch_name}' ({br_code})")
        conn.close()
        self.send_json({"success": True, "branch_code": br_code, "message": f"Branch {branch_name} ({br_code}) created"})

    def handle_get_employees(self, user: dict, query: dict):
        scope_comp = self.resolve_company_scope(user, query)
        conn = get_db()
        cur = conn.cursor()
        sql = """
            SELECT e.*, b.branch_name, comp.company_name, comp.short_code as bank_short_code,
                   op.username as operator_username, op.role_code as operator_role
            FROM employees e
            LEFT JOIN branches b ON e.branch_code = b.branch_code
            LEFT JOIN companies comp ON e.company_code = comp.company_code
            LEFT JOIN operators op ON op.employee_id = e.employee_id
        """
        params = []
        if scope_comp:
            sql += " WHERE e.company_code = ?"
            params.append(scope_comp)
        sql += " ORDER BY e.employee_id ASC"
        cur.execute(sql, params)
        employees = [dict(row) for row in cur.fetchall()]
        conn.close()
        self.send_json({"success": True, "data": employees})

    def handle_create_employee(self, user: dict, body: dict):
        scope_comp = self.resolve_company_scope(user, requested_company=body.get("company_code"), require_single_for_write=False)
        branch_code = (body.get("branch_code") or "").strip()
        first_name = (body.get("first_name") or "").strip()
        last_name = (body.get("last_name") or "").strip()
        email = (body.get("email") or "").strip()
        phone = (body.get("phone") or "").strip() or None
        position = (body.get("position") or "Bank Officer").strip()
        salary = float(body.get("salary") or 60000.0)
        department = (body.get("department") or "Retail Banking").strip()
        hire_date = body.get("hire_date") or datetime.date.today().isoformat()

        if not first_name or not last_name or not email or not branch_code:
            return self.send_error_json("branch_code, first_name, last_name, and email are required")

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT branch_code, company_code FROM branches WHERE branch_code = ?", (branch_code,))
        br = cur.fetchone()
        if not br:
            conn.close()
            return self.send_error_json("Branch not found")

        br_comp = br["company_code"]
        if scope_comp and br_comp != scope_comp:
            conn.close()
            return self.send_error_json(f"Branch {branch_code} belongs to {br_comp}, outside your bank scope", status=403)

        emp_id = generate_next_id(cur, "employees", "employee_id", "EMP", 1, 3)
        try:
            cur.execute("BEGIN TRANSACTION")
            cur.execute(
                """
                INSERT INTO employees (employee_id, company_code, branch_code, first_name, last_name, email, phone, position, salary, hire_date, department)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (emp_id, br_comp, branch_code, first_name, last_name, email, phone, position, salary, hire_date, department),
            )

            created_op = None
            if body.get("create_operator"):
                op_username = (body.get("operator_username") or "").strip()
                op_password = body.get("operator_password") or "Bank@123"
                op_role = (body.get("operator_role") or "TELLER").strip()
                if not op_username:
                    raise ValueError("operator_username is required when provisioning an operator login")
                cur.execute("SELECT hierarchy_level FROM roles WHERE role_code = ?", (op_role,))
                rrow = cur.fetchone()
                if not rrow:
                    raise ValueError(f"Unknown role {op_role}")
                if rrow["hierarchy_level"] > user["hierarchy_level"]:
                    raise PermissionDenied("Cannot assign a role higher than your own")
                op_id = generate_next_id(cur, "operators", "operator_id", "OP", 1, 3)
                cur.execute(
                    """
                    INSERT INTO operators (operator_id, employee_id, company_code, branch_code, username, password_hash, full_name, role_code, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                    """,
                    (op_id, emp_id, br_comp, branch_code, op_username, db_setup.hash_password(op_password), f"{first_name} {last_name}", op_role),
                )
                created_op = op_username

            log_audit(conn, user, br_comp, "CREATE_EMPLOYEE", "employees", emp_id, "SUCCESS", f"Added {first_name} {last_name} ({position}); operator={created_op}")
            conn.close()
            self.send_json({"success": True, "employee_id": emp_id, "operator_username": created_op, "message": f"Employee {emp_id} added"})
        except PermissionDenied:
            conn.rollback()
            conn.close()
            raise
        except Exception as e:
            conn.rollback()
            conn.close()
            self.send_error_json(str(e))

    def handle_get_operators(self, user: dict, query: dict):
        scope_comp = self.resolve_company_scope(user, query)
        conn = get_db()
        cur = conn.cursor()
        sql = """
            SELECT o.operator_id, o.employee_id, o.company_code, o.branch_code,
                   o.username, o.full_name, o.role_code, o.is_active, o.last_login, o.created_at,
                   r.role_name, r.hierarchy_level,
                   COALESCE(c.company_name, 'All Consortium Banks') as company_name,
                   COALESCE(c.short_code, 'ALL') as bank_short_code,
                   b.branch_name
            FROM operators o
            JOIN roles r ON o.role_code = r.role_code
            LEFT JOIN companies c ON o.company_code = c.company_code
            LEFT JOIN branches b ON o.branch_code = b.branch_code
            WHERE 1=1
        """
        params = []
        if scope_comp:
            sql += " AND o.company_code = ?"
            params.append(scope_comp)
        sql += " ORDER BY r.hierarchy_level DESC, o.operator_id ASC"
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        self.send_json({"success": True, "data": rows})

    def handle_create_operator(self, user: dict, body: dict):
        username = (body.get("username") or "").strip()
        password = body.get("password") or ""
        full_name = (body.get("full_name") or "").strip()
        role_code = (body.get("role_code") or "").strip()
        employee_id = (body.get("employee_id") or "").strip() or None
        branch_code = (body.get("branch_code") or "").strip() or None
        req_comp = (body.get("company_code") or "").strip() or None
        if req_comp == "ALL":
            req_comp = None

        if not username or not password or not role_code:
            return self.send_error_json("username, password, and role_code are required")

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT role_code, hierarchy_level FROM roles WHERE role_code = ?", (role_code,))
        role_row = cur.fetchone()
        if not role_row:
            conn.close()
            return self.send_error_json(f"Invalid role_code: {role_code}")
        if role_row["hierarchy_level"] > user["hierarchy_level"]:
            log_audit(conn, user, user.get("company_code"), "CREATE_OPERATOR", "operators", username, "DENIED", f"Privilege escalation attempt to {role_code}")
            conn.close()
            return self.send_error_json("Cannot create an operator with a higher role than your own", status=403)

        target_comp = user["company_code"] if user.get("company_code") else req_comp
        if user.get("company_code") and req_comp and req_comp != user["company_code"]:
            conn.close()
            return self.send_error_json("Cannot provision operator for another bank", status=403)
        if role_code not in ("SUPER_ADMIN", "AUDITOR") and not target_comp:
            conn.close()
            return self.send_error_json(f"Role {role_code} must be assigned to a specific bank (company_code)")

        if employee_id:
            cur.execute("SELECT first_name, last_name, company_code, branch_code FROM employees WHERE employee_id = ?", (employee_id,))
            emp = cur.fetchone()
            if not emp:
                conn.close()
                return self.send_error_json("Employee not found")
            if user.get("company_code") and emp["company_code"] != user["company_code"]:
                conn.close()
                return self.send_error_json("Employee belongs to another bank", status=403)
            full_name = full_name or f"{emp['first_name']} {emp['last_name']}"
            target_comp = target_comp or emp["company_code"]
            branch_code = branch_code or emp["branch_code"]

        if not full_name:
            full_name = username

        op_id = generate_next_id(cur, "operators", "operator_id", "OP", 1, 3)
        cur.execute(
            """
            INSERT INTO operators (operator_id, employee_id, company_code, branch_code, username, password_hash, full_name, role_code, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (op_id, employee_id, target_comp, branch_code, username, db_setup.hash_password(password), full_name, role_code),
        )
        log_audit(conn, user, target_comp, "CREATE_OPERATOR", "operators", op_id, "SUCCESS", f"Provisioned '{username}' with role {role_code}")
        conn.close()
        self.send_json({"success": True, "operator_id": op_id, "message": f"Operator '{username}' ({role_code}) created"})

    def handle_update_operator_status(self, user: dict, op_id: str, body: dict):
        if op_id == user["operator_id"] and body.get("is_active") == 0:
            return self.send_error_json("You cannot disable your own active operator account")

        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT o.*, r.hierarchy_level
            FROM operators o JOIN roles r ON o.role_code = r.role_code
            WHERE o.operator_id = ?
            """,
            (op_id,),
        )
        target = cur.fetchone()
        if not target:
            conn.close()
            return self.send_error_json("Operator not found", status=404)

        if user.get("company_code") and target["company_code"] != user["company_code"]:
            conn.close()
            return self.send_error_json("Access denied: operator belongs to another bank", status=403)
        if target["hierarchy_level"] > user["hierarchy_level"]:
            conn.close()
            return self.send_error_json("Cannot modify an operator with higher privileges", status=403)

        new_active = target["is_active"] if "is_active" not in body else (1 if body["is_active"] else 0)
        new_role = body.get("role_code") or target["role_code"]

        if new_role != target["role_code"]:
            cur.execute("SELECT hierarchy_level FROM roles WHERE role_code = ?", (new_role,))
            rrow = cur.fetchone()
            if not rrow:
                conn.close()
                return self.send_error_json("Invalid role_code")
            if rrow["hierarchy_level"] > user["hierarchy_level"]:
                conn.close()
                return self.send_error_json("Cannot promote operator above your own role", status=403)

        cur.execute("UPDATE operators SET is_active = ?, role_code = ? WHERE operator_id = ?", (new_active, new_role, op_id))
        log_audit(conn, user, target["company_code"], "UPDATE_OPERATOR", "operators", op_id, "SUCCESS", f"role={new_role}, is_active={new_active}")
        conn.close()
        self.send_json({"success": True, "message": f"Operator {target['username']} updated"})

    # ---------------- AUDIT LOGS ---------------- #

    def handle_get_audit_logs(self, user: dict, query: dict):
        scope_comp = self.resolve_company_scope(user, query)
        status_filter = query.get("status", [""])[0].strip()

        conn = get_db()
        cur = conn.cursor()
        sql = """
            SELECT a.*, comp.short_code as bank_short_code
            FROM audit_logs a
            LEFT JOIN companies comp ON a.company_code = comp.company_code
            WHERE 1=1
        """
        params = []
        if scope_comp:
            sql += " AND a.company_code = ?"
            params.append(scope_comp)
        if status_filter:
            sql += " AND a.status = ?"
            params.append(status_filter)
        sql += " ORDER BY a.log_id DESC LIMIT 120"
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        self.send_json({"success": True, "data": rows})

    # ---------------- METADATA & SQL STUDIO ---------------- #

    def handle_get_metadata(self, user: dict, query: dict):
        scope_comp = self.resolve_company_scope(user, query)
        conn = get_db()
        cur = conn.cursor()

        if scope_comp:
            cur.execute("SELECT * FROM account_types WHERE company_code IS NULL OR company_code = ? ORDER BY account_type_code", (scope_comp,))
        else:
            cur.execute("SELECT * FROM account_types ORDER BY account_type_code")
        account_types = [dict(r) for r in cur.fetchall()]

        cur.execute("SELECT * FROM transaction_categories")
        categories = [dict(r) for r in cur.fetchall()]

        if user.get("company_code"):
            cur.execute("SELECT company_code, company_name, short_code, currency_code, currency_symbol, brand_color FROM companies WHERE company_code = ?", (user["company_code"],))
        else:
            cur.execute("SELECT company_code, company_name, short_code, currency_code, currency_symbol, brand_color FROM companies ORDER BY company_code")
        companies = [dict(r) for r in cur.fetchall()]

        if scope_comp:
            cur.execute("SELECT branch_code, branch_name, company_code FROM branches WHERE company_code = ? ORDER BY branch_code", (scope_comp,))
        else:
            cur.execute("SELECT branch_code, branch_name, company_code FROM branches ORDER BY branch_code")
        branches = [dict(r) for r in cur.fetchall()]

        if scope_comp:
            cur.execute("SELECT employee_id, first_name || ' ' || last_name || ' (' || position || ')' as name, company_code, branch_code FROM employees WHERE company_code = ?", (scope_comp,))
        else:
            cur.execute("SELECT employee_id, first_name || ' ' || last_name || ' (' || position || ' - ' || COALESCE(company_code, '') || ')' as name, company_code, branch_code FROM employees")
        employees = [dict(r) for r in cur.fetchall()]

        if scope_comp:
            cur.execute("SELECT customer_id, customer_id || ' - ' || first_name || ' ' || last_name as name, company_code FROM customers WHERE company_code = ?", (scope_comp,))
        else:
            cur.execute("SELECT customer_id, customer_id || ' - ' || first_name || ' ' || last_name || ' [' || COALESCE(company_code, '') || ']' as name, company_code FROM customers")
        customers = [dict(r) for r in cur.fetchall()]

        if scope_comp:
            cur.execute(
                """
                SELECT a.account_number,
                       a.account_number || ' (' || a.customer_id || ' - ' || COALESCE(c.currency_symbol, '₹') || a.balance || ')' as label,
                       a.company_code
                FROM accounts a LEFT JOIN companies c ON a.company_code = c.company_code
                WHERE a.status = 'active' AND a.company_code = ?
                """,
                (scope_comp,),
            )
            accounts = [dict(r) for r in cur.fetchall()]
            cur.execute(
                """
                SELECT a.account_number,
                       CASE WHEN a.company_code = ?
                            THEN a.account_number || ' (' || a.customer_id || ' - ' || COALESCE(c.currency_symbol, '₹') || a.balance || ')'
                            ELSE a.account_number || ' (' || COALESCE(c.short_code, 'EXT') || ' • Inter-Bank ' || COALESCE(c.currency_code, 'INR') || ')'
                       END as label,
                       a.company_code
                FROM accounts a LEFT JOIN companies c ON a.company_code = c.company_code
                WHERE a.status = 'active'
                ORDER BY a.company_code = ? DESC, a.account_number ASC
                """,
                (scope_comp, scope_comp),
            )
            destination_accounts = [dict(r) for r in cur.fetchall()]
        else:
            cur.execute(
                """
                SELECT a.account_number,
                       a.account_number || ' (' || a.customer_id || ' / ' || COALESCE(c.short_code, '') || ' - ' || COALESCE(c.currency_symbol, '₹') || a.balance || ')' as label,
                       a.company_code
                FROM accounts a LEFT JOIN companies c ON a.company_code = c.company_code
                WHERE a.status = 'active'
                """
            )
            accounts = [dict(r) for r in cur.fetchall()]
            destination_accounts = list(accounts)

        cur.execute("SELECT role_code, role_name, hierarchy_level FROM roles ORDER BY hierarchy_level DESC")
        roles = [dict(r) for r in cur.fetchall()]

        conn.close()
        self.send_json(
            {
                "success": True,
                "data": {
                    "account_types": account_types,
                    "categories": categories,
                    "companies": companies,
                    "branches": branches,
                    "employees": employees,
                    "customers": customers,
                    "accounts": accounts,
                    "destination_accounts": destination_accounts,
                    "roles": roles,
                },
            }
        )

    def handle_run_sql(self, user: dict, body: dict):
        raw_sql = (body.get("query") or "").strip()
        if not raw_sql:
            return self.send_error_json("No SQL query provided")

        upper = raw_sql.upper()
        if "DROP DATABASE" in upper:
            return self.send_error_json("Drop database operation is prohibited")

        start = time.time()
        conn = get_db()
        if not user.get("can_run_sql_write"):
            conn.set_authorizer(readonly_sqlite_authorizer)

        cur = conn.cursor()
        try:
            cur.execute(raw_sql)
            duration_ms = round((time.time() - start) * 1000, 2)

            if cur.description:
                columns = [col[0] for col in cur.description]
                rows = [list(row) for row in cur.fetchall()]
                conn.commit()
                # Re-open/clear authorizer before writing audit log
                conn.set_authorizer(None)
                log_audit(conn, user, user.get("company_code"), "RUN_SQL_READ", "sql_studio", None, "SUCCESS", raw_sql[:240])
                conn.close()
                return self.send_json(
                    {
                        "success": True,
                        "columns": columns,
                        "rows": rows,
                        "row_count": len(rows),
                        "execution_time_ms": duration_ms,
                    }
                )
            else:
                affected = cur.rowcount
                conn.commit()
                conn.set_authorizer(None)
                log_audit(conn, user, user.get("company_code"), "RUN_SQL_WRITE", "sql_studio", None, "SUCCESS", raw_sql[:240])
                conn.close()
                return self.send_json(
                    {
                        "success": True,
                        "columns": ["Result"],
                        "rows": [[f"Query executed successfully. Rows affected: {affected}"]],
                        "row_count": affected,
                        "execution_time_ms": duration_ms,
                    }
                )
        except sqlite3.DatabaseError as e:
            err_msg = str(e)
            conn.set_authorizer(None)
            is_denied = "not authorized" in err_msg.lower()
            log_audit(
                conn,
                user,
                user.get("company_code"),
                "RUN_SQL",
                "sql_studio",
                None,
                "DENIED" if is_denied else "ERROR",
                f"{err_msg} | SQL: {raw_sql[:180]}",
            )
            conn.close()
            if is_denied:
                return self.send_error_json(
                    f"SQL Read-Only Guard: '{user['role_name']}' can only execute SELECT queries. Write/DDL SQL requires SUPER_ADMIN.",
                    status=403,
                )
            return self.send_error_json(f"SQL Error: {err_msg}")
        except Exception as e:
            conn.set_authorizer(None)
            conn.close()
            return self.send_error_json(f"SQL Error: {str(e)}")

    def handle_export_sql(self):
        dump_path = os.path.join(BASE_DIR, "mysql_dump.sql")
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
    db_setup.ensure_schema_and_seed(DB_PATH)
    server_address = ("0.0.0.0", port)
    httpd = ThreadingHTTPServer(server_address, BankingRequestHandler)
    print(f"Bank Management System (Multi-Bank RBAC) API & Frontend Server running at http://localhost:{port}")
    httpd.serve_forever()


if __name__ == "__main__":
    run_server()
