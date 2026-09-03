import enum
import uuid
from datetime import datetime, date

from sqlalchemy import (
    Column, Integer, String, Float, Enum, DateTime, Date, ForeignKey, Text
)
from sqlalchemy.orm import relationship

from .database import Base


class ItemType(str, enum.Enum):
    food = "food"
    drink = "drink"


class OrderStatus(str, enum.Enum):
    placed = "placed"          # customer submitted, no waiter assigned yet
    assigned = "assigned"      # a waiter has picked it up
    served = "served"          # every item prepared, waiter marked it served
    paid = "paid"              # payment recorded


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
    availability_status = Column(String, default="available")

    menu = relationship("Menu", back_populates="items")
    order_items = relationship("OrderItem", back_populates="menu_item")


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
    phone_number = Column(String, nullable=False, unique=True, index=True)
    email = Column(String, nullable=True)
    date_registered = Column(DateTime, default=datetime.utcnow)

    orders = relationship("Order", back_populates="customer")


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

    customer = relationship("Customer", back_populates="orders")
    waiter = relationship("Waiter")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    preparations = relationship("OrderPreparation", back_populates="order", cascade="all, delete-orphan")
    complaint = relationship("Complaint", back_populates="order", uselist=False, cascade="all, delete-orphan")
    rating = relationship("Rating", back_populates="order", uselist=False, cascade="all, delete-orphan")
    payment = relationship("Payment", back_populates="order", uselist=False, cascade="all, delete-orphan")

    @property
    def estimated_waiting_time_minutes(self) -> int:
        """Kitchen/bar prepares items in parallel, so waiting time is the
        slowest single item in the order, not the sum of all of them."""
        if not self.items:
            return 0
        return max(item.menu_item.prep_time_minutes for item in self.items)

    @property
    def total_amount(self) -> float:
        return sum(item.subtotal for item in self.items)


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

    order = relationship("Order", back_populates="complaint")


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

    order = relationship("Order", back_populates="payment")
