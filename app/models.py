import enum
import uuid
from datetime import datetime, date

from sqlalchemy import (
    Column, Integer, String, Float, Enum, DateTime, Date, ForeignKey, Text,
    Boolean, UniqueConstraint
)
from sqlalchemy.orm import relationship

from .database import Base


class ItemType(str, enum.Enum):
    food = "food"
    drink = "drink"


class AvailabilityStatus(str, enum.Enum):
    available = "available"
    sold_out = "sold_out"          # 86'd for now, comes back
    discontinued = "discontinued"  # retired for good — never deleted, so its sales history stays linked


class OrderStatus(str, enum.Enum):
    placed = "placed"          # customer submitted, no waiter assigned yet
    assigned = "assigned"      # a waiter has picked it up
    served = "served"          # every item prepared, waiter marked it served
    paid = "paid"              # payment recorded
    cancelled = "cancelled"    # customer cancelled before prep started


class PreparationStatus(str, enum.Enum):
    pending = "pending"
    completed = "completed"


class ComplaintStatus(str, enum.Enum):
    open = "open"
    resolved = "resolved"


class PaymentStatus(str, enum.Enum):
    successful = "successful"


# ---------------------------------------------------------------------------
# Restaurant / Menu
# ---------------------------------------------------------------------------
class Restaurant(Base):
    __tablename__ = "restaurants"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    address = Column(String)
    phone_number = Column(String)
    email = Column(String)
    # BRD: "one official name and code per location". The code is the
    # stable business key; names can be tidied without breaking reports.
    location_code = Column(String, unique=True, index=True)

    menus = relationship("Menu", back_populates="restaurant")
    waiters = relationship("Waiter", back_populates="restaurant")
    chefs = relationship("Chef", back_populates="restaurant")
    bartenders = relationship("Bartender", back_populates="restaurant")


class Menu(Base):
    __tablename__ = "menus"

    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), nullable=False)
    name = Column(String, nullable=False)
    menu_type = Column(String)
    description = Column(String)

    restaurant = relationship("Restaurant", back_populates="menus")
    items = relationship("MenuItem", back_populates="menu")


class MenuItem(Base):
    __tablename__ = "menu_items"

    id = Column(Integer, primary_key=True, index=True)
    menu_id = Column(Integer, ForeignKey("menus.id"), nullable=False)
    item_name = Column(String, nullable=False)
    item_type = Column(Enum(ItemType), nullable=False)
    description = Column(String)
    price = Column(Float, nullable=False)
    prep_time_minutes = Column(Integer, nullable=False)
    availability_status = Column(String, nullable=False, default=AvailabilityStatus.available.value)
    # Stable business key that survives renames (BRD: "menu item identity
    # survives renames"). Anything keyed on item_name breaks on a rename.
    item_code = Column(String, unique=True, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    menu = relationship("Menu", back_populates="items")
    order_items = relationship("OrderItem", back_populates="menu_item")
    events = relationship("MenuItemEvent", back_populates="menu_item", order_by="MenuItemEvent.id")


class MenuItemEvent(Base):
    """Append-only log of every menu change (BRD: "log menu changes as
    events"). Prices and names are still updated in place on MenuItem for
    the live app, but nothing is lost: each change leaves a row here with
    the old and new value and when it happened, so the price on any past
    date can be rebuilt."""

    __tablename__ = "menu_item_events"

    id = Column(Integer, primary_key=True, index=True)
    menu_item_id = Column(Integer, ForeignKey("menu_items.id"), nullable=False, index=True)
    event_type = Column(String, nullable=False)  # created | price_changed | renamed | availability_changed | discontinued
    old_value = Column(String, nullable=True)
    new_value = Column(String, nullable=True)
    changed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    changed_by = Column(String, nullable=True)
    is_backfilled = Column(Boolean, default=False, nullable=False)

    menu_item = relationship("MenuItem", back_populates="events")


# ---------------------------------------------------------------------------
# Staff
# ---------------------------------------------------------------------------
class Waiter(Base):
    __tablename__ = "waiters"

    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    phone_number = Column(String)

    restaurant = relationship("Restaurant", back_populates="waiters")


class Chef(Base):
    __tablename__ = "chefs"

    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    phone_number = Column(String)

    restaurant = relationship("Restaurant", back_populates="chefs")


class Bartender(Base):
    __tablename__ = "bartenders"

    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    phone_number = Column(String)

    restaurant = relationship("Restaurant", back_populates="bartenders")


# ---------------------------------------------------------------------------
# Customer (captured at order time — no login/account creation)
# ---------------------------------------------------------------------------
class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    # Stored in one format only: +234XXXXXXXXXX (see app/phone.py)
    phone_number = Column(String, nullable=True, unique=True, index=True)
    email = Column(String, nullable=True)
    date_registered = Column(DateTime, default=datetime.utcnow)
    # Set when this record turned out to be a duplicate of another customer.
    merged_into_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)

    orders = relationship("Order", back_populates="customer")


class CustomerMerge(Base):
    """Record of every duplicate-customer merge (BRD: "merges recorded").
    Source rows are never rewritten; this table is the map from the
    duplicate to the surviving customer."""

    __tablename__ = "customer_merges"

    id = Column(Integer, primary_key=True, index=True)
    duplicate_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    surviving_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    match_key = Column(String, nullable=False)        # e.g. the normalised phone number
    original_phone_number = Column(String, nullable=True)
    merged_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    merged_by = Column(String, nullable=True)


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------
class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), nullable=False)
    waiter_id = Column(Integer, ForeignKey("waiters.id"), nullable=True)

    table_number = Column(Integer, nullable=False)
    order_date = Column(Date, default=date.today)
    order_time = Column(DateTime, default=datetime.utcnow)
    status = Column(Enum(OrderStatus), nullable=False, default=OrderStatus.placed)
    actual_completion_time = Column(DateTime, nullable=True)
    # --- Lab 1 additions (all nullable / defaulted, so old rows stay valid) ---
    channel = Column(String, default="dine_in")              # dine_in today; delivery orders arrive via partner import
    promised_wait_minutes = Column(Integer, nullable=True)   # the estimate shown to the customer, frozen at order time
    cancellation_reason = Column(String, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    restaurant = relationship("Restaurant")
    customer = relationship("Customer", back_populates="orders")
    waiter = relationship("Waiter")
    status_events = relationship("OrderStatusEvent", back_populates="order", order_by="OrderStatusEvent.id")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    preparations = relationship("OrderPreparation", back_populates="order", cascade="all, delete-orphan")
    complaint = relationship("Complaint", back_populates="order", uselist=False, cascade="all, delete-orphan")
    rating = relationship("Rating", back_populates="order", uselist=False, cascade="all, delete-orphan")
    payment = relationship("Payment", back_populates="order", uselist=False, cascade="all, delete-orphan")

    @property
    def estimated_waiting_time_minutes(self) -> int:
        """Kitchen/bar prepares items in parallel, so waiting time is the
        slowest single item in the order, not the sum of all of them.
        New orders store the promise at order time (promised_wait_minutes),
        so a later change to prep times can't rewrite what we promised."""
        if self.promised_wait_minutes is not None:
            return self.promised_wait_minutes
        if not self.items:
            return 0
        return max(item.menu_item.prep_time_minutes for item in self.items)

    @property
    def location_code(self):
        return self.restaurant.location_code if self.restaurant else None

    @property
    def total_amount(self) -> float:
        return sum(item.subtotal for item in self.items)


class OrderStatusEvent(Base):
    """Append-only history of every status change on an order, with a
    timestamp and who did it (BRD: "full order state history with
    timestamps"). Order.status is only the latest value."""

    __tablename__ = "order_status_events"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    from_status = Column(String, nullable=True)
    to_status = Column(String, nullable=False)
    changed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    actor_role = Column(String, nullable=True)   # customer | waiter | system
    actor_id = Column(Integer, nullable=True)
    note = Column(Text, nullable=True)
    is_backfilled = Column(Boolean, default=False, nullable=False)

    order = relationship("Order", back_populates="status_events")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    menu_item_id = Column(Integer, ForeignKey("menu_items.id"), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    unit_price = Column(Float, nullable=False)

    order = relationship("Order", back_populates="items")
    menu_item = relationship("MenuItem", back_populates="order_items")
    preparation = relationship("OrderPreparation", back_populates="order_item", uselist=False, cascade="all, delete-orphan")

    @property
    def subtotal(self) -> float:
        return self.unit_price * self.quantity


class OrderPreparation(Base):
    """Records which chef or bartender prepared a given item in an order.
    One row per OrderItem — a chef is set for food items, a bartender for
    drink items, matching 'the waiter... specifying the chef and the
    bartender who prepared the order' at the level of what was actually
    prepared."""

    __tablename__ = "order_preparations"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    order_item_id = Column(Integer, ForeignKey("order_items.id"), nullable=False, unique=True)
    menu_item_id = Column(Integer, ForeignKey("menu_items.id"), nullable=False)
    chef_id = Column(Integer, ForeignKey("chefs.id"), nullable=True)
    bartender_id = Column(Integer, ForeignKey("bartenders.id"), nullable=True)
    status = Column(Enum(PreparationStatus), nullable=False, default=PreparationStatus.pending)
    preparation_start_time = Column(DateTime, default=datetime.utcnow)
    preparation_end_time = Column(DateTime, nullable=True)

    order = relationship("Order", back_populates="preparations")
    order_item = relationship("OrderItem", back_populates="preparation")
    menu_item = relationship("MenuItem")
    chef = relationship("Chef")
    bartender = relationship("Bartender")


# ---------------------------------------------------------------------------
# Complaint, Rating, Payment — separate entities
# ---------------------------------------------------------------------------
class Complaint(Base):
    __tablename__ = "complaints"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, unique=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    description = Column(Text, nullable=False)
    complaint_date = Column(DateTime, default=datetime.utcnow)
    status = Column(Enum(ComplaintStatus), nullable=False, default=ComplaintStatus.open)
    # --- Lab 1 additions ---
    category = Column(String, nullable=True)                 # see COMPLAINT_CATEGORIES in schemas.py
    menu_item_id = Column(Integer, ForeignKey("menu_items.id"), nullable=True)  # which dish, if it's about one
    resolved_at = Column(DateTime, nullable=True)
    resolution_note = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    order = relationship("Order", back_populates="complaint")
    menu_item = relationship("MenuItem")


class Rating(Base):
    __tablename__ = "ratings"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, unique=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    rating_value = Column(Integer, nullable=False)  # 1-5
    comment = Column(Text, nullable=True)
    rating_date = Column(DateTime, default=datetime.utcnow)

    order = relationship("Order", back_populates="rating")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, unique=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    amount = Column(Float, nullable=False)
    payment_method = Column(String, default="Simulated (pretend) payment")
    payment_time = Column(DateTime, default=datetime.utcnow)
    status = Column(Enum(PaymentStatus), nullable=False, default=PaymentStatus.successful)
    transaction_reference = Column(String, default=lambda: f"PRETEND-{uuid.uuid4().hex[:10].upper()}")
    recorded_by_waiter_id = Column(Integer, ForeignKey("waiters.id"), nullable=True)

    order = relationship("Order", back_populates="payment")
    corrections = relationship("PaymentCorrection", back_populates="payment", order_by="PaymentCorrection.id")


class PaymentCorrection(Base):
    """Payments are never edited (a database trigger blocks it). A refund
    or a fix is recorded here as a new row against the original payment
    (BRD: "payment records immutable, with corrections as new records")."""

    __tablename__ = "payment_corrections"

    id = Column(Integer, primary_key=True, index=True)
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    amount = Column(Float, nullable=False)     # negative = money back to the customer
    reason = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    recorded_by = Column(String, nullable=True)

    payment = relationship("Payment", back_populates="corrections")


# ---------------------------------------------------------------------------
# Partner data imports (delivery platform, suppliers, card acquirer)
# ---------------------------------------------------------------------------
class ImportBatch(Base):
    """One uploaded partner file. Kept even when the load fails, so a
    failure is visible rather than silent."""

    __tablename__ = "import_batches"
    __table_args__ = (UniqueConstraint("source", "file_sha256", name="uq_import_source_file"),)

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String, nullable=False)          # delivery_platform | supplier_invoice | card_acquirer
    filename = Column(String, nullable=False)
    file_sha256 = Column(String, nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    uploaded_by = Column(String, nullable=True)
    status = Column(String, nullable=False)          # loaded | partial | failed
    rows_total = Column(Integer, default=0, nullable=False)
    rows_loaded = Column(Integer, default=0, nullable=False)
    rows_duplicate = Column(Integer, default=0, nullable=False)
    rows_rejected = Column(Integer, default=0, nullable=False)
    error = Column(Text, nullable=True)              # file-level problem, e.g. missing columns

    rejections = relationship("ImportRejection", back_populates="batch", order_by="ImportRejection.row_number")


class ImportRejection(Base):
    """Quarantine: rows that failed a quality rule. Never loaded, never
    silently dropped — kept here with the reason so someone can fix them."""

    __tablename__ = "import_rejections"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("import_batches.id"), nullable=False, index=True)
    row_number = Column(Integer, nullable=False)     # 2 = first data row under the header
    raw_row = Column(Text, nullable=False)           # the row exactly as received (JSON)
    errors = Column(Text, nullable=False)

    batch = relationship("ImportBatch", back_populates="rejections")


class DeliverySettlement(Base):
    __tablename__ = "delivery_settlements"
    __table_args__ = (UniqueConstraint("platform_order_ref", "settlement_ref", name="uq_delivery_order_settlement"),)

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("import_batches.id"), nullable=False, index=True)
    platform_order_ref = Column(String, nullable=False)
    chowly_order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), nullable=False)
    order_date = Column(Date, nullable=False)
    gross_amount = Column(Float, nullable=False)
    commission_amount = Column(Float, nullable=False)
    net_amount = Column(Float, nullable=False)
    settlement_date = Column(Date, nullable=False)
    settlement_ref = Column(String, nullable=False)


class SupplierInvoiceLine(Base):
    __tablename__ = "supplier_invoice_lines"
    __table_args__ = (UniqueConstraint("supplier_key", "invoice_number", "line_number", name="uq_supplier_invoice_line"),)

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("import_batches.id"), nullable=False, index=True)
    supplier_name = Column(String, nullable=False)
    supplier_key = Column(String, nullable=False)    # lower-cased, single-spaced name, used to spot the same supplier
    invoice_number = Column(String, nullable=False)
    invoice_date = Column(Date, nullable=False)
    line_number = Column(Integer, nullable=False)
    item_description = Column(String, nullable=False)
    quantity = Column(Float, nullable=False)
    unit = Column(String, nullable=True)
    unit_price = Column(Float, nullable=False)
    line_total = Column(Float, nullable=False)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), nullable=False)


class CardSettlement(Base):
    __tablename__ = "card_settlements"
    __table_args__ = (UniqueConstraint("transaction_reference", "transaction_type", name="uq_card_txn"),)

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("import_batches.id"), nullable=False, index=True)
    transaction_reference = Column(String, nullable=False)
    transaction_type = Column(String, nullable=False)   # sale | refund | chargeback
    transaction_date = Column(Date, nullable=False)
    settlement_date = Column(Date, nullable=False)
    gross_amount = Column(Float, nullable=False)
    fee_amount = Column(Float, nullable=False)
    net_amount = Column(Float, nullable=False)
    chowly_order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), nullable=False)
