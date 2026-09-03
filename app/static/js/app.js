// ---------------------------------------------------------------------
// State
// ---------------------------------------------------------------------
const state = {
  role: "customer",
  menu: [],
  staff: { waiters: [], chefs: [], bartenders: [] },
  cart: {},           // menu_item_id -> quantity
  tableNumber: localStorage.getItem("chowly_table") || "",
  customerName: localStorage.getItem("chowly_customer_name") || "",
  customerPhone: localStorage.getItem("chowly_customer_phone") || "",
  myOrderIds: JSON.parse(localStorage.getItem("chowly_my_orders") || "[]"),
  myOrders: [],
  waiterOrders: [],
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

function splitName(fullName) {
  const trimmed = fullName.trim();
  const idx = trimmed.indexOf(" ");
  if (idx === -1) return { first_name: trimmed, last_name: "-" };
  return { first_name: trimmed.slice(0, idx), last_name: trimmed.slice(idx + 1) };
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
    (categories[item.item_type] = categories[item.item_type] || []).push(item);
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
    <div class="section-hint">Tell us who you are and which table you're at, then send your order to the kitchen.</div>
    <div class="table-picker">
      <label for="name-input">Your name</label>
      <input id="name-input" type="text" value="${escapeAttr(state.customerName)}" placeholder="e.g. Daniel Adeyemi">
      <label for="phone-input">Phone</label>
      <input id="phone-input" type="tel" value="${escapeAttr(state.customerPhone)}" placeholder="e.g. 08012345678">
      <label for="table-input">Table</label>
      <input id="table-input" type="number" min="1" value="${state.tableNumber}" placeholder="e.g. 5">
    </div>
    ${categoryHtml}
    ${ticketsHtml}
  `;

  document.getElementById("name-input").addEventListener("input", (e) => {
    state.customerName = e.target.value;
    localStorage.setItem("chowly_customer_name", state.customerName);
  });
  document.getElementById("phone-input").addEventListener("input", (e) => {
    state.customerPhone = e.target.value;
    localStorage.setItem("chowly_customer_phone", state.customerPhone);
  });
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
  app.querySelectorAll("[data-rating-form]").forEach(wireRatingForm);
  app.querySelectorAll("[data-pay-order]").forEach((btn) => {
    btn.addEventListener("click", () => payOrder(Number(btn.dataset.payOrder)));
  });

  renderCartBar();
}

function escapeAttr(str) {
  return String(str).replace(/"/g, "&quot;");
}

function menuItemHtml(item) {
  const qty = state.cart[item.id] || 0;
  return `
    <div class="menu-item">
      <div class="menu-item-name">${item.item_name}</div>
      <div class="menu-item-meta">${item.prep_time_minutes} min &middot; ${item.item_type}</div>
      <div class="menu-item-footer">
        <div class="menu-item-price">${money(item.price)}</div>
        <div class="qty-control">
          <button class="qty-btn" data-qty-action="-1" data-id="${item.id}" aria-label="Remove one ${item.item_name}">&minus;</button>
          <span class="qty-value">${qty}</span>
          <button class="qty-btn" data-qty-action="1" data-id="${item.id}" aria-label="Add one ${item.item_name}">&plus;</button>
        </div>
      </div>
    </div>`;
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
  if (!state.customerName.trim() || !state.customerPhone.trim()) {
    showToast("Enter your name and phone number first");
    return;
  }
  const items = Object.entries(state.cart).map(([menu_item_id, quantity]) => ({
    menu_item_id: Number(menu_item_id),
    quantity,
  }));
  try {
    const order = await api("/orders", {
      method: "POST",
      body: JSON.stringify({
        table_number: Number(state.tableNumber),
        customer: { ...splitName(state.customerName), phone_number: state.customerPhone.trim() },
        items,
      }),
    });
    state.cart = {};
    state.myOrderIds.push(order.id);
    localStorage.setItem("chowly_my_orders", JSON.stringify(state.myOrderIds));
    state.myOrders.unshift(order);
    showToast(`Order sent to the kitchen \u2014 about ${order.estimated_waiting_time_minutes} min`);
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
      (i) => `<div class="ticket-row"><span><span class="qty">${i.quantity}\u00d7</span>${i.menu_item.item_name}</span><span>${money(i.subtotal)}</span></div>`
    )
    .join("");

  const canRate = !order.rating && order.status !== "placed" && order.status !== "assigned";
  const canComplain = !order.complaint && order.status !== "placed" && order.status !== "assigned";

  const ratingSection = order.rating
    ? `<div class="rating-filed">You rated this order ${order.rating.rating_value}/5${order.rating.comment ? ` \u2014 "${escapeHtml(order.rating.comment)}"` : ""}</div>`
    : canRate
    ? ratingFormHtml(order.id)
    : "";

  const complaintSection = order.complaint
    ? `<div class="complaint-filed">You reported: "${escapeHtml(order.complaint.description)}"</div>`
    : canComplain
    ? complaintFormHtml(order.id)
    : "";

  const payAction =
    !order.payment && order.status === "served"
      ? `<button class="btn-primary" data-pay-order="${order.id}">Pay (pretend)</button>`
      : "";

  const paymentNote = order.payment
    ? `<div class="ticket-meta"><span>Paid \u2713 ref ${order.payment.transaction_reference}</span></div>`
    : "";

  return `
    <div class="ticket">
      <div class="ticket-head">
        <div class="ticket-title">Table ${order.table_number} &middot; Order #${order.id}</div>
        <div class="ticket-status status-${order.status}">${statusLabel}</div>
      </div>
      ${rows}
      <div class="ticket-total"><span>Total</span><span>${money(order.total_amount)}</span></div>
      <div class="ticket-meta">
        <span>Waiting time: ~${order.estimated_waiting_time_minutes} min</span>
        ${order.waiter ? `<span>Waiter: ${order.waiter.first_name} ${order.waiter.last_name}</span>` : ""}
      </div>
      ${paymentNote}
      ${payAction ? `<div class="ticket-actions">${payAction}</div>` : ""}
      ${ratingSection}
      ${complaintSection}
    </div>`;
}

function ratingFormHtml(orderId) {
  return `
    <div class="complaint-box" data-rating-form data-order-id="${orderId}">
      <label>Rate this order</label>
      <div class="rating-picker" data-rating-picker>
        ${[1, 2, 3, 4, 5].map((n) => `<button type="button" class="rating-star" data-star="${n}">&#9733;</button>`).join("")}
      </div>
      <textarea data-rating-comment placeholder="Optional comment"></textarea>
      <div class="ticket-actions">
        <button class="btn-secondary" data-submit-rating>Submit rating</button>
      </div>
    </div>`;
}

function complaintFormHtml(orderId) {
  return `
    <div class="complaint-box" data-complaint-form data-order-id="${orderId}">
      <label>Something wrong with this order? Let the kitchen know.</label>
      <textarea data-complaint-message placeholder="What happened?"></textarea>
      <div class="ticket-actions">
        <button class="btn-secondary" data-submit-complaint>Submit complaint</button>
      </div>
    </div>`;
}

function wireRatingForm(box) {
  let rating = 0;
  const stars = box.querySelectorAll("[data-star]");
  stars.forEach((star) => {
    star.addEventListener("click", () => {
      rating = Number(star.dataset.star);
      stars.forEach((s) => s.classList.toggle("is-active", Number(s.dataset.star) <= rating));
    });
  });

  box.querySelector("[data-submit-rating]").addEventListener("click", async () => {
    if (!rating) {
      showToast("Pick a star rating first");
      return;
    }
    const comment = box.querySelector("[data-rating-comment]").value.trim();
    const orderId = Number(box.dataset.orderId);
    try {
      const updated = await api(`/orders/${orderId}/rating`, {
        method: "POST",
        body: JSON.stringify({ rating_value: rating, comment: comment || null }),
      });
      applyOrderUpdate(updated);
      showToast("Thanks for rating your order");
      render();
    } catch (err) {
      showToast(err.message);
    }
  });
}

function wireComplaintForm(box) {
  box.querySelector("[data-submit-complaint]").addEventListener("click", async () => {
    const description = box.querySelector("[data-complaint-message]").value.trim();
    if (!description) {
      showToast("Add a message first");
      return;
    }
    const orderId = Number(box.dataset.orderId);
    try {
      const updated = await api(`/orders/${orderId}/complaint`, {
        method: "POST",
        body: JSON.stringify({ description }),
      });
      applyOrderUpdate(updated);
      showToast("Complaint sent \u2014 thanks for letting us know");
      render();
    } catch (err) {
      showToast(err.message);
    }
  });
}

async function payOrder(orderId) {
  try {
    const updated = await api(`/orders/${orderId}/pay`, { method: "POST" });
    applyOrderUpdate(updated);
    showToast("Payment recorded (pretend) \u2014 see you again soon");
    render();
  } catch (err) {
    showToast(err.message);
  }
}

function applyOrderUpdate(updated) {
  const midx = state.myOrders.findIndex((o) => o.id === updated.id);
  if (midx >= 0) state.myOrders[midx] = updated;
  const widx = state.waiterOrders.findIndex((o) => o.id === updated.id);
  if (widx >= 0) state.waiterOrders[widx] = updated;
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
  const { waiters, chefs, bartenders } = state.staff;

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
    <div class="section-hint">Pick up new orders, record who prepared each item, and mark them served.</div>
    <div class="table-picker">
      <label for="waiter-select">You are</label>
      <select id="waiter-select">
        <option value="">Select your name\u2026</option>
        ${waiters.map((w) => `<option value="${w.id}" ${String(w.id) === String(state.actingWaiterId) ? "selected" : ""}>${w.first_name} ${w.last_name}</option>`).join("")}
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
  app.querySelectorAll("[data-prepare-item]").forEach((btn) => {
    btn.addEventListener("click", () => recordPreparation(Number(btn.dataset.orderId), Number(btn.dataset.prepareItem)));
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
      (i) => `<div class="ticket-row"><span><span class="qty">${i.quantity}\u00d7</span>${i.menu_item.item_name}</span><span>${money(i.subtotal)}</span></div>`
    )
    .join("");

  const complaintHtml = order.complaint
    ? `<div class="complaint-filed">Complaint: "${escapeHtml(order.complaint.description)}"</div>`
    : "";
  const ratingHtml = order.rating
    ? `<div class="rating-filed">Rated ${order.rating.rating_value}/5${order.rating.comment ? ` \u2014 "${escapeHtml(order.rating.comment)}"` : ""}</div>`
    : "";

  let actionHtml = "";
  if (order.status === "placed") {
    actionHtml = `
      <div class="assign-row">
        <button class="btn-primary" data-assign-order="${order.id}">Assign to me</button>
      </div>`;
  } else if (order.status === "assigned") {
    actionHtml = `<div class="prep-list">${order.preparations.map((p) => preparationRowHtml(order.id, p, chefs, bartenders)).join("")}</div>`;
    const allDone = order.preparations.every((p) => p.status === "completed");
    if (allDone) {
      actionHtml += `<div class="ticket-actions"><button class="btn-primary" data-serve-order="${order.id}">Mark served</button></div>`;
    }
  } else if (order.status === "served") {
    actionHtml = `<div class="ticket-actions"><button class="btn-primary" data-pay-order="${order.id}">Record payment (pretend)</button></div>`;
  }

  return `
    <div class="ticket">
      <div class="ticket-head">
        <div class="ticket-title">Table ${order.table_number} &middot; Order #${order.id}</div>
        <div class="ticket-status status-${order.status}">${statusLabel}</div>
      </div>
      <div class="ticket-meta"><span>${order.customer.first_name} ${order.customer.last_name}</span><span>${order.customer.phone_number}</span></div>
      ${rows}
      <div class="ticket-total"><span>Total</span><span>${money(order.total_amount)}</span></div>
      <div class="ticket-meta">
        <span>Waiting time: ~${order.estimated_waiting_time_minutes} min</span>
        ${order.waiter ? `<span>Waiter: ${order.waiter.first_name} ${order.waiter.last_name}</span>` : ""}
      </div>
      ${complaintHtml}
      ${ratingHtml}
      ${actionHtml}
    </div>`;
}

function preparationRowHtml(orderId, prep, chefs, bartenders) {
  if (prep.status === "completed") {
    const who = prep.chef ? `Chef ${prep.chef.first_name} ${prep.chef.last_name}` : `Bartender ${prep.bartender.first_name} ${prep.bartender.last_name}`;
    return `<div class="prep-row prep-done"><span>${prep.menu_item.item_name}</span><span>${who} \u2713</span></div>`;
  }

  const isFood = prep.menu_item.item_type === "food";
  const options = isFood ? chefs : bartenders;
  const roleLabel = isFood ? "chef" : "bartender";

  return `
    <div class="prep-row">
      <span>${prep.menu_item.item_name}</span>
      <div class="prep-controls">
        <select data-preparer-select="${prep.order_item_id}">
          <option value="">${roleLabel}\u2026</option>
          ${options.map((o) => `<option value="${o.id}">${o.first_name} ${o.last_name}</option>`).join("")}
        </select>
        <button class="btn-secondary" data-prepare-item="${prep.order_item_id}" data-order-id="${orderId}" data-item-type="${prep.menu_item.item_type}">Record</button>
      </div>
    </div>`;
}

async function assignOrder(orderId) {
  if (!state.actingWaiterId) {
    showToast("Select your name first");
    return;
  }
  try {
    const updated = await api(`/orders/${orderId}/assign`, {
      method: "POST",
      body: JSON.stringify({ waiter_id: Number(state.actingWaiterId) }),
    });
    applyOrderUpdate(updated);
    showToast(`Order #${orderId} assigned`);
    renderWaiter();
  } catch (err) {
    showToast(err.message);
  }
}

async function recordPreparation(orderId, orderItemId) {
  const select = document.querySelector(`[data-preparer-select="${orderItemId}"]`);
  if (!select.value) {
    showToast("Pick who prepared this item first");
    return;
  }
  const btn = document.querySelector(`[data-prepare-item="${orderItemId}"]`);
  const isFood = btn.dataset.itemType === "food";
  const payload = isFood ? { chef_id: Number(select.value) } : { bartender_id: Number(select.value) };
  try {
    const updated = await api(`/orders/${orderId}/items/${orderItemId}/prepare`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    applyOrderUpdate(updated);
    renderWaiter();
  } catch (err) {
    showToast(err.message);
  }
}

async function serveOrder(orderId) {
  try {
    const updated = await api(`/orders/${orderId}/serve`, { method: "POST" });
    applyOrderUpdate(updated);
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
  const [menu, staff] = await Promise.all([api("/menu"), api("/staff")]);
  state.menu = menu;
  state.staff = staff;
  await render();
  setInterval(() => {
    if (document.visibilityState === "visible") render();
  }, 6000);
}

init().catch((err) => showToast(err.message));
