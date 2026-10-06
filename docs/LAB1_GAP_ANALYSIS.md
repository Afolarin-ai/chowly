# Lab 1: Find the Gaps in Your App

## 1. Read the BRD: the business questions it asks

1. What are sales per location, per day, week and month?
2. What exactly counts as "revenue"?
3. Can the monthly investor pack be ready one day after month end, with one set of totals?
4. What was the price of a dish on any past date?
5. What status was an order in at any time, and how long did each step take?
6. Did we keep the waiting-time promise on at least 90% of orders?
7. How do dishes sell year on year, even after being renamed or removed?
8. Which orders were cancelled, when, and why?
9. Which staff member handled each step of each order?
10. Who are our real (unique) customers, and who are the top 500?
11. What are complaints by type, dish and location? Was the cause found within 48 hours?
12. Can complaints be traced back to orders and supplier invoices?
13. Do delivery-platform payouts match our orders?
14. Do card payouts, fees and refunds match our payments?
15. What do ingredients cost, by supplier, over time?
16. How do holidays and promotions affect sales?
17. Which payment methods and channels do customers use?
18. How good is the data from each source?
19. Who can see customer and payment data?
20. Which customers are due to be anonymised (18 months after their last order)?

## 2. What the app stores (tables and columns exactly as built)

| Table | Columns |
|---|---|
| restaurants | id, name, address, phone_number, email |
| menus | id, restaurant_id, name, menu_type, description |
| menu_items | id, menu_id, item_name, item_type, description, price, prep_time_minutes, availability_status |
| waiters | id, restaurant_id, first_name, last_name, phone_number |
| chefs | id, restaurant_id, first_name, last_name, phone_number |
| bartenders | id, restaurant_id, first_name, last_name, phone_number |
| customers | id, first_name, last_name, phone_number, email, date_registered |
| orders | id, customer_id, restaurant_id, waiter_id, table_number, order_date, order_time, status, actual_completion_time |
| order_items | id, order_id, menu_item_id, quantity, unit_price |
| order_preparations | id, order_id, order_item_id, menu_item_id, chef_id, bartender_id, status, preparation_start_time, preparation_end_time |
| complaints | id, order_id, customer_id, description, complaint_date, status |
| ratings | id, order_id, customer_id, rating_value, comment, rating_date |
| payments | id, order_id, customer_id, amount, payment_method, payment_time, status, transaction_reference |

## 3 and 4. The gap table

| BRD need | What exists | What to add |
|---|---|---|
| Location on every order | Only one restaurant, with no location code | Location codes for the 3 branches (LEK, IKJ, WUS), and a location picker for customers and waiters |
| Time of every order status change | Status is overwritten. Only order time and completion time are kept. | A status history table: old status, new status, time, who |
| Waiting-time promise kept | Estimate is recalculated each time, never saved | Save the promised waiting time when the order is placed |
| Price of a dish on any past date | Price on the order is saved, but menu price changes are overwritten | A menu change log (old value, new value, time, who) |
| Renamed or removed dishes keep their history | Dishes are identified only by name | A permanent item code, and "discontinue" instead of delete |
| Cancellations and reasons | Status says "cancelled", with no time or reason | Cancellation reason and time |
| Staff on every action | Waiter, chef and bartender are recorded. Who took payment or cancelled is not. | Record who did each status change and who took payment |
| Complaint categories | Free text only | A complaint category and which dish it was about |
| Valid phone numbers, one record per customer | Phone is free text and isn't asked for at checkout | Check and store phones in one format (+234…) and recognise returning customers |
| Payment method and channel | Every payment says "Simulated (pretend) payment" | Payment method (cash, card, transfer) and order channel |
| Payments never edited; fixes added as new records | One payment per order; refunds not possible | A payment corrections table for refunds |
| Partner data: delivery platform, supplier invoices, card payouts | None | A file import (CSV/Excel) for each partner, which holds back bad rows with a reason and never loads the same data twice |
| A safe way for the data platform to read data | Only the live database | An `updated_at` time on changing tables, and a read-only database login |
| Named logins and role-based access | No logins (role switch only) | Staff logins by role (not built yet) |

**The updated app** is on the `lab1-gap-analysis` branch. Every row above is built except staff logins.
