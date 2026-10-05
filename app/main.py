import io
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import qrcode
from fastapi import Body, FastAPI, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse, HTMLResponse, PlainTextResponse
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from . import imports, migrate, models, schemas
from .database import get_db

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Chowly")

# Additive, re-runnable schema upgrade + reference data (see app/migrate.py).
migrate.run()

STATIC_DIR = Path(__file__).parent / "static"
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def get_location(db: Session, location_code: Optional[str]) -> models.Restaurant:
    code = (location_code or "LEK").strip().upper()
    loc = db.query(models.Restaurant).filter(models.Restaurant.location_code == code).first()
    if not loc:
        raise HTTPException(400, f"Unknown location '{code}'")
    return loc


def get_menu_row(db: Session) -> models.Menu:
    # One group menu, shared by every location (see app/seed.py).
    menu = db.query(models.Menu).order_by(models.Menu.id).first()
    if not menu:
        raise HTTPException(500, "Menu has not been seeded")
    return menu


def order_query(db: Session):
    return db.query(models.Order).options(
        joinedload(models.Order.restaurant),
        joinedload(models.Order.customer),
        joinedload(models.Order.waiter),
        joinedload(models.Order.items).joinedload(models.OrderItem.menu_item),
        joinedload(models.Order.preparations).joinedload(models.OrderPreparation.menu_item),
        joinedload(models.Order.preparations).joinedload(models.OrderPreparation.chef),
        joinedload(models.Order.preparations).joinedload(models.OrderPreparation.bartender),
        joinedload(models.Order.complaint).joinedload(models.Complaint.menu_item),
        joinedload(models.Order.rating),
        joinedload(models.Order.payment).joinedload(models.Payment.corrections),
        joinedload(models.Order.status_events),
    )


def fetch_order(db: Session, order_id: int):
    return order_query(db).filter(models.Order.id == order_id).first()


def change_status(db: Session, order: models.Order, to_status: models.OrderStatus,
                  actor_role: str, actor_id: Optional[int] = None, note: Optional[str] = None):
    """The only way an order's status changes: update the current value AND
    append the change to order_status_events, with a timestamp and who."""
    from_status = order.status.value if order.status else None
    order.status = to_status
    db.add(models.OrderStatusEvent(
        order_id=order.id, from_status=from_status, to_status=to_status.value,
        actor_role=actor_role, actor_id=actor_id, note=note,
    ))


def waiter_label(db: Session, waiter_id: Optional[int]) -> Optional[str]:
    if not waiter_id:
        return None
    w = db.get(models.Waiter, waiter_id)
    return f"waiter #{w.id} {w.first_name} {w.last_name}" if w else None


# ---------------------------------------------------------------------------
# Reference data: locations, menu, staff, vocabularies
# ---------------------------------------------------------------------------
@app.get("/api/locations", response_model=list[schemas.LocationOut])
def list_locations(db: Session = Depends(get_db)):
    return db.query(models.Restaurant).filter(models.Restaurant.location_code.isnot(None)) \
        .order_by(models.Restaurant.id).all()


@app.get("/api/vocab")
def vocab():
    """Fixed choice lists, so the UI and reports use the same codes."""
    return {
        "complaint_categories": schemas.COMPLAINT_CATEGORIES,
        "cancel_reasons": schemas.CANCEL_REASONS,
        "payment_methods": schemas.PAYMENT_METHODS,
    }


@app.get("/api/menu", response_model=list[schemas.MenuItemOut])
def get_menu(include_discontinued: bool = False, db: Session = Depends(get_db)):
    q = db.query(models.MenuItem).filter(models.MenuItem.menu_id == get_menu_row(db).id)
    if not include_discontinued:
        q = q.filter(models.MenuItem.availability_status != models.AvailabilityStatus.discontinued.value)
    return q.order_by(models.MenuItem.id).all()


@app.post("/api/menu/{item_id}/toggle-availability", response_model=schemas.MenuItemOut)
def toggle_availability(item_id: int, changed_by: Optional[str] = Body(None, embed=True), db: Session = Depends(get_db)):
    """86 / un-86 a menu item, and log it as a menu event."""
    item = db.get(models.MenuItem, item_id)
    if not item:
        raise HTTPException(404, "Menu item not found")
    if item.availability_status == models.AvailabilityStatus.discontinued.value:
        raise HTTPException(400, "This item has been discontinued")
    old = item.availability_status
    item.availability_status = (
        models.AvailabilityStatus.sold_out.value
        if old == models.AvailabilityStatus.available.value
        else models.AvailabilityStatus.available.value
    )
    db.add(models.MenuItemEvent(menu_item_id=item.id, event_type="availability_changed",
                                old_value=old, new_value=item.availability_status, changed_by=changed_by))
    db.commit()
    db.refresh(item)
    return item


@app.patch("/api/menu/{item_id}", response_model=schemas.MenuItemOut)
def update_menu_item(item_id: int, payload: schemas.MenuItemUpdate, db: Session = Depends(get_db)):
    """Change a price or a name. The live row is updated, and the old and new
    values go into menu_item_events, so the past is never lost (TE-2, TE-7).
    Orders already placed keep the price they were sold at (OrderItem.unit_price)."""
    item = db.get(models.MenuItem, item_id)
    if not item:
        raise HTTPException(404, "Menu item not found")
    changed = False
    if payload.price is not None and payload.price != item.price:
        db.add(models.MenuItemEvent(menu_item_id=item.id, event_type="price_changed",
                                    old_value=f"{item.price:g}", new_value=f"{payload.price:g}",
                                    changed_by=payload.changed_by))
        item.price = payload.price
        changed = True
    new_name = payload.item_name.strip() if payload.item_name else None
    if new_name and new_name != item.item_name:
        db.add(models.MenuItemEvent(menu_item_id=item.id, event_type="renamed",
                                    old_value=item.item_name, new_value=new_name, changed_by=payload.changed_by))
        item.item_name = new_name
        changed = True
    if not changed:
        raise HTTPException(400, "Nothing to change")
    db.commit()
    db.refresh(item)
    return item


@app.post("/api/menu/{item_id}/discontinue", response_model=schemas.MenuItemOut)
def discontinue_menu_item(item_id: int, changed_by: str = Body(..., embed=True), db: Session = Depends(get_db)):
    """Retire a dish. It is never deleted, so its past sales stay linked to it (TE-7)."""
    item = db.get(models.MenuItem, item_id)
    if not item:
        raise HTTPException(404, "Menu item not found")
    if item.availability_status == models.AvailabilityStatus.discontinued.value:
        raise HTTPException(400, "Already discontinued")
    db.add(models.MenuItemEvent(menu_item_id=item.id, event_type="discontinued",
                                old_value=item.availability_status,
                                new_value=models.AvailabilityStatus.discontinued.value, changed_by=changed_by))
    item.availability_status = models.AvailabilityStatus.discontinued.value
    db.commit()
    db.refresh(item)
    return item


@app.get("/api/menu/events", response_model=list[schemas.MenuItemEventOut])
def menu_events(limit: int = 30, db: Session = Depends(get_db)):
    return db.query(models.MenuItemEvent).order_by(models.MenuItemEvent.id.desc()).limit(min(limit, 200)).all()


@app.get("/api/staff")
def get_staff(location_code: Optional[str] = None, db: Session = Depends(get_db)):
    loc = get_location(db, location_code)
    waiters = db.query(models.Waiter).filter(models.Waiter.restaurant_id == loc.id).all()
    chefs = db.query(models.Chef).filter(models.Chef.restaurant_id == loc.id).all()
    bartenders = db.query(models.Bartender).filter(models.Bartender.restaurant_id == loc.id).all()
    return {
        "waiters": [schemas.WaiterOut.model_validate(w) for w in waiters],
        "chefs": [schemas.ChefOut.model_validate(c) for c in chefs],
        "bartenders": [schemas.BartenderOut.model_validate(b) for b in bartenders],
    }


@app.get("/api/stats/today")
def stats_today(location_code: Optional[str] = None, db: Session = Depends(get_db)):
    """A small snapshot for the waiter dashboard, for one location."""
    loc = get_location(db, location_code)
    today = date.today()
    in_scope = (models.Order.order_date == today, models.Order.restaurant_id == loc.id)

    revenue_today = (
        db.query(func.coalesce(func.sum(models.Payment.amount), 0.0))
        .join(models.Order, models.Payment.order_id == models.Order.id)
        .filter(*in_scope)
        .scalar()
    )
    orders_today = (
        db.query(func.count(models.Order.id))
        .filter(*in_scope, models.Order.status != models.OrderStatus.cancelled)
        .scalar()
    )
    top_item_row = (
        db.query(models.MenuItem.item_name, func.sum(models.OrderItem.quantity).label("qty"))
        .join(models.OrderItem, models.OrderItem.menu_item_id == models.MenuItem.id)
        .join(models.Order, models.OrderItem.order_id == models.Order.id)
        .filter(*in_scope, models.Order.status != models.OrderStatus.cancelled)
        .group_by(models.MenuItem.item_name)
        .order_by(func.sum(models.OrderItem.quantity).desc())
        .first()
    )
    avg_rating = (
        db.query(func.avg(models.Rating.rating_value))
        .join(models.Order, models.Rating.order_id == models.Order.id)
        .filter(*in_scope)
        .scalar()
    )
    return {
        "location_code": loc.location_code,
        "revenue_today": float(revenue_today or 0),
        "orders_today": orders_today or 0,
        "top_item": top_item_row[0] if top_item_row else None,
        "top_item_quantity": int(top_item_row[1]) if top_item_row else 0,
        "average_rating": round(float(avg_rating), 1) if avg_rating is not None else None,
    }


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------
@app.get("/api/orders", response_model=list[schemas.OrderOut])
def list_orders(location_code: Optional[str] = None, db: Session = Depends(get_db)):
    q = order_query(db)
    if location_code:
        q = q.filter(models.Order.restaurant_id == get_location(db, location_code).id)
    return q.order_by(models.Order.id.desc()).all()


@app.get("/api/orders/{order_id}", response_model=schemas.OrderOut)
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = fetch_order(db, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    return order


@app.post("/api/orders", response_model=schemas.OrderOut)
def create_order(payload: schemas.OrderCreate, db: Session = Depends(get_db)):
    if not payload.items:
        raise HTTPException(400, "An order needs at least one item")

    location = get_location(db, payload.location_code)

    # Phone is optional. When given it's already in +234 format (see
    # schemas.CustomerIn), so a returning customer is recognised however
    # they typed it. If that record was merged, use the surviving customer.
    customer = None
    if payload.customer.phone_number:
        customer = db.query(models.Customer).filter(
            models.Customer.phone_number == payload.customer.phone_number
        ).first()
        while customer and customer.merged_into_customer_id:
            customer = db.get(models.Customer, customer.merged_into_customer_id)
    if not customer:
        customer = models.Customer(**payload.customer.model_dump())
        db.add(customer)
        db.flush()

    menu_ids = [i.menu_item_id for i in payload.items]
    menu_items = {
        m.id: m for m in db.query(models.MenuItem).filter(models.MenuItem.id.in_(menu_ids)).all()
    }
    if len(menu_items) != len(set(menu_ids)):
        raise HTTPException(400, "One or more menu items don't exist")
    unavailable = [m.item_name for m in menu_items.values()
                   if m.availability_status != models.AvailabilityStatus.available.value]
    if unavailable:
        raise HTTPException(400, f"Not available right now: {', '.join(unavailable)}")

    order = models.Order(
        customer_id=customer.id,
        restaurant_id=location.id,
        table_number=payload.table_number,
        status=models.OrderStatus.placed,
        channel="dine_in",
        promised_wait_minutes=max(m.prep_time_minutes for m in menu_items.values()),
    )
    db.add(order)
    db.flush()
    db.add(models.OrderStatusEvent(order_id=order.id, from_status=None, to_status="placed",
                                   actor_role="customer", actor_id=customer.id))

    for item in payload.items:
        menu_item = menu_items[item.menu_item_id]
        order_item = models.OrderItem(
            order_id=order.id,
            menu_item_id=menu_item.id,
            quantity=item.quantity,
            unit_price=menu_item.price,   # price frozen at order time
        )
        db.add(order_item)
        db.flush()
        db.add(models.OrderPreparation(
            order_id=order.id,
            order_item_id=order_item.id,
            menu_item_id=menu_item.id,
        ))

    db.commit()
    return fetch_order(db, order.id)


@app.post("/api/orders/{order_id}/assign", response_model=schemas.OrderOut)
def assign_waiter(order_id: int, payload: schemas.AssignWaiter, db: Session = Depends(get_db)):
    order = db.get(models.Order, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    if order.status != models.OrderStatus.placed:
        raise HTTPException(400, "Only a newly placed order can be picked up")

    waiter = db.get(models.Waiter, payload.waiter_id)
    if not waiter:
        raise HTTPException(400, "waiter_id does not reference a known waiter")
    if waiter.restaurant_id != order.restaurant_id:
        raise HTTPException(400, "That waiter works at a different location")

    order.waiter_id = waiter.id
    change_status(db, order, models.OrderStatus.assigned, "waiter", waiter.id)
    db.commit()
    return fetch_order(db, order_id)


@app.post("/api/orders/{order_id}/items/{order_item_id}/prepare", response_model=schemas.OrderOut)
def record_preparation(order_id: int, order_item_id: int, payload: schemas.AssignPreparer, db: Session = Depends(get_db)):
    prep = db.query(models.OrderPreparation).filter(
        models.OrderPreparation.order_id == order_id,
        models.OrderPreparation.order_item_id == order_item_id,
    ).first()
    if not prep:
        raise HTTPException(404, "Preparation record not found for this item")

    if prep.menu_item.item_type == models.ItemType.food:
        if not payload.chef_id:
            raise HTTPException(400, "This is a food item — chef_id is required")
        chef = db.get(models.Chef, payload.chef_id)
        if not chef:
            raise HTTPException(400, "chef_id does not reference a known chef")
        prep.chef_id = chef.id
    else:
        if not payload.bartender_id:
            raise HTTPException(400, "This is a drink item — bartender_id is required")
        bartender = db.get(models.Bartender, payload.bartender_id)
        if not bartender:
            raise HTTPException(400, "bartender_id does not reference a known bartender")
        prep.bartender_id = bartender.id

    prep.status = models.PreparationStatus.completed
    prep.preparation_end_time = datetime.utcnow()
    db.commit()
    return fetch_order(db, order_id)


@app.post("/api/orders/{order_id}/serve", response_model=schemas.OrderOut)
def mark_served(order_id: int, db: Session = Depends(get_db)):
    order = db.get(models.Order, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    if order.status != models.OrderStatus.assigned:
        raise HTTPException(400, "Order must be assigned to a waiter before it can be marked served")

    unprepared = [p for p in order.preparations if p.status != models.PreparationStatus.completed]
    if unprepared:
        raise HTTPException(400, "Every item needs a chef or bartender recorded before serving")

    order.actual_completion_time = datetime.utcnow()
    change_status(db, order, models.OrderStatus.served, "waiter", order.waiter_id)
    db.commit()
    return fetch_order(db, order_id)


@app.post("/api/orders/{order_id}/cancel", response_model=schemas.OrderOut)
def cancel_order(order_id: int, payload: Optional[schemas.CancelOrder] = None, db: Session = Depends(get_db)):
    """A customer can cancel while the order is still just sitting in the
    queue. The reason and time are recorded (BRD: "cancellations and reasons")."""
    order = db.get(models.Order, order_id)
    if not order:
        raise HTTPException(404, "Order not found")

    prep_started = any(p.status == models.PreparationStatus.completed for p in order.preparations)
    cancellable = order.status == models.OrderStatus.placed or (
        order.status == models.OrderStatus.assigned and not prep_started
    )
    if not cancellable:
        raise HTTPException(400, "This order can no longer be cancelled — preparation has already started")

    reason = (payload or schemas.CancelOrder()).reason
    order.cancellation_reason = reason
    order.cancelled_at = datetime.utcnow()
    change_status(db, order, models.OrderStatus.cancelled, "customer", order.customer_id, note=reason)
    db.commit()
    return fetch_order(db, order_id)


@app.post("/api/orders/{order_id}/pay", response_model=schemas.OrderOut)
def pay_order(order_id: int, payload: schemas.PayOrder, db: Session = Depends(get_db)):
    order = db.get(models.Order, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    if order.payment:
        raise HTTPException(400, "Order is already paid")
    if order.status != models.OrderStatus.served:
        raise HTTPException(400, "Only a served order can be paid")
    if payload.waiter_id and not db.get(models.Waiter, payload.waiter_id):
        raise HTTPException(400, "waiter_id does not reference a known waiter")

    db.add(models.Payment(
        order_id=order.id,
        customer_id=order.customer_id,
        amount=order.total_amount,
        payment_method=payload.payment_method,
        recorded_by_waiter_id=payload.waiter_id,
    ))
    actor = ("waiter", payload.waiter_id) if payload.waiter_id else ("customer", order.customer_id)
    change_status(db, order, models.OrderStatus.paid, *actor, note=payload.payment_method)
    db.commit()
    return fetch_order(db, order_id)


@app.post("/api/orders/{order_id}/payment-corrections", response_model=schemas.OrderOut)
def add_payment_correction(order_id: int, payload: schemas.PaymentCorrectionCreate, db: Session = Depends(get_db)):
    """Refunds and fixes are new rows; the original payment is never edited."""
    order = fetch_order(db, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    if not order.payment:
        raise HTTPException(400, "This order has no payment to correct")
    net = order.payment.amount + sum(c.amount for c in order.payment.corrections) + payload.amount
    if net < 0:
        raise HTTPException(400, "That would refund more than the customer paid")
    db.add(models.PaymentCorrection(payment_id=order.payment.id, order_id=order.id, amount=payload.amount,
                                    reason=payload.reason, recorded_by=payload.recorded_by))
    db.commit()
    db.expire_all()
    return fetch_order(db, order_id)


@app.get("/api/payment-corrections")
def list_payment_corrections(limit: int = 20, db: Session = Depends(get_db)):
    rows = db.query(models.PaymentCorrection).order_by(models.PaymentCorrection.id.desc()).limit(min(limit, 200)).all()
    return [{"id": c.id, "order_id": c.order_id, "amount": c.amount, "reason": c.reason,
             "created_at": c.created_at, "recorded_by": c.recorded_by} for c in rows]


@app.post("/api/orders/{order_id}/complaint", response_model=schemas.OrderOut)
def submit_complaint(order_id: int, payload: schemas.ComplaintCreate, db: Session = Depends(get_db)):
    order = db.get(models.Order, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    if order.complaint:
        raise HTTPException(400, "This order already has a complaint on file")
    if payload.menu_item_id and payload.menu_item_id not in {i.menu_item_id for i in order.items}:
        raise HTTPException(400, "That dish isn't on this order")

    db.add(models.Complaint(
        order_id=order.id,
        customer_id=order.customer_id,
        description=payload.description,
        category=payload.category,
        menu_item_id=payload.menu_item_id,
    ))
    db.commit()
    return fetch_order(db, order_id)


@app.get("/api/complaints")
def list_complaints(status: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(models.Complaint).options(joinedload(models.Complaint.menu_item),
                                           joinedload(models.Complaint.order).joinedload(models.Order.restaurant))
    if status:
        q = q.filter(models.Complaint.status == models.ComplaintStatus(status))
    out = []
    for c in q.order_by(models.Complaint.id.desc()).all():
        out.append({
            "id": c.id, "order_id": c.order_id, "description": c.description,
            "category": c.category, "dish": c.menu_item.item_name if c.menu_item else None,
            "location_code": c.order.location_code if c.order else None,
            "complaint_date": c.complaint_date, "status": c.status.value,
            "resolved_at": c.resolved_at, "resolution_note": c.resolution_note,
        })
    return out


@app.post("/api/complaints/{complaint_id}/resolve")
def resolve_complaint(complaint_id: int, payload: schemas.ComplaintResolve, db: Session = Depends(get_db)):
    """Recording when and how a complaint was closed makes "root cause within
    48 hours" (BO-5) measurable."""
    c = db.get(models.Complaint, complaint_id)
    if not c:
        raise HTTPException(404, "Complaint not found")
    if c.status == models.ComplaintStatus.resolved:
        raise HTTPException(400, "Already resolved")
    c.status = models.ComplaintStatus.resolved
    c.resolved_at = datetime.utcnow()
    note = payload.resolution_note.strip()
    c.resolution_note = f"{note} (by {payload.resolved_by})" if payload.resolved_by else note
    db.commit()
    return {"id": c.id, "status": c.status.value, "resolved_at": c.resolved_at}


@app.post("/api/orders/{order_id}/rating", response_model=schemas.OrderOut)
def submit_rating(order_id: int, payload: schemas.RatingCreate, db: Session = Depends(get_db)):
    order = db.get(models.Order, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    if order.rating:
        raise HTTPException(400, "This order already has a rating on file")

    db.add(models.Rating(
        order_id=order.id,
        customer_id=order.customer_id,
        rating_value=payload.rating_value,
        comment=payload.comment,
    ))
    db.commit()
    return fetch_order(db, order_id)


# ---------------------------------------------------------------------------
# Partner data imports (see app/imports.py)
# ---------------------------------------------------------------------------
@app.get("/api/imports/sources")
def import_sources():
    return [{"key": s.key, "label": s.label, "owner": s.owner, "columns": s.columns, "required": s.required}
            for s in imports.SOURCES.values()]


@app.get("/api/imports/templates/{source_key}.csv", response_class=PlainTextResponse)
def import_template(source_key: str):
    if source_key not in imports.SOURCES:
        raise HTTPException(404, "Unknown source")
    return PlainTextResponse(imports.template_csv(source_key), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{source_key}_template.csv"'})


@app.post("/api/imports/{source_key}", response_model=schemas.ImportBatchOut)
async def upload_partner_file(source_key: str, file: UploadFile = File(...),
                              uploaded_by: str = Form(...), db: Session = Depends(get_db)):
    if source_key not in imports.SOURCES:
        raise HTTPException(404, "Unknown source")
    name = file.filename or "upload"
    if not name.lower().endswith((".csv", ".xlsx")):
        raise HTTPException(400, "Upload a .csv or .xlsx file")
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "File is larger than 5 MB")
    try:
        return imports.run_import(db, source_key, name, content, uploaded_by.strip() or None)
    except imports.DuplicateFile as dup:
        b = dup.batch
        raise HTTPException(409, f"This exact file was already imported as batch #{b.id} on "
                                 f"{b.uploaded_at:%Y-%m-%d %H:%M}. Nothing was loaded twice.")


@app.get("/api/imports", response_model=list[schemas.ImportBatchOut])
def list_imports(limit: int = 30, db: Session = Depends(get_db)):
    return db.query(models.ImportBatch).order_by(models.ImportBatch.id.desc()).limit(min(limit, 200)).all()


@app.get("/api/imports/{batch_id}", response_model=schemas.ImportBatchDetail)
def get_import(batch_id: int, db: Session = Depends(get_db)):
    b = db.query(models.ImportBatch).options(joinedload(models.ImportBatch.rejections)).get(batch_id)
    if not b:
        raise HTTPException(404, "Import not found")
    return b


# ---------------------------------------------------------------------------
# Table QR codes — not part of the assignment's requirements; generated on
# request rather than stored, and just encode a link back to this same app
# with the table number pre-filled.
# ---------------------------------------------------------------------------
@app.get("/api/qr/{table_number}")
def table_qr(table_number: int, request: Request, location_code: str = "LEK"):
    base = str(request.base_url).rstrip("/")
    url = f"{base}/?location={location_code}&table={table_number}"

    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1A1512", back_color="#F8EFDC")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")


@app.get("/qr", response_class=HTMLResponse)
def qr_sheet(request: Request, count: int = 12, location_code: str = "LEK", db: Session = Depends(get_db)):
    base = str(request.base_url).rstrip("/")
    loc = get_location(db, location_code)
    code = loc.location_code
    cards = "".join(
        f'<div class="qr-card"><div class="qr-card-accent"></div>'
        f'<img src="{base}/api/qr/{n}?location_code={code}" alt="Table {n} QR code">'
        f'<div class="qr-label">{loc.name} &middot; Table {n}</div></div>'
        for n in range(1, count + 1)
    )
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Chowly — Table QR Codes</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,600;0,9..144,700;1,9..144,500&family=Sora:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {{
    --ivory: #F8EFDC;
    --slate: #1A1512;
    --slate-soft: #5C4E40;
    --marigold: #EB8A1E;
    --marigold-deep: #A85712;
    --teal: #1E7A6E;
    --line: rgba(26, 21, 18, 0.14);
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: "Sora", -apple-system, BlinkMacSystemFont, sans-serif;
    background: var(--ivory);
    margin: 0;
    padding: 0;
    color: var(--slate);
    position: relative;
    min-height: 100vh;
  }}
  body::before {{
    content: "";
    position: fixed;
    inset: 0;
    z-index: 0;
    background-image: linear-gradient(175deg, rgba(248,239,220,0.55) 0%, rgba(248,239,220,0.75) 100%), url("/static/images/bg/waiter.jpg");
    background-size: cover;
    background-position: center 30%;
  }}
  .scene-glow {{
    position: fixed;
    top: -140px; left: -100px;
    width: 420px; height: 420px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(235,138,30,0.35), transparent 70%);
    filter: blur(70px);
    z-index: 0;
  }}
  .page {{ position: relative; z-index: 1; max-width: 1100px; margin: 0 auto; padding: 40px 36px 60px; }}
  .header-panel {{
    background: rgba(255, 252, 245, 0.82);
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    border: 1px solid rgba(255,255,255,0.6);
    border-radius: 16px;
    padding: 26px 30px;
    margin-bottom: 30px;
    box-shadow: 0 6px 16px rgba(26,21,18,0.09);
  }}
  .brand-row {{ display: flex; align-items: center; gap: 12px; margin-bottom: 4px; }}
  h1 {{
    font-family: "Fraunces", Georgia, serif;
    font-weight: 700;
    font-size: 30px;
    margin: 0;
    letter-spacing: -0.01em;
  }}
  p {{ color: var(--slate-soft); margin: 6px 0 0; font-size: 15px; }}
  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
    gap: 20px;
  }}
  .qr-card {{
    background: white;
    border: 1px solid var(--line);
    border-radius: 4px;
    overflow: hidden;
    text-align: center;
    box-shadow: 0 6px 16px rgba(26,21,18,0.10);
    transition: transform 0.15s ease;
  }}
  .qr-card-accent {{ height: 5px; background: linear-gradient(90deg, var(--marigold), var(--teal)); }}
  .qr-card img {{ width: 78%; height: auto; display: block; margin: 18px auto 8px; }}
  .qr-label {{
    font-family: "Fraunces", Georgia, serif;
    font-weight: 600;
    font-size: 19px;
    padding: 6px 0 18px;
  }}
  @media print {{
    body::before, .scene-glow {{ display: none; }}
    body {{ background: white; }}
    .header-panel {{ background: white; box-shadow: none; border: none; backdrop-filter: none; }}
    .qr-card {{ box-shadow: none; border: 1px solid #ccc; break-inside: avoid; }}
    p {{ display: none; }}
  }}
</style></head>
<body>
  <div class="scene-glow"></div>
  <div class="page">
    <div class="header-panel">
      <div class="brand-row">
        <svg width="30" height="30" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
          <circle cx="16" cy="20" r="10" fill="#F6F0E4" stroke="#1A1512" stroke-width="1.8"/>
          <path d="M10.5 11c0 1.9 1.4 2.5 1.4 4.4 0 1.1-.7 1.7-.7 1.7" stroke="#EB8A1E" stroke-width="2.1" stroke-linecap="round"/>
          <path d="M16 9c0 2.1 1.5 2.8 1.5 5 0 1.2-.8 1.9-.8 1.9" stroke="#EB8A1E" stroke-width="2.1" stroke-linecap="round"/>
          <path d="M21.5 11c0 1.9-1.4 2.5-1.4 4.4 0 1.1.7 1.7.7 1.7" stroke="#EB8A1E" stroke-width="2.1" stroke-linecap="round"/>
        </svg>
        <h1>Chowly &mdash; Table QR Codes</h1>
      </div>
      <p>Print this page and place one card per table. Scanning a code opens the ordering page with that table already filled in.</p>
    </div>
    <div class="grid">{cards}</div>
  </div>
</body></html>"""


# ---------------------------------------------------------------------------
# Frontend (single-page app, vanilla HTML/CSS/JS served from the same origin)
# ---------------------------------------------------------------------------
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def serve_index():
    return FileResponse(STATIC_DIR / "index.html")