from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
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

    # Get-or-create the customer by phone number — no login, but a real
    # Customer record, matching phone as the natural identifier.
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


@app.post("/api/orders/{order_id}/pay", response_model=schemas.OrderOut)
def pay_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(models.Order).get(order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    if order.payment:
        raise HTTPException(400, "Order is already paid")

    db.add(models.Payment(
        order_id=order.id,
        customer_id=order.customer_id,
        amount=order.total_amount,
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
# Frontend (single-page app, vanilla HTML/CSS/JS served from the same origin)
# ---------------------------------------------------------------------------
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def serve_index():
    return FileResponse(STATIC_DIR / "index.html")
