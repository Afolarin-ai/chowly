# Chowly

A table-side ordering platform for a restaurant: customers order and pay from
their table, waiters pick up orders and record who prepared them, and every
order carries its own waiting time, rating, and payment status.

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
│   ├── seed.py          # loads menu + staff reference data on startup
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
| `MenuItem` | name, category (food/drink), price, prep_time_minutes |
| `StaffMember` | name, role (waiter/chef/bartender) |
| `Order` | table_number, status, waiter_id, chef_id, bartender_id, paid, paid_at, created_at |
| `OrderItem` | order_id, menu_item_id, quantity |
| `Complaint` | order_id, message, rating (1–5) |

**Note on the model:** this assignment builds on data modeling work from an
earlier assignment. I designed this model fresh for the build rather than
carrying the prior one forward unmodified — two decisions worth flagging
explicitly, per the instruction to say why when the build forces a change:

- **Waiting time is derived, not stored.** It's computed as the *slowest
  single item* in the order (`max` of prep times), not the sum, because a
  kitchen and bar work in parallel rather than making items one after
  another. Storing a static "wait time" field would drift from reality the
  moment an order has more than one item.
- **`chef_id` and `bartender_id` are both optional on `Order`.** A
  drinks-only order has no chef to record, and a food-only order has no
  bartender. Making both mandatory would force waiters to pick a name that
  didn't actually touch the order.

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
data model, API, frontend, deployment packaging — under a same-day deadline,
with a specific instruction to prioritize a polished, non-templated visual
design over speed of scaffolding.

**What I accepted:**
- The overall architecture (single FastAPI service serving both API and
  static frontend, SQLite→Postgres via one env var) — this was proposed by
  Claude as the fastest path to a real deployed link without sacrificing a
  proper UI, and I agreed it fit the timeline.
- The full data model and API surface as designed (see Section 1).
- The visual design direction (ivory/slate/marigold palette, Fraunces +
  Inter type, ticket-style order cards) — Claude proposed this specifically
  to avoid the generic "AI-generated SaaS card" look, and I kept it as
  proposed.
- The waiting-time calculation (max prep time, not sum) — I hadn't
  specified this, and I agreed with the parallel-kitchen reasoning once
  Claude explained it.

**What I corrected / rejected:**
- _[Fill this in with anything you personally changed after reviewing the
  code — e.g. menu items, copy, a design tweak, a business rule you wanted
  different. Be specific; this section should reflect your actual review,
  not Claude's.]_

**What I verified myself, rather than taking on faith:**
- Every screen and the full order lifecycle (place → assign → serve →
  complain/rate → pay) was tested by actually clicking through the running
  app — not just reading the code — before I accepted it as done.
- _[Add anything else you personally re-checked before submitting.]_

---

## 3. Application behaviour

**Menu browsing.** A customer opens the app and lands on the Customer tab
by default. Food and drinks are shown in separate sections, each item
listing its name, price, and prep time. This data is loaded once from the
database at startup — not hardcoded in the frontend.

**Order placement.** The customer enters their table number, adjusts
quantities with the +/− controls on each item, and a cart bar appears at
the bottom of the screen showing the running item count and total. Pressing
**Place order** sends it to the backend, which returns the created order
immediately — the customer sees an order ticket with its status, itemised
total, and estimated waiting time (the slowest item's prep time) without
leaving the page.

**Order assignment.** Switching to the Waiter tab shows every order that
hasn't been paid yet. A waiter selects their own name once (remembered for
the session), then for any new order picks the chef and/or bartender who
prepared it and presses **Assign to me** — this records the waiter against
the order and moves its status to "in progress." A **Mark served** button
then appears.

**Complaint and rating.** Once an order is no longer in the "just placed"
state, the customer's ticket for that order grows a complaint form: a
1–5 star picker and a free-text message. Submitting it stores both against
the order and immediately shows a confirmation on the ticket — a complaint
can only be filed once per order.

**Payment.** Once an order is marked served, both the customer's own ticket
and the waiter's dashboard show a **Pay (pretend)** button — either side can
record it, matching "payment is made on the platform just before the
customer exits." The button is explicitly labelled pretend, and paying
marks the order paid, timestamps it, and moves it to the waiter's "Settled
tonight" list.

**Real storage.** Every action above is a write to the database (Postgres
in production). Refreshing the page, or coming back later, doesn't lose
anything — the customer's own orders are remembered by browser (via order
IDs kept in `localStorage`, since there's no login), and the waiter
dashboard just re-fetches the full current order list from the server.

---

## 4. How to use it (walkthrough)

1. Open the live link. You land on the **Customer** view.
2. Enter a table number (any number — there's no real table registry).
3. Use the **+ / −** buttons on any menu item to build an order. A bar
   appears at the bottom showing your item count and total.
4. Press **Place order**. Your order appears under "Your orders" with a
   status of *Placed* and an estimated waiting time.
5. Click **Waiter** at the top right to switch roles (no login — this is a
   simple view switch, as the assignment allows).
6. Pick your name from **You are**. Your new order appears at the top,
   waiting to be picked up.
7. Optionally choose the chef and/or bartender who prepared it, then press
   **Assign to me**. The order moves to "in progress."
8. Once ready, press **Mark served**.
9. Switch back to **Customer** — your ticket now shows *Served* and a
   **Pay (pretend)** button, and a complaint form has appeared underneath
   it. You can file a complaint and rating, pay, or both.
10. Pressing **Pay (pretend)** marks the order paid and moves it out of the
    waiter's active list into **Settled tonight**.

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
   tables and seeds the menu/staff automatically (see `app/seed.py`) —
   nothing else to run by hand.
5. Update the **Live app** and **Repo** links at the top of this document,
   commit, and push.

If Render's free tier spins the service down after inactivity, the first
request after a while will just be slow (10–30s) while it wakes up — that's
normal for a free-tier deploy and not a bug in the app.
