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
  drafts: {},   // orderId -> { rating, comment, complaint, category, dish, cancelReason, payMethod } — survives background re-renders
  prepDrafts: {}, // orderItemId -> selected staff id — survives background re-renders
  // Lab 1
  locations: [],
  locationCode: localStorage.getItem("chowly_location") || "LEK",
  customerPhone: localStorage.getItem("chowly_customer_phone") || "",
  vocab: { complaint_categories: {}, cancel_reasons: {}, payment_methods: {} },
  office: {
    name: localStorage.getItem("chowly_office_name") || "",
    sources: [],
    imports: [],
    openBatch: null,       // batch detail with quarantined rows
    importSource: "delivery_platform",
    menuAll: [],
    menuEvents: [],
    complaints: [],
    corrections: [],
  },
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
    throw new Error(errorText(body.detail));
  }
  return res.status === 204 ? null : res.json();
}

// FastAPI sends validation errors as a list; turn them into one readable line.
function errorText(detail) {
  if (!detail) return "Something went wrong";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => String(d.msg || d).replace(/^Value error, /, "")).join("; ");
  return String(detail);
}

// The API stores times in UTC without a zone marker; show them in local time.
function parseTime(s) {
  if (!s) return null;
  return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(s) ? s : s + "Z");
}

function fmtTime(s) {
  const d = parseTime(s);
  return d ? d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";
}

function fmtDateTime(s) {
  const d = parseTime(s);
  return d ? d.toLocaleString([], { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "";
}

function locationName(code) {
  const loc = state.locations.find((l) => l.location_code === code);
  return loc ? loc.name.replace(/^Chowly /, "") : code;
}

function setLocation(code) {
  state.locationCode = code;
  localStorage.setItem("chowly_location", code);
}

function optionsHtml(map, selected, placeholder) {
  const first = placeholder ? `<option value="">${placeholder}</option>` : "";
  return first + Object.entries(map)
    .map(([value, label]) => `<option value="${value}"${value === selected ? " selected" : ""}>${escapeHtml(label)}</option>`)
    .join("");
}

function locationSelectHtml(id) {
  return `<select id="${id}">${state.locations
    .map((l) => `<option value="${l.location_code}"${l.location_code === state.locationCode ? " selected" : ""}>${escapeHtml(l.name.replace(/^Chowly /, ""))}</option>`)
    .join("")}</select>`;
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
// Real dish photography, matched by the item's permanent code — not its
// name, so renaming a dish doesn't lose its photo (the same TE-7 problem
// the BRD describes, in miniature).
// ---------------------------------------------------------------------
const MENU_PHOTOS = {
  "M-001": "jollof_rice_and_grilled_chicken.jpg",
  "M-002": "suya_platter.jpg",
  "M-003": "pounded_yam_and_egusi_soup.jpg",
  "M-004": "peppered_snail.jpg",
  "M-005": "plantain_and_fish_pepper_stew.jpg",
  "M-006": "chapman.jpg",
  "M-007": "zobo.jpg",
  "M-008": "palm_wine.jpg",
  "M-009": "star_lager.jpg",
  "M-010": "pineapple_juice.jpg",
};

function menuPhotoUrl(item) {
  const file = MENU_PHOTOS[item.item_code];
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
    roleSwitchEl.classList.toggle("is-office", btn.dataset.role === "office");
    document.querySelector(".scene-photo-customer").classList.toggle("is-active", btn.dataset.role === "customer");
    document.querySelector(".scene-photo-waiter").classList.toggle("is-active", btn.dataset.role !== "customer");
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
        <label for="location-input">Restaurant</label>
        ${locationSelectHtml("location-input")}
        <label for="table-input">Table</label>
        <input id="table-input" type="number" min="1" value="${state.tableNumber}" placeholder="e.g. 5">
      </div>
      <div class="table-picker">
        <label for="name-input">Your name</label>
        <input id="name-input" type="text" value="${escapeAttr(state.customerName)}" placeholder="e.g. Daniel Adeyemi">
        <label for="phone-input">Phone <span class="optional">(optional, so we recognise you next time)</span></label>
        <input id="phone-input" type="tel" value="${escapeAttr(state.customerPhone)}" placeholder="e.g. 0803 123 4567">
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
  document.getElementById("phone-input").addEventListener("input", (e) => {
    state.customerPhone = e.target.value;
    localStorage.setItem("chowly_customer_phone", state.customerPhone);
  });
  document.getElementById("location-input").addEventListener("change", (e) => {
    setLocation(e.target.value);
    renderCustomer(false);
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
  wireTicketActions();
  renderCartBar();
}

// Pay / cancel / print buttons and their dropdowns, shared by customer and waiter views.
function wireTicketActions() {
  app.querySelectorAll("[data-pay-order]").forEach((btn) => {
    btn.addEventListener("click", () => payOrder(Number(btn.dataset.payOrder)));
  });
  app.querySelectorAll("[data-cancel-order]").forEach((btn) => {
    btn.addEventListener("click", () => cancelOrder(Number(btn.dataset.cancelOrder)));
  });
  app.querySelectorAll("[data-print-order]").forEach((btn) => {
    btn.addEventListener("click", () => printOrder(Number(btn.dataset.printOrder)));
  });
  app.querySelectorAll("[data-draft-field]").forEach((el) => {
    el.addEventListener("change", () => {
      getDraft(Number(el.dataset.orderId))[el.dataset.draftField] = el.value;
    });
  });
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
        location_code: state.locationCode,
        table_number: Number(state.tableNumber),
        customer: { ...splitName(state.customerName), phone_number: state.customerPhone.trim() || null },
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
    ? `<div class="complaint-filed">You reported (${escapeHtml(categoryLabel(order.complaint.category))}): "${escapeHtml(order.complaint.description)}"${order.complaint.resolved_at ? " \u2014 resolved" : ""}</div>`
    : canComplain
    ? complaintFormHtml(order)
    : "";

  const payAction =
    !order.payment && order.status === "served" ? payControlHtml(order, "Pay (pretend)") : "";

  const draft = state.drafts[order.id] || {};
  const cancelAction = isCancellable(order)
    ? `<select class="inline-select" data-draft-field="cancelReason" data-order-id="${order.id}" aria-label="Reason for cancelling">
         ${optionsHtml(state.vocab.cancel_reasons, draft.cancelReason || "", "Reason for cancelling\u2026")}
       </select>
       <button class="btn-cancel" data-cancel-order="${order.id}">Cancel order</button>`
    : "";

  const paymentNote = order.payment ? paymentNoteHtml(order) : "";
  const cancelNote = order.status === "cancelled" && order.cancellation_reason
    ? `<div class="ticket-meta"><span>Cancelled${order.cancelled_at ? ` at ${fmtTime(order.cancelled_at)}` : ""} \u2014 ${escapeHtml(state.vocab.cancel_reasons[order.cancellation_reason] || order.cancellation_reason)}</span></div>`
    : "";

  const statusPop = state.justSettledOrderIds.has(order.id) ? " just-settled" : "";

  return `
    <div class="ticket">
      <div class="ticket-head">
        <div class="ticket-title">${escapeHtml(locationName(order.location_code))} &middot; Table ${order.table_number} &middot; Order #${order.id}</div>
        <div class="ticket-status status-${order.status}${statusPop}">${statusLabel}</div>
      </div>
      ${rows}
      <div class="ticket-total"><span>Total</span><span>${money(order.total_amount)}</span></div>
      <div class="ticket-meta">
        <span>Waiting time: ~${order.estimated_waiting_time_minutes} min</span>
        ${order.waiter ? `<span class="avatar-tag">${avatarHtml(order.waiter.first_name, order.waiter.last_name, "sm")} ${order.waiter.first_name} ${order.waiter.last_name}</span>` : ""}
      </div>
      ${paymentNote}
      ${cancelNote}
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

function categoryLabel(code) {
  return state.vocab.complaint_categories[code] || code || "uncategorised";
}

function paymentNoteHtml(order) {
  const p = order.payment;
  const method = state.vocab.payment_methods[p.payment_method] || p.payment_method;
  const corrections = (p.corrections || [])
    .map((c) => `<span class="correction">Correction ${money(c.amount)} \u2014 ${escapeHtml(c.reason)}</span>`)
    .join("");
  return `<div class="ticket-meta"><span>Paid \u2713 ${escapeHtml(method)} &middot; ref ${p.transaction_reference}</span>${corrections}</div>`;
}

// A payment-method dropdown next to the pay button: the BRD wants the method recorded.
function payControlHtml(order, label) {
  const draft = state.drafts[order.id] || {};
  return `<select class="inline-select" data-draft-field="payMethod" data-order-id="${order.id}" aria-label="Payment method">
      ${optionsHtml(state.vocab.payment_methods, draft.payMethod || "", "Paying by\u2026")}
    </select>
    <button class="btn-primary" data-pay-order="${order.id}">${label}</button>`;
}

function complaintFormHtml(order) {
  const orderId = order.id;
  const draft = state.drafts[orderId] || {};
  const dishes = {};
  order.items.forEach((i) => { dishes[String(i.menu_item.id)] = i.menu_item.item_name; });
  return `
    <div class="complaint-box" data-complaint-form data-order-id="${orderId}">
      <label>Something wrong with this order? Let the kitchen know.</label>
      <div class="complaint-pickers">
        <select data-complaint-category aria-label="What kind of problem">
          ${optionsHtml(state.vocab.complaint_categories, draft.category || "", "What kind of problem?")}
        </select>
        <select data-complaint-dish aria-label="Which dish">
          ${optionsHtml(dishes, draft.dish || "", "Which dish? (optional)")}
        </select>
      </div>
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
  box.querySelector("[data-complaint-category]").addEventListener("change", (e) => {
    draft.category = e.target.value;
  });
  box.querySelector("[data-complaint-dish]").addEventListener("change", (e) => {
    draft.dish = e.target.value;
  });

  box.querySelector("[data-submit-complaint]").addEventListener("click", async () => {
    const description = (draft.complaint || "").trim();
    if (!draft.category) {
      showToast("Pick what kind of problem it was");
      return;
    }
    if (!description) {
      showToast("Add a message first");
      return;
    }
    try {
      const updated = await api(`/orders/${orderId}/complaint`, {
        method: "POST",
        body: JSON.stringify({ description, category: draft.category, menu_item_id: draft.dish ? Number(draft.dish) : null }),
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
  const method = (state.drafts[orderId] || {}).payMethod;
  if (!method) {
    showToast("Pick how the bill was paid first");
    return;
  }
  const waiterId = state.role === "waiter" && state.actingWaiterId ? Number(state.actingWaiterId) : null;
  try {
    const updated = await api(`/orders/${orderId}/pay`, {
      method: "POST",
      body: JSON.stringify({ payment_method: method, waiter_id: waiterId }),
    });
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
  const reason = (state.drafts[orderId] || {}).cancelReason;
  if (!reason) {
    showToast("Pick a reason for cancelling first");
    return;
  }
  try {
    const updated = await api(`/orders/${orderId}/cancel`, { method: "POST", body: JSON.stringify({ reason }) });
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
      <h2>Chowly ${escapeHtml(locationName(order.location_code))} \u2014 Table ${order.table_number}</h2>
      <div class="print-meta">
        Order #${order.id} &middot; ${parseTime(order.order_time).toLocaleString()}<br>
        ${order.customer.first_name} ${order.customer.last_name}
        ${order.waiter ? ` &middot; Waiter: ${order.waiter.first_name} ${order.waiter.last_name}` : ""}
      </div>
      <table>${rows}</table>
      <div class="print-total">Total: ${money(order.total_amount)}</div>
      ${isReceipt ? `<div class="print-meta">Paid (pretend) by ${escapeHtml(state.vocab.payment_methods[order.payment.payment_method] || order.payment.payment_method)} &middot; ref ${order.payment.transaction_reference}</div>` : ""}
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
      <a class="qr-link" href="/qr?location_code=${state.locationCode}" target="_blank" rel="noopener">Print ${escapeHtml(locationName(state.locationCode))} table QR codes &#8599;</a>
    </div>`;

  app.innerHTML = `
    <div class="intro-panel">
      <div class="section-title">Floor</div>
      <div class="section-hint">Pick up new orders, record who prepared each item, and mark them served.</div>
      <div class="table-picker">
        <label for="waiter-location">Restaurant</label>
        ${locationSelectHtml("waiter-location")}
      </div>
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

  document.getElementById("waiter-location").addEventListener("change", async (e) => {
    setLocation(e.target.value);
    state.actingWaiterId = "";
    localStorage.removeItem("chowly_waiter_id");
    await loadStaff();
    render(false);
  });

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
  app.querySelectorAll("[data-preparer-select]").forEach((select) => {
    select.addEventListener("change", (e) => {
      state.prepDrafts[Number(select.dataset.preparerSelect)] = e.target.value;
    });
  });
  app.querySelectorAll("[data-prepare-item]").forEach((btn) => {
    btn.addEventListener("click", () => recordPreparation(Number(btn.dataset.orderId), Number(btn.dataset.prepareItem)));
  });
  app.querySelectorAll("[data-serve-order]").forEach((btn) => {
    btn.addEventListener("click", () => serveOrder(Number(btn.dataset.serveOrder)));
  });
  wireTicketActions();
  renderCartBar();
}

function actingWaiterLabel() {
  const w = state.staff.waiters.find((x) => String(x.id) === String(state.actingWaiterId));
  return w ? `waiter #${w.id} ${w.first_name} ${w.last_name} (${state.locationCode})` : `waiter (${state.locationCode})`;
}

async function toggleAvailability(itemId) {
  try {
    await api(`/menu/${itemId}/toggle-availability`, {
      method: "POST",
      body: JSON.stringify({ changed_by: actingWaiterLabel() }),
    });
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
    ? `<div class="complaint-filed">Complaint (${escapeHtml(categoryLabel(order.complaint.category))}${order.complaint.menu_item ? `, ${escapeHtml(order.complaint.menu_item.item_name)}` : ""}): "${escapeHtml(order.complaint.description)}"</div>`
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
    actionHtml = `<div class="ticket-actions">${payControlHtml(order, "Record payment (pretend)")}</div>`;
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
      ${order.payment ? paymentNoteHtml(order) : ""}
      ${timelineHtml(order)}
      ${complaintHtml}
      ${ratingHtml}
      ${actionHtml}
      ${printHtml}
    </div>`;
}

// Every status change with its time — read from order_status_events.
function timelineHtml(order) {
  const events = order.status_events || [];
  if (!events.length) return "";
  const labels = { placed: "Placed", assigned: "Picked up", served: "Served", paid: "Paid", cancelled: "Cancelled" };
  const steps = events
    .map((e) => `<span class="timeline-step${e.is_backfilled ? " is-backfilled" : ""}" title="${e.is_backfilled ? escapeAttr(e.note || "Rebuilt after the fact") : ""}">${labels[e.to_status] || e.to_status} ${fmtTime(e.changed_at)}</span>`)
    .join('<span class="timeline-sep">\u2192</span>');
  return `<div class="timeline">${steps}</div>`;
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
  const draftValue = state.prepDrafts[prep.order_item_id] || "";

  return `
    <div class="prep-row">
      <span>${prep.menu_item.item_name}</span>
      <div class="prep-controls">
        <select data-preparer-select="${prep.order_item_id}">
          <option value="">${roleLabel}\u2026</option>
          ${options.map((o) => `<option value="${o.id}"${String(o.id) === draftValue ? " selected" : ""}>${o.first_name} ${o.last_name}</option>`).join("")}
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
    delete state.prepDrafts[orderItemId];
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
  state.waiterOrders = await api(`/orders?location_code=${state.locationCode}`);
}

async function loadStaff() {
  state.staff = await api(`/staff?location_code=${state.locationCode}`);
}

// ---------------------------------------------------------------------
// Office view (Lab 1): partner imports, menu changes, complaints,
// payment corrections. Every action is stamped with the person's name.
// ---------------------------------------------------------------------
const SOURCE_LABELS = {
  delivery_platform: "Delivery platform",
  supplier_invoice: "Supplier invoices",
  card_acquirer: "Card acquirer",
};
const EVENT_LABELS = {
  created: "Added",
  baseline_snapshot: "Baseline snapshot",
  price_changed: "Price changed",
  renamed: "Renamed",
  availability_changed: "Availability",
  discontinued: "Discontinued",
};

async function loadOffice() {
  const o = state.office;
  const [sources, imports, menuAll, menuEvents, complaints, corrections] = await Promise.all([
    o.sources.length ? Promise.resolve(o.sources) : api("/imports/sources"),
    api("/imports"),
    api("/menu?include_discontinued=true"),
    api("/menu/events?limit=15"),
    api("/complaints"),
    api("/payment-corrections"),
  ]);
  Object.assign(o, { sources, imports, menuAll, menuEvents, complaints, corrections });
  if (o.openBatch) o.openBatch = await api(`/imports/${o.openBatch.id}`).catch(() => null);
}

function requireOfficeName() {
  const name = state.office.name.trim();
  if (!name) {
    showToast("Enter your name at the top first — every change is recorded against it");
    document.getElementById("office-name")?.focus();
    return null;
  }
  return name;
}

function renderOffice() {
  const o = state.office;
  const source = o.sources.find((x) => x.key === o.importSource) || o.sources[0];

  const importRows = o.imports.length
    ? o.imports.map((b) => `
        <tr>
          <td>#${b.id}</td>
          <td>${SOURCE_LABELS[b.source] || b.source}</td>
          <td class="cell-file" title="${escapeAttr(b.filename)}">${escapeHtml(b.filename)}</td>
          <td>${fmtDateTime(b.uploaded_at)}<div class="cell-sub">${escapeHtml(b.uploaded_by || "")}</div></td>
          <td class="num">${b.rows_total}</td>
          <td class="num">${b.rows_loaded}</td>
          <td class="num">${b.rows_duplicate}</td>
          <td class="num${b.rows_rejected ? " is-bad" : ""}">${b.rows_rejected}</td>
          <td><span class="pill pill-${b.status}">${b.status}</span>${b.error ? `<div class="cell-sub is-bad">${escapeHtml(b.error)}</div>` : ""}</td>
          <td>${b.rows_rejected && !b.error ? `<button class="link-btn" data-open-batch="${b.id}">View rows</button>` : ""}</td>
        </tr>`).join("")
    : `<tr><td colspan="10" class="cell-empty">No partner files imported yet.</td></tr>`;

  const quarantine = o.openBatch
    ? `<div class="quarantine">
        <div class="quarantine-head">
          <strong>Batch #${o.openBatch.id} — ${o.openBatch.rows_rejected} row(s) in quarantine</strong>
          <button class="link-btn" data-close-batch>Close</button>
        </div>
        <p class="office-note">These rows were not loaded and not thrown away. Fix them in the source file and upload it again — rows that already loaded are recognised and skipped, so nothing is counted twice.</p>
        <table class="office-table">
          <tr><th>Row</th><th>Problem</th><th>Row as received</th></tr>
          ${o.openBatch.rejections.map((r) => `
            <tr><td class="num">${r.row_number}</td><td class="is-bad">${escapeHtml(r.errors)}</td>
            <td class="cell-raw">${escapeHtml(Object.values(JSON.parse(r.raw_row)).join(", "))}</td></tr>`).join("")}
        </table>
      </div>`
    : "";

  const itemName = (id) => {
    const m = o.menuAll.find((x) => x.id === id);
    return m ? `${m.item_code} ${m.item_name}` : `#${id}`;
  };

  const menuRows = o.menuAll.map((m) => {
    const discontinued = m.availability_status === "discontinued";
    return `
      <tr class="${discontinued ? "is-retired" : ""}">
        <td class="mono">${m.item_code || ""}</td>
        <td><input class="cell-input" data-menu-name="${m.id}" value="${escapeAttr(m.item_name)}" ${discontinued ? "disabled" : ""}></td>
        <td><input class="cell-input cell-price" type="number" min="1" step="50" data-menu-price="${m.id}" value="${m.price}" ${discontinued ? "disabled" : ""}></td>
        <td><span class="pill pill-${m.availability_status}">${m.availability_status.replace("_", " ")}</span></td>
        <td class="cell-actions">${discontinued ? "" : `
          <button class="btn-secondary btn-sm" data-menu-save="${m.id}">Save</button>
          <button class="link-btn is-bad" data-menu-discontinue="${m.id}">Discontinue</button>`}</td>
      </tr>`;
  }).join("");

  const eventRows = o.menuEvents.map((e) => {
    let change = "";
    if (e.event_type === "price_changed") change = `${money(e.old_value)} → ${money(e.new_value)}`;
    else if (e.event_type === "baseline_snapshot") {
      const v = JSON.parse(e.new_value || "{}");
      change = `${escapeHtml(v.item_name || "")} @ ${money(v.price || 0)}`;
    } else change = `${escapeHtml(e.old_value || "—")} → ${escapeHtml(e.new_value || "")}`;
    return `<tr>
      <td>${fmtDateTime(e.changed_at)}</td><td>${escapeHtml(itemName(e.menu_item_id))}</td>
      <td>${EVENT_LABELS[e.event_type] || e.event_type}${e.is_backfilled ? ' <span class="pill pill-backfilled" title="Recorded after the fact by the Lab 1 migration">backfilled</span>' : ""}</td>
      <td>${change}</td><td class="cell-sub">${escapeHtml(e.changed_by || "")}</td></tr>`;
  }).join("");

  const hoursSince = (from, to) => ((parseTime(to) || new Date()) - parseTime(from)) / 36e5;
  const complaintRows = o.complaints.length
    ? o.complaints.map((c) => {
        const open = c.status === "open";
        const hrs = hoursSince(c.complaint_date, c.resolved_at);
        const age = hrs < 1 ? "< 1 h" : `${Math.round(hrs)} h`;
        return `<div class="complaint-row${open ? "" : " is-resolved"}">
          <div class="complaint-row-head">
            <span><strong>#${c.id}</strong> &middot; Order #${c.order_id} &middot; ${escapeHtml(locationName(c.location_code))}</span>
            <span class="pill ${open ? (hrs > 48 ? "pill-failed" : "pill-partial") : "pill-loaded"}">${open ? `open ${age}` : `resolved in ${age}`}</span>
          </div>
          <div class="complaint-row-meta">${escapeHtml(categoryLabel(c.category))}${c.dish ? ` &middot; ${escapeHtml(c.dish)}` : ""} &middot; ${fmtDateTime(c.complaint_date)}</div>
          <div class="complaint-row-text">"${escapeHtml(c.description)}"</div>
          ${open
            ? `<div class="office-form"><input data-resolve-note="${c.id}" placeholder="Root cause / what was done"><button class="btn-secondary btn-sm" data-resolve="${c.id}">Resolve</button></div>`
            : `<div class="complaint-row-meta">Resolution: ${escapeHtml(c.resolution_note || "")}</div>`}
        </div>`;
      }).join("")
    : `<p class="office-note">No complaints yet.</p>`;

  const correctionRows = o.corrections.length
    ? o.corrections.map((c) => `<tr><td>${fmtDateTime(c.created_at)}</td><td>Order #${c.order_id}</td><td class="num">${money(c.amount)}</td><td>${escapeHtml(c.reason)}</td><td class="cell-sub">${escapeHtml(c.recorded_by || "")}</td></tr>`).join("")
    : `<tr><td colspan="5" class="cell-empty">No corrections recorded.</td></tr>`;

  app.innerHTML = `
    <div class="intro-panel">
      <div class="section-title">Back office</div>
      <div class="section-hint">Partner files, menu prices, complaints and refunds. Every change here is recorded with your name and the time.</div>
      <div class="table-picker">
        <label for="office-name">Your name</label>
        <input id="office-name" type="text" value="${escapeAttr(o.name)}" placeholder="e.g. Finance Manager">
      </div>
    </div>

    <section class="office-card">
      <div class="office-card-title">Partner data imports</div>
      <p class="office-note">Upload a CSV or Excel file from a partner. Rows that break a rule are held in quarantine with the reason. Uploading the same file twice, or rows that were already loaded, never creates duplicates.</p>
      <div class="office-form">
        <select id="import-source">${o.sources.map((x) => `<option value="${x.key}"${x.key === source.key ? " selected" : ""}>${escapeHtml(x.label)}</option>`).join("")}</select>
        <input id="import-file" type="file" accept=".csv,.xlsx">
        <button class="btn-primary" id="import-upload">Upload</button>
        <a class="qr-link" href="/api/imports/templates/${source.key}.csv">Download template</a>
      </div>
      <div class="office-note">Owner: <strong>${escapeHtml(source.owner)}</strong> &middot; Columns: <span class="mono">${source.columns.map((c) => (source.required.includes(c) ? c : `${c}?`)).join(", ")}</span> <span class="cell-sub">(? = optional)</span></div>
      <div class="table-scroll"><table class="office-table">
        <tr><th>Batch</th><th>Source</th><th>File</th><th>Uploaded</th><th class="num">Rows</th><th class="num">Loaded</th><th class="num">Duplicates</th><th class="num">Quarantined</th><th>Status</th><th></th></tr>
        ${importRows}
      </table></div>
      ${quarantine}
    </section>

    <section class="office-card">
      <div class="office-card-title">Menu &amp; prices</div>
      <p class="office-note">Changing a price or name keeps the old value in the change log, so the price on any past date can be proved. Discontinued dishes are never deleted, so their sales history stays linked. Orders already placed keep the price they were sold at.</p>
      <div class="table-scroll"><table class="office-table">
        <tr><th>Code</th><th>Name</th><th>Price (₦)</th><th>Status</th><th></th></tr>
        ${menuRows}
      </table></div>
      <div class="office-subtitle">Recent changes</div>
      <div class="table-scroll"><table class="office-table">
        <tr><th>When</th><th>Item</th><th>Change</th><th>Value</th><th>By</th></tr>
        ${eventRows || `<tr><td colspan="5" class="cell-empty">No changes yet.</td></tr>`}
      </table></div>
    </section>

    <section class="office-card">
      <div class="office-card-title">Complaints</div>
      <p class="office-note">Each complaint has a category and, where relevant, the dish, so problems can be traced. Resolving records when and why, which is what "root cause within 48 hours" is measured from.</p>
      ${complaintRows}
    </section>

    <section class="office-card">
      <div class="office-card-title">Payment corrections</div>
      <p class="office-note">Payments are never edited. A refund is recorded as a new line against the original payment.</p>
      <div class="office-form">
        <input id="corr-order" type="number" min="1" placeholder="Order #">
        <input id="corr-amount" type="number" min="1" placeholder="Refund amount (₦)">
        <input id="corr-reason" placeholder="Reason" class="grow">
        <button class="btn-secondary" id="corr-save">Record refund</button>
      </div>
      <div class="table-scroll"><table class="office-table">
        <tr><th>When</th><th>Order</th><th class="num">Amount</th><th>Reason</th><th>By</th></tr>
        ${correctionRows}
      </table></div>
    </section>
  `;

  document.getElementById("office-name").addEventListener("input", (e) => {
    o.name = e.target.value;
    localStorage.setItem("chowly_office_name", o.name);
  });
  document.getElementById("import-source").addEventListener("change", (e) => {
    o.importSource = e.target.value;
    renderOffice();
  });
  document.getElementById("import-upload").addEventListener("click", uploadPartnerFile);
  app.querySelectorAll("[data-open-batch]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      o.openBatch = await api(`/imports/${btn.dataset.openBatch}`);
      renderOffice();
    })
  );
  app.querySelector("[data-close-batch]")?.addEventListener("click", () => {
    o.openBatch = null;
    renderOffice();
  });
  app.querySelectorAll("[data-menu-save]").forEach((btn) => btn.addEventListener("click", () => saveMenuItem(Number(btn.dataset.menuSave))));
  app.querySelectorAll("[data-menu-discontinue]").forEach((btn) => btn.addEventListener("click", () => discontinueMenuItem(Number(btn.dataset.menuDiscontinue))));
  app.querySelectorAll("[data-resolve]").forEach((btn) => btn.addEventListener("click", () => resolveComplaint(Number(btn.dataset.resolve))));
  document.getElementById("corr-save").addEventListener("click", recordCorrection);
}

async function officeAction(fn, successMessage) {
  try {
    await fn();
    if (successMessage) showToast(successMessage);
    await loadOffice();
    renderOffice();
  } catch (err) {
    showToast(err.message);
  }
}

async function uploadPartnerFile() {
  const who = requireOfficeName();
  if (!who) return;
  const file = document.getElementById("import-file").files[0];
  if (!file) {
    showToast("Choose a file first");
    return;
  }
  const form = new FormData();
  form.append("file", file);
  form.append("uploaded_by", who);
  try {
    const res = await fetch(`/api/imports/${state.office.importSource}`, { method: "POST", body: form });
    const body = await res.json();
    if (!res.ok) throw new Error(errorText(body.detail));
    // Alert, never silently: say exactly what happened to the rows.
    const msg =
      body.status === "failed"
        ? `Import failed — ${body.error || `all ${body.rows_rejected} rows quarantined`}`
        : `Loaded ${body.rows_loaded}, skipped ${body.rows_duplicate} duplicate(s), quarantined ${body.rows_rejected}`;
    showToast(msg);
    if (body.rows_rejected && !body.error) state.office.openBatch = { id: body.id };
    await loadOffice();
    renderOffice();
  } catch (err) {
    showToast(err.message);
  }
}

function saveMenuItem(id) {
  const who = requireOfficeName();
  if (!who) return;
  const item = state.office.menuAll.find((m) => m.id === id);
  const name = app.querySelector(`[data-menu-name="${id}"]`).value.trim();
  const price = Number(app.querySelector(`[data-menu-price="${id}"]`).value);
  const body = { changed_by: who };
  if (name !== item.item_name) body.item_name = name;
  if (price !== item.price) body.price = price;
  if (!body.item_name && !body.price) {
    showToast("Nothing changed");
    return;
  }
  officeAction(() => api(`/menu/${id}`, { method: "PATCH", body: JSON.stringify(body) }), `${item.item_code} updated — old value kept in the change log`);
}

function discontinueMenuItem(id) {
  const who = requireOfficeName();
  if (!who) return;
  const item = state.office.menuAll.find((m) => m.id === id);
  if (!confirm(`Discontinue ${item.item_name}? It disappears from the menu but its sales history is kept.`)) return;
  officeAction(() => api(`/menu/${id}/discontinue`, { method: "POST", body: JSON.stringify({ changed_by: who }) }), `${item.item_name} discontinued`);
}

function resolveComplaint(id) {
  const who = requireOfficeName();
  if (!who) return;
  const note = app.querySelector(`[data-resolve-note="${id}"]`).value.trim();
  if (!note) {
    showToast("Write the root cause or what was done first");
    return;
  }
  officeAction(() => api(`/complaints/${id}/resolve`, { method: "POST", body: JSON.stringify({ resolution_note: note, resolved_by: who }) }), `Complaint #${id} resolved`);
}

function recordCorrection() {
  const who = requireOfficeName();
  if (!who) return;
  const orderId = Number(document.getElementById("corr-order").value);
  const amount = Number(document.getElementById("corr-amount").value);
  const reason = document.getElementById("corr-reason").value.trim();
  if (!orderId || !amount || amount <= 0 || !reason) {
    showToast("Enter the order number, a refund amount and a reason");
    return;
  }
  officeAction(
    () => api(`/orders/${orderId}/payment-corrections`, { method: "POST", body: JSON.stringify({ amount: -amount, reason, recorded_by: who }) }),
    `Refund of ${money(amount)} recorded against order #${orderId}`
  );
}

// ---------------------------------------------------------------------
// Render dispatch + polling
// ---------------------------------------------------------------------
async function render(isUserAction) {
  if (state.role === "office") {
    await loadOffice();
    renderOffice();
    renderCartBar();
    return;
  }
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
  state.todayStats = await api(`/stats/today?location_code=${state.locationCode}`).catch(() => null);
}

async function init() {
  const params = new URLSearchParams(window.location.search);
  const tableParam = params.get("table");
  if (tableParam) {
    state.tableNumber = tableParam;
    localStorage.setItem("chowly_table", state.tableNumber);
  }

  const [locations, vocab] = await Promise.all([api("/locations"), api("/vocab")]);
  state.locations = locations;
  state.vocab = vocab;
  const locParam = (params.get("location") || "").toUpperCase();
  if (locations.some((l) => l.location_code === locParam)) setLocation(locParam);
  if (!locations.some((l) => l.location_code === state.locationCode)) setLocation(locations[0].location_code);

  await loadStaff();
  await render(true);
  setInterval(() => {
    const active = document.activeElement;
    const isTyping = active && (active.tagName === "TEXTAREA" || active.tagName === "INPUT" || active.tagName === "SELECT");
    // The office screen has forms and a file picker, and nothing on it is live, so it isn't polled.
    if (document.visibilityState === "visible" && !isTyping && state.role !== "office") render(false);
  }, 6000);
}

init().catch((err) => showToast(err.message));