# Chowly

A table-side ordering platform for a restaurant: customers order and pay from
their table, waiters pick up orders and record which chef or bartender
prepared each item, and every order carries its own waiting time, rating,
complaint, and payment record.

**Live app:** _add your Render URL here once deployed_
**Repo:** _add your GitHub URL here_

---

## 1. How it was built

### Stack
- **Backend:** FastAPI (Python) + SQLAlchemy ORM
- **Database:** SQLite for local development, PostgreSQL in production
  (the app reads a `DATABASE_URL` environment variable and falls back to
  SQLite if it isn't set — same codebase, no branching logic needed)
- **Frontend:** vanilla HTML/CSS/JS, no build step, no framework. Served as
  static files by the same FastAPI process, so the whole app is one
  deployable service and one live link.
- **Deployment:** Render (web service) + Neon (managed Postgres), wired
  together with `render.yaml`

One service instead of a separate frontend/backend deploy was a deliberate
call given the timeline — it halves the moving parts without giving up a
real, polished UI.

### Structure
```
chowly/
├── app/
│   ├── main.py          # FastAPI app + all API routes
│   ├── models.py        # SQLAlchemy tables
│   ├── schemas.py       # Pydantic request/response models
│   ├── seed.py          # loads restaurant, menu, and staff on startup
│   ├── database.py      # engine/session setup, SQLite<->Postgres switch
│   └── static/           # the entire frontend
│       ├── index.html
│       ├── css/style.css
│       └── js/app.js
├── requirements.txt
├── render.yaml
└── .gitignore
```

### Data model, as finally implemented

This build's model is a direct implementation of the entities from the
prior engineered-model assignment, carried through unchanged: `Customer`,
`Restaurant`, `Menu`, `MenuItem`, `Waiter`, `Chef`, `Bartender`, `Order`,
`OrderItem`, `OrderPreparation`, `Complaint`, `Rating`, and `Payment`.

| Table | Key fields |
|---|---|
| `Customer` | first_name, last_name, phone_number (unique), email, date_registered |
| `Restaurant` | name, address, phone_number, email |
| `Menu` | restaurant_id, name, menu_type, description |
| `MenuItem` | menu_id, item_name, item_type (food/drink), price, prep_time_minutes, availability_status |
| `Waiter` / `Chef` / `Bartender` | restaurant_id, first_name, last_name, phone_number |
| `Order` | customer_id, restaurant_id, waiter_id, table_number, status, order_time, actual_completion_time |
| `OrderItem` | order_id, menu_item_id, quantity, unit_price |
| `OrderPreparation` | order_id, order_item_id, menu_item_id, chef_id, bartender_id, status, preparation_start/end_time |
| `Complaint` | order_id, customer_id, description, complaint_date, status |
| `Rating` | order_id, customer_id, rating_value (1–5), comment, rating_date |
| `Payment` | order_id, customer_id, amount, payment_method, payment_time, status, transaction_reference |

**Three deliberate deviations remain, each forced by the build itself,**
per the instruction to change the model where the build requires it and
say why:

- **No `CustomerID`-based login.** The assignment explicitly states
  "logins are not required, a simple switch is enough." `Customer` still
  exists as a real table — a customer's name and phone are captured at
  order time and get-or-created by phone number — but there's no
  authentication layer sitting in front of it.
- **A single seeded `Restaurant` and `Menu`.** The original model supports
  many restaurants, each with their own menu. This build is a single
  restaurant's ordering system (Chowly deployed *for* one restaurant, not
  a multi-tenant platform serving many), so one `Restaurant` row and one
  `Menu` row are seeded at startup and everything else hangs off them.
  The foreign keys are still there — a second restaurant could be added
  without a schema change — there's just no UI for restaurant selection.
- **`estimated_waiting_time` is derived, not stored.** It's computed as
  the *slowest single item* in the order (`max` of each item's
  `prep_time_minutes`), not entered or stored as a free field on `Order`,
  because a kitchen and bar work in parallel rather than making items one
  after another — and because deriving it means it can never drift out of
  sync with what's actually on the order.

`OrderPreparation` is implemented exactly as originally modelled: one row
per order item, referencing either a chef or a bartender depending on
whether the item is food or a drink. A waiter picks up an order (setting
`Order.waiter_id`), then records a preparer for each item individually —
the API rejects a chef on a drink item or a bartender on a food item.
Serving an order is blocked until every item's preparation is complete.

`Rating` and `Complaint` are separate, independent actions, matching the
original model's separate tables — a customer can rate an order without
complaining, or complain without rating, and each can only be filed once
per order.

### Visual design
Menu items use hand-illustrated SVG icons (a skewer for suya, a spiral
shell for snails, a distinct wine-glass shape from the cocktail glass,
and so on) in a colored tile, rather than stock photography — real
photos would mean either hotlinking third-party images with unclear
licensing or bundling large binary assets, and neither survives a
lightweight, freely-deployable app well. Staff are represented with
generated initials avatars (a deterministic color per name), not fake
stock headshots of people who don't exist. Motion is scoped
deliberately: one staggered entrance for the menu on first load, and
functional micro-motion elsewhere (the role toggle, the cart bar, a
prep row popping when checked off, a ticket glowing once when paid) —
not hover animations on every card, which reads as generic rather than
intentional.

### Deployment
See [Section 5](#5-how-to-deploy-it-yourself) below for the exact steps —
I can't create accounts or click through a deploy on your behalf, so
this is written as a walkthrough for you to run.

---

## 2. How AI was used

This app was built working turn-by-turn with Claude (Anthropic), in an
agentic coding environment with real file access and a live server —
not just a chat that suggested snippets.

**What I asked for:** a working build of the Chowly assignment end-to-end
— data model, API, frontend, deployment packaging — under a same-day
deadline, prioritizing a polished, non-templated visual design over speed
of scaffolding.

**How it actually went, in two passes:**
1. Claude first designed a simplified schema from scratch (no separate
   Customer/Restaurant/Menu tables, chef/bartender fields bolted directly
   onto `Order`, complaint and rating merged into one entity) because it
   didn't have my original engineered-model document in front of it.
2. I supplied that document, and Claude reconciled the build against it —
   restructuring the tables, rewriting the API's assignment flow from a
   single order-level action into a two-step "pick up the order, then
   record a preparer per item" flow, and splitting rating and complaint
   back into two independent actions. I chose to spend the extra time on
   this rather than keep the simplified version, specifically so the
   submitted model matches the one I was actually graded on designing.

**What I accepted:**
- The overall architecture (single FastAPI service serving both API and
  static frontend, SQLite→Postgres via one env var).
- The visual design direction (ivory/slate/marigold palette, Fraunces +
  Inter type, ticket-style order cards), proposed specifically to avoid
  the generic "AI-generated SaaS card" look.
- The three named deviations from my original model (no login, single
  restaurant/menu, derived rather than stored waiting time) — Claude
  flagged these as forced by the assignment's actual feature list rather
  than silently dropping them, and I agreed with the reasoning for each.

**What I corrected / rejected:**
- _[Fill this in with anything you personally changed after reviewing the
  code — e.g. menu items, copy, a design tweak, a business rule you
  wanted different. Be specific; this section should reflect your actual
  review, not Claude's.]_

**What I verified myself, rather than taking on faith:**
- Every screen and the full order lifecycle (place → assign → per-item
  preparation → serve → rate/complain → pay) was tested by actually
  clicking through the running app — not just reading the code — both
  before and after the model reconciliation, since the rewrite touched
  every layer of the stack.
- _[Add anything else you personally re-checked before submitting.]_

---

## 3. Application behaviour

**Menu browsing.** A customer opens the app and lands on the Customer tab
by default. Food and drinks are shown in separate sections, each item
listing its name, price, and prep time — loaded from the database at
startup via `Restaurant` → `Menu` → `MenuItem`, not hardcoded in the
frontend.

**Order placement.** The customer enters their name, phone number, and
table number, adjusts quantities with the +/− controls on each item, and
a cart bar appears at the bottom showing the running item count and
total. Pressing **Place order** looks up or creates their `Customer`
record by phone number, creates the `Order` and its `OrderItem` rows, and
creates one `OrderPreparation` row per item (unassigned). The customer
immediately sees an order ticket with its status, itemised total, and
estimated waiting time.

**Order assignment.** Switching to the Waiter tab shows every unpaid
order. A waiter selects their own name once (remembered for the
session). Pressing **Assign to me** on a new order records that waiter
against the order (`Order.waiter_id`) and reveals a preparation checklist
— one row per item. Each row shows a chef selector for food items or a
bartender selector for drinks (never both), because the preparer is
recorded per item, not once for the whole order. **Mark served** only
appears once every row is checked off.

**Complaint and rating.** Once an order is being prepared or later, the
customer's ticket grows two independent, optional forms: a star rating
(1–5, with an optional comment) and a free-text complaint. Either, both,
or neither can be submitted — each is stored as its own record and can
only be filed once per order.

**Payment.** Once an order is marked served, both the customer's ticket
and the waiter's dashboard show a **Pay (pretend)** button — either side
can record it, matching "payment is made on the platform just before the
customer exits." Paying creates a `Payment` row with a generated
transaction reference, explicitly labelled pretend, marks the order paid,
and moves it to the waiter's "Settled tonight" list.

**Real storage.** Every action above is a write to the database (Postgres
in production). Refreshing the page, or coming back later, doesn't lose
anything — the customer's own orders are remembered by browser (order IDs
kept in `localStorage`, since there's no login), and the waiter dashboard
re-fetches the full current order list from the server on every load.

---

## 4. How to use it (walkthrough)

1. Open the live link. You land on the **Customer** view.
2. Enter your name, phone number, and a table number (any number — there's
   no real table registry).
3. Use the **+ / −** buttons on any menu item to build an order. A bar
   appears at the bottom showing your item count and total.
4. Press **Place order**. Your order appears under "Your orders" with a
   status of *Placed* and an estimated waiting time.
5. Click **Waiter** at the top right to switch roles (no login — this is
   a simple view switch, as the assignment allows).
6. Pick your name from **You are**. Your new order appears at the top.
7. Press **Assign to me**. A checklist appears — one row per item.
8. For each row, pick the chef (food items) or bartender (drink items)
   who prepared it, and press **Record**.
9. Once every row is checked off, press **Mark served**.
10. Switch back to **Customer** — your ticket now shows *Served*, a
    **Pay (pretend)** button, a star-rating form, and a complaint form.
    Use either, both, or neither.
11. Pressing **Pay (pretend)** marks the order paid and moves it out of
    the waiter's active list into **Settled tonight**.

---

## 5. How to deploy it yourself

You'll need a free [GitHub](https://github.com) account (you already have
one), a free [Neon](https://neon.tech) account for Postgres, and a free
[Render](https://render.com) account for hosting. No credit card needed
for either.

1. **Push this repo to GitHub.**
   ```bash
   cd chowly
   git remote add origin https://github.com/Afolarin-ai/chowly.git
   git branch -M main
   git push -u origin main
   ```
2. **Create a Neon Postgres database.** Sign up at neon.tech, create a
   project, and copy the connection string it gives you (starts with
   `postgres://` or `postgresql://`).
3. **Deploy to Render.**
   - New → Blueprint → connect your GitHub repo. Render will read
     `render.yaml` automatically and propose a web service called `chowly`.
   - When prompted for the `DATABASE_URL` environment variable, paste the
     Neon connection string from step 2.
   - Deploy. Render installs `requirements.txt` and starts the app with
     `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
4. **Visit the URL Render gives you.** The first request creates the
   tables and seeds the restaurant/menu/staff automatically (see
   `app/seed.py`) — nothing else to run by hand.
5. Update the **Live app** and **Repo** links at the top of this document,
   commit, and push.

If Render's free tier spins the service down after inactivity, the first
request after a while will just be slow (10–30s) while it wakes up —
that's normal for a free-tier deploy and not a bug in the app.
