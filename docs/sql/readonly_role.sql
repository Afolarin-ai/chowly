-- A read-only login for the data platform (BRD: "a safe way to read data
-- without slowing service", "named accounts, no shared logins").
--
-- Run once in the Neon SQL editor as the database owner. Replace
-- neondb with your database name and pick a real password.
--
-- Best practice: point extracts at a Neon read replica, if your plan
-- offers one, so analytics never runs on the primary that takes orders.
-- Until then, run extracts outside trading hours (BRD constraint).

CREATE ROLE chowly_reader WITH LOGIN PASSWORD 'change-me';
GRANT CONNECT ON DATABASE neondb TO chowly_reader;
GRANT USAGE ON SCHEMA public TO chowly_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO chowly_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO chowly_reader;

-- Incremental extraction keys added in Lab 1:
--   orders.updated_at, menu_items.updated_at, complaints.updated_at
--   order_status_events.id, menu_item_events.id, payment_corrections.id,
--   import_batches.id (append-only tables: new rows only, ids only go up)
