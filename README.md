# Chowly

A table-side ordering platform for a restaurant: customers order and pay from
their table, waiters pick up orders and record which chef or bartender
prepared each item, and every order carries its own waiting time, rating,
complaint, and payment record.

**Live app:** https://chowly-9hem.onrender.com/
**Repo:** https://github.com/Afolarin-ai/chowly

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
│       ├── js/app.js
│       └── images/
│           ├── food/     # dish photography, one file per menu item
│           └── bg/       # kitchen + dining-room background photos
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
| `Customer` | first_name, last_name, phone_number (optional, unique when given), email, date_registered |
| `Restaurant` | name, address, phone_number, email |
| `Menu` | restaurant_id, name, menu_type, description |
| `MenuItem` | menu_id, item_name, item_type (food/drink), price, prep_time_minutes, availability_status |
| `Waiter` / `Chef` / `Bartender` | restaurant_id, first_name, last_name, phone_number |
| `Order` | customer_id, restaurant_id, waiter_id, table_number, status (placed/assigned/served/paid/cancelled), order_time, actual_completion_time |
| `OrderItem` | order_id, menu_item_id, quantity, unit_price |
| `OrderPreparation` | order_id, order_item_id, menu_item_id, chef_id, bartender_id, status, preparation_start/end_time |
| `Complaint` | order_id, customer_id, description, complaint_date, status |
| `Rating` | order_id, customer_id, rating_value (1–5), comment, rating_date |
| `Payment` | order_id, customer_id, amount, payment_method, payment_time, status, transaction_reference |

**Three deliberate deviations remain, each forced by the build itself,**
per the instruction to change the model where the build requires it and
say why:

- **No `CustomerID`-based login, and phone number is optional.** The
  assignment explicitly states "logins are not required, a simple switch
  is enough." `Customer` still exists as a real table — a customer's name
  is captured at order time, with phone number as an optional field for
  recognizing a returning customer (get-or-created by phone when given;
  a fresh row is created per order when it isn't) — but there's no
  authentication layer sitting in front of it. Making phone optional was
  a deliberate UX call once the app was actually being used: requiring it
  added friction for no real benefit in a no-login flow.
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
Menu items show real dish photography (resized and compressed from the
original uploads down to a few KB each) instead of stock icons, laid out
like a typical food-ordering app: photo on top, name/price/controls
below, with a category-coded accent stripe (marigold for food, teal for
drinks) along the top edge of each card. Two venue photos (kitchen,
dining room) sit behind everything and swap with the Customer/Waiter
toggle — visible enough for real ambient depth, not just a decorative
gradient, with legibility coming from frosted-glass panels
(`backdrop-filter: blur`) behind the header and intro text rather than
from flattening the photo into near-invisibility. Staff are represented
with generated initials avatars (a deterministic color per name), not
fake stock headshots of people who don't exist. Type pairs Fraunces
(display — pushed to a heavier weight, with italic used for the tagline
and category headers) with Sora (body/UI). The color palette is
deliberately saturated rather than a muted "safe" version of itself —
status pills, prices, and section accents all use fuller-strength color
rather than pastel tints. Motion is scoped deliberately: one staggered
entrance for the menu on first load, and functional micro-motion
elsewhere (the role toggle, the cart bar, a prep row popping when
checked off, a ticket glowing once when paid) — not hover animations on
every card, which reads as generic rather than intentional.

### Deployment
See [Section 6](#6-how-to-deploy-it-yourself) below for the exact steps —
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

**How it actually went, across several passes:**
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
3. I asked for a first visual pass — a logo, generated staff avatars, and
   motion. Claude used hand-illustrated SVG icons for menu items at this
   stage, since it didn't have real photos yet.
4. I supplied real photography for every dish plus two venue shots.
   Claude swapped the illustrated icons for the actual photos, added a
   background photo treatment behind the app, and — separately, based on
   my own read of the ordering flow — dropped the phone number field
   from checkout since it added friction with no benefit in a no-login
   app.
5. I asked for the visual design to be pushed further — bolder fonts,
   more saturated color, and backgrounds that were actually visible
   rather than washed almost flat. Claude resaturated the palette,
   swapped the body font, and rebuilt how the background photos stay
   legible (frosted panels instead of a heavy wash).
6. I asked for the "assigned" order status to be split into two distinct
   labels — "Assigned to a waiter" versus "Order is being prepared" —
   once I noticed the single "Being prepared" label didn't distinguish
   between a waiter just picking up an order and a chef/bartender
   actually starting on it. Claude computed this from whether any
   `OrderPreparation` row was complete yet, rather than adding a new
   stored status value, since it's fully derivable from existing state.
7. Given the assignment's bonus prompt, I asked what was worth adding
   beyond the requirements. Claude proposed five options with a rough
   sense of effort for each; I picked all five (cancel an order, 86 an
   item, a small stats panel, table QR codes, printable tickets) rather
   than one or two. While testing that batch, Claude found and fixed a
   real bug on its own — the cart bar stayed stuck visible after
   switching from Customer to Waiter with items still in the cart — by
   checking the actual DOM state directly rather than assuming a
   screenshot showing it was just a rendering artifact (which is what an
   earlier, similar-looking screenshot had turned out to be).

**What I accepted:**
- The overall architecture (single FastAPI service serving both API and
  static frontend, SQLite→Postgres via one env var).
- The visual design direction at each stage — the ticket-style order
  cards, the illustrated-icon system before I had real photos, and later
  the photo-and-frosted-panel treatment — each proposed specifically to
  avoid the generic "AI-generated SaaS card" look.
- The three named deviations from my original model (no login, single
  restaurant/menu, derived rather than stored waiting time) — Claude
  flagged these as forced by the assignment's actual feature list rather
  than silently dropping them, and I agreed with the reasoning for each.
- Computing the "Assigned to a waiter" / "Order is being prepared" split
  from existing preparation data instead of adding a new stored status.
- All five proposed bonus features, and the same eligibility rule
  (nothing prepared yet) being reused for both Cancel and — when I asked
  about it — the not-yet-built Edit feature, rather than inventing a
  second rule for a very similar situation.

**What I corrected / rejected:**
- Rejected the first data model outright — even though it worked, it
  wasn't the one I'd actually designed and been graded on, so I had it
  fully restructured to match my original document rather than accept
  the shortcut version.
- Rejected phone number as a required field once I saw it sitting in
  the actual checkout flow — it added friction for no real benefit in
  an app with no login, so I had it dropped and made properly optional
  on the backend, not just hidden in the UI.
- Pushed back on the single "Being prepared" status label as
  ambiguous — a waiter picking up an order and a chef actually starting
  to cook are two different moments, and I wanted the label to say
  which one had actually happened.
- Rejected the first visual pass as too safe — illustrated icons, a
  muted palette, background photos washed almost to invisibility. Asked
  for real dish photography, then a second time for bolder fonts, more
  saturated color, and backgrounds that were actually visible rather
  than decorative.

**What I verified myself, rather than taking on faith:**
- Every screen and the full order lifecycle (place → assign → per-item
  preparation → serve → rate/complain → pay) was tested by actually
  clicking through the running app — not just reading the code — both
  before and after the model reconciliation, since the rewrite touched
  every layer of the stack.
- Walked through the actual Neon database setup and Render deployment
  myself rather than taking the instructions on faith — along the way I
  caught that my extracted project was missing its `.git` folder (my
  file manager was just hiding dotfiles, not a real bug) and confirmed
  the fix before moving on.
- Noticed independently that the README had gone stale after a run of
  feature commits, by checking it against the actual commit history
  rather than assuming it was current.
- Flagged things that looked off during my own use of the app — an
  apparent missing waiting-time display, and a report of orders looking
  duplicated on the customer page — rather than assuming everything was
  fine. The first turned out to be a screenshot-tool artifact, confirmed
  against the live DOM state, not a real bug; the second I chose to
  deprioritize rather than chase down immediately, and it's noted as an
  open item in the Bonus section above instead of being quietly dropped.

---

## 3. The specific behaviour of the application

**Menu browsing.** A customer opens the app and lands on the Customer tab
by default. Food and drinks are shown in separate sections, each item
listing its name, price, and prep time — loaded from the database at
startup via `Restaurant` → `Menu` → `MenuItem`, not hardcoded in the
frontend.

**Order placement.** The customer enters their name and table number
(phone number is optional — a small field to ask for up front when
there's no real benefit to requiring it in a no-login flow), adjusts
quantities with the +/− controls on each item, and a cart bar appears at
the bottom showing the running item count and total. Pressing **Place
order** looks up or creates their `Customer` record (by phone when one
was given, otherwise a fresh record), creates the `Order` and its
`OrderItem` rows, and creates one `OrderPreparation` row per item
(unassigned). The customer immediately sees an order ticket with its
status, itemised total, and estimated waiting time.

**Order assignment.** Switching to the Waiter tab shows every unpaid
order. A waiter selects their own name once (remembered for the
session). Pressing **Assign to me** on a new order records that waiter
against the order (`Order.waiter_id`) and reveals a preparation checklist
— one row per item. Each row shows a chef selector for food items or a
bartender selector for drinks (never both), because the preparer is
recorded per item, not once for the whole order. The order's status
label reads "Assigned to a waiter" until at least one item has an actual
chef or bartender recorded, at which point it switches to "Order is
being prepared" — both are derived from existing data, not a separate
stored status. **Mark served** only appears once every row is checked
off.

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

## 4. Bonus — beyond the requirements

The assignment calls out bonus points for anything built beyond the core
requirements. Everything below is additional; none of it is needed for
the required story to work.

**Cancel an order.** A customer can cancel from their ticket while it's
still genuinely just sitting in the queue — either nobody's picked it up
yet (`placed`), or a waiter has but no chef/bartender has actually
started on any item (`assigned` with every `OrderPreparation` still
pending). The instant real prep work begins on even one item, the Cancel
button disappears — cancelling at that point would mean wasting food
already being made. The backend enforces the same rule independently
(rejects with a 400 if called too late), so this isn't just a hidden UI
button.

**86 an item.** A waiter can mark any menu item sold out from a small
"Menu availability" panel on the Floor screen. This flips
`MenuItem.availability_status`, which already existed in the original
data model but wasn't wired to anything until now. A sold-out item
disappears from the customer's menu within one polling cycle (the app
already refreshes every few seconds) — no page reload needed.

**Today's numbers.** The waiter dashboard shows a small live panel:
revenue today, order count, the top-selling item, and the average
rating — all computed from data the app already has (`Payment`,
`OrderItem`, `Rating`), scoped to the current date.

**Table QR codes.** Every table gets a generated QR code
(`/api/qr/{table_number}`) encoding a link straight back to the ordering
page with that table pre-filled, plus a printable sheet of them
(`/qr?count=N`) for however many tables the restaurant has — print it,
cut it up, one card per table.

**Printable kitchen ticket / receipt.** Every order ticket, on both the
customer and waiter side, has a Print button. It builds a clean,
minimal, monospace ticket in a hidden print-only area and triggers the
browser's print dialog — labelled "KITCHEN TICKET" for an unpaid order
or "RECEIPT" once it's paid, matching what a restaurant would actually
want to hand someone or stick on a rail.

**Known gaps, honestly.** Editing an order's items before prep starts
(same eligibility rule as cancel) was discussed and scoped — roughly a
30–45 minute build — but hasn't been built yet as of this document. A
report of orders appearing duplicated on the customer page was also
raised during development; it wasn't investigated further because it
didn't reproduce as a blocking issue and was deprioritized, so it's
listed here rather than silently left out.

---

## 5. How to use it (walkthrough)

1. Open the live link. You land on the **Customer** view.
2. Enter your name and a table number (any number — there's no real
   table registry).
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
12. Any ticket has a **Print** button (kitchen ticket before payment,
    receipt after) that opens your browser's print dialog with a clean,
    minimal version of the ticket.
13. While an order is still just placed, or assigned but untouched, its
    ticket also shows a **Cancel order** button — try it, then try
    placing a fresh order and letting a waiter start prep before
    checking again; the button is gone once prep has begun.
14. On the Floor screen, waiters can mark a dish sold out under **Menu
    availability** (it disappears from the customer menu within a few
    seconds), see **today's revenue/orders/top-seller/rating**, and open
    a **printable sheet of table QR codes** — each one deep-links back
    to the ordering page with that table pre-filled.

---

## 6. How to deploy it yourself

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
