"""Reference data: Chowly's locations, the group menu, and staff.

Safe to run on every startup and on an existing database: each step only
adds what's missing. (The original single seeded restaurant becomes the
Lekki Phase 1 location, so its existing orders stay attached to it.)
"""
from .database import SessionLocal
from .models import (
    Restaurant, Menu, MenuItem, MenuItemEvent, ItemType, Waiter, Chef, Bartender,
)

# BRD: three locations today — Lekki Phase 1, Ikeja GRA and Wuse 2 Abuja.
LOCATIONS = [
    {"location_code": "LEK", "name": "Chowly Lekki Phase 1", "address": "Lekki Phase 1, Lagos", "phone_number": "+2348012340000"},
    {"location_code": "IKJ", "name": "Chowly Ikeja GRA", "address": "Ikeja GRA, Lagos", "phone_number": "+2348012340001"},
    {"location_code": "WUS", "name": "Chowly Wuse 2", "address": "Wuse 2, Abuja", "phone_number": "+2348012340002"},
]

# One group menu shared by every location, so a dish has one identity
# everywhere (item_code) and sales can be compared across branches.
MENU_ITEMS = [
    ("M-001", "Jollof Rice & Grilled Chicken", ItemType.food, 4500, 18),
    ("M-002", "Suya Platter", ItemType.food, 3800, 15),
    ("M-003", "Pounded Yam & Egusi Soup", ItemType.food, 5200, 20),
    ("M-004", "Peppered Snails", ItemType.food, 6000, 25),
    ("M-005", "Plantain & Fish Pepper Soup", ItemType.food, 4200, 17),
    ("M-006", "Chapman", ItemType.drink, 1800, 5),
    ("M-007", "Zobo", ItemType.drink, 1200, 3),
    ("M-008", "Palm Wine", ItemType.drink, 2000, 2),
    ("M-009", "Chilled Star Lager", ItemType.drink, 1500, 1),
    ("M-010", "Fresh Pineapple Juice", ItemType.drink, 1600, 4),
]

STAFF = {
    "LEK": {
        "waiters": [("Amaka", "Obi", "+2348011111111"), ("Tunde", "Bakare", "+2348022222222")],
        "chefs": [("Ifeoma", "Nwosu", "+2348033333333"), ("Emeka", "Uche", "+2348044444444")],
        "bartenders": [("Bode", "Ajayi", "+2348055555555"), ("Ngozi", "Eze", "+2348066666666")],
    },
    "IKJ": {
        "waiters": [("Kemi", "Adebayo", "+2348071111111"), ("Segun", "Ojo", "+2348072222222")],
        "chefs": [("Halima", "Bello", "+2348073333333"), ("Uche", "Okafor", "+2348074444444")],
        "bartenders": [("Femi", "Lawal", "+2348075555555"), ("Zainab", "Musa", "+2348076666666")],
    },
    "WUS": {
        "waiters": [("Aisha", "Yusuf", "+2348091111111"), ("Chinedu", "Eze", "+2348092222222")],
        "chefs": [("Ibrahim", "Sani", "+2348093333333"), ("Ngozi", "Okeke", "+2348094444444")],
        "bartenders": [("Tobi", "Adeyemi", "+2348095555555"), ("Hauwa", "Garba", "+2348096666666")],
    },
}


def seed():
    db = SessionLocal()
    try:
        _ensure_locations(db)
        _ensure_menu(db)
        _ensure_staff(db)
        db.commit()
    finally:
        db.close()


def _ensure_locations(db):
    existing = {r.location_code: r for r in db.query(Restaurant).all() if r.location_code}

    # Pre-Lab-1 databases have one restaurant with no code: it becomes Lekki.
    legacy = db.query(Restaurant).filter(Restaurant.location_code.is_(None)).order_by(Restaurant.id).first()
    if legacy and "LEK" not in existing:
        lek = LOCATIONS[0]
        legacy.location_code, legacy.name, legacy.address = lek["location_code"], lek["name"], lek["address"]
        existing["LEK"] = legacy

    for loc in LOCATIONS:
        if loc["location_code"] not in existing:
            db.add(Restaurant(**loc))
    db.flush()


def _ensure_menu(db):
    lek = db.query(Restaurant).filter(Restaurant.location_code == "LEK").one()
    menu = db.query(Menu).order_by(Menu.id).first()
    if not menu:
        menu = Menu(restaurant_id=lek.id, name="Main Menu", menu_type="Food & Drinks",
                    description="The Chowly group menu, served at every location.")
        db.add(menu)
        db.flush()

    by_name = {m.item_name: m for m in db.query(MenuItem).all()}
    if not by_name:
        for code, name, kind, price, prep in MENU_ITEMS:
            item = MenuItem(menu_id=menu.id, item_code=code, item_name=name, item_type=kind,
                            price=price, prep_time_minutes=prep)
            db.add(item)
            db.flush()
            db.add(MenuItemEvent(menu_item_id=item.id, event_type="created", new_value=f"{name} @ {price}",
                                 changed_by="system: seed"))
        return

    # Existing database: give each item its permanent code (matched by its original name).
    codes = {name: code for code, name, *_ in MENU_ITEMS}
    for item in by_name.values():
        if not item.item_code:
            item.item_code = codes.get(item.item_name, f"M-{item.id:03d}")


def _ensure_staff(db):
    for loc in db.query(Restaurant).all():
        plan = STAFF.get(loc.location_code)
        if not plan or db.query(Waiter).filter(Waiter.restaurant_id == loc.id).count():
            continue
        for model, key in ((Waiter, "waiters"), (Chef, "chefs"), (Bartender, "bartenders")):
            for first, last, phone in plan[key]:
                db.add(model(restaurant_id=loc.id, first_name=first, last_name=last, phone_number=phone))


if __name__ == "__main__":
    from .migrate import run
    run()
    print("Database upgraded and seeded.")
