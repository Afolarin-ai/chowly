// ---------------------------------------------------------------------
// State
// ---------------------------------------------------------------------
const state = {
  role: "customer",
  menu: [],
  staff: [],
  cart: {},           // menu_item_id -> quantity
  tableNumber: localStorage.getItem("chowly_table") || "",
  myOrderIds: JSON.parse(localStorage.getItem("chowly_my_orders") || "[]"),
  myOrders: [],        // full order objects for this browser's customer
  waiterOrders: [],     // all orders, for the waiter dashboard
  actingWaiterId: localStorage.getItem("chowly_waiter_id") || "",
};

const app = document.getElementById("app");
const toastEl = document.getElementById("toast");

// ---------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------
async function api(path, opts = {}) {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || "Something went wrong");
  }
  return res.status === 204 ? null : res.json();
}

function showToast(message) {
  toastEl.textContent = message;
  toastEl.classList.add("is-visible");
  setTimeout(() => toastEl.classList.remove("is-visible"), 2600);
}

function money(n) {
  return "\u20a6" + Number(n).toLocaleString();
}

// ---------------------------------------------------------------------
// Role switch
// ---------------------------------------------------------------------
document.querySelectorAll(".role-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".role-btn").forEach((b) => {
      b.classList.remove("is-active");
      b.setAttribute("aria-selected", "false");
    });
    btn.classList.add("is-active");
    btn.setAttribute("aria-selected", "true");
    state.role = btn.dataset.role;
    render();
  });
});

// ---------------------------------------------------------------------
// Customer view
// ---------------------------------------------------------------------
function renderCustomer() {
  const categories = {};
  state.menu.forEach((item) => {
    (categories[item.category] = categories[item.category] || []).push(item);
  });

  const categoryLabels = { food: "Food", drink: "Drinks" };
  const categoryHtml = Object.entries(categories)
    .map(
      ([cat, items]) => `
      <div class="menu-category">
        <h3>${categoryLabels[cat] || cat}</h3>
        <div class="menu-grid">
          ${items.map(menuItemHtml).join("")}
        </div>
      </div>`
    )
    .join("");

  const ticketsHtml = state.myOrders.length
    ? `<div class="section-title" style="margin-top:44px">Your orders</div>
       <div class="section-hint">Track status, waiting time, and pay when you're ready to leave.</div>
       ${state.myOrders.map(orderTicketHtml).join("")}`
    : "";

  app.innerHTML = `
    <div class="section-title">Tonight's menu</div>
    <div class="section-hint">Pick your table, add items, and send it to the kitchen.</div>
    <div class="table-picker">
      <label for="table-input">Table number</label>
      <input id="table-input" type="number" min="1" value="${state.tableNumber}" placeholder="e.g. 5">
    </div>
    ${categoryHtml}
    ${ticketsHtml}
  `;

  document.getElementById("table-input").addEventListener("input", (e) => {
    state.tableNumber = e.target.value;
    localStorage.setItem("chowly_table", state.tableNumber);
  });

  app.querySelectorAll("[data-qty-action]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = Number(btn.dataset.id);
      const delta = Number(btn.dataset.qtyAction);
      const next = (state.cart[id] || 0) + delta;
      if (next <= 0) delete state.cart[id];
      else state.cart[id] = next;
      renderCustomer();
      renderCartBar();
    });
  });

  app.querySelectorAll("[data-complaint-form]").forEach(wireComplaintForm);
  app.querySelectorAll("[data-pay-order]").forEach((btn) => {
    btn.addEventListener("click", () => payOrder(Number(btn.dataset.payOrder)));
  });

  renderCartBar();
}

function menuItemHtml(item) {
  const qty = state.cart[item.id] || 0;
  return `
    <div class="menu-item">
      <div class="menu-item-name">${item.name}</div>
      <div class="menu-item-meta">${item.prep_time_minutes} min &middot; ${categoryWord(item.category)}</div>
      <div class="menu-item-footer">
        <div class="menu-item-price">${money(item.price)}</div>
        <div class="qty-control">
          <button class="qty-btn" data-qty-action="-1" data-id="${item.id}" aria-label="Remove one ${item.name}">&minus;</button>
          <span class="qty-value">${qty}</span>
          <button class="qty-btn" data-qty-action="1" data-id="${item.id}" aria-label="Add one ${item.name}">&plus;</button>
        </div>
      </div>
    </div>`;
}

function categoryWord(cat) {
  return cat === "food" ? "food" : "drink";
}

function renderCartBar() {
  let bar = document.querySelector(".cart-bar");
  if (!bar) {
    bar = document.createElement("div");
    bar.className = "cart-bar";
    document.body.appendChild(bar);
  }

  const entries = Object.entries(state.cart);
  const itemCount = entries.reduce((sum, [, q]) => sum + q, 0);
  const total = entries.reduce((sum, [id, q]) => {
    const item = state.menu.find((m) => m.id === Number(id));
    return sum + (item ? item.price * q : 0);
  }, 0);

  if (state.role !== "customer" || itemCount === 0) {
    bar.classList.remove("is-visible");
    return;
  }

  bar.classList.add("is-visible");
  bar.innerHTML = `
    <div class="cart-summary">${itemCount} item${itemCount === 1 ? "" : "s"} &middot; <strong>${money(total)}</strong></div>
    <button class="btn-primary" id="place-order-btn">Place order</button>
  `;
  document.getElementById("place-order-btn").addEventListener("click", placeOrder);
}

async function placeOrder() {
  if (!state.tableNumber) {
    showToast("Enter your table number first");
    return;
  }
  const items = Object.entries(state.cart).map(([menu_item_id, quantity]) => ({
    menu_item_id: Number(menu_item_id),
    quantity,
  }));
  try {
    const order = await api("/orders", {
      method: "POST",
      body: JSON.stringify({ table_number: Number(state.tableNumber), items }),
    });
    state.cart = {};
    state.myOrderIds.push(order.id);
    localStorage.setItem("chowly_my_orders", JSON.stringify(state.myOrderIds));
    state.myOrders.unshift(order);
    showToast(`Order sent to the kitchen \u2014 about ${order.waiting_time_minutes} min`);
    renderCustomer();
  } catch (err) {
    showToast(err.message);
  }
}

function orderTicketHtml(order) {
  const statusLabel = {
    placed: "Placed \u2014 waiting on a waiter",
    assigned: "Being prepared",
    served: "Served",
    paid: "Paid",
  }[order.status];

  const rows = order.items
    .map(
      (i) => `<div class="ticket-row"><span><span class="qty">${i.quantity}\u00d7</span>${i.menu_item.name}</span><span>${money(i.menu_item.price * i.quantity)}</span></div>`
    )
    .join("");

  const canComplain = !order.complaint && order.status !== "placed";
  const complaintSection = order.complaint
    ? `<div class="complaint-filed">You reported: "${escapeHtml(order.complaint.message)}" (${order.complaint.rating}/5)</div>`
    : canComplain
    ? complaintFormHtml(order.id)
    : "";

  const payAction =
    !order.paid && order.status === "served"
      ? `<button class="btn-primary" data-pay-order="${order.id}">Pay (pretend)</button>`
      : "";

  return `
    <div class="ticket">
      <div class="ticket-head">
        <div class="ticket-title">Table ${order.table_number} &middot; Order #${order.id}</div>
        <div class="ticket-status status-${order.status}">${statusLabel}</div>
      </div>
      ${rows}
      <div class="ticket-total"><span>Total</span><span>${money(order.total_price)}</span></div>
      <div class="ticket-meta">
        <span>Waiting time: ~${order.waiting_time_minutes} min</span>
        ${order.waiter ? `<span>Waiter: ${order.waiter.name}</span>` : ""}
        ${order.chef ? `<span>Chef: ${order.chef.name}</span>` : ""}
        ${order.bartender ? `<span>Bartender: ${order.bartender.name}</span>` : ""}
        ${order.paid ? `<span>Paid \u2713</span>` : ""}
      </div>
      ${payAction ? `<div class="ticket-actions">${payAction}</div>` : ""}
      ${complaintSection}
    </div>`;
}

function complaintFormHtml(orderId) {
  return `
    <div class="complaint-box" data-complaint-form data-order-id="${orderId}">
      <label>Something wrong with this order? Let the kitchen know.</label>
      <div class="rating-picker" data-rating-picker>
        ${[1, 2, 3, 4, 5].map((n) => `<button type="button" class="rating-star" data-star="${n}">&#9733;</button>`).join("")}
      </div>
      <textarea data-complaint-message placeholder="What happened?"></textarea>
      <div class="ticket-actions">
        <button class="btn-secondary" data-submit-complaint>Submit complaint</button>
      </div>
    </div>`;
}

function wireComplaintForm(box) {
  let rating = 0;
  const stars = box.querySelectorAll("[data-star]");
  stars.forEach((star) => {
    star.addEventListener("click", () => {
      rating = Number(star.dataset.star);
      stars.forEach((s) => s.classList.toggle("is-active", Number(s.dataset.star) <= rating));
    });
  });

  box.querySelector("[data-submit-complaint]").addEventListener("click", async () => {
    const message = box.querySelector("[data-complaint-message]").value.trim();
    if (!message || !rating) {
      showToast("Add a message and a rating first");
      return;
    }
    const orderId = Number(box.dataset.orderId);
    try {
      const updated = await api(`/orders/${orderId}/complaint`, {
        method: "POST",
        body: JSON.stringify({ message, rating }),
      });
      const idx = state.myOrders.findIndex((o) => o.id === orderId);
      if (idx >= 0) state.myOrders[idx] = updated;
      showToast("Complaint sent \u2014 thanks for letting us know");
      renderCustomer();
    } catch (err) {
      showToast(err.message);
    }
  });
}

async function payOrder(orderId) {
  try {
    const updated = await api(`/orders/${orderId}/pay`, { method: "POST" });
    const idx = state.myOrders.findIndex((o) => o.id === orderId);
    if (idx >= 0) state.myOrders[idx] = updated;
    const widx = state.waiterOrders.findIndex((o) => o.id === orderId);
    if (widx >= 0) state.waiterOrders[widx] = updated;
    showToast("Payment recorded (pretend) \u2014 see you again soon");
    render();
  } catch (err) {
    showToast(err.message);
  }
}

async function loadMyOrders() {
  if (!state.myOrderIds.length) {
    state.myOrders = [];
    return;
  }
  const results = await Promise.all(
    state.myOrderIds.map((id) => api(`/orders/${id}`).catch(() => null))
  );
  state.myOrders = results.filter(Boolean).sort((a, b) => b.id - a.id);
}

// ---------------------------------------------------------------------
// Waiter view
// ---------------------------------------------------------------------
function renderWaiter() {
  const waiters = state.staff.filter((s) => s.role === "waiter");
  const chefs = state.staff.filter((s) => s.role === "chef");
  const bartenders = state.staff.filter((s) => s.role === "bartender");

  const active = state.waiterOrders.filter((o) => o.status !== "paid");
  const settled = state.waiterOrders.filter((o) => o.status === "paid");

  const listHtml = active.length
    ? active.map((o) => waiterOrderCardHtml(o, waiters, chefs, bartenders)).join("")
    : `<div class="empty-state"><p>All caught up</p><span>No active orders right now.</span></div>`;

  const settledHtml = settled.length
    ? `<div class="section-title" style="margin-top:44px">Settled tonight</div>
       <div class="order-list">${settled.map((o) => waiterOrderCardHtml(o, waiters, chefs, bartenders)).join("")}</div>`
    : "";

  app.innerHTML = `
    <div class="section-title">Floor</div>
    <div class="section-hint">Pick up new orders, record who prepared them, and mark them served.</div>
    <div class="table-picker">
      <label for="waiter-select">You are</label>
      <select id="waiter-select">
        <option value="">Select your name\u2026</option>
        ${waiters.map((w) => `<option value="${w.id}" ${String(w.id) === String(state.actingWaiterId) ? "selected" : ""}>${w.name}</option>`).join("")}
      </select>
    </div>
    <div class="order-list">${listHtml}</div>
    ${settledHtml}
  `;

  document.getElementById("waiter-select").addEventListener("change", (e) => {
    state.actingWaiterId = e.target.value;
    localStorage.setItem("chowly_waiter_id", state.actingWaiterId);
  });

  app.querySelectorAll("[data-assign-order]").forEach((btn) => {
    btn.addEventListener("click", () => assignOrder(Number(btn.dataset.assignOrder)));
  });
  app.querySelectorAll("[data-serve-order]").forEach((btn) => {
    btn.addEventListener("click", () => serveOrder(Number(btn.dataset.serveOrder)));
  });
  app.querySelectorAll("[data-pay-order]").forEach((btn) => {
    btn.addEventListener("click", () => payOrder(Number(btn.dataset.payOrder)));
  });
}

function waiterOrderCardHtml(order, waiters, chefs, bartenders) {
  const statusLabel = {
    placed: "New \u2014 needs a waiter",
    assigned: "In progress",
    served: "Served \u2014 awaiting payment",
    paid: "Paid",
  }[order.status];

  const rows = order.items
    .map(
      (i) => `<div class="ticket-row"><span><span class="qty">${i.quantity}\u00d7</span>${i.menu_item.name}</span><span>${money(i.menu_item.price * i.quantity)}</span></div>`
    )
    .join("");

  const complaintHtml = order.complaint
    ? `<div class="complaint-filed">Complaint: "${escapeHtml(order.complaint.message)}" \u2014 rated ${order.complaint.rating}/5</div>`
    : "";

  let actionHtml = "";
  if (order.status === "placed") {
    actionHtml = `
      <div class="assign-row">
        <select data-chef-select="${order.id}">
          <option value="">Chef\u2026</option>
          ${chefs.map((c) => `<option value="${c.id}">${c.name}</option>`).join("")}
        </select>
        <select data-bartender-select="${order.id}">
          <option value="">Bartender\u2026</option>
          ${bartenders.map((b) => `<option value="${b.id}">${b.name}</option>`).join("")}
        </select>
        <button class="btn-primary" data-assign-order="${order.id}">Assign to me</button>
      </div>`;
  } else if (order.status === "assigned") {
    actionHtml = `<div class="ticket-actions"><button class="btn-primary" data-serve-order="${order.id}">Mark served</button></div>`;
  } else if (order.status === "served") {
    actionHtml = `<div class="ticket-actions"><button class="btn-primary" data-pay-order="${order.id}">Record payment (pretend)</button></div>`;
  }

  return `
    <div class="ticket">
      <div class="ticket-head">
        <div class="ticket-title">Table ${order.table_number} &middot; Order #${order.id}</div>
        <div class="ticket-status status-${order.status}">${statusLabel}</div>
      </div>
      ${rows}
      <div class="ticket-total"><span>Total</span><span>${money(order.total_price)}</span></div>
      <div class="ticket-meta">
        <span>Waiting time: ~${order.waiting_time_minutes} min</span>
        ${order.waiter ? `<span>Waiter: ${order.waiter.name}</span>` : ""}
        ${order.chef ? `<span>Chef: ${order.chef.name}</span>` : ""}
        ${order.bartender ? `<span>Bartender: ${order.bartender.name}</span>` : ""}
      </div>
      ${complaintHtml}
      ${actionHtml}
    </div>`;
}

async function assignOrder(orderId) {
  if (!state.actingWaiterId) {
    showToast("Select your name first");
    return;
  }
  const chefSelect = document.querySelector(`[data-chef-select="${orderId}"]`);
  const bartenderSelect = document.querySelector(`[data-bartender-select="${orderId}"]`);
  const payload = {
    waiter_id: Number(state.actingWaiterId),
    chef_id: chefSelect.value ? Number(chefSelect.value) : null,
    bartender_id: bartenderSelect.value ? Number(bartenderSelect.value) : null,
  };
  try {
    const updated = await api(`/orders/${orderId}/assign`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    const idx = state.waiterOrders.findIndex((o) => o.id === orderId);
    if (idx >= 0) state.waiterOrders[idx] = updated;
    showToast(`Order #${orderId} assigned`);
    renderWaiter();
  } catch (err) {
    showToast(err.message);
  }
}

async function serveOrder(orderId) {
  try {
    const updated = await api(`/orders/${orderId}/serve`, { method: "POST" });
    const idx = state.waiterOrders.findIndex((o) => o.id === orderId);
    if (idx >= 0) state.waiterOrders[idx] = updated;
    showToast(`Order #${orderId} marked served`);
    renderWaiter();
  } catch (err) {
    showToast(err.message);
  }
}

async function loadWaiterOrders() {
  state.waiterOrders = await api("/orders");
}

// ---------------------------------------------------------------------
// Render dispatch + polling
// ---------------------------------------------------------------------
function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

async function render() {
  if (state.role === "customer") {
    await loadMyOrders();
    renderCustomer();
  } else {
    await loadWaiterOrders();
    renderWaiter();
  }
}

async function init() {
  [state.menu, state.staff] = await Promise.all([api("/menu"), api("/staff")]);
  await render();
  // Light polling so both roles see near-live status without a login/session layer
  setInterval(() => {
    if (document.visibilityState === "visible") render();
  }, 6000);
}

init().catch((err) => showToast(err.message));
