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
  myOrderIds: JSON.parse(localStorage.getItem("chowly_my_orders") || "[]"),
  myOrders: [],
  waiterOrders: [],
  actingWaiterId: localStorage.getItem("chowly_waiter_id") || "",
  justCompletedPrepIds: new Set(),   // order_item_id -> plays the "just recorded" pop once
  justSettledOrderIds: new Set(),    // order_id -> plays the "just paid" glow once
  todayStats: null,
  drafts: {},   // orderId -> { rating, comment, complaint } — survives background re-renders
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

function escapeAttr(str) {
  return String(str).replace(/"/g, "&quot;");
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// "assigned" covers two real moments: a waiter has picked the order up,
// and — once at least one item has an actual chef/bartender recorded —
// the kitchen is actually working on it.
function assignedStageLabel(order) {
  const anyPrepped = order.preparations.some((p) => p.status === "completed");
  return anyPrepped ? "Order is being prepared" : "Assigned to a waiter";
}

// ---------------------------------------------------------------------
// Generated avatars — deterministic color + initials, no fake stock photos
// ---------------------------------------------------------------------
const AVATAR_PALETTE = ["#EB8A1E", "#1E7A52", "#1E7A6E", "#D33F3F", "#8C3A63", "#A85712"];

function avatarColor(name) {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
  return AVATAR_PALETTE[hash % AVATAR_PALETTE.length];
}

function initials(first, last) {
  return `${(first || "?")[0] || ""}${(last || "")[0] || ""}`.toUpperCase();
}

function avatarHtml(first, last, size = "md") {
  const name = `${first} ${last}`;
  return `<span class="avatar avatar-${size}" style="background:${avatarColor(name)}">${initials(first, last)}</span>`;
}

// ---------------------------------------------------------------------
// Real dish photography, matched by exact menu item name
// ---------------------------------------------------------------------
const MENU_PHOTOS = {
  "Jollof Rice & Grilled Chicken": "jollof_rice_and_grilled_chicken.jpg",
  "Suya Platter": "suya_platter.jpg",
  "Pounded Yam & Egusi Soup": "pounded_yam_and_egusi_soup.jpg",
  "Peppered Snails": "peppered_snail.jpg",
  "Plantain & Fish Pepper Soup": "plantain_and_fish_pepper_stew.jpg",
  "Chapman": "chapman.jpg",
  "Zobo": "zobo.jpg",
  "Palm Wine": "palm_wine.jpg",
  "Chilled Star Lager": "star_lager.jpg",
  "Fresh Pineapple Juice": "pineapple_juice.jpg",
};

function menuPhotoUrl(item) {
  const file = MENU_PHOTOS[item.item_name];
  return file ? `/static/images/food/${file}` : null;
}

function menuItemPhotoHtml(item) {
  const url = menuPhotoUrl(item);
  if (!url) return "";
  return `<img class="menu-item-photo" src="${url}" alt="${escapeAttr(item.item_name)}" loading="lazy">`;
}

// ---------------------------------------------------------------------
// Dark mode toggle
// ---------------------------------------------------------------------
(function initTheme() {
  const stored = localStorage.getItem("chowly_theme");
  if (stored === "dark") document.documentElement.dataset.theme = "dark";
  document.getElementById("theme-toggle").addEventListener("click", () => {
    const isDark = document.documentElement.dataset.theme === "dark";
    if (isDark) {
      delete document.documentElement.dataset.theme;
      localStorage.setItem("chowly_theme", "light");
    } else {
      document.documentElement.dataset.theme = "dark";
      localStorage.setItem("chowly_theme", "dark");
    }
  });
})();

// ---------------------------------------------------------------------
// Role switch
// ---------------------------------------------------------------------
const roleSwitchEl = document.querySelector(".role-switch");

document.querySelectorAll(".role-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".role-btn").forEach((b) => {
      b.classList.remove("is-active");
      b.setAttribute("aria-selected", "false");
    });
    btn.classList.add("is-active");
    btn.setAttribute("aria-selected", "true");
    roleSwitchEl.classList.toggle("is-waiter", btn.dataset.role === "waiter");
    document.querySelector(".scene-photo-customer").classList.toggle("is-active", btn.dataset.role === "customer");
    document.querySelector(".scene-photo-waiter").classList.toggle("is-active", btn.dataset.role === "waiter");
    state.role = btn.dataset.role;
    render(true);
  });
});

// ---------------------------------------------------------------------
// Customer view
// ---------------------------------------------------------------------
function renderCustomer(animateEntrance) {
  const categories = {};
  state.menu
    .filter((item) => item.availability_status !== "sold_out")
    .forEach((item) => {
      (categories[item.item_type] = categories[item.item_type] || []).push(item);
    });

  const categoryLabels = { food: "Food", drink: "Drinks" };
  let runningIndex = 0;
  const categoryHtml = Object.entries(categories)
    .map(([cat, items]) => {
      const itemsHtml = items
        .map((item) => {
          const html = menuItemHtml(item, animateEntrance ? runningIndex : null);
          runningIndex++;
          return html;
        })
        .join("");
      return `
      <div class="menu-category">
        <h3 class="cat-${cat}">${categoryLabels[cat] || cat}</h3>
        <div class="menu-grid${animateEntrance ? " enter-stagger" : ""}">
          ${itemsHtml}
        </div>
      </div>`;
    })
    .join("");

  const ticketsHtml = state.myOrders.length
    ? `<div class="section-title" style="margin-top:44px">Your orders</div>
       <div class="section-hint">Track status, waiting time, and pay when you're ready to leave.</div>
       ${state.myOrders.map(orderTicketHtml).join("")}`
    : "";

  app.innerHTML = `
    <div class="intro-panel">
      <div class="section-title">Tonight's menu</div>
      <div class="section-hint">Tell us who you are and which table you're at, then send your order to the kitchen.</div>
      <div class="table-picker">
        <label for="name-input">Your name</label>
        <input id="name-input" type="text" value="${escapeAttr(state.customerName)}" placeholder="e.g. Daniel Adeyemi">
        <label for="table-input">Table</label>
        <input id="table-input" type="number" min="1" value="${state.tableNumber}" placeholder="e.g. 5">
      </div>
    </div>
    ${categoryHtml}
    ${ticketsHtml}
  `;

  document.getElementById("name-input").addEventListener("input", (e) => {
    state.customerName = e.target.value;
    localStorage.setItem("chowly_customer_name", state.customerName);
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
      renderCustomer(false);
      renderCartBar();
    });
  });

  app.querySelectorAll("[data-complaint-form]").forEach(wireComplaintForm);
  app.querySelectorAll("[data-rating-form]").forEach(wireRatingForm);
  app.querySelectorAll("[data-pay-order]").forEach((btn) => {
    btn.addEventListener("click", () => payOrder(Number(btn.dataset.payOrder)));
  });
  app.querySelectorAll("[data-cancel-order]").forEach((btn) => {
    btn.addEventListener("click", () => cancelOrder(Number(btn.dataset.cancelOrder)));
  });
  app.querySelectorAll("[data-print-order]").forEach((btn) => {
    btn.addEventListener("click", () => printOrder(Number(btn.dataset.printOrder)));
  });

  renderCartBar();
}

function menuItemHtml(item, staggerIndex) {
  const qty = state.cart[item.id] || 0;
  const styleAttr = staggerIndex !== null ? ` style="--i:${staggerIndex}"` : "";
  const typeClass = item.item_type === "drink" ? " is-drink" : "";
  return `
    <div class="menu-item${typeClass}"${styleAttr}>
      ${menuItemPhotoHtml(item)}
      <div class="menu-item-body">
        <div class="menu-item-name">${item.item_name}</div>
        <div class="menu-item-meta">${item.prep_time_minutes} min</div>
        <div class="menu-item-footer">
          <div class="menu-item-price">${money(item.price)}</div>
          <div class="qty-control">
            <button class="qty-btn" data-qty-action="-1" data-id="${item.id}" aria-label="Remove one ${item.item_name}">&minus;</button>
            <span class="qty-value">${qty}</span>
            <button class="qty-btn" data-qty-action="1" data-id="${item.id}" aria-label="Add one ${item.item_name}">&plus;</button>
          </div>
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
  if (!state.customerName.trim()) {
    showToast("Enter your name first");
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
        customer: { ...splitName(state.customerName), phone_number: null },
        items,
      }),
    });
    state.cart = {};
    state.myOrderIds.push(order.id);
    localStorage.setItem("chowly_my_orders", JSON.stringify(state.myOrderIds));
    state.myOrders.unshift(order);
    showToast(`Order sent to the kitchen \u2014 about ${order.estimated_waiting_time_minutes} min`);
    renderCustomer(false);
  } catch (err) {
    showToast(err.message);
  }
}

function orderTicketHtml(order) {
  const statusLabel = {
    placed: "Placed \u2014 waiting on a waiter",
    assigned: assignedStageLabel(order),
    served: "Served",
    paid: "Paid",
    cancelled: "Cancelled",
  }[order.status];

  const rows = order.items
    .map(
      (i) => `<div class="ticket-row"><span><span class="qty">${i.quantity}\u00d7</span>${i.menu_item.item_name}</span><span>${money(i.subtotal)}</span></div>`
    )
    .join("");

  const inactiveStatuses = ["placed", "assigned", "cancelled"];
  const canRate = !order.rating && !inactiveStatuses.includes(order.status);
  const canComplain = !order.complaint && !inactiveStatuses.includes(order.status);

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

  const cancelAction = isCancellable(order)
    ? `<button class="btn-cancel" data-cancel-order="${order.id}">Cancel order</button>`
    : "";

  const paymentNote = order.payment
    ? `<div class="ticket-meta"><span>Paid \u2713 ref ${order.payment.transaction_reference}</span></div>`
    : "";

  const statusPop = state.justSettledOrderIds.has(order.id) ? " just-settled" : "";

  return `
    <div class="ticket">
      <div class="ticket-head">
        <div class="ticket-title">Table ${order.table_number} &middot; Order #${order.id}</div>
        <div class="ticket-status status-${order.status}${statusPop}">${statusLabel}</div>
      </div>
      ${rows}
      <div class="ticket-total"><span>Total</span><span>${money(order.total_amount)}</span></div>
      <div class="ticket-meta">
        <span>Waiting time: ~${order.estimated_waiting_time_minutes} min</span>
        ${order.waiter ? `<span class="avatar-tag">${avatarHtml(order.waiter.first_name, order.waiter.last_name, "sm")} ${order.waiter.first_name} ${order.waiter.last_name}</span>` : ""}
      </div>
      ${paymentNote}
      ${order.status !== "cancelled" ? `
      <div class="ticket-actions">
        ${payAction}
        <button class="btn-print" data-print-order="${order.id}">Print ${order.payment ? "receipt" : "ticket"}</button>
        ${cancelAction}
      </div>` : ""}
      ${ratingSection}
      ${complaintSection}
    </div>`;
}

// Cancellable while it's still just sitting in the queue: nobody's picked
// it up yet, or a waiter has but no chef/bartender has actually started.
function isCancellable(order) {
  if (order.status === "placed") return true;
  if (order.status !== "assigned") return false;
  return !order.preparations.some((p) => p.status === "completed");
}

function ratingFormHtml(orderId) {
  const draft = state.drafts[orderId] || {};
  const rating = draft.rating || 0;
  return `
    <div class="complaint-box" data-rating-form data-order-id="${orderId}">
      <label>Rate this order</label>
      <div class="rating-picker" data-rating-picker>
        ${[1, 2, 3, 4, 5].map((n) => `<button type="button" class="rating-star${n <= rating ? " is-active" : ""}" data-star="${n}">&#9733;</button>`).join("")}
      </div>
      <textarea data-rating-comment placeholder="Optional comment">${escapeHtml(draft.comment || "")}</textarea>
      <div class="ticket-actions">
        <button class="btn-secondary" data-submit-rating>Submit rating</button>
      </div>
    </div>`;
}

function complaintFormHtml(orderId) {
  const draft = state.drafts[orderId] || {};
  return `
    <div class="complaint-box" data-complaint-form data-order-id="${orderId}">
      <label>Something wrong with this order? Let the kitchen know.</label>
      <textarea data-complaint-message placeholder="What happened?">${escapeHtml(draft.complaint || "")}</textarea>
      <div class="ticket-actions">
        <button class="btn-secondary" data-submit-complaint>Submit complaint</button>
      </div>
    </div>`;
}

function getDraft(orderId) {
  if (!state.drafts[orderId]) state.drafts[orderId] = {};
  return state.drafts[orderId];
}

function wireRatingForm(box) {
  const orderId = Number(box.dataset.orderId);
  const draft = getDraft(orderId);
  const stars = box.querySelectorAll("[data-star]");
  stars.forEach((star) => {
    star.addEventListener("click", () => {
      draft.rating = Number(star.dataset.star);
      stars.forEach((s) => s.classList.toggle("is-active", Number(s.dataset.star) <= draft.rating));
    });
  });
  box.querySelector("[data-rating-comment]").addEventListener("input", (e) => {
    draft.comment = e.target.value;
  });

  box.querySelector("[data-submit-rating]").addEventListener("click", async () => {
    if (!draft.rating) {
      showToast("Pick a star rating first");
      return;
    }
    const comment = (draft.comment || "").trim();
    try {
      const updated = await api(`/orders/${orderId}/rating`, {
        method: "POST",
        body: JSON.stringify({ rating_value: draft.rating, comment: comment || null }),
      });
      applyOrderUpdate(updated);
      delete state.drafts[orderId];
      showToast("Thanks for rating your order");
      render(false);
    } catch (err) {
      showToast(err.message);
    }
  });
}

function wireComplaintForm(box) {
  const orderId = Number(box.dataset.orderId);
  const draft = getDraft(orderId);
  box.querySelector("[data-complaint-message]").addEventListener("input", (e) => {
    draft.complaint = e.target.value;
  });

  box.querySelector("[data-submit-complaint]").addEventListener("click", async () => {
    const description = (draft.complaint || "").trim();
    if (!description) {
      showToast("Add a message first");
      return;
    }
    try {
      const updated = await api(`/orders/${orderId}/complaint`, {
        method: "POST",
        body: JSON.stringify({ description }),
      });
      applyOrderUpdate(updated);
      delete state.drafts[orderId];
      showToast("Complaint sent \u2014 thanks for letting us know");
      render(false);
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
    state.justSettledOrderIds.add(orderId);
    render(false);
    setTimeout(() => state.justSettledOrderIds.delete(orderId), 1300);
  } catch (err) {
    showToast(err.message);
  }
}

async function cancelOrder(orderId) {
  try {
    const updated = await api(`/orders/${orderId}/cancel`, { method: "POST" });
    applyOrderUpdate(updated);
    showToast(`Order #${orderId} cancelled`);
    render(false);
  } catch (err) {
    showToast(err.message);
  }
}

function printOrder(orderId) {
  const order =
    state.myOrders.find((o) => o.id === orderId) || state.waiterOrders.find((o) => o.id === orderId);
  if (!order) {
    showToast("Couldn't find that order to print");
    return;
  }

  const isReceipt = !!order.payment;
  const rows = order.items
    .map((i) => {
      const prep = order.preparations.find((p) => p.order_item_id === i.id);
      const who = prep && prep.status === "completed" ? (prep.chef || prep.bartender) : null;
      const whoLine = who ? ` (${who.first_name} ${who.last_name})` : "";
      return `<tr><td>${i.quantity}\u00d7 ${i.menu_item.item_name}${isReceipt ? "" : whoLine}</td><td style="text-align:right">${money(i.subtotal)}</td></tr>`;
    })
    .join("");

  document.getElementById("print-area").innerHTML = `
    <div class="print-ticket">
      <span class="print-tag">${isReceipt ? "RECEIPT" : "KITCHEN TICKET"}</span>
      <h2>Chowly \u2014 Table ${order.table_number}</h2>
      <div class="print-meta">
        Order #${order.id} &middot; ${new Date(order.order_time).toLocaleString()}<br>
        ${order.customer.first_name} ${order.customer.last_name}
        ${order.waiter ? ` &middot; Waiter: ${order.waiter.first_name} ${order.waiter.last_name}` : ""}
      </div>
      <table>${rows}</table>
      <div class="print-total">Total: ${money(order.total_amount)}</div>
      ${isReceipt ? `<div class="print-meta">Paid (pretend) &middot; ref ${order.payment.transaction_reference}</div>` : ""}
    </div>`;

  window.print();
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

  const active = state.waiterOrders.filter((o) => o.status !== "paid" && o.status !== "cancelled");
  const settled = state.waiterOrders.filter((o) => o.status === "paid");
  const cancelled = state.waiterOrders.filter((o) => o.status === "cancelled");

  const listHtml = active.length
    ? `<div class="ticket-rail"></div><div class="order-list is-rail">${active.map((o) => waiterOrderCardHtml(o, waiters, chefs, bartenders, true)).join("")}</div>`
    : `<div class="empty-state"><p>All caught up</p><span>No active orders right now.</span></div>`;

  const settledHtml = settled.length
    ? `<div class="section-title" style="margin-top:44px">Settled tonight</div>
       <div class="order-list">${settled.map((o) => waiterOrderCardHtml(o, waiters, chefs, bartenders)).join("")}</div>`
    : "";

  const cancelledHtml = cancelled.length
    ? `<div class="section-title" style="margin-top:44px">Cancelled</div>
       <div class="order-list">${cancelled.map((o) => waiterOrderCardHtml(o, waiters, chefs, bartenders)).join("")}</div>`
    : "";

  const waiterChipsHtml = waiters
    .map((w) => {
      const isActive = String(w.id) === String(state.actingWaiterId);
      return `<button type="button" class="waiter-chip${isActive ? " is-active" : ""}" data-waiter-chip="${w.id}">${avatarHtml(w.first_name, w.last_name, "sm")} ${w.first_name} ${w.last_name}</button>`;
    })
    .join("");

  const s = state.todayStats;
  const statsHtml = s
    ? `<div class="stats-grid">
        <div class="stat-card"><div class="stat-value">${money(s.revenue_today)}</div><div class="stat-label">Revenue today</div></div>
        <div class="stat-card"><div class="stat-value">${s.orders_today}</div><div class="stat-label">Orders today</div></div>
        <div class="stat-card"><div class="stat-value">${s.top_item ? escapeHtml(s.top_item) : "\u2014"}</div><div class="stat-label">${s.top_item ? `Top seller \u00b7 ${s.top_item_quantity} sold` : "Top seller"}</div></div>
        <div class="stat-card"><div class="stat-value">${s.average_rating !== null ? `${s.average_rating}/5` : "\u2014"}</div><div class="stat-label">Avg rating today</div></div>
      </div>`
    : "";

  const manageMenuHtml = `
    <div class="manage-menu">
      <label>Menu availability</label>
      <div class="manage-menu-list">
        ${state.menu
          .map((item) => {
            const soldOut = item.availability_status === "sold_out";
            return `<span class="manage-chip${soldOut ? " is-sold-out" : ""}">${item.item_name}
              <button type="button" class="manage-chip-toggle" data-toggle-availability="${item.id}">${soldOut ? "Un-86" : "86 it"}</button></span>`;
          })
          .join("")}
      </div>
      <a class="qr-link" href="/qr" target="_blank" rel="noopener">Print table QR codes &#8599;</a>
    </div>`;

  app.innerHTML = `
    <div class="intro-panel">
      <div class="section-title">Floor</div>
      <div class="section-hint">Pick up new orders, record who prepared each item, and mark them served.</div>
      <div class="table-picker">
        <label>You are</label>
        <div class="waiter-picker">${waiterChipsHtml}</div>
      </div>
      ${statsHtml}
      ${manageMenuHtml}
    </div>
    ${listHtml}
    ${settledHtml}
    ${cancelledHtml}
  `;

  app.querySelectorAll("[data-waiter-chip]").forEach((chip) => {
    chip.addEventListener("click", () => {
      state.actingWaiterId = chip.dataset.waiterChip;
      localStorage.setItem("chowly_waiter_id", state.actingWaiterId);
      renderWaiter();
    });
  });

  app.querySelectorAll("[data-toggle-availability]").forEach((btn) => {
    btn.addEventListener("click", () => toggleAvailability(Number(btn.dataset.toggleAvailability)));
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
  app.querySelectorAll("[data-print-order]").forEach((btn) => {
    btn.addEventListener("click", () => printOrder(Number(btn.dataset.printOrder)));
  });

  renderCartBar();
}

async function toggleAvailability(itemId) {
  try {
    await api(`/menu/${itemId}/toggle-availability`, { method: "POST" });
    state.menu = await api("/menu");
    renderWaiter();
  } catch (err) {
    showToast(err.message);
  }
}

function waiterOrderCardHtml(order, waiters, chefs, bartenders, onRail) {
  const statusLabel = {
    placed: "New \u2014 needs a waiter",
    assigned: assignedStageLabel(order),
    served: "Served \u2014 awaiting payment",
    paid: "Paid",
    cancelled: "Cancelled by customer",
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

  const statusPop = state.justSettledOrderIds.has(order.id) ? " just-settled" : "";
  const printHtml =
    order.status !== "cancelled"
      ? `<div class="ticket-actions"><button class="btn-print" data-print-order="${order.id}">Print ${order.payment ? "receipt" : "ticket"}</button></div>`
      : "";

  return `
    <div class="ticket">
      ${onRail ? '<div class="spike-hole"></div>' : ""}
      <div class="ticket-head">
        <div class="ticket-title">Table ${order.table_number} &middot; Order #${order.id}</div>
        <div class="ticket-status status-${order.status}${statusPop}">${statusLabel}</div>
      </div>
      <div class="ticket-meta"><span>${order.customer.first_name} ${order.customer.last_name}</span></div>
      ${rows}
      <div class="ticket-total"><span>Total</span><span>${money(order.total_amount)}</span></div>
      <div class="ticket-meta">
        <span>Waiting time: ~${order.estimated_waiting_time_minutes} min</span>
        ${order.waiter ? `<span class="avatar-tag">${avatarHtml(order.waiter.first_name, order.waiter.last_name, "sm")} ${order.waiter.first_name} ${order.waiter.last_name}</span>` : ""}
      </div>
      ${complaintHtml}
      ${ratingHtml}
      ${actionHtml}
      ${printHtml}
    </div>`;
}

function preparationRowHtml(orderId, prep, chefs, bartenders) {
  if (prep.status === "completed") {
    const person = prep.chef || prep.bartender;
    const roleWord = prep.chef ? "Chef" : "Bartender";
    const justDone = state.justCompletedPrepIds.has(prep.order_item_id) ? " prep-pop" : "";
    return `
      <div class="prep-row prep-done${justDone}">
        <span>${prep.menu_item.item_name}</span>
        <span class="prep-done-who">${avatarHtml(person.first_name, person.last_name, "sm")} ${roleWord} ${person.first_name} ${person.last_name} \u2713</span>
      </div>`;
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
    state.justCompletedPrepIds.add(orderItemId);
    renderWaiter();
    setTimeout(() => state.justCompletedPrepIds.delete(orderItemId), 600);
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
async function render(isUserAction) {
  state.menu = await api("/menu");
  if (state.role === "customer") {
    await loadMyOrders();
    renderCustomer(!!isUserAction);
  } else {
    await Promise.all([loadWaiterOrders(), loadTodayStats()]);
    renderWaiter();
  }
}

async function loadTodayStats() {
  state.todayStats = await api("/stats/today").catch(() => null);
}

async function init() {
  const params = new URLSearchParams(window.location.search);
  const tableParam = params.get("table");
  if (tableParam) {
    state.tableNumber = tableParam;
    localStorage.setItem("chowly_table", state.tableNumber);
  }

  state.staff = await api("/staff");
  await render(true);
  setInterval(() => {
    const active = document.activeElement;
    const isTyping = active && (active.tagName === "TEXTAREA" || active.tagName === "INPUT");
    if (document.visibilityState === "visible" && !isTyping) render(false);
  }, 6000);
}

init().catch((err) => showToast(err.message));