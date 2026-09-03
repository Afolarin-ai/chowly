# Chowly

A table-side ordering platform for a restaurant: customers order and pay from
their table, waiters pick up orders and record who prepared each item, and
every order carries its own waiting time, rating, and payment record.

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
│   ├── seed.py          # loads restaurant/menu/staff reference data on startup
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

| Table | Fields |
|---|---|
| `Restaurant` | name, address, phone_number, email |
| `Menu` | restaurant_id, name, menu_type, description |
| `MenuItem` | menu_id, item_name, item_type (food/drink), price, prep_time_minutes, availability_status |
| `Waiter` / `Chef` / `Bartender` | restaurant_id, first_name, last_name, phone_number |
| `Customer` | first_name, last_name, phone_number (unique), email, date_registered |
| `Order` | customer_id, restaurant_id, waiter_id, table_number, order_date, order_time, status, actual_completion_time |
| `OrderItem` | order_id, menu_item_id, quantity, unit_price |
| `OrderPreparation` | order_id, order_item_id, menu_item_id, chef_id, bartender_id, status, preparation_start_time, preparation_end_time |
| `Complaint` | order_id, customer_id, description, complaint_date, status |
| `Rating` | order_id, customer_id, rating_value (1–5), comment, rating_date |
| `Payment` | order_id, customer_id, amount, payment_method, payment_time, status, transaction_reference |

This is the full entity set from the earlier data-modeling assignment,
carried forward and implemented as-is, with three deliberate, documented
deviations:

- **No customer login.** The assignment explicitly says *"logins are not
  required, a simple switch is enough."* `Customer` is still a real table —
  a customer's name and phone are captured when they place their first
  order, and repeat orders on the same phone number are matched to the
  same `Customer` row (get-or-create, not a session or password).
- **One seeded `Restaurant` and one `Menu`.** The original model supports
  many restaurants, each with their own menu. This build deploys Chowly for
  a single restaurant, so `Restaurant` and `Menu` each have exactly one row,
  seeded at startup — the tables exist and are wired up correctly, they're
  just not exercised by a restaurant-switching UI, because nothing in the
  assignment calls for one.
- **`estimated_waiting_time` is derived, not stored.** It's computed as the
  *slowest single item* in the order (`max` of each item's
  `prep_time_minutes`), not a value entered by hand — because a kitchen and
  bar work in parallel rather than making items one after another, and a
  free-text field would drift from reality the moment an order has more
  than one item.

Everything else — `OrderPreparation` recording a chef or bartender per
item, `Rating` and `Complaint` as independent entities, `Payment` as its
own record with a transaction reference — matches the original model
exactly.

### Deployment
See [Section 5](#5-how-to-deploy-it-yourself) below for the exact steps —
I can't create accounts or click through a deploy on your behalf, so
this is written as a walkthrough for you to run.

---

## 2. How AI was used

This app was built working turn-by-turn with Claude (Anthropic), in an
agentic coding environment with real file access and a live server —
not just a chat that suggested snippets.

**What I asked for:** a working build of the Chowly assignment end-to-end —
data model, API, frontend, deployment packaging — under a same-day
deadline, prioritizing a polished, non-templated visual design over speed
of scaffolding. Partway through, I supplied my original data-modeling
document from the prior assignment and asked for the build to be
reconciled against it rather than left as an independently-designed
schema.

**What I accepted:**
- The overall architecture (single FastAPI service serving both API and
  static frontend, SQLite→Postgres via one env var).
- The initial simplified schema as a starting point, then — once I saw it
  didn't reflect my actual prior model — the full reconciliation: adding
  back `Customer`, `Restaurant`, and `Menu` as real tables, replacing the
  single order-level chef/bartender fields with a per-item
  `OrderPreparation` table, and splitting `Rating`, `Complaint`, and
  `Payment` back out into independent entities.
- The visual design direction (ivory/slate/marigold palette, Fraunces +
  Inter type, ticket-style order cards), proposed specifically to avoid
  the generic "AI-generated SaaS card" look.
- The three remaining deviations from my original model (no login,
  single seeded restaurant/menu, computed rather than stored waiting
  time) — each was explained with a reason tied to the assignment's
  actual requirements, and I agreed each was justified rather than
  a shortcut.

**What I corrected / rejected:**
- _[Fill this in with anything you personally changed after reviewing the
  code — e.g. menu items, copy, a design tweak, a business rule you wanted
  different. Be specific; this section should reflect your actual review,
  not Claude's.]_

**What I verified myself, rather than taking on faith:**
- After the reconciliation, I re-ran the full order lifecycle — place,
  assign, prepare each item (checking that food items only accept a chef
  and drink items only accept a bartender), serve, rate, complain, pay —
  by actually clicking through the running app, not just reading the diff.
- _[Add anything else you personally re-checked before submitting.]_

---

## 3. Application behaviour

**Menu browsing.** A customer opens the app and lands on the Customer tab
by default. Food and drinks are shown in separate sections, each item
listing its name, price, and prep time — loaded from the database at
startup, not hardcoded in the frontend.

**Order placement.** The customer enters their name, phone number, and
table number once (remembered by the browser for next time), adjusts
quantities with the +/− controls on each item, and a cart bar appears at
the bottom showing the running item count and total. Pressing **Place
order** creates (or matches, by phone number) a `Customer` record, creates
the `Order`, and creates one `OrderItem` and one pending `OrderPreparation`
row per item. The customer immediately sees an order ticket with status,
itemised total, and estimated waiting time — the slowest item's prep time
— without leaving the page.

**Order assignment.** Switching to the Waiter tab shows every order that
hasn't been paid yet. A waiter selects their own name once (remembered for
the session). Pressing **Assign to me** on a new order records that waiter
against the order and moves it to "in progress" — this is a pickup, not yet
a preparation record.

**Recording preparation, per item.** Once picked up, the order shows a row
per item. A food item's row offers a chef dropdown; a drink item's row
offers a bartender dropdown — the two are never interchangeable, matching
`OrderPreparation`'s split between `chef_id` and `bartender_id`. Pressing
**Record** on a row marks that item prepared and shows who prepared it.
**Mark served** only appears once every row is checked off — the API
rejects a serve attempt while any item is still pending.

**Rating.** Once an order is being prepared or later, the customer's
ticket grows a 1–5 star picker with an optional comment, independent of
any complaint. Submitting it creates a `Rating` row; it can only be
submitted once per order.

**Complaint.** Independently of rating, the same ticket offers a free-text
complaint field for anything that went wrong. Submitting it creates a
`Complaint` row, again once per order.

**Payment.** Once an order is served, both the customer's ticket and the
waiter's dashboard show a **Pay (pretend)** button — either side can record
it, matching "payment is made on the platform just before the customer
exits." Paying creates a `Payment` row with a generated `PRETEND-XXXXXXXXXX`
transaction reference, clearly labelled as simulated, and moves the order
to the waiter's "Settled tonight" list.

**Real storage.** Every action above is a write to the database (Postgres
in production). Refreshing the page, or coming back later, doesn't lose
anything — the customer's own orders are remembered by browser (order IDs
kept in `localStorage`, since there's no login), and the waiter dashboard
re-fetches the full current order list from the server.

---

## 4. How to use it (walkthrough)

1. Open the live link. You land on the **Customer** view.
2. Enter your name, phone number, and table number (any table number —
   there's no real table registry).
3. Use the **+ / −** buttons on any menu item to build an order. A bar
   appears at the bottom showing your item count and total.
4. Press **Place order**. Your order appears under "Your orders" with a
   status of *Placed* and an estimated waiting time.
5. Click **Waiter** at the top right to switch roles (no login — this is a
   simple view switch, as the assignment allows).
6. Pick your name from **You are**. Your new order appears at the top,
   waiting to be picked up.
7. Press **Assign to me**. A checklist appears — one row per item.
8. For each row, pick the chef (food) or bartender (drink) who prepared it
   and press **Record**. The row turns green with a checkmark once done.
9. Once every row is checked off, press **Mark served**.
10. Switch back to **Customer** — your ticket now shows *Served*, a
    **Pay (pretend)** button, a star-rating form, and a complaint field.
    You can rate, complain, pay — any combination, independently.
11. Pressing **Pay (pretend)** marks the order paid with a generated
    transaction reference and moves it out of the waiter's active list
    into **Settled tonight**.

---

## 5. How to deploy it yourself

You'll need a free [GitHub](https://github.com) account (you already have
one), a free [Neon](https://neon.tech) account for Postgres, and a free
[Render](https://render.com) account for hosting. No credit card needed for
either.

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
request after a while will just be slow (10–30s) while it wakes up — that's
normal for a free-tier deploy and not a bug in the app.
