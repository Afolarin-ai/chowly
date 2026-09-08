from datetime import datetime, date
from typing import List, Optional

from pydantic import BaseModel, Field

from .models import ItemType, OrderStatus, PreparationStatus


# ---------- Menu ----------
class MenuItemOut(BaseModel):
    id: int
    item_name: str
    item_type: ItemType
    price: float
    prep_time_minutes: int
    availability_status: str

    class Config:
        from_attributes = True


# ---------- Staff ----------
class WaiterOut(BaseModel):
    id: int
    first_name: str
    last_name: str

    class Config:
        from_attributes = True


class ChefOut(BaseModel):
    id: int
    first_name: str
    last_name: str

    class Config:
        from_attributes = True


class BartenderOut(BaseModel):
    id: int
    first_name: str
    last_name: str

    class Config:
        from_attributes = True


# ---------- Customer ----------
class CustomerIn(BaseModel):
    first_name: str
    last_name: str
    phone_number: Optional[str] = None
    email: Optional[str] = None


class CustomerOut(BaseModel):
    id: int
    first_name: str
    last_name: str
    phone_number: Optional[str] = None

    class Config:
        from_attributes = True


# ---------- Orders ----------
class OrderItemIn(BaseModel):
    menu_item_id: int
    quantity: int = Field(gt=0)


class OrderCreate(BaseModel):
    table_number: int = Field(gt=0)
    customer: CustomerIn
    items: List[OrderItemIn]


class OrderItemOut(BaseModel):
    id: int
    menu_item: MenuItemOut
    quantity: int
    unit_price: float
    subtotal: float

    class Config:
        from_attributes = True


class PreparationOut(BaseModel):
    id: int
    order_item_id: int
    menu_item: MenuItemOut
    chef: Optional[ChefOut] = None
    bartender: Optional[BartenderOut] = None
    status: PreparationStatus

    class Config:
        from_attributes = True


class ComplaintOut(BaseModel):
    id: int
    description: str
    complaint_date: datetime

    class Config:
        from_attributes = True


class RatingOut(BaseModel):
    id: int
    rating_value: int
    comment: Optional[str] = None
    rating_date: datetime

    class Config:
        from_attributes = True


class PaymentOut(BaseModel):
    id: int
    amount: float
    tip_amount: float
    payment_method: str
    payment_time: datetime
    status: str
    transaction_reference: str

    class Config:
        from_attributes = True


class OrderOut(BaseModel):
    id: int
    table_number: int
    status: OrderStatus
    order_time: datetime
    estimated_waiting_time_minutes: int
    total_amount: float
    customer: CustomerOut
    waiter: Optional[WaiterOut] = None
    items: List[OrderItemOut]
    preparations: List[PreparationOut]
    complaint: Optional[ComplaintOut] = None
    rating: Optional[RatingOut] = None
    payment: Optional[PaymentOut] = None

    class Config:
        from_attributes = True


class AssignWaiter(BaseModel):
    waiter_id: int


class AssignPreparer(BaseModel):
    chef_id: Optional[int] = None
    bartender_id: Optional[int] = None


class PayRequest(BaseModel):
    tip_amount: float = Field(default=0.0, ge=0)


class ComplaintCreate(BaseModel):
    description: str


class RatingCreate(BaseModel):
    rating_value: int = Field(ge=1, le=5)
    comment: Optional[str] = None
