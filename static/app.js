// Apex Core Bank - CS209 DBMS Frontend Logic
let metaData = {
  account_types: [],
  categories: [],
  companies: [],
  employees: [],
  customers: [],
  accounts: []
};

// Formatting helpers
function formatINR(val) {
  const num = Number(val) || 0;
  return "₹" + num.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function showToast(message, type = "success") {
  const box = document.getElementById("toast-box");
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <span>${type === "success" ? "✓" : "⚠"}</span>
    <div>${message}</div>
  `;
  box.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(10px)";
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Tab navigation
function switchTab(tabId) {
  document.querySelectorAll(".nav-item").forEach(item => {
    item.classList.toggle("active", item.getAttribute("data-tab") === tabId);
  });
  document.querySelectorAll(".tab-pane").forEach(pane => {
    pane.classList.remove("active");
  });
  const target = document.getElementById(`tab-${tabId}`);
  if (target) {
    target.classList.add("active");
  }

  // Update topbar headline
  const titles = {
    dashboard: ["Executive Banking Dashboard", "Real-time core ledger monitoring and database operations"],
    customers: ["Customer Directory & KYC", "Customer master records, credit scores, and RM portfolios"],
    accounts: ["Core Banking Accounts", "Savings, current, salary, and business accounts management"],
    transactions: ["Transaction Audit Trail", "Double-entry transaction logging and running balance ledger"],
    cards: ["Card Center", "Debit, credit, and prepaid payment cards management"],
    loans: ["Credit & Lending Facilities", "Loan management, EMI schedules, and principal tracking"],
    branches: ["Branch Network & Staff", "Geographical branches and employee hierarchy"],
    "sql-studio": ["SQL Query Studio", "Direct SQL querying against DTU CS209 relational engine"],
    "schema-view": ["Database Design & ER Model", "10-table normalized relational database architecture"]
  };
  if (titles[tabId]) {
    document.getElementById("page-title").innerText = titles[tabId][0];
    document.getElementById("page-subtitle").innerText = titles[tabId][1];
  }

  // Trigger data reload for active tab
  if (tabId === "dashboard") fetchDashboard();
  else if (tabId === "customers") fetchCustomers();
  else if (tabId === "accounts") fetchAccounts();
  else if (tabId === "transactions") fetchTransactions();
  else if (tabId === "cards") fetchCards();
  else if (tabId === "loans") fetchLoans();
  else if (tabId === "branches") fetchBranchesAndStaff();
}

// Modal helpers
function openModal(id) {
  const modal = document.getElementById(id);
  if (modal) modal.classList.add("active");
}

function closeModal(id) {
  const modal = document.getElementById(id);
  if (modal) modal.classList.remove("active");
}

// Fetch Metadata for dropdowns
async function fetchMetadata() {
  try {
    const res = await fetch("/api/metadata");
    const json = await res.json();
    if (json.success) {
      metaData = json.data;
      populateDropdowns();
    }
  } catch (err) {
    console.error("Failed to load metadata", err);
  }
}

function populateDropdowns() {
  // Transfer source and dest
  const srcSel = document.getElementById("transfer-src-account");
  const dstSel = document.getElementById("transfer-dst-account");
  const dwAccSel = document.getElementById("dw-account");
  const cardAccSel = document.getElementById("card-account");

  const accOptions = metaData.accounts.map(a => `<option value="${a.account_number}">${a.label}</option>`).join("");
  if (srcSel) srcSel.innerHTML = accOptions;
  if (dstSel) dstSel.innerHTML = accOptions;
  if (dwAccSel) dwAccSel.innerHTML = accOptions;
  if (cardAccSel) cardAccSel.innerHTML = accOptions;

  // Customers dropdown
  const custOptions = metaData.customers.map(c => `<option value="${c.customer_id}">${c.name}</option>`).join("");
  const newaccCust = document.getElementById("newacc-customer");
  const loanCust = document.getElementById("loan-customer");
  if (newaccCust) newaccCust.innerHTML = custOptions;
  if (loanCust) loanCust.innerHTML = custOptions;

  // Account types
  const typeOptions = metaData.account_types.map(t => `<option value="${t.account_type_code}">${t.type_name} (Min: ₹${t.minimum_balance})</option>`).join("");
  const newaccType = document.getElementById("newacc-type");
  if (newaccType) newaccType.innerHTML = typeOptions;

  // Relationship managers
  const rmOptions = metaData.employees.map(e => `<option value="${e.employee_id}">${e.name}</option>`).join("");
  const custRm = document.getElementById("cust-rm");
  if (custRm) custRm.innerHTML = rmOptions;

  // Categories
  const catOptions = metaData.categories.map(c => `<option value="${c.category_code}">${c.category_name} (${c.category_type})</option>`).join("");
  const dwCat = document.getElementById("dw-category");
  if (dwCat) dwCat.innerHTML = catOptions;
}

// 1. Dashboard
async function fetchDashboard() {
  try {
    const res = await fetch("/api/dashboard/stats");
    const json = await res.json();
    if (!json.success) return;

    const data = json.data;
    document.getElementById("kpi-total-balance").innerText = formatINR(data.total_balance);
    document.getElementById("kpi-accounts-count").innerText = `${data.active_accounts} Active Accounts`;
    document.getElementById("kpi-customers-count").innerText = data.total_customers;
    document.getElementById("kpi-loan-balance").innerText = formatINR(data.outstanding_loans);
    document.getElementById("kpi-loans-count").innerText = `${data.active_loans} Running Facilities`;
    document.getElementById("kpi-active-cards").innerText = data.active_cards;
    document.getElementById("kpi-txn-count").innerText = `${data.total_transactions} Ledger Transactions`;

    // Recent Transactions
    const tbody = document.getElementById("dashboard-recent-txns");
    if (data.recent_transactions.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:20px;">No transactions recorded</td></tr>`;
    } else {
      tbody.innerHTML = data.recent_transactions.map(t => `
        <tr>
          <td><strong style="font-family:var(--font-mono); color:#58a6ff;">${t.transaction_reference}</strong></td>
          <td>
            <div>${t.customer_name}</div>
            <div style="font-size:11px; color:var(--text-muted); font-family:var(--font-mono);">${t.account_number}</div>
          </td>
          <td>${t.category_name || t.category_code}</td>
          <td>
            <span class="badge badge-${t.transaction_type}">
              ${t.transaction_type === 'credit' ? '↓ Credit' : '↑ Debit'}
            </span>
          </td>
          <td style="font-weight:700; color: ${t.transaction_type === 'credit' ? 'var(--accent-primary)' : 'var(--accent-rose)'};">
            ${t.transaction_type === 'credit' ? '+' : '-'}${formatINR(t.amount)}
          </td>
          <td style="font-family:var(--font-mono);">${formatINR(t.running_balance)}</td>
        </tr>
      `).join("");
    }

    // Account distribution
    const distBox = document.getElementById("account-type-distribution");
    distBox.innerHTML = data.account_distribution.map(d => {
      const pct = data.total_balance > 0 ? Math.min(100, Math.round((d.total_balance / data.total_balance) * 100)) : 0;
      return `
        <div>
          <div style="display:flex; justify-content:space-between; font-size:12px; margin-bottom:4px;">
            <span>${d.type_name} (${d.count})</span>
            <span style="font-weight:600;">${formatINR(d.total_balance)} (${pct}%)</span>
          </div>
          <div style="background:rgba(255,255,255,0.06); height:6px; border-radius:3px; overflow:hidden;">
            <div style="width:${pct}%; background:var(--accent-secondary); height:100%;"></div>
          </div>
        </div>
      `;
    }).join("");

    // Branches table
    const bbody = document.getElementById("dashboard-branches-table");
    bbody.innerHTML = data.branch_stats.map(b => `
      <tr>
        <td><strong style="font-family:var(--font-mono);">${b.branch_code}</strong></td>
        <td>${b.branch_name}</td>
        <td>${b.employee_count} Personnel</td>
        <td><strong>${b.customer_accounts_managed} Accounts</strong></td>
      </tr>
    `).join("");

  } catch (err) {
    console.error("Dashboard load failed", err);
  }
}

// 2. Customers
async function fetchCustomers() {
  const query = document.getElementById("customer-search-input") ? document.getElementById("customer-search-input").value : "";
  try {
    const res = await fetch(`/api/customers?q=${encodeURIComponent(query)}`);
    const json = await res.json();
    const tbody = document.getElementById("customers-table-body");
    if (!json.success || json.data.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding:30px;">No customers found</td></tr>`;
      return;
    }

    tbody.innerHTML = json.data.map(c => {
      let scoreColor = "#10b981";
      if (c.credit_score < 700) scoreColor = "#f59e0b";
      if (c.credit_score < 650) scoreColor = "#f43f5e";

      return `
        <tr>
          <td><strong style="font-family:var(--font-mono); color:#58a6ff;">${c.customer_id}</strong></td>
          <td>
            <div style="font-weight:600;">${c.first_name} ${c.last_name}</div>
            <div style="font-size:11px; color:var(--text-muted);">${c.address || 'N/A'}</div>
          </td>
          <td>
            <div>${c.email}</div>
            <div style="font-size:11px; color:var(--text-muted); font-family:var(--font-mono);">${c.phone}</div>
          </td>
          <td>
            <span class="badge" style="background:rgba(255,255,255,0.05); color:${scoreColor}; border:1px solid ${scoreColor}; font-family:var(--font-mono);">
              ★ ${c.credit_score}
            </span>
          </td>
          <td>${c.rm_name || 'Unassigned'}</td>
          <td>${c.accounts_count} accounts</td>
          <td style="font-weight:700; color:var(--accent-primary);">${formatINR(c.total_customer_balance)}</td>
          <td>
            <button class="btn btn-secondary btn-sm" onclick="viewCustomerDossier('${c.customer_id}')">Dossier</button>
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
    const res = await fetch(`/api/customers/${custId}`);
    const json = await res.json();
    if (!json.success) return showToast(json.error, "error");

    const c = json.data;
    document.getElementById("cust-detail-title").innerText = `Customer Dossier: ${c.first_name} ${c.last_name} (${c.customer_id})`;
    
    let accountsHtml = c.accounts.map(a => `
      <div style="background:rgba(0,0,0,0.3); padding:12px; border-radius:8px; margin-bottom:8px; display:flex; justify-content:space-between; align-items:center;">
        <div>
          <strong style="font-family:var(--font-mono);">${a.account_number}</strong> - ${a.type_name}
          <div style="font-size:11px; color:var(--text-muted);">Opened: ${a.opening_date} • Overdraft: ${formatINR(a.overdraft_limit)}</div>
        </div>
        <div style="text-align:right;">
          <div style="font-weight:700; color:var(--accent-primary);">${formatINR(a.balance)}</div>
          <span class="badge badge-${a.status}">${a.status}</span>
        </div>
      </div>
    `).join("") || '<p style="color:var(--text-muted);">No accounts found</p>';

    let cardsHtml = c.cards.map(cd => `
      <div style="display:inline-block; background:rgba(255,255,255,0.05); padding:8px 12px; border-radius:6px; margin:4px; font-size:12px;">
        💳 <strong>${cd.card_number_masked}</strong> (${cd.card_type.toUpperCase()}) - <span class="badge badge-${cd.status}">${cd.status}</span>
      </div>
    `).join("") || '<p style="color:var(--text-muted);">No cards issued</p>';

    let loansHtml = c.loans.map(l => `
      <div style="background:rgba(0,0,0,0.3); padding:10px; border-radius:8px; margin-bottom:6px; display:flex; justify-content:space-between; font-size:12px;">
        <div><strong>${l.loan_number}</strong> (${l.loan_type.toUpperCase()}) • Term: ${l.term_months}mo • EMI: ${formatINR(l.monthly_payment)}</div>
        <div>Outstanding: <strong>${formatINR(l.outstanding_balance)}</strong> <span class="badge badge-${l.status === 'running' ? 'active' : 'closed'}">${l.status}</span></div>
      </div>
    `).join("") || '<p style="color:var(--text-muted);">No active loans</p>';

    document.getElementById("cust-detail-body").innerHTML = `
      <div style="display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:20px; font-size:13px;">
        <div>
          <div><strong>Email:</strong> ${c.email}</div>
          <div><strong>Phone:</strong> ${c.phone}</div>
          <div><strong>DOB:</strong> ${c.date_of_birth}</div>
          <div><strong>Govt ID:</strong> ${c.id_number}</div>
        </div>
        <div>
          <div><strong>Credit Score:</strong> <span style="font-weight:700; color:var(--accent-primary);">${c.credit_score}</span></div>
          <div><strong>Assigned RM:</strong> ${c.rm_name || 'N/A'}</div>
          <div><strong>Home Branch:</strong> ${c.branch_name || 'N/A'}</div>
          <div><strong>Member Since:</strong> ${c.registration_date}</div>
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

// 3. Accounts
async function fetchAccounts() {
  const query = document.getElementById("account-search-input") ? document.getElementById("account-search-input").value : "";
  try {
    const res = await fetch(`/api/accounts?q=${encodeURIComponent(query)}`);
    const json = await res.json();
    const tbody = document.getElementById("accounts-table-body");
    if (!json.success || json.data.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding:30px;">No accounts found</td></tr>`;
      return;
    }

    tbody.innerHTML = json.data.map(a => `
      <tr>
        <td><strong style="font-family:var(--font-mono); color:#58a6ff;">${a.account_number}</strong></td>
        <td>
          <div style="font-weight:600;">${a.customer_name}</div>
          <div style="font-size:11px; color:var(--text-muted);">${a.customer_id}</div>
        </td>
        <td>
          <div>${a.type_name}</div>
          <div style="font-size:11px; color:var(--text-muted);">${(a.interest_rate * 100).toFixed(2)}% p.a.</div>
        </td>
        <td style="font-weight:700; font-size:14px; color:${a.balance >= 0 ? 'var(--text-main)' : 'var(--accent-rose)'};">
          ${formatINR(a.balance)}
        </td>
        <td style="font-family:var(--font-mono);">${formatINR(a.overdraft_limit)}</td>
        <td>${a.opening_date}</td>
        <td>
          <span class="badge badge-${a.status}">${a.status}</span>
        </td>
        <td>
          <div style="display:flex; gap:6px;">
            <button class="btn btn-secondary btn-sm" onclick="quickTransact('${a.account_number}')">Transact</button>
            <select class="form-control" style="width:90px; padding:4px 6px; font-size:11px;" onchange="changeAccountStatus('${a.account_number}', this.value)">
              <option value="active" ${a.status === 'active' ? 'selected' : ''}>Active</option>
              <option value="frozen" ${a.status === 'frozen' ? 'selected' : ''}>Freeze</option>
              <option value="closed" ${a.status === 'closed' ? 'selected' : ''}>Close</option>
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
    const res = await fetch(`/api/accounts/${accNo}/status`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: newStatus })
    });
    const json = await res.json();
    if (json.success) {
      showToast(json.message);
      fetchAccounts();
    } else {
      showToast(json.error, "error");
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

// 4. Transactions Ledger
async function fetchTransactions() {
  const typeFilter = document.getElementById("txn-filter-type") ? document.getElementById("txn-filter-type").value : "";
  try {
    const res = await fetch(`/api/transactions?type=${encodeURIComponent(typeFilter)}`);
    const json = await res.json();
    const tbody = document.getElementById("transactions-table-body");
    if (!json.success || json.data.length === 0) {
      tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding:30px;">No transactions recorded</td></tr>`;
      return;
    }

    tbody.innerHTML = json.data.map(t => `
      <tr>
        <td><strong style="font-family:var(--font-mono); color:#58a6ff;">${t.transaction_reference}</strong></td>
        <td style="font-family:var(--font-mono);">${t.account_number}</td>
        <td>${t.customer_name}</td>
        <td>${t.category_name || t.category_code}</td>
        <td>
          <span class="badge badge-${t.transaction_type}">
            ${t.transaction_type === 'credit' ? '↓ Credit' : '↑ Debit'}
          </span>
        </td>
        <td style="font-weight:700; color:${t.transaction_type === 'credit' ? 'var(--accent-primary)' : 'var(--accent-rose)'};">
          ${t.transaction_type === 'credit' ? '+' : '-'}${formatINR(t.amount)}
        </td>
        <td style="font-family:var(--font-mono);">${formatINR(t.running_balance)}</td>
        <td style="color:var(--text-muted); max-width:200px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
          ${t.description || '-'}
        </td>
        <td style="font-size:11px; color:var(--text-muted); font-family:var(--font-mono);">${t.transaction_date}</td>
      </tr>
    `).join("");
  } catch (err) {
    console.error("Fetch transactions failed", err);
  }
}

// 5. Cards Center
async function fetchCards() {
  try {
    const res = await fetch("/api/cards");
    const json = await res.json();
    const container = document.getElementById("cards-container");
    if (!json.success || json.data.length === 0) {
      container.innerHTML = `<div style="grid-column: 1/-1; text-align:center; padding:40px; color:var(--text-muted);">No payment cards issued yet.</div>`;
      return;
    }

    container.innerHTML = json.data.map(cd => `
      <div class="virtual-card ${cd.card_type}">
        <div class="card-top">
          <div class="card-chip"></div>
          <div style="font-weight:800; font-size:14px; letter-spacing:1px; text-transform:uppercase;">
            ${cd.card_type} CARD
          </div>
        </div>
        <div class="card-number">${cd.card_number_masked}</div>
        <div class="card-bottom">
          <div>
            <div style="font-size:9px; text-transform:uppercase; opacity:0.8;">Cardholder</div>
            <div class="card-holder">${cd.customer_name}</div>
          </div>
          <div style="text-align:right;">
            <div style="font-size:9px; text-transform:uppercase; opacity:0.8;">Expires</div>
            <div class="card-expiry">${cd.expiry_date}</div>
          </div>
        </div>
        <div style="display:flex; justify-content:space-between; align-items:center; margin-top:10px; padding-top:10px; border-top:1px solid rgba(255,255,255,0.1);">
          <span class="badge badge-${cd.status}">${cd.status}</span>
          <div style="display:flex; gap:6px;">
            ${cd.status === 'active' ? `
              <button class="btn btn-secondary btn-sm" style="padding:2px 8px; font-size:10px;" onclick="updateCardStatus('${cd.card_id}', 'blocked')">Block Card</button>
            ` : `
              <button class="btn btn-primary btn-sm" style="padding:2px 8px; font-size:10px;" onclick="updateCardStatus('${cd.card_id}', 'active')">Unblock</button>
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
    const res = await fetch(`/api/cards/${cardId}/status`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: newStatus })
    });
    const json = await res.json();
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

// 6. Loans & Credit
async function fetchLoans() {
  try {
    const res = await fetch("/api/loans");
    const json = await res.json();
    const tbody = document.getElementById("loans-table-body");
    if (!json.success || json.data.length === 0) {
      tbody.innerHTML = `<tr><td colspan="10" style="text-align:center; padding:30px;">No loan accounts found</td></tr>`;
      return;
    }

    tbody.innerHTML = json.data.map(l => {
      const paidPct = l.principal_amount > 0 ? Math.max(0, Math.min(100, Math.round(((l.principal_amount - l.outstanding_balance) / l.principal_amount) * 100))) : 0;
      return `
        <tr>
          <td><strong style="font-family:var(--font-mono); color:#58a6ff;">${l.loan_number}</strong></td>
          <td>
            <div style="font-weight:600;">${l.customer_name}</div>
            <div style="font-size:11px; color:var(--text-muted); font-family:var(--font-mono);">${l.customer_id}</div>
          </td>
          <td><span style="text-transform:capitalize;">${l.loan_type}</span></td>
          <td style="font-weight:600;">${formatINR(l.principal_amount)}</td>
          <td>${(l.interest_rate * 100).toFixed(2)}%</td>
          <td>${l.term_months} mos</td>
          <td style="font-weight:700; color:var(--accent-amber);">${formatINR(l.monthly_payment)}</td>
          <td>
            <div style="font-weight:700;">${formatINR(l.outstanding_balance)}</div>
            <div style="font-size:10px; color:var(--text-muted);">${paidPct}% amortized</div>
          </td>
          <td><span class="badge badge-${l.status === 'running' ? 'active' : (l.status === 'closed' ? 'closed' : 'frozen')}">${l.status}</span></td>
          <td>
            ${l.status === 'running' ? `
              <button class="btn btn-secondary btn-sm" onclick="quickRepayLoan('${l.loan_number}', ${l.monthly_payment})">Repay EMI</button>
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
  const sel = document.getElementById("repay-loan-num");
  if (sel) sel.value = loanNum;
  const amt = document.getElementById("repay-loan-amount");
  if (amt) amt.value = monthlyPayment;
}

// 7. Branches & Staff
async function fetchBranchesAndStaff() {
  try {
    const [bRes, eRes] = await Promise.all([
      fetch("/api/branches"),
      fetch("/api/employees")
    ]);
    const bJson = await bRes.json();
    const eJson = await eRes.json();

    const bbody = document.getElementById("branches-list-table");
    if (bJson.success) {
      bbody.innerHTML = bJson.data.map(b => `
        <tr>
          <td><strong style="font-family:var(--font-mono); color:#58a6ff;">${b.branch_code}</strong></td>
          <td><strong>${b.branch_name}</strong></td>
          <td>${b.company_name}</td>
          <td style="font-size:12px; color:var(--text-muted);">${b.address}</td>
          <td style="font-family:var(--font-mono); font-size:12px;">${b.phone}</td>
          <td>${b.manager_name}</td>
          <td style="font-size:11px;">${b.opening_hours} - ${b.closing_hours}</td>
          <td><span class="badge badge-active">${b.employee_count} Employees</span></td>
        </tr>
      `).join("");
    }

    const ebody = document.getElementById("employees-list-table");
    if (eJson.success) {
      ebody.innerHTML = eJson.data.map(e => `
        <tr>
          <td><strong style="font-family:var(--font-mono); color:#58a6ff;">${e.employee_id}</strong></td>
          <td><strong>${e.first_name} ${e.last_name}</strong></td>
          <td>${e.department}</td>
          <td>${e.position}</td>
          <td>${e.branch_name || e.branch_code}</td>
          <td style="font-size:12px;">${e.email}</td>
          <td style="font-family:var(--font-mono); font-size:12px;">${e.phone}</td>
          <td style="font-weight:700;">${formatINR(e.salary)}</td>
        </tr>
      `).join("");
    }
  } catch (err) {
    console.error("Fetch branches and staff failed", err);
  }
}

// 8. SQL Query Studio
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
    const res = await fetch("/api/sql", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query })
    });
    const json = await res.json();

    if (!json.success) {
      timerLabel.innerText = "Error";
      errorBox.innerText = json.error;
      errorBox.style.display = "block";
      return;
    }

    timerLabel.innerText = `${json.row_count} rows in ${json.execution_time_ms} ms`;
    resultsContainer.style.display = "block";

    // Build thead
    thead.innerHTML = `<tr>${json.columns.map(col => `<th>${col}</th>`).join("")}</tr>`;

    // Build tbody
    if (json.rows.length === 0) {
      tbody.innerHTML = `<tr><td colspan="${json.columns.length}" style="text-align:center; padding:20px; color:var(--text-muted);">Query returned 0 rows</td></tr>`;
    } else {
      tbody.innerHTML = json.rows.map(row => `
        <tr>
          ${row.map(val => `<td style="font-family:var(--font-mono);">${val !== null ? val : '<em style="color:var(--text-dim);">NULL</em>'}</td>`).join("")}
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
UNION ALL
SELECT 'branches', COUNT(*) FROM branches
UNION ALL
SELECT 'employees', COUNT(*) FROM employees
UNION ALL
SELECT 'customers', COUNT(*) FROM customers
UNION ALL
SELECT 'account_types', COUNT(*) FROM account_types
UNION ALL
SELECT 'accounts', COUNT(*) FROM accounts
UNION ALL
SELECT 'transaction_categories', COUNT(*) FROM transaction_categories
UNION ALL
SELECT 'transactions', COUNT(*) FROM transactions
UNION ALL
SELECT 'loans', COUNT(*) FROM loans
UNION ALL
SELECT 'cards', COUNT(*) FROM cards;`,
    2: `SELECT c.customer_id, c.first_name || ' ' || c.last_name AS customer_name,
       a.account_number, at.type_name, a.balance, c.credit_score
FROM accounts a
JOIN customers c ON a.customer_id = c.customer_id
JOIN account_types at ON a.account_type_code = at.account_type_code
ORDER BY a.balance DESC
LIMIT 10;`,
    3: `SELECT b.branch_code, b.branch_name, comp.company_name, b.manager_name,
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
    6: `SELECT t.transaction_reference, t.transaction_date, t.amount, t.transaction_type,
       t.account_number, c.first_name || ' ' || c.last_name AS customer_name,
       t.description
FROM transactions t
JOIN accounts a ON t.account_number = a.account_number
JOIN customers c ON a.customer_id = c.customer_id
WHERE t.amount >= 50000
ORDER BY t.amount DESC;`
  };

  const editor = document.getElementById("sql-input");
  if (editor && presets[num]) {
    editor.value = presets[num];
    executeSQLQuery();
  }
}

// ================= MODAL ACTIONS =================

// Fund Transfer Modal
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
    const res = await fetch("/api/transact", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "transfer", from_account, to_account, amount, description })
    });
    const json = await res.json();
    if (json.success) {
      showToast(json.message);
      closeModal("modal-transfer");
      document.getElementById("transfer-amount").value = "";
      document.getElementById("transfer-desc").value = "";
      fetchDashboard();
      fetchAccounts();
      fetchTransactions();
      fetchMetadata();
    } else {
      showToast(json.error, "error");
    }
  } catch (err) {
    showToast("Transfer network error", "error");
  }
}

// Deposit / Withdraw Modal
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
    const res = await fetch("/api/transact", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, account_number, amount, category_code, description })
    });
    const json = await res.json();
    if (json.success) {
      showToast(json.message);
      closeModal("modal-deposit-withdraw");
      document.getElementById("dw-amount").value = "";
      document.getElementById("dw-desc").value = "";
      fetchDashboard();
      fetchAccounts();
      fetchTransactions();
      fetchMetadata();
    } else {
      showToast(json.error, "error");
    }
  } catch (err) {
    showToast("Transaction network error", "error");
  }
}

// Open Account Modal
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
    const res = await fetch("/api/accounts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ customer_id, account_type_code, initial_deposit, overdraft_limit })
    });
    const json = await res.json();
    if (json.success) {
      showToast(`Account ${json.account_number} created successfully!`);
      closeModal("modal-account");
      fetchAccounts();
      fetchDashboard();
      fetchMetadata();
    } else {
      showToast(json.error, "error");
    }
  } catch (err) {
    showToast("Error creating account", "error");
  }
}

// Register Customer Modal
function openCustomerModal() {
  populateDropdowns();
  openModal("modal-customer");
}

async function submitNewCustomer() {
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
    const res = await fetch("/api/customers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        first_name, last_name, email, phone, date_of_birth, id_number,
        credit_score, relationship_manager_id, address
      })
    });
    const json = await res.json();
    if (json.success) {
      showToast(`Customer registered as ${json.customer_id}`);
      closeModal("modal-customer");
      fetchCustomers();
      fetchDashboard();
      fetchMetadata();
    } else {
      showToast(json.error, "error");
    }
  } catch (err) {
    showToast("Error creating customer", "error");
  }
}

// Issue Card Modal
function openCardModal() {
  populateDropdowns();
  openModal("modal-card");
}

async function submitIssueCard() {
  const linked_account_number = document.getElementById("card-account").value;
  const card_type = document.getElementById("card-type").value;
  const credit_limit = parseFloat(document.getElementById("card-limit").value || 0);

  // find customer_id from account
  const accObj = metaData.accounts.find(a => a.account_number === linked_account_number);
  const custIdMatch = accObj ? accObj.label.match(/\((CUST\d+)/) : null;
  const customer_id = custIdMatch ? custIdMatch[1] : "CUST001";

  try {
    const res = await fetch("/api/cards", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ linked_account_number, customer_id, card_type, credit_limit })
    });
    const json = await res.json();
    if (json.success) {
      showToast(`Card issued: ${json.card_id}`);
      closeModal("modal-card");
      fetchCards();
      fetchDashboard();
    } else {
      showToast(json.error, "error");
    }
  } catch (err) {
    showToast("Card creation failed", "error");
  }
}

// Sanction Loan Modal
function openLoanModal() {
  populateDropdowns();
  openModal("modal-loan");
}

async function submitSanctionLoan() {
  const customer_id = document.getElementById("loan-customer").value;
  const loan_type = document.getElementById("loan-type").value;
  const principal_amount = parseFloat(document.getElementById("loan-principal").value);
  const interest_rate = parseFloat(document.getElementById("loan-rate").value);
  const term_months = parseInt(document.getElementById("loan-tenure").value);

  if (isNaN(principal_amount) || principal_amount <= 0) return showToast("Enter valid principal amount", "error");

  try {
    const res = await fetch("/api/loans", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ customer_id, loan_type, principal_amount, interest_rate, term_months })
    });
    const json = await res.json();
    if (json.success) {
      showToast(`Loan ${json.loan_number} sanctioned! Monthly EMI: ₹${json.monthly_payment}`);
      closeModal("modal-loan");
      fetchLoans();
      fetchDashboard();
    } else {
      showToast(json.error, "error");
    }
  } catch (err) {
    showToast("Loan creation error", "error");
  }
}

// Repay Loan Modal
function openRepayLoanModal() {
  fetch("/api/loans").then(r => r.json()).then(j => {
    if (j.success) {
      const activeLoans = j.data.filter(l => l.status === "running");
      const sel = document.getElementById("repay-loan-num");
      sel.innerHTML = activeLoans.map(l => `<option value="${l.loan_number}">${l.loan_number} (${l.customer_name} - ${l.loan_type} - Bal: ₹${l.outstanding_balance})</option>`).join("");
      openModal("modal-loan-repay");
    }
  });
}

async function submitLoanRepayment() {
  const loan_number = document.getElementById("repay-loan-num").value;
  const amount = parseFloat(document.getElementById("repay-loan-amount").value);

  if (isNaN(amount) || amount <= 0) return showToast("Enter valid payment amount", "error");

  try {
    const res = await fetch("/api/loans/repay", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ loan_number, amount })
    });
    const json = await res.json();
    if (json.success) {
      showToast(json.message);
      closeModal("modal-loan-repay");
      document.getElementById("repay-loan-amount").value = "";
      fetchLoans();
      fetchDashboard();
    } else {
      showToast(json.error, "error");
    }
  } catch (err) {
    showToast("Repayment error", "error");
  }
}

// Initialize navigation listeners
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".nav-item").forEach(item => {
    item.addEventListener("click", () => {
      const tabId = item.getAttribute("data-tab");
      switchTab(tabId);
    });
  });

  fetchMetadata();
  fetchDashboard();
});
