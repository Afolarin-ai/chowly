"""Safe, additive schema evolution — runs on every startup.

BRD constraint: "Changes to the Chowly application must be backward-
compatible with no downtime." So this module only ever ADDS things:
new tables, new nullable columns, new indexes, new triggers. It never
drops, renames or retypes anything, and every step can run again safely
(it checks before it acts). The live Neon database upgrades itself on the
next deploy; old rows stay valid as they are.

History that was never recorded can't be recreated (BRD constraint), so
anything filled in after the fact is written with is_backfilled = TRUE.
"""
import json
import logging
from datetime import datetime

from sqlalchemy import inspect, text

from .database import Base, engine
from .phone import InvalidPhone, normalise_ng_phone

log = logging.getLogger("chowly.migrate")

# Tables whose rows may be added but never changed or deleted.
APPEND_ONLY_TABLES = [
    "payments",
    "payment_corrections",
    "order_status_events",
    "menu_item_events",
    "customer_merges",
]


# ---------------------------------------------------------------------------
# 1. Schema: create new tables, add new columns to existing tables
# ---------------------------------------------------------------------------
def upgrade_schema() -> None:
    from . import models  # noqa: F401  (registers every table on Base)

    Base.metadata.create_all(bind=engine)  # creates only tables that don't exist yet

    insp = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            existing = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in existing:
                    continue
                col_type = col.type.compile(dialect=engine.dialect)
                conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {col.name} {col_type}'))
                log.info("added column %s.%s", table.name, col.name)
                if col.index or col.unique:
                    unique = "UNIQUE " if col.unique else ""
                    conn.execute(text(
                        f"CREATE {unique}INDEX IF NOT EXISTS ix_{table.name}_{col.name} "
                        f"ON {table.name} ({col.name})"
                    ))


# ---------------------------------------------------------------------------
# 2. Backfill what can honestly be backfilled, flagged as such
# ---------------------------------------------------------------------------
def backfill() -> None:
    now = datetime.utcnow()
    with engine.begin() as conn:
        conn.execute(text("UPDATE orders SET channel = 'dine_in' WHERE channel IS NULL"))
        conn.execute(text(
            "UPDATE orders SET updated_at = COALESCE(actual_completion_time, order_time) WHERE updated_at IS NULL"
        ))
        conn.execute(text("UPDATE complaints SET updated_at = complaint_date WHERE updated_at IS NULL"))
        conn.execute(text("UPDATE menu_items SET updated_at = :now WHERE updated_at IS NULL"), {"now": now})

        _backfill_order_events(conn, now)
        _backfill_menu_baseline(conn, now)
        _normalise_and_merge_customers(conn, now)


def _backfill_order_events(conn, now) -> None:
    """Orders placed before Lab 1 have no status history. Rebuild only the
    moments we have real timestamps for; for the rest, record the status as
    found today and say so in the note."""
    rows = conn.execute(text("""
        SELECT o.id, o.status, o.order_time, o.actual_completion_time, p.payment_time
        FROM orders o
        LEFT JOIN payments p ON p.order_id = o.id
        WHERE NOT EXISTS (SELECT 1 FROM order_status_events e WHERE e.order_id = o.id)
        ORDER BY o.id
    """)).fetchall()

    insert = text("""
        INSERT INTO order_status_events
            (order_id, from_status, to_status, changed_at, actor_role, note, is_backfilled)
        VALUES (:order_id, :from_status, :to_status, :changed_at, 'system', :note, :flag)
    """)
    for order_id, status, order_time, completed, paid_time in rows:
        status = str(status).split(".")[-1]  # enum may come back as 'OrderStatus.paid' on some drivers
        events = [(None, "placed", order_time, "Rebuilt from orders.order_time")]
        last = "placed"
        if status in ("served", "paid") and completed:
            events.append((None, "served", completed, "Rebuilt from orders.actual_completion_time; assignment time was never recorded"))
            last = "served"
        if status == "paid" and paid_time:
            events.append((last, "paid", paid_time, "Rebuilt from payments.payment_time"))
            last = "paid"
        if status != last:
            events.append((last, status, now, "Status as found at migration; the real time of this change was never recorded"))
        for from_s, to_s, at, note in events:
            conn.execute(insert, {"order_id": order_id, "from_status": from_s, "to_status": to_s,
                                  "changed_at": at or now, "note": note, "flag": True})
    if rows:
        log.info("backfilled status history for %d orders", len(rows))


def _backfill_menu_baseline(conn, now) -> None:
    """Price history before Lab 1 is gone. Take a flagged snapshot of every
    item as it is today, so history from here on is complete."""
    rows = conn.execute(text("""
        SELECT m.id, m.item_name, m.price, m.availability_status FROM menu_items m
        WHERE NOT EXISTS (SELECT 1 FROM menu_item_events e WHERE e.menu_item_id = m.id)
    """)).fetchall()
    for item_id, name, price, availability in rows:
        conn.execute(text("""
            INSERT INTO menu_item_events (menu_item_id, event_type, old_value, new_value, changed_at, changed_by, is_backfilled)
            VALUES (:id, 'baseline_snapshot', NULL, :value, :now, 'system: Lab 1 migration', :flag)
        """), {"id": item_id, "now": now, "flag": True,
               "value": json.dumps({"item_name": name, "price": price, "availability_status": availability})})


def _normalise_and_merge_customers(conn, now) -> None:
    """Rewrite stored phones into +234 format. When two customers turn out to
    share a number, keep the older record, move the duplicate's number into
    customer_merges, and point the duplicate at the survivor. Orders and
    payments are not rewritten — the merge table is the map."""
    rows = conn.execute(text("""
        SELECT id, phone_number FROM customers
        WHERE phone_number IS NOT NULL AND merged_into_customer_id IS NULL
        ORDER BY id
    """)).fetchall()

    groups: dict[str, list[tuple[int, str]]] = {}
    for cid, phone in rows:
        try:
            groups.setdefault(normalise_ng_phone(phone), []).append((cid, phone))
        except InvalidPhone:
            log.warning("customer %s has an unrecognised phone number; left as is", cid)

    for normalised, members in groups.items():
        survivor_id, _ = members[0]
        for dup_id, original in members[1:]:
            conn.execute(text("UPDATE customers SET phone_number = NULL, merged_into_customer_id = :s WHERE id = :d"),
                         {"s": survivor_id, "d": dup_id})
            conn.execute(text("""
                INSERT INTO customer_merges (duplicate_customer_id, surviving_customer_id, match_key,
                                             original_phone_number, merged_at, merged_by)
                VALUES (:d, :s, :k, :p, :now, 'system: phone normalisation')
            """), {"d": dup_id, "s": survivor_id, "k": normalised, "p": original, "now": now})
            log.info("merged duplicate customer %s into %s (%s)", dup_id, survivor_id, normalised)
        conn.execute(text("UPDATE customers SET phone_number = :p WHERE id = :s AND phone_number <> :p"),
                     {"p": normalised, "s": survivor_id})


# ---------------------------------------------------------------------------
# 3. Protect append-only tables at the database level
# ---------------------------------------------------------------------------
def protect_append_only_tables() -> None:
    """A database trigger, not just app code, stops UPDATE/DELETE on money
    and history tables — so a stray script or console query can't quietly
    rewrite a payment either."""
    dialect = engine.dialect.name
    try:
        with engine.begin() as conn:
            if dialect == "postgresql":
                conn.execute(text("""
                    CREATE OR REPLACE FUNCTION chowly_append_only() RETURNS trigger AS $$
                    BEGIN
                        RAISE EXCEPTION '% is append-only: record a new row instead of changing or deleting one', TG_TABLE_NAME;
                    END;
                    $$ LANGUAGE plpgsql
                """))
                for t in APPEND_ONLY_TABLES:
                    conn.execute(text(f"DROP TRIGGER IF EXISTS {t}_append_only ON {t}"))
                    conn.execute(text(
                        f"CREATE TRIGGER {t}_append_only BEFORE UPDATE OR DELETE ON {t} "
                        f"FOR EACH ROW EXECUTE FUNCTION chowly_append_only()"
                    ))
            elif dialect == "sqlite":
                for t in APPEND_ONLY_TABLES:
                    for action in ("UPDATE", "DELETE"):
                        conn.execute(text(
                            f"CREATE TRIGGER IF NOT EXISTS {t}_no_{action.lower()} BEFORE {action} ON {t} "
                            f"BEGIN SELECT RAISE(ABORT, '{t} is append-only: record a new row instead'); END"
                        ))
    except Exception:  # never take the app down over a safety net
        log.exception("could not install append-only triggers")


def run() -> None:
    upgrade_schema()
    from .seed import seed
    seed()
    backfill()
    protect_append_only_tables()
