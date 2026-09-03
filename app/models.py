import enum
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Float, Enum, DateTime, ForeignKey, Boolean, Text
)
from sqlalchemy.orm import relationship

from .database import Base


class MenuCategory(str, enum.Enum):
    food = "food"
    drink = "drink"


class StaffRole(str, enum.Enum):
    waiter = "waiter"
    chef = "chef"
    bartender = "bartender"


class OrderStatus(str, enum.Enum):
    placed = "placed"          # customer submitted, no waiter assigned yet
    assigned = "assigned"      # waiter has taken it, chef/bartender recorded
    served = "served"          # waiter marked it served
    paid = "paid"              # payment recorded


class MenuItem(Base):
    __tablename__ = "menu_items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    category = Column(Enum(MenuCategory), nullable=False)
    price = Column(Float, nullable=False)
    prep_time_minutes = Column(Integer, nullable=False)

    order_items = relationship("OrderItem", back_populates="menu_item")


class StaffMember(Base):
    __tablename__ = "staff_members"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    role = Column(Enum(StaffRole), nullable=False)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    table_number = Column(Integer, nullable=False)
    status = Column(Enum(OrderStatus), nullable=False, default=OrderStatus.placed)
    created_at = Column(DateTime, default=datetime.utcnow)

    waiter_id = Column(Integer, ForeignKey("staff_members.id"), nullable=True)
    chef_id = Column(Integer, ForeignKey("staff_members.id"), nullable=True)
    bartender_id = Column(Integer, ForeignKey("staff_members.id"), nullable=True)

    paid = Column(Boolean, default=False)
    paid_at = Column(DateTime, nullable=True)

    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    complaint = relationship("Complaint", back_populates="order", uselist=False, cascade="all, delete-orphan")

    waiter = relationship("StaffMember", foreign_keys=[waiter_id])
    chef = relationship("StaffMember", foreign_keys=[chef_id])
    bartender = relationship("StaffMember", foreign_keys=[bartender_id])

    @property
    def waiting_time_minutes(self) -> int:
        """Kitchen/bar prepares items in parallel, so waiting time is the
        slowest single item in the order, not the sum of all of them."""
        if not self.items:
            return 0
        return max(item.menu_item.prep_time_minutes for item in self.items)

    @property
    def total_price(self) -> float:
        return sum(item.menu_item.price * item.quantity for item in self.items)


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    menu_item_id = Column(Integer, ForeignKey("menu_items.id"), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)

    order = relationship("Order", back_populates="items")
    menu_item = relationship("MenuItem", back_populates="order_items")


class Complaint(Base):
    __tablename__ = "complaints"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, unique=True)
    message = Column(Text, nullable=False)
    rating = Column(Integer, nullable=False)  # 1-5
    created_at = Column(DateTime, default=datetime.utcnow)

    order = relationship("Order", back_populates="complaint")
