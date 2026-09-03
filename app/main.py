from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from . import models, schemas
from .database import get_db, engine, Base
from .seed import seed

app = FastAPI(title="Chowly")

# Create tables + seed reference data (menu, staff) on startup
Base.metadata.create_all(bind=engine)
seed()

STATIC_DIR = Path(__file__).parent / "static"


# ---------------------------------------------------------------------------
# Menu & staff (read-only reference data, loaded once at seed time)
# ---------------------------------------------------------------------------
@app.get("/api/menu", response_model=list[schemas.MenuItemOut])
def get_menu(db: Session = Depends(get_db)):
    return db.query(models.MenuItem).all()


@app.get("/api/staff", response_model=list[schemas.StaffOut])
def get_staff(db: Session = Depends(get_db)):
    return db.query(models.StaffMember).all()


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------
@app.get("/api/orders", response_model=list[schemas.OrderOut])
def list_orders(db: Session = Depends(get_db)):
    return db.query(models.Order).order_by(models.Order.created_at.desc()).all()


@app.get("/api/orders/{order_id}", response_model=schemas.OrderOut)
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(models.Order).get(order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    return order


@app.post("/api/orders", response_model=schemas.OrderOut)
def create_order(payload: schemas.OrderCreate, db: Session = Depends(get_db)):
    if not payload.items:
        raise HTTPException(400, "An order needs at least one item")

    menu_ids = [i.menu_item_id for i in payload.items]
    found = db.query(models.MenuItem).filter(models.MenuItem.id.in_(menu_ids)).all()
    if len(found) != len(set(menu_ids)):
        raise HTTPException(400, "One or more menu items don't exist")

    order = models.Order(table_number=payload.table_number, status=models.OrderStatus.placed)
    db.add(order)
    db.flush()  # get order.id before adding items

    for item in payload.items:
        db.add(models.OrderItem(order_id=order.id, menu_item_id=item.menu_item_id, quantity=item.quantity))

    db.commit()
    db.refresh(order)
    return order


@app.post("/api/orders/{order_id}/assign", response_model=schemas.OrderOut)
def assign_order(order_id: int, payload: schemas.AssignOrder, db: Session = Depends(get_db)):
    order = db.query(models.Order).get(order_id)
    if not order:
        raise HTTPException(404, "Order not found")

    waiter = db.query(models.StaffMember).get(payload.waiter_id)
    if not waiter or waiter.role != models.StaffRole.waiter:
        raise HTTPException(400, "waiter_id must reference a staff member with role 'waiter'")

    order.waiter_id = waiter.id

    if payload.chef_id is not None:
        chef = db.query(models.StaffMember).get(payload.chef_id)
        if not chef or chef.role != models.StaffRole.chef:
            raise HTTPException(400, "chef_id must reference a staff member with role 'chef'")
        order.chef_id = chef.id

    if payload.bartender_id is not None:
        bartender = db.query(models.StaffMember).get(payload.bartender_id)
        if not bartender or bartender.role != models.StaffRole.bartender:
            raise HTTPException(400, "bartender_id must reference a staff member with role 'bartender'")
        order.bartender_id = bartender.id

    order.status = models.OrderStatus.assigned
    db.commit()
    db.refresh(order)
    return order


@app.post("/api/orders/{order_id}/serve", response_model=schemas.OrderOut)
def mark_served(order_id: int, db: Session = Depends(get_db)):
    order = db.query(models.Order).get(order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    if order.status not in (models.OrderStatus.assigned,):
        raise HTTPException(400, "Order must be assigned to a waiter before it can be marked served")
    order.status = models.OrderStatus.served
    db.commit()
    db.refresh(order)
    return order


@app.post("/api/orders/{order_id}/pay", response_model=schemas.OrderOut)
def pay_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(models.Order).get(order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    if order.paid:
        raise HTTPException(400, "Order is already paid")
    order.paid = True
    order.paid_at = datetime.utcnow()
    order.status = models.OrderStatus.paid
    db.commit()
    db.refresh(order)
    return order


@app.post("/api/orders/{order_id}/complaint", response_model=schemas.OrderOut)
def submit_complaint(order_id: int, payload: schemas.ComplaintCreate, db: Session = Depends(get_db)):
    order = db.query(models.Order).get(order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    if order.complaint:
        raise HTTPException(400, "This order already has a complaint on file")

    complaint = models.Complaint(order_id=order.id, message=payload.message, rating=payload.rating)
    db.add(complaint)
    db.commit()
    db.refresh(order)
    return order


# ---------------------------------------------------------------------------
# Frontend (single-page app, vanilla HTML/CSS/JS served from the same origin)
# ---------------------------------------------------------------------------
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def serve_index():
    return FileResponse(STATIC_DIR / "index.html")
