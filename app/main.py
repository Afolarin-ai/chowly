import io
from datetime import datetime, date
from pathlib import Path

import qrcode
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse, HTMLResponse
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from . import models, schemas
from .database import get_db, engine, Base
from .seed import seed

app = FastAPI(title="Chowly")

Base.metadata.create_all(bind=engine)
seed()

STATIC_DIR = Path(__file__).parent / "static"


def get_restaurant(db: Session) -> models.Restaurant:
    # This build serves a single restaurant, seeded once at startup.
    restaurant = db.query(models.Restaurant).first()
    if not restaurant:
        raise HTTPException(500, "Restaurant has not been seeded")
    return restaurant


def order_query(db: Session):
    return db.query(models.Order).options(
        joinedload(models.Order.customer),
        joinedload(models.Order.waiter),
        joinedload(models.Order.items).joinedload(models.OrderItem.menu_item),
        joinedload(models.Order.preparations).joinedload(models.OrderPreparation.menu_item),
        joinedload(models.Order.preparations).joinedload(models.OrderPreparation.chef),
        joinedload(models.Order.preparations).joinedload(models.OrderPreparation.bartender),
        joinedload(models.Order.complaint),
        joinedload(models.Order.rating),
        joinedload(models.Order.payment),
    )


# ---------------------------------------------------------------------------
# Menu & staff (reference data, loaded once at seed time)
# ---------------------------------------------------------------------------
@app.get("/api/menu", response_model=list[schemas.MenuItemOut])
def get_menu(db: Session = Depends(get_db)):
    restaurant = get_restaurant(db)
    menu = db.query(models.Menu).filter(models.Menu.restaurant_id == restaurant.id).first()
    return menu.items if menu else []


@app.post("/api/menu/{item_id}/toggle-availability", response_model=schemas.MenuItemOut)
def toggle_availability(item_id: int, db: Session = Depends(get_db)):
    """86 / un-86 a menu item. A waiter-facing action — customers only ever
    see the resulting list, they don't call this directly."""
    item = db.query(models.MenuItem).get(item_id)
    if not item:
        raise HTTPException(404, "Menu item not found")
    item.availability_status = (
        models.AvailabilityStatus.sold_out
        if item.availability_status == models.AvailabilityStatus.available
        else models.AvailabilityStatus.available
    )
    db.commit()
    db.refresh(item)
    return item


@app.get("/api/staff")
def get_staff(db: Session = Depends(get_db)):
    restaurant = get_restaurant(db)
    waiters = db.query(models.Waiter).filter(models.Waiter.restaurant_id == restaurant.id).all()
    chefs = db.query(models.Chef).filter(models.Chef.restaurant_id == restaurant.id).all()
    bartenders = db.query(models.Bartender).filter(models.Bartender.restaurant_id == restaurant.id).all()
    return {
        "waiters": [schemas.WaiterOut.model_validate(w) for w in waiters],
        "chefs": [schemas.ChefOut.model_validate(c) for c in chefs],
        "bartenders": [schemas.BartenderOut.model_validate(b) for b in bartenders],
    }


@app.get("/api/stats/today")
def stats_today(db: Session = Depends(get_db)):
    """A small end-of-day snapshot for the waiter dashboard — revenue,
    order count, top-selling item, and average rating, all scoped to
    today. This isn't part of the assignment's requirements; it's built
    on data the app already has, purely as a bonus."""
    today = date.today()

    revenue_today = (
        db.query(func.coalesce(func.sum(models.Payment.amount), 0.0))
        .join(models.Order, models.Payment.order_id == models.Order.id)
        .filter(models.Order.order_date == today)
        .scalar()
    )

    orders_today = (
        db.query(func.count(models.Order.id))
        .filter(models.Order.order_date == today, models.Order.status != models.OrderStatus.cancelled)
        .scalar()
    )

    top_item_row = (
        db.query(models.MenuItem.item_name, func.sum(models.OrderItem.quantity).label("qty"))
        .join(models.OrderItem, models.OrderItem.menu_item_id == models.MenuItem.id)
        .join(models.Order, models.OrderItem.order_id == models.Order.id)
        .filter(models.Order.order_date == today, models.Order.status != models.OrderStatus.cancelled)
        .group_by(models.MenuItem.item_name)
        .order_by(func.sum(models.OrderItem.quantity).desc())
        .first()
    )

    avg_rating = (
        db.query(func.avg(models.Rating.rating_value))
        .join(models.Order, models.Rating.order_id == models.Order.id)
        .filter(models.Order.order_date == today)
        .scalar()
    )

    tips_today = (
        db.query(func.coalesce(func.sum(models.Payment.tip_amount), 0.0))
        .join(models.Order, models.Payment.order_id == models.Order.id)
        .filter(models.Order.order_date == today)
        .scalar()
    )

    return {
        "revenue_today": float(revenue_today or 0),
        "tips_today": float(tips_today or 0),
        "orders_today": orders_today or 0,
        "top_item": top_item_row[0] if top_item_row else None,
        "top_item_quantity": int(top_item_row[1]) if top_item_row else 0,
        "average_rating": round(float(avg_rating), 1) if avg_rating is not None else None,
    }


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------
@app.get("/api/orders", response_model=list[schemas.OrderOut])
def list_orders(db: Session = Depends(get_db)):
    return order_query(db).order_by(models.Order.id.desc()).all()


@app.get("/api/orders/{order_id}", response_model=schemas.OrderOut)
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = order_query(db).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Order not found")
    return order


@app.post("/api/orders", response_model=schemas.OrderOut)
def create_order(payload: schemas.OrderCreate, db: Session = Depends(get_db)):
    if not payload.items:
        raise HTTPException(400, "An order needs at least one item")

    restaurant = get_restaurant(db)

    # Get-or-create the customer. Phone is optional — when given, it's used
    # to recognize a returning customer; when not, a fresh Customer row is
    # created per order (still a real record, just without a dedupe key).
    customer = None
    if payload.customer.phone_number:
        customer = db.query(models.Customer).filter(
            models.Customer.phone_number == payload.customer.phone_number
        ).first()
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

    order = models.Order(
        customer_id=customer.id,
        restaurant_id=restaurant.id,
        table_number=payload.table_number,
        status=models.OrderStatus.placed,
    )
    db.add(order)
    db.flush()

    for item in payload.items:
        menu_item = menu_items[item.menu_item_id]
        order_item = models.OrderItem(
            order_id=order.id,
            menu_item_id=menu_item.id,
            quantity=item.quantity,
            unit_price=menu_item.price,
        )
        db.add(order_item)
        db.flush()

        db.add(models.OrderPreparation(
            order_id=order.id,
            order_item_id=order_item.id,
            menu_item_id=menu_item.id,
        ))

    db.commit()
    return order_query(db).filter(models.Order.id == order.id).first()


@app.post("/api/orders/{order_id}/assign", response_model=schemas.OrderOut)
def assign_waiter(order_id: int, payload: schemas.AssignWaiter, db: Session = Depends(get_db)):
    order = db.query(models.Order).get(order_id)
    if not order:
        raise HTTPException(404, "Order not found")

    waiter = db.query(models.Waiter).get(payload.waiter_id)
    if not waiter:
        raise HTTPException(400, "waiter_id does not reference a known waiter")

    order.waiter_id = waiter.id
    order.status = models.OrderStatus.assigned
    db.commit()
    return order_query(db).filter(models.Order.id == order_id).first()


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
        chef = db.query(models.Chef).get(payload.chef_id)
        if not chef:
            raise HTTPException(400, "chef_id does not reference a known chef")
        prep.chef_id = chef.id
    else:
        if not payload.bartender_id:
            raise HTTPException(400, "This is a drink item — bartender_id is required")
        bartender = db.query(models.Bartender).get(payload.bartender_id)
        if not bartender:
            raise HTTPException(400, "bartender_id does not reference a known bartender")
        prep.bartender_id = bartender.id

    prep.status = models.PreparationStatus.completed
    prep.preparation_end_time = datetime.utcnow()
    db.commit()
    return order_query(db).filter(models.Order.id == order_id).first()


@app.post("/api/orders/{order_id}/serve", response_model=schemas.OrderOut)
def mark_served(order_id: int, db: Session = Depends(get_db)):
    order = db.query(models.Order).get(order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    if order.status != models.OrderStatus.assigned:
        raise HTTPException(400, "Order must be assigned to a waiter before it can be marked served")

    unprepared = [p for p in order.preparations if p.status != models.PreparationStatus.completed]
    if unprepared:
        raise HTTPException(400, "Every item needs a chef or bartender recorded before serving")

    order.status = models.OrderStatus.served
    order.actual_completion_time = datetime.utcnow()
    db.commit()
    return order_query(db).filter(models.Order.id == order_id).first()


@app.post("/api/orders/{order_id}/cancel", response_model=schemas.OrderOut)
def cancel_order(order_id: int, db: Session = Depends(get_db)):
    """A customer can cancel while the order is still just sitting in the
    queue — either nobody has picked it up yet, or a waiter has but no
    chef/bartender has actually started on any item. Once real prep work
    has begun, it's too late: cancelling would waste food already being
    made."""
    order = db.query(models.Order).get(order_id)
    if not order:
        raise HTTPException(404, "Order not found")

    prep_started = any(p.status == models.PreparationStatus.completed for p in order.preparations)
    cancellable = order.status == models.OrderStatus.placed or (
        order.status == models.OrderStatus.assigned and not prep_started
    )
    if not cancellable:
        raise HTTPException(400, "This order can no longer be cancelled — preparation has already started")

    order.status = models.OrderStatus.cancelled
    db.commit()
    return order_query(db).filter(models.Order.id == order_id).first()


@app.post("/api/orders/{order_id}/pay", response_model=schemas.OrderOut)
def pay_order(order_id: int, payload: schemas.PayRequest = schemas.PayRequest(), db: Session = Depends(get_db)):
    order = db.query(models.Order).get(order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    if order.payment:
        raise HTTPException(400, "Order is already paid")

    db.add(models.Payment(
        order_id=order.id,
        customer_id=order.customer_id,
        amount=order.total_amount + payload.tip_amount,
        tip_amount=payload.tip_amount,
    ))
    order.status = models.OrderStatus.paid
    db.commit()
    return order_query(db).filter(models.Order.id == order_id).first()


@app.post("/api/orders/{order_id}/complaint", response_model=schemas.OrderOut)
def submit_complaint(order_id: int, payload: schemas.ComplaintCreate, db: Session = Depends(get_db)):
    order = db.query(models.Order).get(order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    if order.complaint:
        raise HTTPException(400, "This order already has a complaint on file")

    db.add(models.Complaint(
        order_id=order.id,
        customer_id=order.customer_id,
        description=payload.description,
    ))
    db.commit()
    return order_query(db).filter(models.Order.id == order_id).first()


@app.post("/api/orders/{order_id}/rating", response_model=schemas.OrderOut)
def submit_rating(order_id: int, payload: schemas.RatingCreate, db: Session = Depends(get_db)):
    order = db.query(models.Order).get(order_id)
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
    return order_query(db).filter(models.Order.id == order_id).first()


# ---------------------------------------------------------------------------
# Table QR codes — not part of the assignment's requirements; generated on
# request rather than stored, and just encode a link back to this same app
# with the table number pre-filled.
# ---------------------------------------------------------------------------
@app.get("/api/qr/{table_number}")
def table_qr(table_number: int, request: Request):
    base = str(request.base_url).rstrip("/")
    url = f"{base}/?table={table_number}"

    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1A1512", back_color="#F8EFDC")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")


@app.get("/qr", response_class=HTMLResponse)
def qr_sheet(request: Request, count: int = 12):
    base = str(request.base_url).rstrip("/")
    cards = "".join(
        f'<div class="qr-card"><div class="qr-card-accent"></div>'
        f'<img src="{base}/api/qr/{n}" alt="Table {n} QR code">'
        f'<div class="qr-label">Table {n}</div></div>'
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