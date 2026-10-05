# Lab 1: Find the Gaps in the Chowly App

**Deliverable:** a gap table (BRD need, what exists, what to add) and the updated app.

- **BRD:** Chowly Restaurants Ltd, Business Requirements Document (condensed summary)
- **App before this lab:** commit `0c40ab4` ("Final"), the table-side ordering app
- **App after this lab:** branch `lab1-gap-analysis`

The four lab steps are below in order. Step 4 is the gap table itself, with what was built to close each gap.

---

## Step 1. The business questions the BRD asks

| # | Business question | Where in the BRD |
|---|---|---|
| Q1 | What are sales and revenue per location, channel, day, week and month? | §5 Reporting; BO-1; PS-1 |
| Q2 | What exactly counts as "revenue"? (one agreed definition) | TE-8; §7 Governance |
| Q3 | Can the investor pack be produced within one business day of month end, with one set of totals? | TE-3; §6 Freshness |
| Q4 | What was the price of a dish on any past date? | TE-2; BO-3 |
| Q5 | What status was an order in at any moment, and how long did each stage take? | §5 History; BO-3 |
| Q6 | Did we keep the waiting-time promise on 90%+ of orders? | BO-5 |
| Q7 | How does a dish sell year on year, even after it's renamed or discontinued? | TE-7 |
| Q8 | Which orders were cancelled, when, and why? | §5 Data capture |
| Q9 | Which staff member took, prepared, served and settled each order? How do shifts perform? | §5 Data capture; S5 rota |
| Q10 | Who are our real, unique customers, and who are the top N? | TE-5; PS-5 |
| Q11 | Do customers come back, and to which locations? | §5 Master data ("one customer identity across locations") |
| Q12 | What are complaints by category, dish and location? Is the root cause found within 48 hours? | TE-6; BO-5 |
| Q13 | Can a cluster of complaints be traced to orders and supplier invoices (food safety)? | TE-6 |
| Q14 | Do delivery-platform settlements match our delivery orders after commission? | TE-4; BO-6; S2 |
| Q15 | Do card settlements, fees, refunds and chargebacks match our card payments? | BO-6; S4 |
| Q16 | What is the daily unexplained money difference? (target under 0.5%) | BO-6 |
| Q17 | What do ingredients cost, by supplier, location and over time? | S3 |
| Q18 | How do holidays and promotions affect sales? | S6 calendars |
| Q19 | How is the mix of payment methods and channels changing? | §5 Data capture |
| Q20 | How good is each source's data? (quality scorecard) | §5 Quality |
| Q21 | Who can see customer and payment data, and who looked at what? | §5 Security; §7 |
| Q22 | Which customers are due for anonymisation (18 months after their last order)? | §6 Retention |
| Q23 | Where did each published number come from? (lineage) | §7 |
| Q24 | Has analytics ever slowed down ordering? (target: never) | BO-2; TE-1 |

---

## Step 2. What the app stored, exactly as built (before Lab 1)

13 tables, from `app/models.py` at commit `0c40ab4`:

| Table | Columns |
|---|---|
| `restaurants` | id, name, address, phone_number, email |
| `menus` | id, restaurant_id, name, menu_type, description |
| `menu_items` | id, menu_id, item_name, item_type (food/drink), description, price, prep_time_minutes, availability_status (available/sold_out) |
| `waiters` | id, restaurant_id, first_name, last_name, phone_number |
| `chefs` | id, restaurant_id, first_name, last_name, phone_number |
| `bartenders` | id, restaurant_id, first_name, last_name, phone_number |
| `customers` | id, first_name, last_name, phone_number (optional, unique, free text), email, date_registered |
| `orders` | id, customer_id, restaurant_id, waiter_id, table_number, order_date, order_time, status (placed/assigned/served/paid/cancelled), actual_completion_time |
| `order_items` | id, order_id, menu_item_id, quantity, unit_price |
| `order_preparations` | id, order_id, order_item_id, menu_item_id, chef_id, bartender_id, status (pending/completed), preparation_start_time, preparation_end_time |
| `complaints` | id, order_id (one per order), customer_id, description, complaint_date, status (open/resolved) |
| `ratings` | id, order_id (one per order), customer_id, rating_value (1–5), comment, rating_date |
| `payments` | id, order_id (one per order), customer_id, amount, payment_method (always "Simulated (pretend) payment"), payment_time, status (successful), transaction_reference |

Computed but never stored: `estimated_waiting_time_minutes` (from current prep times) and `total_amount`.

How the app behaved, which matters for the gaps:

- Only one restaurant was seeded ("The Grand Table", Victoria Island). Every query used "the first restaurant", and there was no location code.
- `orders.status` was overwritten at every step. The only times kept were `order_time` and `actual_completion_time`.
- The checkout sent `phone_number: null`, so every order created a new customer. When a phone was sent, it was stored exactly as typed.
- The frontend matched dish photos by `item_name`, so renaming a dish would have lost its photo. That's the BRD's TE-7 problem in miniature.
- `preparation_start_time` defaults to when the order was placed, not when a chef started. It records queue time, not cooking time.
- There was no partner data of any kind: no delivery platform, supplier invoices or card settlements.

---

## Steps 3 and 4. The gap table

**Status key:**
- ✅ Closed in this lab
- ◐ Partly closed (the remainder is noted)
- ⏭ Later: belongs to the data platform labs, not the ordering app
- ✖ Not closed (reason given)

| # | BRD need | What exists (as built) | What was added (Lab 1) | Status |
|---|---|---|---|---|
| G1 | **Location** recorded on every order; one official name and code per location (§5 capture, §5 master data) | `orders.restaurant_id` existed, but there was only one restaurant, with no code. | `restaurants.location_code`. LEK, IKJ and WUS are seeded, and the old restaurant became LEK so its orders stay attached. Customers and waiters pick a location. QR codes carry the location. Staff belong to a location, and a waiter can't pick up another location's order. | ✅ |
| G2 | **Full order status history with timestamps** (§5 history, BO-3) | Status was overwritten. Only order and completion times were kept. | New append-only `order_status_events` table: from, to, time, who (role and id), note. Every status change goes through one function. Old orders were backfilled only from times that really exist, and flagged `is_backfilled`. | ✅ (history from before the lab is partial and flagged) |
| G3 | **Waiting-time promise measurable** (BO-5) | The estimate was recalculated live, so changing a prep time would rewrite past promises. | `orders.promised_wait_minutes` is frozen when the order is placed. The served time comes from the status events. | ✅ |
| G4 | **Price of every item on each sale date** (TE-2) | `order_items.unit_price` kept the price on the order (good). The menu price was overwritten with no record. | `menu_item_events` records each price change (old → new, when, by whom). Every item got a flagged baseline snapshot at migration. Prices are edited in the Office tab. | ✅ |
| G5 | **Menu changes as events; renamed or discontinued items stay analysable** (TE-7) | No rename or delete in the app. Photos keyed by name. | `menu_items.item_code` (M-001…) as a permanent key. Renames and discontinues are logged as events. "Discontinue" replaces delete, so history stays linked. Photos are keyed by code. | ✅ |
| G6 | **Cancellations and reasons** (§5 capture) | Status became "cancelled", with no time, reason or actor. | `orders.cancellation_reason` (fixed list) and `cancelled_at`. The status event records who cancelled. | ✅ |
| G7 | **Staff references** (§5 capture) | Waiter on the order and chef/bartender per item were already captured. Who took payment, who cancelled and who changed the menu were not. | Every status event has actor role and id. `payments.recorded_by_waiter_id`. `changed_by` on menu events. A name is recorded on every Office action. | ✅ (but see G18: no logins) |
| G8 | **Complaint categories** (§5 capture, TE-6) | Free-text description only | `complaints.category` (7 fixed codes) and `complaints.menu_item_id` (which dish) | ✅ |
| G9 | **Root cause within 48 hours** (BO-5) | A `status` column existed, but nothing could resolve a complaint and no time was kept. | A resolve action stores `resolved_at` and `resolution_note`. The Office tab shows each complaint's age and flags it after 48 h. | ✅ |
| G10 | **Valid phone formats; one customer identity** (TE-5, §5 master data) | Phone was free text, and the checkout didn't send it. | Phones are validated and stored as `+234XXXXXXXXXX`. Phone is back on checkout as optional. Returning customers are recognised however they type the number. Existing numbers were normalised, and duplicates were merged into the older record, with a trail in `customer_merges`. Orders and payments were not rewritten. | ◐ Customers who give a phone get one identity. Name-only guests stay separate, because there's no reliable key to match them. |
| G11 | **Payment method and channel** (§5 capture) | The method was always "Simulated (pretend) payment". There was no channel. | Method is picked at payment (cash, card, bank transfer). `orders.channel` is set to dine_in, and delivery data arrives through the partner import. | ✅ |
| G12 | **Payments immutable; corrections as new records** (§5 history) | One payment per order. Nothing technically stopped an edit, and refunds weren't possible. | `payment_corrections` table, with refunds recorded in the Office tab. A database trigger blocks UPDATE and DELETE on payments, corrections and all history tables, on both Postgres and SQLite. | ✅ |
| G13 | **A safe way for the platform to read data without slowing service** (§5 capture, BO-2, constraint) | Only the live database | `updated_at` on orders, menu items and complaints. The append-only tables have ever-increasing ids, which serve as incremental extraction keys. `docs/sql/readonly_role.sql` creates a named read-only login. | ◐ The read replica or change data capture (CDC) is infrastructure, to be set up in the platform lab. |
| G14 | **Partner data with a file import**: delivery platform, supplier invoices, card acquirer (§5 integration, §6 S2–S4) | None | Office tab → Partner data imports. Accepts CSV or Excel. A downloadable template for each source, and the named owner shown for each source (from §6). Loads into `delivery_settlements`, `supplier_invoice_lines` and `card_settlements`. | ✅ (the delivery-platform API is later) |
| G15 | **Failures alert, never stop silently** (§5) | n/a | Every upload is saved as a batch with status loaded, partial or failed and a plain-English message. Failed files still appear in the history. | ✅ |
| G16 | **Re-runs never duplicate data** (§5) | n/a | Uploading the same file again is refused (it is recognised by a SHA-256 fingerprint). Every row is checked against a natural key, so overlapping files skip rows that were already loaded. | ✅ |
| G17 | **Quality rules; failing records quarantined, never silently loaded or dropped** (§5, QR-001–010) | None | Per-source rules: required fields, numbers, dates, known location, known order, net = gross − fees, qty × price = line total, and refunds/chargebacks must be negative. Failing rows go to `import_rejections` with the raw row and the reason, and the Office tab shows them. | ◐ The official QR-001 to QR-010 list isn't in the condensed BRD, so these rules are a proposal to align with it. |
| G18 | **Role-based access, named accounts, no shared logins** (§5 security) | No logins (the original assignment allowed a role switch) | Names are recorded on every Office action, plus the read-only database role from G13. | ✖ Needs real authentication. Flagged for a later lab. |
| G19 | **Anonymise customers 18 months after their last order** (§6 retention) | Nothing | Now possible, since customers are de-duplicated and the last-order date can be computed. | ⏭ A scheduled governance job |
| G20 | **Daily reconciliation and variance report** (BO-6, TE-4) | None | The inputs are now captured: settlements, payment methods and corrections. | ⏭ The platform lab does the matching |
| G21 | **Agreed definitions (e.g. revenue), data dictionary, lineage, investor pack** (BO-1, TE-3, TE-8) | Waiter "Today's numbers" panel; revenue = sum of payments | That panel is now per location. | ⏭ The platform and governance labs |
| G22 | **Rota, calendars, supplier list** (§6 S5–S7) | None | Not built. These are internal spreadsheets, and the same import pattern can be extended to them. | ⏭ |
| G23 | **Delivery-platform orders and status changes** (§6 S2) | None | Settlements are imported. Order-level status data needs the platform's API. | ⏭ |

---

## How the app was changed safely

The BRD constraint is that "changes … must be backward-compatible with no downtime." Here's how the change meets it:

- **Additive only.** `app/migrate.py` runs on every startup. It only creates new tables, adds nullable columns, creates indexes and installs triggers. It never drops, renames or retypes anything, and it checks before each step, so running it twice changes nothing.
- **Honest backfill.** Old orders get status events only for moments with real timestamps. Anything else is labelled as "status as found at migration". Every backfilled row has `is_backfilled = TRUE`, as the BRD requires.
- **Tested against the old schema.** I built a database with the pre-Lab-1 code on both SQLite and Postgres 16, filled it with orders, then started the new code on it. The run included a real duplicate: the same customer typed as "0803 123 4567" and "+2348031234567". The migration merged that customer into one record and logged the merge. It also blocked a direct `UPDATE payments …` with an error, and a second run changed nothing.
- **Deploying:** push the branch and merge it to `main`. Render redeploys and the migration runs on the first start, with nothing to run by hand. Taking a Neon branch (snapshot) first is a good habit.

## Try it

1. **Customer:** pick a restaurant and table, optionally add a phone number, then order. A ticket can be cancelled only with a reason. A complaint needs a category and can name the dish. Paying asks for the method.
2. **Waiter:** pick the restaurant. The orders, staff, stats and QR codes all follow that choice. Each ticket shows its status timeline, and backfilled steps have a dashed outline.
3. **Office:** enter your name, then:
   - Upload the files in `samples/partner_files/`. Each one contains deliberate mistakes, and the expected results are in the table below.
   - Change a price or rename a dish, then look at the change log.
   - Resolve a complaint.
   - Record a refund.

| Sample file | Source | Rows | Loaded | Duplicates | Quarantined | Why |
|---|---|---|---|---|---|---|
| `delivery_platform_settlement_2026-10-03.csv` | Delivery platform | 8 | 4 | 1 | 3 | net ≠ gross − commission; unknown location "ABJ"; missing gross. A repeated row is skipped. One row uses DD/MM/YYYY and "11,400", which load fine. |
| `delivery_platform_settlement_2026-10-04.csv` | Delivery platform | 3 | 2 | 1 | 0 | One row was already loaded from the previous day's file. |
| `supplier_invoices_2026-10.xlsx` | Supplier invoices | 7 | 4 | 1 | 2 | Line total ≠ qty × price; negative quantity. "MAMA PUT FOODS LTD " is recognised as the same supplier. |
| `card_acquirer_settlement_2026-10-02.csv` | Card acquirer | 5 | 3 | 0 | 2 | A chargeback with a positive amount; an order number that doesn't exist |
| Any file uploaded a second time | Any | | | | | Refused: "already imported as batch #N" |
| A delivery file uploaded as "Card acquirer" | Card acquirer | | | | | Failed: missing required columns. The failure is recorded, not silent. |

## Files changed

| File | Change |
|---|---|
| `app/models.py` | New columns; new tables `order_status_events`, `menu_item_events`, `customer_merges`, `payment_corrections`, `import_batches`, `import_rejections`, `delivery_settlements`, `supplier_invoice_lines`, `card_settlements` |
| `app/migrate.py` | **New.** Additive schema upgrade, flagged backfill, customer merge, append-only triggers |
| `app/imports.py` | **New.** Partner file import: per-source rules, quarantine, idempotent loading |
| `app/phone.py` | **New.** Nigerian phone normalisation |
| `app/seed.py` | Three locations, staff per location, item codes; safe to run on an existing database |
| `app/schemas.py`, `app/main.py` | Fixed choice lists; location-aware endpoints; menu, complaint, payment-correction and import endpoints |
| `app/static/*` | Location pickers, capture fields, status timeline, new Office tab |
| `samples/partner_files/` | **New.** Sample partner files with deliberate errors |
| `docs/sql/readonly_role.sql` | **New.** Read-only login for the data platform |
| `requirements.txt` | Adds `python-multipart` (file upload) and `openpyxl` (Excel) |
