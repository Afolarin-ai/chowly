from datetime import datetime, date
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from .models import ItemType, OrderStatus, PreparationStatus
from .phone import InvalidPhone, normalise_ng_phone


# ---------- Controlled vocabularies (BRD: categories, reasons, methods) ----------
# A fixed list instead of free text, so these can be counted and compared.
COMPLAINT_CATEGORIES = {
    "food_quality": "Food quality",
    "food_safety": "Food safety / felt unwell",
    "wrong_item": "Wrong or missing item",
    "slow_service": "Slow service",
    "staff_behaviour": "Staff behaviour",
    "billing": "Billing / payment",
    "other": "Other",
}
CANCEL_REASONS = {
    "changed_mind": "Changed my mind",
    "waited_too_long": "Waiting too long",
    "ordered_by_mistake": "Ordered by mistake",
    "item_unavailable": "Item not available",
    "other": "Other",
}
PAYMENT_METHODS = {
    "cash": "Cash",
    "card": "Card",
    "bank_transfer": "Bank transfer",
}

ComplaintCategory = Literal["food_quality", "food_safety", "wrong_item", "slow_service", "staff_behaviour", "billing", "other"]
CancelReason = Literal["changed_mind", "waited_too_long", "ordered_by_mistake", "item_unavailable", "other"]
PaymentMethod = Literal["cash", "card", "bank_transfer"]


# ---------- Locations ----------
class LocationOut(BaseModel):
    id: int
    location_code: str
    name: str
    address: Optional[str] = None

    class Config:
        from_attributes = True


# ---------- Menu ----------
class MenuItemOut(BaseModel):
    id: int
    item_code: Optional[str] = None
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

    @field_validator("phone_number")
    @classmethod
    def phone_in_one_format(cls, v):
        if v is None or not v.strip():
            return None
        try:
            return normalise_ng_phone(v)
        except InvalidPhone as e:
            raise ValueError(str(e))


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
    # Older clients didn't send a location; they were all at Lekki.
    location_code: str = "LEK"


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


class StatusEventOut(BaseModel):
    from_status: Optional[str] = None
    to_status: str
    changed_at: datetime
    actor_role: Optional[str] = None
    actor_id: Optional[int] = None
    note: Optional[str] = None
    is_backfilled: bool

    class Config:
        from_attributes = True


class ComplaintOut(BaseModel):
    id: int
    description: str
    complaint_date: datetime
    category: Optional[str] = None
    menu_item: Optional[MenuItemOut] = None
    status: str
    resolved_at: Optional[datetime] = None
    resolution_note: Optional[str] = None

    class Config:
        from_attributes = True


class RatingOut(BaseModel):
    id: int
    rating_value: int
    comment: Optional[str] = None
    rating_date: datetime

    class Config:
        from_attributes = True


class PaymentCorrectionOut(BaseModel):
    id: int
    amount: float
    reason: str
    created_at: datetime
    recorded_by: Optional[str] = None

    class Config:
        from_attributes = True


class PaymentOut(BaseModel):
    id: int
    amount: float
    payment_method: str
    payment_time: datetime
    status: str
    transaction_reference: str
    recorded_by_waiter_id: Optional[int] = None
    corrections: List[PaymentCorrectionOut] = []

    class Config:
        from_attributes = True


class OrderOut(BaseModel):
    id: int
    location_code: Optional[str] = None
    channel: Optional[str] = None
    table_number: int
    status: OrderStatus
    order_time: datetime
    cancellation_reason: Optional[str] = None
    cancelled_at: Optional[datetime] = None
    status_events: List[StatusEventOut] = []
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


class ComplaintCreate(BaseModel):
    description: str = Field(min_length=1)
    category: ComplaintCategory
    menu_item_id: Optional[int] = None


class ComplaintResolve(BaseModel):
    resolution_note: str = Field(min_length=1)
    resolved_by: Optional[str] = None


class CancelOrder(BaseModel):
    reason: CancelReason = "other"


class PayOrder(BaseModel):
    payment_method: PaymentMethod
    waiter_id: Optional[int] = None   # set when a waiter records it, empty when the customer pays


class PaymentCorrectionCreate(BaseModel):
    amount: float                      # negative = refund to the customer
    reason: str = Field(min_length=3)
    recorded_by: str = Field(min_length=1)

    @field_validator("amount")
    @classmethod
    def not_zero(cls, v):
        if v == 0:
            raise ValueError("A correction can't be zero")
        return v


class MenuItemUpdate(BaseModel):
    item_name: Optional[str] = Field(default=None, min_length=2)
    price: Optional[float] = Field(default=None, gt=0)
    changed_by: str = Field(min_length=1)


class MenuItemEventOut(BaseModel):
    id: int
    menu_item_id: int
    event_type: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    changed_at: datetime
    changed_by: Optional[str] = None
    is_backfilled: bool

    class Config:
        from_attributes = True


class ImportRejectionOut(BaseModel):
    row_number: int
    raw_row: str
    errors: str

    class Config:
        from_attributes = True


class ImportBatchOut(BaseModel):
    id: int
    source: str
    filename: str
    uploaded_at: datetime
    uploaded_by: Optional[str] = None
    status: str
    rows_total: int
    rows_loaded: int
    rows_duplicate: int
    rows_rejected: int
    error: Optional[str] = None

    class Config:
        from_attributes = True


class ImportBatchDetail(ImportBatchOut):
    rejections: List[ImportRejectionOut] = []


class RatingCreate(BaseModel):
    rating_value: int = Field(ge=1, le=5)
    comment: Optional[str] = None
