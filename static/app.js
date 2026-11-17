// Multi-Bank Core Banking & RBAC Frontend
let authToken = sessionStorage.getItem("bms_token") || null;
let currentUser = null;
let activeCompanyCode = sessionStorage.getItem("bms_company") || "ALL";
let activeCompanyInfo = {
  company_code: "ALL",
  company_name: "Multi-Bank Consortium",
  short_code: "ALL",
  currency_symbol: "₹",
  currency_code: "INR",
  brand_color: "#10b981"
};

let metaData = {
  account_types: [],
  categories: [],
  companies: [],
  branches: [],
  employees: [],
  customers: [],
  accounts: [],
  destination_accounts: [],
  roles: []
};

function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatINR(val, symbolOverride = null) {
  const num = Number(val) || 0;
  const sym = symbolOverride || activeCompanyInfo.currency_symbol || "₹";
  return sym + num.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function showToast(message, type = "success") {
  const box = document.getElementById("toast-box");
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <span>${type === "success" ? "✓" : "⚠"}</span>
    <div>${escapeHtml(message)}</div>
  `;
  box.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(10px)";
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

async function apiFetch(url, options = {}) {
  const headers = Object.assign({}, options.headers || {});
  if (authToken) {
    headers["Authorization"] = `Bearer ${authToken}`;
  }
  if (activeCompanyCode) {
    headers["X-Company-Code"] = activeCompanyCode;
  }
  const res = await fetch(url, Object.assign({}, options, { headers }));
  if (res.status === 401) {
    logoutOperator(false);
    throw new Error("Session expired. Please sign in.");
  }
  return res.json();
}

function scopedUrl(base) {
  const sep = base.includes("?") ? "&" : "?";
  return `${base}${sep}company_code=${encodeURIComponent(activeCompanyCode || "ALL")}`;
}

// ---------------- AUTH & RBAC ---------------- #

async function loadDemoAccounts() {
  try {
    const res = await fetch("/api/auth/demo-accounts");
    const json = await res.json();
    const container = document.getElementById("demo-role-presets");
    if (!json.success) return;

    container.innerHTML = json.data.map(op => `
      <button type="button" class="demo-role-card" onclick="quickLogin('${escapeHtml(op.username)}', '${escapeHtml(op.demo_password)}')">
        <div style="display:flex; justify-content:space-between; align-items:center; gap:6px; margin-bottom:4px;">
          <strong style="font-size:12px;">${escapeHtml(op.full_name)}</strong>
          <span class="role-chip">${escapeHtml(op.short_code)}</span>
        </div>
        <div style="font-size:11px; color:var(--accent-primary); font-weight:600;">${escapeHtml(op.role_name)}</div>
        <div style="font-size:10px; color:var(--text-muted); font-family:var(--font-mono); margin-top:2px;">
          ${escapeHtml(op.username)} • ${escapeHtml(op.company_name)}
        </div>
      </button>
    `).join("");
  } catch (err) {
    console.error("Failed loading demo accounts", err);
  }
}

function openAuthOverlay(canCancel = false) {
  loadDemoAccounts();
  document.getElementById("login-error-msg").style.display = "none";
  document.getElementById("auth-cancel-btn").style.display = canCancel && currentUser ? "inline-flex" : "none";
  document.getElementById("auth-overlay").classList.add("active");
}

function closeAuthOverlay() {
  document.getElementById("auth-overlay").classList.remove("active");
}

async function quickLogin(username, password) {
  document.getElementById("login-username").value = username;
  document.getElementById("login-password").value = password;
  await performLogin(username, password);
}

async function submitLogin(event) {
  event.preventDefault();
  const username = document.getElementById("login-username").value.trim();
  const password = document.getElementById("login-password").value;
  await performLogin(username, password);
}

async function performLogin(username, password) {
  const errEl = document.getElementById("login-error-msg");
  errEl.style.display = "none";
  try {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password })
    });
    const json = await res.json();
    if (!json.success) {
      errEl.innerText = json.error || "Sign-in failed";
      errEl.style.display = "block";
      return;
    }

    authToken = json.token;
    currentUser = json.user;
    sessionStorage.setItem("bms_token", authToken);

    activeCompanyCode = currentUser.company_code || "ALL";
    sessionStorage.setItem("bms_company", activeCompanyCode);

    closeAuthOverlay();
    applyUserContext();
    await reloadAllActiveData();
    showToast(`Signed in as ${currentUser.full_name} (${currentUser.role_name})`);
  } catch (err) {
    errEl.innerText = "Network error during sign-in";
    errEl.style.display = "block";
  }
}

function logoutOperator(showNotice = true) {
  authToken = null;
  currentUser = null;
  sessionStorage.removeItem("bms_token");
  openAuthOverlay(false);
  if (showNotice) showToast("Signed out", "success");
}

function applyUserContext() {
  if (!currentUser) return;

  document.getElementById("operator-pill-name").innerText = `${currentUser.full_name} (${currentUser.username})`;
  document.getElementById("operator-pill-role").innerText = currentUser.role_code;

  // Apply permission-based UI state (backend also strictly enforces 403)
  const perms = currentUser.permissions || {};
  document.querySelectorAll("[data-perm]").forEach(el => {
    const req = el.getAttribute("data-perm");
    const allowed = !!perms[req];
    el.disabled = !allowed;
    el.title = allowed ? "" : `Restricted: requires '${req}' permission (current role: ${currentUser.role_code})`;
  });

  // SQL Studio indicator
  const sqlBadge = document.getElementById("sql-mode-badge");
  if (sqlBadge) {
    if (perms.can_run_sql_write) {
      sqlBadge.innerText = "Full R/W SQL (SUPER_ADMIN)";
      sqlBadge.style.color = "#10b981";
    } else if (perms.can_run_sql_read) {
      sqlBadge.innerText = "SELECT-Only SQL Guard";
      sqlBadge.style.color = "#f59e0b";
    } else {
      sqlBadge.innerText = "SQL Restricted (403)";
      sqlBadge.style.color = "#f43f5e";
    }
  }
}

function updateBankBranding(info) {
  if (!info) return;
  activeCompanyInfo = info;
  const shortEl = document.getElementById("sidebar-logo-short");
  const titleEl = document.getElementById("sidebar-brand-title");
  const subEl = document.getElementById("sidebar-brand-subtitle");
  const kpiSym = document.getElementById("kpi-currency-symbol");

  if (shortEl) {
    shortEl.innerText = info.short_code || "ALL";
    if (info.brand_color) {
      shortEl.style.background = `linear-gradient(135deg, ${info.brand_color} 0%, #3b82f6 100%)`;
    }
  }
  if (titleEl) titleEl.innerText = (info.company_name || "CORE BANKING").toUpperCase();
  if (subEl) subEl.innerText = `${info.currency_code || "INR"} • ${info.company_code === "ALL" ? "Multi-Bank Engine" : info.company_code}`;
  if (kpiSym) kpiSym.innerText = info.currency_symbol || "₹";
}

function onBankContextChange() {
  const sel = document.getElementById("bank-context-select");
  if (!sel) return;
  activeCompanyCode = sel.value;
  sessionStorage.setItem("bms_company", activeCompanyCode);
  reloadAllActiveData();
}

async function reloadAllActiveData() {
  await fetchMetadata();
  const activeNav = document.querySelector(".nav-item.active");
  const activeTab = activeNav ? activeNav.getAttribute("data-tab") : "dashboard";
  refreshTab(activeTab);
}

// ---------------- NAVIGATION ---------------- #

function switchTab(tabId) {
  document.querySelectorAll(".nav-item").forEach(item => {
    item.classList.toggle("active", item.getAttribute("data-tab") === tabId);
  });
  document.querySelectorAll(".tab-pane").forEach(pane => {
    pane.classList.remove("active");
  });
  const target = document.getElementById(`tab-${tabId}`);
  if (target) target.classList.add("active");

  const titles = {
    dashboard: ["Executive Banking Dashboard", "Real-time multi-bank ledger monitoring and role-based operations"],
    customers: ["Customer Directory & KYC", "Tenant-isolated customer profiles, credit scores, and RM portfolios"],
    accounts: ["Core Banking Accounts", "Savings, current, salary, and custom bank accounts"],
    transactions: ["Transaction Audit Trail", "Double-entry ledger with operator attribution"],
    cards: ["Card Center", "Debit, credit, and prepaid payment cards"],
    loans: ["Credit & Lending Facilities", "Loan management, EMI schedules, and approvals"],
    branches: ["Branch Network & Staff", "Multi-bank branches, staff, and operator provisioning"],
    banks: ["Multi-Bank Registry", "Onboard independent banks, currencies, and custom account products"],
    "rbac-audit": ["Access Control & Audit Trail", "Role permission matrix, operator accounts, and security logs"],
    "sql-studio": ["SQL Query Studio", "Role-guarded SQL querying against SQLite relational engine"],
    "schema-view": ["Database Design & ER Model", "13-table normalized Multi-Bank + RBAC relational architecture"]
  };
  if (titles[tabId]) {
    document.getElementById("page-title").innerText = titles[tabId][0];
    document.getElementById("page-subtitle").innerText = titles[tabId][1];
  }

  refreshTab(tabId);
}

function refreshTab(tabId) {
  if (tabId === "dashboard") fetchDashboard();
  else if (tabId === "customers") fetchCustomers();
  else if (tabId === "accounts") fetchAccounts();
  else if (tabId === "transactions") fetchTransactions();
  else if (tabId === "cards") fetchCards();
  else if (tabId === "loans") fetchLoans();
  else if (tabId === "branches") fetchBranchesAndStaff();
  else if (tabId === "banks") fetchBanksRegistry();
  else if (tabId === "rbac-audit") fetchRbacAndAudit();
}

function openModal(id) {
  const modal = document.getElementById(id);
  if (modal) modal.classList.add("active");
}

function closeModal(id) {
  const modal = document.getElementById(id);
  if (modal) modal.classList.remove("active");
}

// ---------------- METADATA ---------------- #

async function fetchMetadata() {
  try {
    const json = await apiFetch(scopedUrl("/api/metadata"));
    if (json.success) {
      metaData = json.data;
      populateDropdowns();
    }
  } catch (err) {
    console.error("Failed to load metadata", err);
  }
}

function populateDropdowns() {
  // Topbar bank context selector
  const bankCtxSel = document.getElementById("bank-context-select");
  if (bankCtxSel && currentUser) {
    let opts = "";
    if (currentUser.is_global_scope) {
      opts += `<option value="ALL">All Banks (Consortium)</option>`;
    }
    opts += metaData.companies.map(c =>
      `<option value="${escapeHtml(c.company_code)}">${escapeHtml(c.short_code)} — ${escapeHtml(c.company_name)} (${escapeHtml(c.currency_symbol)})</option>`
    ).join("");
    bankCtxSel.innerHTML = opts;
    bankCtxSel.value = currentUser.is_global_scope ? (activeCompanyCode || "ALL") : currentUser.company_code;
    bankCtxSel.disabled = !currentUser.is_global_scope;
  }

  const srcSel = document.getElementById("transfer-src-account");
  const dstSel = document.getElementById("transfer-dst-account");
  const dwAccSel = document.getElementById("dw-account");
  const cardAccSel = document.getElementById("card-account");

  const accOptions = metaData.accounts.map(a => `<option value="${escapeHtml(a.account_number)}">${escapeHtml(a.label)}</option>`).join("");
  const dstOptions = (metaData.destination_accounts || metaData.accounts).map(a => `<option value="${escapeHtml(a.account_number)}">${escapeHtml(a.label)}</option>`).join("");
  if (srcSel) srcSel.innerHTML = accOptions;
  if (dstSel) dstSel.innerHTML = dstOptions;
  if (dwAccSel) dwAccSel.innerHTML = accOptions;
  if (cardAccSel) cardAccSel.innerHTML = accOptions;

  const custOptions = metaData.customers.map(c => `<option value="${escapeHtml(c.customer_id)}">${escapeHtml(c.name)}</option>`).join("");
  const newaccCust = document.getElementById("newacc-customer");
  const loanCust = document.getElementById("loan-customer");
  if (newaccCust) newaccCust.innerHTML = custOptions;
  if (loanCust) loanCust.innerHTML = custOptions;

  const typeOptions = metaData.account_types.map(t => `<option value="${escapeHtml(t.account_type_code)}">${escapeHtml(t.type_name)} (Min: ${t.minimum_balance})</option>`).join("");
  const newaccType = document.getElementById("newacc-type");
  if (newaccType) newaccType.innerHTML = typeOptions;

  const rmOptions = `<option value="">-- Optional / Auto --</option>` + metaData.employees.map(e => `<option value="${escapeHtml(e.employee_id)}">${escapeHtml(e.name)}</option>`).join("");
  const custRm = document.getElementById("cust-rm");
  if (custRm) custRm.innerHTML = rmOptions;

  const catOptions = metaData.categories.map(c => `<option value="${escapeHtml(c.category_code)}">${escapeHtml(c.category_name)} (${escapeHtml(c.category_type)})</option>`).join("");
  const dwCat = document.getElementById("dw-category");
  if (dwCat) dwCat.innerHTML = catOptions;

  // Company dropdowns in modals
  const compOpts = metaData.companies.map(c => `<option value="${escapeHtml(c.company_code)}">${escapeHtml(c.short_code)} — ${escapeHtml(c.company_name)}</option>`).join("");
  const custComp = document.getElementById("cust-company");
  const brComp = document.getElementById("br-company");
  const opComp = document.getElementById("op-company");
  const atComp = document.getElementById("at-company");
  if (custComp) {
    custComp.innerHTML = compOpts;
    if (activeCompanyCode && activeCompanyCode !== "ALL") custComp.value = activeCompanyCode;
  }
  if (brComp) {
    brComp.innerHTML = compOpts;
    if (activeCompanyCode && activeCompanyCode !== "ALL") brComp.value = activeCompanyCode;
  }
  if (opComp) {
    opComp.innerHTML = (currentUser && currentUser.is_global_scope ? `<option value="ALL">ALL (Global Consortium)</option>` : "") + compOpts;
    if (activeCompanyCode && activeCompanyCode !== "ALL") opComp.value = activeCompanyCode;
  }
  if (atComp) {
    atComp.innerHTML = (currentUser && currentUser.is_global_scope ? `<option value="">GLOBAL (Available to All Banks)</option>` : "") + compOpts;
    if (activeCompanyCode && activeCompanyCode !== "ALL") atComp.value = activeCompanyCode;
  }

  // Branches dropdown
  const brOpts = metaData.branches.map(b => `<option value="${escapeHtml(b.branch_code)}">${escapeHtml(b.branch_code)} — ${escapeHtml(b.branch_name)}</option>`).join("");
  const empBr = document.getElementById("emp-branch");
  if (empBr) empBr.innerHTML = brOpts;

  // Roles dropdown (filtered to <= caller hierarchy)
  const callerLevel = currentUser ? currentUser.hierarchy_level : 0;
  const assignableRoles = metaData.roles.filter(r => r.hierarchy_level <= callerLevel);
  const roleOpts = assignableRoles.map(r => `<option value="${escapeHtml(r.role_code)}">${escapeHtml(r.role_name)} (${escapeHtml(r.role_code)})</option>`).join("");
  const empRole = document.getElementById("emp-op-role");
  const opRole = document.getElementById("op-role");
  if (empRole) {
    empRole.innerHTML = roleOpts;
    if (assignableRoles.some(r => r.role_code === "TELLER")) empRole.value = "TELLER";
  }
  if (opRole) {
    opRole.innerHTML = roleOpts;
    if (assignableRoles.some(r => r.role_code === "TELLER")) opRole.value = "TELLER";
  }

  const opEmp = document.getElementById("op-employee");
  if (opEmp) {
    opEmp.innerHTML = `<option value="">-- Standalone Operator --</option>` + metaData.employees.map(e => `<option value="${escapeHtml(e.employee_id)}">${escapeHtml(e.name)}</option>`).join("");
  }
}

// ---------------- 1. DASHBOARD ---------------- #

async function fetchDashboard() {
  try {
    const json = await apiFetch(scopedUrl("/api/dashboard/stats"));
    if (!json.success) return;

    const data = json.data;
    updateBankBranding(data.company_info);

    document.getElementById("kpi-total-balance").innerText = formatINR(data.total_balance);
    document.getElementById("kpi-accounts-count").innerText = `${data.active_accounts} Active Accounts`;
    document.getElementById("kpi-customers-count").innerText = data.total_customers;
    document.getElementById("kpi-customers-sub").innerText = `Across ${data.total_branches} Active Branches`;
    document.getElementById("kpi-loan-balance").innerText = formatINR(data.outstanding_loans);
    document.getElementById("kpi-loans-count").innerText = `${data.active_loans} Running Facilities`;
    document.getElementById("kpi-active-cards").innerText = data.active_cards;
    document.getElementById("kpi-txn-count").innerText = `${data.total_transactions} Ledger Transactions`;

    const tbody = document.getElementById("dashboard-recent-txns");
    if (data.recent_transactions.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:20px;">No transactions recorded</td></tr>`;
    } else {
      tbody.innerHTML = data.recent_transactions.map(t => `
        <tr>
          <td><strong style="font-family:var(--font-mono); color:#58a6ff;">${escapeHtml(t.transaction_reference)}</strong></td>
          <td>
            <div>${escapeHtml(t.customer_name)} <span class="role-chip" style="font-size:9px;">${escapeHtml(t.bank_short_code || "-")}</span></div>
            <div style="font-size:11px; color:var(--text-muted); font-family:var(--font-mono);">${escapeHtml(t.account_number)}</div>
          </td>
          <td style="font-family:var(--font-mono); font-size:11px;">${escapeHtml(t.performed_by)}</td>
          <td>
            <span class="badge badge-${escapeHtml(t.transaction_type)}">
              ${t.transaction_type === "credit" ? "↓ Credit" : "↑ Debit"}
            </span>
          </td>
          <td style="font-weight:700; color: ${t.transaction_type === "credit" ? "var(--accent-primary)" : "var(--accent-rose)"};">
            ${t.transaction_type === "credit" ? "+" : "-"}${formatINR(t.amount, t.currency_symbol)}
          </td>
          <td style="font-family:var(--font-mono);">${formatINR(t.running_balance, t.currency_symbol)}</td>
        </tr>
      `).join("");
    }

    const distBox = document.getElementById("account-type-distribution");
    distBox.innerHTML = data.account_distribution.map(d => {
      const pct = data.total_balance > 0 ? Math.min(100, Math.round((d.total_balance / data.total_balance) * 100)) : 0;
      return `
        <div>
          <div style="display:flex; justify-content:space-between; font-size:12px; margin-bottom:4px;">
            <span>${escapeHtml(d.type_name)} (${d.count})</span>
            <span style="font-weight:600;">${formatINR(d.total_balance)} (${pct}%)</span>
          </div>
          <div style="background:rgba(255,255,255,0.06); height:6px; border-radius:3px; overflow:hidden;">
            <div style="width:${pct}%; background:var(--accent-secondary); height:100%;"></div>
          </div>
        </div>
      `;
    }).join("");

    const bbody = document.getElementById("dashboard-branches-table");
    bbody.innerHTML = data.branch_stats.map(b => `
      <tr>
        <td><strong style="font-family:var(--font-mono);">${escapeHtml(b.branch_code)}</strong></td>
        <td><span class="role-chip">${escapeHtml(b.bank_short_code)}</span></td>
        <td>${escapeHtml(b.branch_name)}</td>
        <td>${b.employee_count} Personnel</td>
        <td><strong>${b.customer_accounts_managed} Accounts</strong></td>
      </tr>
    `).join("");
  } catch (err) {
    console.error("Dashboard load failed", err);
  }
}

// ---------------- 2. CUSTOMERS ---------------- #

async function fetchCustomers() {
  const query = document.getElementById("customer-search-input") ? document.getElementById("customer-search-input").value : "";
  try {
    const json = await apiFetch(scopedUrl(`/api/customers?q=${encodeURIComponent(query)}`));
    const tbody = document.getElementById("customers-table-body");
    if (!json.success || json.data.length === 0) {
      tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding:30px;">No customers found</td></tr>`;
      return;
    }

    tbody.innerHTML = json.data.map(c => {
      let scoreColor = "#10b981";
      if (c.credit_score < 700) scoreColor = "#f59e0b";
      if (c.credit_score < 650) scoreColor = "#f43f5e";

      return `
        <tr>
          <td><strong style="font-family:var(--font-mono); color:#58a6ff;">${escapeHtml(c.customer_id)}</strong></td>
          <td><span class="role-chip">${escapeHtml(c.bank_short_code || "-")}</span></td>
          <td>
            <div style="font-weight:600;">${escapeHtml(c.first_name)} ${escapeHtml(c.last_name)}</div>
            <div style="font-size:11px; color:var(--text-muted);">${escapeHtml(c.address || "N/A")}</div>
          </td>
          <td>
            <div>${escapeHtml(c.email)}</div>
            <div style="font-size:11px; color:var(--text-muted); font-family:var(--font-mono);">${escapeHtml(c.phone)}</div>
          </td>
          <td>
            <span class="badge" style="background:rgba(255,255,255,0.05); color:${scoreColor}; border:1px solid ${scoreColor}; font-family:var(--font-mono);">
              ★ ${escapeHtml(c.credit_score)}
            </span>
          </td>
          <td>${escapeHtml(c.rm_name || "Unassigned")}</td>
          <td>${c.accounts_count} accounts</td>
          <td style="font-weight:700; color:var(--accent-primary);">${formatINR(c.total_customer_balance, c.currency_symbol)}</td>
          <td>
            <button class="btn btn-secondary btn-sm" onclick="viewCustomerDossier('${escapeHtml(c.customer_id)}')">Dossier</button>
          </td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    console.error("Fetch customers failed", err);
  }
}

async function viewCustomerDossier(custId) {
  try {
    const json = await apiFetch(`/api/customers/${encodeURIComponent(custId)}`);
    if (!json.success) return showToast(json.error, "error");

    const c = json.data;
    document.getElementById("cust-detail-title").innerText = `Customer Dossier: ${c.first_name} ${c.last_name} (${c.customer_id})`;

    const accountsHtml = c.accounts.map(a => `
      <div style="background:rgba(0,0,0,0.3); padding:12px; border-radius:8px; margin-bottom:8px; display:flex; justify-content:space-between; align-items:center;">
        <div>
          <strong style="font-family:var(--font-mono);">${escapeHtml(a.account_number)}</strong> - ${escapeHtml(a.type_name)}
          <div style="font-size:11px; color:var(--text-muted);">Opened: ${escapeHtml(a.opening_date)} • Overdraft: ${formatINR(a.overdraft_limit, c.currency_symbol)}</div>
        </div>
        <div style="text-align:right;">
          <div style="font-weight:700; color:var(--accent-primary);">${formatINR(a.balance, c.currency_symbol)}</div>
          <span class="badge badge-${escapeHtml(a.status)}">${escapeHtml(a.status)}</span>
        </div>
      </div>
    `).join("") || '<p style="color:var(--text-muted);">No accounts found</p>';

    const cardsHtml = c.cards.map(cd => `
      <div style="display:inline-block; background:rgba(255,255,255,0.05); padding:8px 12px; border-radius:6px; margin:4px; font-size:12px;">
        💳 <strong>${escapeHtml(cd.card_number_masked)}</strong> (${escapeHtml(cd.card_type.toUpperCase())}) - <span class="badge badge-${escapeHtml(cd.status)}">${escapeHtml(cd.status)}</span>
      </div>
    `).join("") || '<p style="color:var(--text-muted);">No cards issued</p>';

    const loansHtml = c.loans.map(l => `
      <div style="background:rgba(0,0,0,0.3); padding:10px; border-radius:8px; margin-bottom:6px; display:flex; justify-content:space-between; font-size:12px;">
        <div><strong>${escapeHtml(l.loan_number)}</strong> (${escapeHtml(l.loan_type.toUpperCase())}) • Term: ${l.term_months}mo • EMI: ${formatINR(l.monthly_payment, c.currency_symbol)}</div>
        <div>Outstanding: <strong>${formatINR(l.outstanding_balance, c.currency_symbol)}</strong> <span class="badge badge-${l.status === "running" ? "active" : "closed"}">${escapeHtml(l.status)}</span></div>
      </div>
    `).join("") || '<p style="color:var(--text-muted);">No active loans</p>';

    document.getElementById("cust-detail-body").innerHTML = `
      <div style="display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:20px; font-size:13px;">
        <div>
          <div><strong>Bank:</strong> ${escapeHtml(c.company_name || c.company_code || "-")}</div>
          <div><strong>Email:</strong> ${escapeHtml(c.email)}</div>
          <div><strong>Phone:</strong> ${escapeHtml(c.phone)}</div>
          <div><strong>DOB:</strong> ${escapeHtml(c.date_of_birth)}</div>
          <div><strong>Govt ID:</strong> ${escapeHtml(c.id_number)}</div>
        </div>
        <div>
          <div><strong>Credit Score:</strong> <span style="font-weight:700; color:var(--accent-primary);">${escapeHtml(c.credit_score)}</span></div>
          <div><strong>Assigned RM:</strong> ${escapeHtml(c.rm_name || "N/A")}</div>
          <div><strong>Home Branch:</strong> ${escapeHtml(c.branch_name || "N/A")}</div>
          <div><strong>Member Since:</strong> ${escapeHtml(c.registration_date)}</div>
        </div>
      </div>

      <h4 style="font-size:14px; margin-bottom:10px; border-bottom:1px solid var(--border-color); padding-bottom:6px;">Linked Bank Accounts</h4>
      ${accountsHtml}

      <h4 style="font-size:14px; margin:16px 0 10px; border-bottom:1px solid var(--border-color); padding-bottom:6px;">Payment Cards</h4>
      <div>${cardsHtml}</div>

      <h4 style="font-size:14px; margin:16px 0 10px; border-bottom:1px solid var(--border-color); padding-bottom:6px;">Credit & Loans</h4>
      ${loansHtml}
    `;

    openModal("modal-customer-detail");
  } catch (err) {
    showToast("Error retrieving dossier", "error");
  }
}

// ---------------- 3. ACCOUNTS ---------------- #

async function fetchAccounts() {
  const query = document.getElementById("account-search-input") ? document.getElementById("account-search-input").value : "";
  try {
    const json = await apiFetch(scopedUrl(`/api/accounts?q=${encodeURIComponent(query)}`));
    const tbody = document.getElementById("accounts-table-body");
    if (!json.success || json.data.length === 0) {
      tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding:30px;">No accounts found</td></tr>`;
      return;
    }

    const canTransact = !!(currentUser && currentUser.permissions.can_transact);
    const canFreeze = !!(currentUser && currentUser.permissions.can_freeze_accounts);

    tbody.innerHTML = json.data.map(a => `
      <tr>
        <td><strong style="font-family:var(--font-mono); color:#58a6ff;">${escapeHtml(a.account_number)}</strong></td>
        <td><span class="role-chip">${escapeHtml(a.bank_short_code || "-")}</span></td>
        <td>
          <div style="font-weight:600;">${escapeHtml(a.customer_name)}</div>
          <div style="font-size:11px; color:var(--text-muted);">${escapeHtml(a.customer_id)}</div>
        </td>
        <td>
          <div>${escapeHtml(a.type_name)}</div>
          <div style="font-size:11px; color:var(--text-muted);">${(a.interest_rate * 100).toFixed(2)}% p.a.</div>
        </td>
        <td style="font-weight:700; font-size:14px; color:${a.balance >= 0 ? "var(--text-main)" : "var(--accent-rose)"};">
          ${formatINR(a.balance, a.currency_symbol)}
        </td>
        <td style="font-family:var(--font-mono);">${formatINR(a.overdraft_limit, a.currency_symbol)}</td>
        <td>${escapeHtml(a.opening_date)}</td>
        <td><span class="badge badge-${escapeHtml(a.status)}">${escapeHtml(a.status)}</span></td>
        <td>
          <div style="display:flex; gap:6px;">
            <button class="btn btn-secondary btn-sm" ${canTransact ? "" : "disabled"} onclick="quickTransact('${escapeHtml(a.account_number)}')">Transact</button>
            <select class="form-control" style="width:92px; padding:4px 6px; font-size:11px;" ${canFreeze ? "" : "disabled"} onchange="changeAccountStatus('${escapeHtml(a.account_number)}', this.value)">
              <option value="active" ${a.status === "active" ? "selected" : ""}>Active</option>
              <option value="frozen" ${a.status === "frozen" ? "selected" : ""}>Freeze</option>
              <option value="closed" ${a.status === "closed" ? "selected" : ""}>Close</option>
            </select>
          </div>
        </td>
      </tr>
    `).join("");
  } catch (err) {
    console.error("Fetch accounts failed", err);
  }
}

async function changeAccountStatus(accNo, newStatus) {
  try {
    const json = await apiFetch(`/api/accounts/${encodeURIComponent(accNo)}/status`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: newStatus })
    });
    if (json.success) {
      showToast(json.message);
      fetchAccounts();
    } else {
      showToast(json.error, "error");
      fetchAccounts();
    }
  } catch (err) {
    showToast("Failed to update account status", "error");
  }
}

function quickTransact(accNo) {
  openDepositWithdrawModal("deposit");
  const sel = document.getElementById("dw-account");
  if (sel) sel.value = accNo;
}

// ---------------- 4. TRANSACTIONS ---------------- #

async function fetchTransactions() {
  const typeFilter = document.getElementById("txn-filter-type") ? document.getElementById("txn-filter-type").value : "";
  try {
    const json = await apiFetch(scopedUrl(`/api/transactions?type=${encodeURIComponent(typeFilter)}`));
    const tbody = document.getElementById("transactions-table-body");
    if (!json.success || json.data.length === 0) {
      tbody.innerHTML = `<tr><td colspan="11" style="text-align:center; padding:30px;">No transactions recorded</td></tr>`;
      return;
    }

    tbody.innerHTML = json.data.map(t => `
      <tr>
        <td><strong style="font-family:var(--font-mono); color:#58a6ff;">${escapeHtml(t.transaction_reference)}</strong></td>
        <td><span class="role-chip">${escapeHtml(t.bank_short_code || "-")}</span></td>
        <td style="font-family:var(--font-mono);">${escapeHtml(t.account_number)}</td>
        <td>${escapeHtml(t.customer_name)}</td>
        <td style="font-family:var(--font-mono); font-size:11px;">${escapeHtml(t.performed_by)} <span style="color:var(--text-dim);">(${escapeHtml(t.operator_role)})</span></td>
        <td>${escapeHtml(t.category_name || t.category_code)}</td>
        <td>
          <span class="badge badge-${escapeHtml(t.transaction_type)}">
            ${t.transaction_type === "credit" ? "↓ Credit" : "↑ Debit"}
          </span>
        </td>
        <td style="font-weight:700; color:${t.transaction_type === "credit" ? "var(--accent-primary)" : "var(--accent-rose)"};">
          ${t.transaction_type === "credit" ? "+" : "-"}${formatINR(t.amount, t.currency_symbol)}
        </td>
        <td style="font-family:var(--font-mono);">${formatINR(t.running_balance, t.currency_symbol)}</td>
        <td style="color:var(--text-muted); max-width:200px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
          ${escapeHtml(t.description || "-")}
        </td>
        <td style="font-size:11px; color:var(--text-muted); font-family:var(--font-mono);">${escapeHtml(t.transaction_date)}</td>
      </tr>
    `).join("");
  } catch (err) {
    console.error("Fetch transactions failed", err);
  }
}

// ---------------- 5. CARDS ---------------- #

async function fetchCards() {
  try {
    const json = await apiFetch(scopedUrl("/api/cards"));
    const container = document.getElementById("cards-container");
    if (!json.success || json.data.length === 0) {
      container.innerHTML = `<div style="grid-column: 1/-1; text-align:center; padding:40px; color:var(--text-muted);">No payment cards issued yet.</div>`;
      return;
    }

    const canManageCards = !!(currentUser && currentUser.permissions.can_manage_cards);

    container.innerHTML = json.data.map(cd => `
      <div class="virtual-card ${escapeHtml(cd.card_type)}">
        <div class="card-top">
          <div class="card-chip"></div>
          <div style="font-weight:800; font-size:13px; letter-spacing:1px; text-transform:uppercase;">
            ${escapeHtml(cd.bank_short_code || "")} • ${escapeHtml(cd.card_type)} CARD
          </div>
        </div>
        <div class="card-number">${escapeHtml(cd.card_number_masked)}</div>
        <div class="card-bottom">
          <div>
            <div style="font-size:9px; text-transform:uppercase; opacity:0.8;">Cardholder</div>
            <div class="card-holder">${escapeHtml(cd.customer_name)}</div>
          </div>
          <div style="text-align:right;">
            <div style="font-size:9px; text-transform:uppercase; opacity:0.8;">Expires</div>
            <div class="card-expiry">${escapeHtml(cd.expiry_date)}</div>
          </div>
        </div>
        <div style="display:flex; justify-content:space-between; align-items:center; margin-top:10px; padding-top:10px; border-top:1px solid rgba(255,255,255,0.1);">
          <span class="badge badge-${escapeHtml(cd.status)}">${escapeHtml(cd.status)}</span>
          <div style="display:flex; gap:6px;">
            ${cd.status === "active" ? `
              <button class="btn btn-secondary btn-sm" style="padding:2px 8px; font-size:10px;" ${canManageCards ? "" : "disabled"} onclick="updateCardStatus('${escapeHtml(cd.card_id)}', 'blocked')">Block Card</button>
            ` : `
              <button class="btn btn-primary btn-sm" style="padding:2px 8px; font-size:10px;" ${canManageCards ? "" : "disabled"} onclick="updateCardStatus('${escapeHtml(cd.card_id)}', 'active')">Unblock</button>
            `}
          </div>
        </div>
      </div>
    `).join("");
  } catch (err) {
    console.error("Fetch cards failed", err);
  }
}

async function updateCardStatus(cardId, newStatus) {
  try {
    const json = await apiFetch(`/api/cards/${encodeURIComponent(cardId)}/status`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: newStatus })
    });
    if (json.success) {
      showToast(json.message);
      fetchCards();
    } else {
      showToast(json.error, "error");
    }
  } catch (err) {
    showToast("Error updating card", "error");
  }
}

// ---------------- 6. LOANS ---------------- #

async function fetchLoans() {
  try {
    const json = await apiFetch(scopedUrl("/api/loans"));
    const tbody = document.getElementById("loans-table-body");
    if (!json.success || json.data.length === 0) {
      tbody.innerHTML = `<tr><td colspan="12" style="text-align:center; padding:30px;">No loan accounts found</td></tr>`;
      return;
    }

    const canRepay = !!(currentUser && currentUser.permissions.can_repay_loans);

    tbody.innerHTML = json.data.map(l => {
      const paidPct = l.principal_amount > 0 ? Math.max(0, Math.min(100, Math.round(((l.principal_amount - l.outstanding_balance) / l.principal_amount) * 100))) : 0;
      return `
        <tr>
          <td><strong style="font-family:var(--font-mono); color:#58a6ff;">${escapeHtml(l.loan_number)}</strong></td>
          <td><span class="role-chip">${escapeHtml(l.bank_short_code || "-")}</span></td>
          <td>
            <div style="font-weight:600;">${escapeHtml(l.customer_name)}</div>
            <div style="font-size:11px; color:var(--text-muted); font-family:var(--font-mono);">${escapeHtml(l.customer_id)}</div>
          </td>
          <td><span style="text-transform:capitalize;">${escapeHtml(l.loan_type)}</span></td>
          <td style="font-weight:600;">${formatINR(l.principal_amount, l.currency_symbol)}</td>
          <td>${(l.interest_rate * 100).toFixed(2)}%</td>
          <td>${l.term_months} mos</td>
          <td style="font-weight:700; color:var(--accent-amber);">${formatINR(l.monthly_payment, l.currency_symbol)}</td>
          <td>
            <div style="font-weight:700;">${formatINR(l.outstanding_balance, l.currency_symbol)}</div>
            <div style="font-size:10px; color:var(--text-muted);">${paidPct}% amortized</div>
          </td>
          <td style="font-family:var(--font-mono); font-size:11px;">${escapeHtml(l.approved_by)}</td>
          <td><span class="badge badge-${l.status === "running" ? "active" : (l.status === "closed" ? "closed" : "frozen")}">${escapeHtml(l.status)}</span></td>
          <td>
            ${l.status === "running" ? `
              <button class="btn btn-secondary btn-sm" ${canRepay ? "" : "disabled"} onclick="quickRepayLoan('${escapeHtml(l.loan_number)}', ${l.monthly_payment})">Repay EMI</button>
            ` : '<span style="color:var(--text-dim);">-</span>'}
          </td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    console.error("Fetch loans failed", err);
  }
}

function quickRepayLoan(loanNum, monthlyPayment) {
  openRepayLoanModal();
  setTimeout(() => {
    const sel = document.getElementById("repay-loan-num");
    if (sel) sel.value = loanNum;
    const amt = document.getElementById("repay-loan-amount");
    if (amt) amt.value = monthlyPayment;
  }, 150);
}

// ---------------- 7. BRANCHES & STAFF ---------------- #

async function fetchBranchesAndStaff() {
  try {
    const [bJson, eJson] = await Promise.all([
      apiFetch(scopedUrl("/api/branches")),
      apiFetch(scopedUrl("/api/employees"))
    ]);

    const bbody = document.getElementById("branches-list-table");
    if (bJson.success) {
      bbody.innerHTML = bJson.data.map(b => `
        <tr>
          <td><strong style="font-family:var(--font-mono); color:#58a6ff;">${escapeHtml(b.branch_code)}</strong></td>
          <td><strong>${escapeHtml(b.branch_name)}</strong></td>
          <td>${escapeHtml(b.company_name)} <span class="role-chip">${escapeHtml(b.bank_short_code)}</span></td>
          <td style="font-size:12px; color:var(--text-muted);">${escapeHtml(b.address)}</td>
          <td style="font-family:var(--font-mono); font-size:12px;">${escapeHtml(b.phone)}</td>
          <td>${escapeHtml(b.manager_name)}</td>
          <td style="font-size:11px;">${escapeHtml(b.opening_hours)} - ${escapeHtml(b.closing_hours)}</td>
          <td><span class="badge badge-active">${b.employee_count} Employees</span></td>
        </tr>
      `).join("");
    }

    const ebody = document.getElementById("employees-list-table");
    if (eJson.success) {
      ebody.innerHTML = eJson.data.map(e => `
        <tr>
          <td><strong style="font-family:var(--font-mono); color:#58a6ff;">${escapeHtml(e.employee_id)}</strong></td>
          <td><span class="role-chip">${escapeHtml(e.bank_short_code || "-")}</span></td>
          <td><strong>${escapeHtml(e.first_name)} ${escapeHtml(e.last_name)}</strong></td>
          <td>${escapeHtml(e.department)}</td>
          <td>${escapeHtml(e.position)}</td>
          <td>${escapeHtml(e.branch_name || e.branch_code)}</td>
          <td>${e.operator_username ? `<span style="font-family:var(--font-mono); font-size:11px;">${escapeHtml(e.operator_username)}</span> <span class="role-chip">${escapeHtml(e.operator_role)}</span>` : '<span style="color:var(--text-dim);">No DB login</span>'}</td>
          <td style="font-weight:700;">${formatINR(e.salary)}</td>
        </tr>
      `).join("");
    }
  } catch (err) {
    console.error("Fetch branches and staff failed", err);
  }
}

// ---------------- 8. MULTI-BANK REGISTRY ---------------- #

async function fetchBanksRegistry() {
  try {
    const [cJson, atJson] = await Promise.all([
      apiFetch("/api/companies"),
      apiFetch(scopedUrl("/api/account-types"))
    ]);

    const grid = document.getElementById("banks-grid");
    if (cJson.success) {
      const canManageBanks = !!(currentUser && currentUser.permissions.can_manage_banks);
      grid.innerHTML = cJson.data.map(c => `
        <div class="bank-card">
          <div class="bank-card-accent" style="background:${escapeHtml(c.brand_color || "#10b981")};"></div>
          <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:10px;">
            <div>
              <div style="font-size:16px; font-weight:700;">${escapeHtml(c.company_name)}</div>
              <div style="font-size:11px; color:var(--text-muted); font-family:var(--font-mono);">
                ${escapeHtml(c.company_code)} • ${escapeHtml(c.short_code)} • SWIFT: ${escapeHtml(c.swift_code || "-")}
              </div>
            </div>
            <span class="badge badge-${c.status === "active" ? "active" : "closed"}">${escapeHtml(c.status)}</span>
          </div>
          <div style="font-size:12px; color:var(--text-muted); margin-bottom:14px;">${escapeHtml(c.headquarters_address || "HQ Address N/A")}</div>
          <div style="display:grid; grid-template-columns:repeat(3,1fr); gap:8px; font-size:11px; background:rgba(0,0,0,0.25); padding:10px; border-radius:8px; margin-bottom:12px;">
            <div><div style="color:var(--text-dim);">Branches</div><strong>${c.branch_count}</strong></div>
            <div><div style="color:var(--text-dim);">Customers</div><strong>${c.customer_count}</strong></div>
            <div><div style="color:var(--text-dim);">Currency</div><strong>${escapeHtml(c.currency_code)} (${escapeHtml(c.currency_symbol)})</strong></div>
          </div>
          <div style="display:flex; justify-content:space-between; align-items:center; font-size:12px;">
            <div>Deposits: <strong style="color:var(--accent-primary);">${formatINR(c.total_deposits, c.currency_symbol)}</strong></div>
            ${canManageBanks ? `
              <button class="btn btn-secondary btn-sm" onclick="toggleBankStatus('${escapeHtml(c.company_code)}', '${c.status === "active" ? "inactive" : "active"}')">
                ${c.status === "active" ? "Deactivate" : "Activate"}
              </button>
            ` : ""}
          </div>
        </div>
      `).join("");
    }

    const atBody = document.getElementById("account-types-table");
    if (atJson.success) {
      atBody.innerHTML = atJson.data.map(t => `
        <tr>
          <td><strong style="font-family:var(--font-mono); color:#58a6ff;">${escapeHtml(t.account_type_code)}</strong></td>
          <td><span class="role-chip">${escapeHtml(t.scope_label)}</span></td>
          <td><strong>${escapeHtml(t.type_name)}</strong></td>
          <td>${formatINR(t.minimum_balance)}</td>
          <td>${(t.interest_rate * 100).toFixed(2)}%</td>
          <td>${t.allows_overdraft ? '<span class="perm-yes">Yes</span>' : '<span class="perm-no">No</span>'}</td>
          <td style="font-size:12px; color:var(--text-muted);">${escapeHtml(t.description)}</td>
        </tr>
      `).join("");
    }
  } catch (err) {
    console.error("Failed loading banks registry", err);
  }
}

async function toggleBankStatus(compCode, newStatus) {
  const json = await apiFetch(`/api/companies/${encodeURIComponent(compCode)}/status`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status: newStatus })
  });
  if (json.success) {
    showToast(json.message);
    fetchBanksRegistry();
    fetchMetadata();
  } else {
    showToast(json.error, "error");
  }
}

// ---------------- 9. ACCESS CONTROL & AUDIT ---------------- #

async function fetchRbacAndAudit() {
  try {
    const rJson = await apiFetch("/api/roles");
    if (rJson.success) {
      const flag = v => v ? `<span class="perm-yes">✓</span>` : `<span class="perm-no">—</span>`;
      document.getElementById("rbac-matrix-body").innerHTML = rJson.data.map(r => `
        <tr>
          <td>
            <div style="font-weight:700;">${escapeHtml(r.role_name)}</div>
            <div style="font-size:10px; font-family:var(--font-mono); color:var(--text-muted);">${escapeHtml(r.role_code)}</div>
          </td>
          <td style="font-family:var(--font-mono);">${r.hierarchy_level}</td>
          <td>${flag(r.can_manage_banks)}</td>
          <td>${flag(r.can_manage_staff)}</td>
          <td>${flag(r.can_manage_customers)}</td>
          <td>${flag(r.can_manage_accounts)}</td>
          <td>${flag(r.can_freeze_accounts)}</td>
          <td>${flag(r.can_transact)}</td>
          <td>${flag(r.can_manage_cards)}</td>
          <td>${flag(r.can_sanction_loans)}</td>
          <td>${flag(r.can_repay_loans)}</td>
          <td>${flag(r.can_run_sql_read)}</td>
          <td>${flag(r.can_run_sql_write)}</td>
          <td>${flag(r.can_view_audit)}</td>
        </tr>
      `).join("");
    }

    if (currentUser && (currentUser.permissions.can_manage_staff || currentUser.permissions.can_view_audit)) {
      const oJson = await apiFetch(scopedUrl("/api/operators"));
      const opBody = document.getElementById("operators-table-body");
      if (oJson.success) {
        const canEdit = !!currentUser.permissions.can_manage_staff;
        opBody.innerHTML = oJson.data.map(op => `
          <tr>
            <td><strong style="font-family:var(--font-mono); color:#58a6ff;">${escapeHtml(op.operator_id)}</strong></td>
            <td style="font-family:var(--font-mono);">${escapeHtml(op.username)}</td>
            <td><strong>${escapeHtml(op.full_name)}</strong></td>
            <td><span class="role-chip">${escapeHtml(op.role_code)}</span></td>
            <td>${escapeHtml(op.bank_short_code)} — ${escapeHtml(op.company_name)}</td>
            <td>${escapeHtml(op.branch_name || "-")}</td>
            <td><span class="badge badge-${op.is_active ? "active" : "closed"}">${op.is_active ? "Active" : "Disabled"}</span></td>
            <td style="font-size:11px; color:var(--text-muted); font-family:var(--font-mono);">${escapeHtml(op.last_login || "Never")}</td>
            <td>
              ${canEdit && op.operator_id !== currentUser.operator_id ? `
                <button class="btn btn-secondary btn-sm" onclick="toggleOperatorStatus('${escapeHtml(op.operator_id)}', ${op.is_active ? 0 : 1})">
                  ${op.is_active ? "Disable" : "Enable"}
                </button>
              ` : '<span style="color:var(--text-dim);">-</span>'}
            </td>
          </tr>
        `).join("");
      }
    }

    if (currentUser && currentUser.permissions.can_view_audit) {
      await fetchAuditLogs();
    }
  } catch (err) {
    console.error("Failed loading RBAC & Audit", err);
  }
}

async function fetchAuditLogs() {
  if (!currentUser || !currentUser.permissions.can_view_audit) return;
  const status = document.getElementById("audit-status-filter") ? document.getElementById("audit-status-filter").value : "";
  try {
    const json = await apiFetch(scopedUrl(`/api/audit-logs?status=${encodeURIComponent(status)}`));
    const tbody = document.getElementById("audit-logs-body");
    if (!json.success || json.data.length === 0) {
      tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding:24px; color:var(--text-muted);">No audit records found</td></tr>`;
      return;
    }
    tbody.innerHTML = json.data.map(a => `
      <tr>
        <td style="font-family:var(--font-mono);">#${a.log_id}</td>
        <td style="font-family:var(--font-mono);">${escapeHtml(a.operator_username || "system")}</td>
        <td><span class="role-chip">${escapeHtml(a.role_code || "-")}</span></td>
        <td>${escapeHtml(a.bank_short_code || a.company_code || "ALL")}</td>
        <td><strong>${escapeHtml(a.action)}</strong></td>
        <td style="font-family:var(--font-mono); font-size:11px;">${escapeHtml(a.target_table || "-")} ${a.target_id ? `(${escapeHtml(a.target_id)})` : ""}</td>
        <td><span class="badge badge-${escapeHtml(a.status)}">${escapeHtml(a.status)}</span></td>
        <td style="font-size:12px; color:var(--text-muted); max-width:260px;">${escapeHtml(a.details || "-")}</td>
        <td style="font-size:11px; font-family:var(--font-mono); color:var(--text-muted);">${escapeHtml(a.created_at)}</td>
      </tr>
    `).join("");
  } catch (err) {
    console.error("Audit log fetch error", err);
  }
}

async function toggleOperatorStatus(opId, isActive) {
  const json = await apiFetch(`/api/operators/${encodeURIComponent(opId)}/status`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ is_active: isActive })
  });
  if (json.success) {
    showToast(json.message);
    fetchRbacAndAudit();
  } else {
    showToast(json.error, "error");
  }
}

// ---------------- 10. SQL STUDIO ---------------- #

async function executeSQLQuery() {
  const query = document.getElementById("sql-input").value.trim();
  const timerLabel = document.getElementById("query-timer");
  const resultsContainer = document.getElementById("sql-results-container");
  const thead = document.getElementById("sql-results-head");
  const tbody = document.getElementById("sql-results-body");
  const errorBox = document.getElementById("sql-error-box");

  if (!query) return showToast("Please input an SQL query", "error");

  timerLabel.innerText = "Executing...";
  errorBox.style.display = "none";
  resultsContainer.style.display = "none";

  try {
    const json = await apiFetch("/api/sql", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query })
    });

    if (!json.success) {
      timerLabel.innerText = "Error / Denied";
      errorBox.innerText = json.error;
      errorBox.style.display = "block";
      return;
    }

    timerLabel.innerText = `${json.row_count} rows in ${json.execution_time_ms} ms`;
    resultsContainer.style.display = "block";

    thead.innerHTML = `<tr>${json.columns.map(col => `<th>${escapeHtml(col)}</th>`).join("")}</tr>`;

    if (json.rows.length === 0) {
      tbody.innerHTML = `<tr><td colspan="${json.columns.length}" style="text-align:center; padding:20px; color:var(--text-muted);">Query returned 0 rows</td></tr>`;
    } else {
      tbody.innerHTML = json.rows.map(row => `
        <tr>
          ${row.map(val => `<td style="font-family:var(--font-mono);">${val !== null ? escapeHtml(val) : '<em style="color:var(--text-dim);">NULL</em>'}</td>`).join("")}
        </tr>
      `).join("");
    }
  } catch (err) {
    timerLabel.innerText = "Network Error";
    errorBox.innerText = err.message;
    errorBox.style.display = "block";
  }
}

function setPresetQuery(num) {
  const presets = {
    1: `SELECT 'companies' AS table_name, COUNT(*) AS record_count FROM companies
UNION ALL SELECT 'roles', COUNT(*) FROM roles
UNION ALL SELECT 'branches', COUNT(*) FROM branches
UNION ALL SELECT 'employees', COUNT(*) FROM employees
UNION ALL SELECT 'operators', COUNT(*) FROM operators
UNION ALL SELECT 'customers', COUNT(*) FROM customers
UNION ALL SELECT 'account_types', COUNT(*) FROM account_types
UNION ALL SELECT 'accounts', COUNT(*) FROM accounts
UNION ALL SELECT 'transaction_categories', COUNT(*) FROM transaction_categories
UNION ALL SELECT 'transactions', COUNT(*) FROM transactions
UNION ALL SELECT 'loans', COUNT(*) FROM loans
UNION ALL SELECT 'cards', COUNT(*) FROM cards
UNION ALL SELECT 'audit_logs', COUNT(*) FROM audit_logs;`,
    2: `SELECT comp.short_code AS bank, c.customer_id, c.first_name || ' ' || c.last_name AS customer_name,
       a.account_number, at.type_name, a.balance, comp.currency_code
FROM accounts a
JOIN customers c ON a.customer_id = c.customer_id
JOIN account_types at ON a.account_type_code = at.account_type_code
LEFT JOIN companies comp ON a.company_code = comp.company_code
ORDER BY a.balance DESC
LIMIT 12;`,
    3: `SELECT comp.short_code, comp.company_name, b.branch_code, b.branch_name, b.manager_name,
       COUNT(DISTINCT e.employee_id) AS total_employees,
       COALESCE(SUM(e.salary), 0) AS monthly_payroll
FROM branches b
JOIN companies comp ON b.company_code = comp.company_code
LEFT JOIN employees e ON b.branch_code = e.branch_code
GROUP BY b.branch_code;`,
    4: `SELECT loan_type, COUNT(*) AS count,
       SUM(principal_amount) AS total_principal,
       SUM(outstanding_balance) AS total_outstanding,
       ROUND(AVG(interest_rate) * 100, 2) AS avg_interest_rate_pct
FROM loans
GROUP BY loan_type;`,
    5: `SELECT cd.card_id, cd.card_number_masked, cd.card_type, cd.credit_limit,
       c.first_name || ' ' || c.last_name AS cardholder, cd.status
FROM cards cd
JOIN customers c ON cd.customer_id = c.customer_id
WHERE cd.credit_limit >= 100000;`,
    6: `SELECT log_id, operator_username, role_code, COALESCE(company_code, 'ALL') AS bank,
       action, target_table, target_id, status, details, created_at
FROM audit_logs
ORDER BY log_id DESC
LIMIT 20;`
  };

  const editor = document.getElementById("sql-input");
  if (editor && presets[num]) {
    editor.value = presets[num];
    executeSQLQuery();
  }
}

// ---------------- MODALS & MUTATIONS ---------------- #

function openTransferModal() {
  populateDropdowns();
  openModal("modal-transfer");
}

async function submitFundTransfer() {
  const from_account = document.getElementById("transfer-src-account").value;
  const to_account = document.getElementById("transfer-dst-account").value;
  const amount = parseFloat(document.getElementById("transfer-amount").value);
  const description = document.getElementById("transfer-desc").value.trim();

  if (isNaN(amount) || amount <= 0) return showToast("Enter a valid amount", "error");
  if (from_account === to_account) return showToast("Source and destination must differ", "error");

  try {
    const json = await apiFetch("/api/transact", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "transfer", from_account, to_account, amount, description })
    });
    if (json.success) {
      showToast(json.message);
      closeModal("modal-transfer");
      document.getElementById("transfer-amount").value = "";
      document.getElementById("transfer-desc").value = "";
      reloadAllActiveData();
    } else {
      showToast(json.error, "error");
    }
  } catch (err) {
    showToast("Transfer network error", "error");
  }
}

function openDepositWithdrawModal(action) {
  populateDropdowns();
  document.getElementById("dw-action").value = action;
  document.getElementById("deposit-withdraw-title").innerText = action === "deposit" ? "Cash / Cheque Deposit" : "Cash / ATM Withdrawal";
  document.getElementById("dw-submit-btn").innerText = action === "deposit" ? "Complete Deposit" : "Complete Withdrawal";
  openModal("modal-deposit-withdraw");
}

async function submitDepositWithdraw() {
  const action = document.getElementById("dw-action").value;
  const account_number = document.getElementById("dw-account").value;
  const amount = parseFloat(document.getElementById("dw-amount").value);
  const category_code = document.getElementById("dw-category").value;
  const description = document.getElementById("dw-desc").value.trim();

  if (isNaN(amount) || amount <= 0) return showToast("Enter a valid amount", "error");

  try {
    const json = await apiFetch("/api/transact", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, account_number, amount, category_code, description })
    });
    if (json.success) {
      showToast(json.message);
      closeModal("modal-deposit-withdraw");
      document.getElementById("dw-amount").value = "";
      document.getElementById("dw-desc").value = "";
      reloadAllActiveData();
    } else {
      showToast(json.error, "error");
    }
  } catch (err) {
    showToast("Transaction network error", "error");
  }
}

function openAccountModal() {
  populateDropdowns();
  openModal("modal-account");
}

async function submitNewAccount() {
  const customer_id = document.getElementById("newacc-customer").value;
  const account_type_code = document.getElementById("newacc-type").value;
  const initial_deposit = parseFloat(document.getElementById("newacc-deposit").value || 0);
  const overdraft_limit = parseFloat(document.getElementById("newacc-overdraft").value || 0);

  try {
    const json = await apiFetch("/api/accounts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ customer_id, account_type_code, initial_deposit, overdraft_limit })
    });
    if (json.success) {
      showToast(`Account ${json.account_number} created successfully!`);
      closeModal("modal-account");
      reloadAllActiveData();
    } else {
      showToast(json.error, "error");
    }
  } catch (err) {
    showToast("Error creating account", "error");
  }
}

function openCustomerModal() {
  populateDropdowns();
  openModal("modal-customer");
}

async function submitNewCustomer() {
  const company_code = document.getElementById("cust-company").value;
  const first_name = document.getElementById("cust-fname").value.trim();
  const last_name = document.getElementById("cust-lname").value.trim();
  const email = document.getElementById("cust-email").value.trim();
  const phone = document.getElementById("cust-phone").value.trim();
  const date_of_birth = document.getElementById("cust-dob").value;
  const id_number = document.getElementById("cust-idnum").value.trim();
  const credit_score = parseFloat(document.getElementById("cust-cscore").value || 700);
  const relationship_manager_id = document.getElementById("cust-rm").value;
  const address = document.getElementById("cust-address").value.trim();

  if (!first_name || !last_name || !email || !date_of_birth) {
    return showToast("Please fill all required customer fields", "error");
  }

  try {
    const json = await apiFetch("/api/customers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        company_code, first_name, last_name, email, phone, date_of_birth,
        id_number, credit_score, relationship_manager_id, address
      })
    });
    if (json.success) {
      showToast(json.message);
      closeModal("modal-customer");
      reloadAllActiveData();
    } else {
      showToast(json.error, "error");
    }
  } catch (err) {
    showToast("Error creating customer", "error");
  }
}

function openCardModal() {
  populateDropdowns();
  openModal("modal-card");
}

async function submitIssueCard() {
  const linked_account_number = document.getElementById("card-account").value;
  const card_type = document.getElementById("card-type").value;
  const credit_limit = parseFloat(document.getElementById("card-limit").value || 0);

  try {
    const json = await apiFetch("/api/cards", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ linked_account_number, card_type, credit_limit })
    });
    if (json.success) {
      showToast(`Card issued: ${json.card_id}`);
      closeModal("modal-card");
      reloadAllActiveData();
    } else {
      showToast(json.error, "error");
    }
  } catch (err) {
    showToast("Card creation failed", "error");
  }
}

function openLoanModal() {
  populateDropdowns();
  openModal("modal-loan");
}

async function submitSanctionLoan() {
  const customer_id = document.getElementById("loan-customer").value;
  const loan_type = document.getElementById("loan-type").value;
  const principal_amount = parseFloat(document.getElementById("loan-principal").value);
  const interest_rate = parseFloat(document.getElementById("loan-rate").value);
  const term_months = parseInt(document.getElementById("loan-tenure").value, 10);

  if (isNaN(principal_amount) || principal_amount <= 0) return showToast("Enter valid principal amount", "error");

  try {
    const json = await apiFetch("/api/loans", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ customer_id, loan_type, principal_amount, interest_rate, term_months })
    });
    if (json.success) {
      showToast(`Loan ${json.loan_number} sanctioned! EMI: ${formatINR(json.monthly_payment)}`);
      closeModal("modal-loan");
      reloadAllActiveData();
    } else {
      showToast(json.error, "error");
    }
  } catch (err) {
    showToast("Loan creation error", "error");
  }
}

function openRepayLoanModal() {
  apiFetch(scopedUrl("/api/loans")).then(j => {
    if (j.success) {
      const activeLoans = j.data.filter(l => l.status === "running");
      const sel = document.getElementById("repay-loan-num");
      sel.innerHTML = activeLoans.map(l => `<option value="${escapeHtml(l.loan_number)}">${escapeHtml(l.loan_number)} (${escapeHtml(l.customer_name)} - ${escapeHtml(l.loan_type)} - Bal: ${formatINR(l.outstanding_balance, l.currency_symbol)})</option>`).join("");
      openModal("modal-loan-repay");
    }
  });
}

async function submitLoanRepayment() {
  const loan_number = document.getElementById("repay-loan-num").value;
  const amount = parseFloat(document.getElementById("repay-loan-amount").value);

  if (isNaN(amount) || amount <= 0) return showToast("Enter valid payment amount", "error");

  try {
    const json = await apiFetch("/api/loans/repay", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ loan_number, amount })
    });
    if (json.success) {
      showToast(json.message);
      closeModal("modal-loan-repay");
      document.getElementById("repay-loan-amount").value = "";
      reloadAllActiveData();
    } else {
      showToast(json.error, "error");
    }
  } catch (err) {
    showToast("Repayment error", "error");
  }
}

// New Multi-Bank & RBAC Modals

function openCompanyModal() {
  openModal("modal-company");
}

async function submitNewCompany() {
  const payload = {
    company_name: document.getElementById("bank-name").value.trim(),
    short_code: document.getElementById("bank-short").value.trim(),
    currency_code: document.getElementById("bank-curr-code").value.trim() || "INR",
    currency_symbol: document.getElementById("bank-curr-sym").value.trim() || "₹",
    swift_code: document.getElementById("bank-swift").value.trim(),
    brand_color: document.getElementById("bank-color").value,
    headquarters_address: document.getElementById("bank-hq").value.trim(),
    total_assets: parseFloat(document.getElementById("bank-assets").value || 1000000000),
    initial_branch_name: document.getElementById("bank-init-branch").value.trim(),
    admin_full_name: document.getElementById("bank-admin-name").value.trim(),
    admin_username: document.getElementById("bank-admin-user").value.trim(),
    admin_password: document.getElementById("bank-admin-pass").value
  };

  if (!payload.company_name || !payload.short_code) {
    return showToast("Bank Name and Short Code are required", "error");
  }

  try {
    const json = await apiFetch("/api/companies", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (json.success) {
      showToast(json.message);
      closeModal("modal-company");
      reloadAllActiveData();
    } else {
      showToast(json.error, "error");
    }
  } catch (err) {
    showToast("Failed to onboard bank", "error");
  }
}

function openBranchModal() {
  populateDropdowns();
  openModal("modal-branch");
}

async function submitNewBranch() {
  const payload = {
    company_code: document.getElementById("br-company").value,
    branch_name: document.getElementById("br-name").value.trim(),
    manager_name: document.getElementById("br-manager").value.trim(),
    phone: document.getElementById("br-phone").value.trim(),
    address: document.getElementById("br-address").value.trim()
  };
  if (!payload.branch_name) return showToast("Branch name is required", "error");

  const json = await apiFetch("/api/branches", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (json.success) {
    showToast(json.message);
    closeModal("modal-branch");
    reloadAllActiveData();
  } else {
    showToast(json.error, "error");
  }
}

function openEmployeeModal() {
  populateDropdowns();
  openModal("modal-employee");
}

async function submitNewEmployee() {
  const payload = {
    branch_code: document.getElementById("emp-branch").value,
    first_name: document.getElementById("emp-fname").value.trim(),
    last_name: document.getElementById("emp-lname").value.trim(),
    email: document.getElementById("emp-email").value.trim(),
    phone: document.getElementById("emp-phone").value.trim(),
    position: document.getElementById("emp-position").value.trim(),
    department: document.getElementById("emp-dept").value.trim(),
    salary: parseFloat(document.getElementById("emp-salary").value || 60000),
    create_operator: document.getElementById("emp-create-op").checked,
    operator_username: document.getElementById("emp-op-user").value.trim(),
    operator_role: document.getElementById("emp-op-role").value,
    operator_password: document.getElementById("emp-op-pass").value
  };
  if (!payload.first_name || !payload.last_name || !payload.email) {
    return showToast("First name, last name, and email are required", "error");
  }

  const json = await apiFetch("/api/employees", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (json.success) {
    showToast(json.message);
    closeModal("modal-employee");
    reloadAllActiveData();
  } else {
    showToast(json.error, "error");
  }
}

function openOperatorModal() {
  populateDropdowns();
  openModal("modal-operator");
}

async function submitNewOperator() {
  const payload = {
    company_code: document.getElementById("op-company").value,
    full_name: document.getElementById("op-fullname").value.trim(),
    username: document.getElementById("op-username").value.trim(),
    password: document.getElementById("op-password").value,
    role_code: document.getElementById("op-role").value,
    employee_id: document.getElementById("op-employee").value
  };
  if (!payload.username || !payload.password) {
    return showToast("Username and password are required", "error");
  }

  const json = await apiFetch("/api/operators", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (json.success) {
    showToast(json.message);
    closeModal("modal-operator");
    reloadAllActiveData();
  } else {
    showToast(json.error, "error");
  }
}

function openAccountTypeModal() {
  populateDropdowns();
  openModal("modal-account-type");
}

async function submitNewAccountType() {
  const payload = {
    company_code: document.getElementById("at-company").value || null,
    account_type_code: document.getElementById("at-code").value.trim().toUpperCase(),
    type_name: document.getElementById("at-name").value.trim(),
    minimum_balance: parseFloat(document.getElementById("at-min").value || 0),
    interest_rate: parseFloat(document.getElementById("at-rate").value || 0),
    allows_overdraft: document.getElementById("at-overdraft").checked,
    description: document.getElementById("at-desc").value.trim()
  };
  if (!payload.account_type_code || !payload.type_name) {
    return showToast("Product code and name are required", "error");
  }

  const json = await apiFetch("/api/account-types", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (json.success) {
    showToast(json.message);
    closeModal("modal-account-type");
    reloadAllActiveData();
  } else {
    showToast(json.error, "error");
  }
}

// ---------------- INIT ---------------- #

document.addEventListener("DOMContentLoaded", async () => {
  document.querySelectorAll(".nav-item").forEach(item => {
    item.addEventListener("click", () => {
      switchTab(item.getAttribute("data-tab"));
    });
  });

  if (authToken) {
    try {
      const json = await apiFetch("/api/auth/me");
      if (json.success) {
        currentUser = json.data;
        if (!currentUser.is_global_scope) {
          activeCompanyCode = currentUser.company_code;
        }
        closeAuthOverlay();
        applyUserContext();
        await reloadAllActiveData();
        return;
      }
    } catch (e) {
      // Fallback to login screen
    }
  }

  openAuthOverlay(false);
});
