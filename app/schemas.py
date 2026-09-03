from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from .models import MenuCategory, StaffRole, OrderStatus


# ---------- Menu ----------
class MenuItemOut(BaseModel):
    id: int
    name: str
    category: MenuCategory
    price: float
    prep_time_minutes: int

    class Config:
        from_attributes = True


# ---------- Staff ----------
class StaffOut(BaseModel):
    id: int
    name: str
    role: StaffRole

    class Config:
        from_attributes = True


# ---------- Orders ----------
class OrderItemIn(BaseModel):
    menu_item_id: int
    quantity: int = Field(gt=0)


class OrderCreate(BaseModel):
    table_number: int = Field(gt=0)
    items: List[OrderItemIn]


class OrderItemOut(BaseModel):
    id: int
    menu_item: MenuItemOut
    quantity: int

    class Config:
        from_attributes = True


class ComplaintOut(BaseModel):
    id: int
    message: str
    rating: int
    created_at: datetime

    class Config:
        from_attributes = True


class OrderOut(BaseModel):
    id: int
    table_number: int
    status: OrderStatus
    created_at: datetime
    waiting_time_minutes: int
    total_price: float
    waiter: Optional[StaffOut] = None
    chef: Optional[StaffOut] = None
    bartender: Optional[StaffOut] = None
    paid: bool
    paid_at: Optional[datetime] = None
    items: List[OrderItemOut]
    complaint: Optional[ComplaintOut] = None

    class Config:
        from_attributes = True


class AssignOrder(BaseModel):
    waiter_id: int
    chef_id: Optional[int] = None
    bartender_id: Optional[int] = None


class ComplaintCreate(BaseModel):
    message: str
    rating: int = Field(ge=1, le=5)
