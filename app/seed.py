from .database import SessionLocal, engine, Base
from .models import Restaurant, Menu, MenuItem, ItemType, Waiter, Chef, Bartender


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(Restaurant).count() > 0:
            return  # already seeded

        restaurant = Restaurant(
            name="The Grand Table",
            address="12 Adeola Odeku Street, Victoria Island, Lagos",
            phone_number="08012340000",
            email="hello@thegrandtable.example",
        )
        db.add(restaurant)
        db.flush()

        menu = Menu(
            restaurant_id=restaurant.id,
            name="Main Menu",
            menu_type="Food & Drinks",
            description="Everything on offer tonight.",
        )
        db.add(menu)
        db.flush()

        menu_items = [
            MenuItem(menu_id=menu.id, item_name="Jollof Rice & Grilled Chicken", item_type=ItemType.food, price=4500, prep_time_minutes=18),
            MenuItem(menu_id=menu.id, item_name="Suya Platter", item_type=ItemType.food, price=3800, prep_time_minutes=15),
            MenuItem(menu_id=menu.id, item_name="Pounded Yam & Egusi Soup", item_type=ItemType.food, price=5200, prep_time_minutes=20),
            MenuItem(menu_id=menu.id, item_name="Peppered Snails", item_type=ItemType.food, price=6000, prep_time_minutes=25),
            MenuItem(menu_id=menu.id, item_name="Plantain & Fish Pepper Soup", item_type=ItemType.food, price=4200, prep_time_minutes=17),
            MenuItem(menu_id=menu.id, item_name="Chapman", item_type=ItemType.drink, price=1800, prep_time_minutes=5),
            MenuItem(menu_id=menu.id, item_name="Zobo", item_type=ItemType.drink, price=1200, prep_time_minutes=3),
            MenuItem(menu_id=menu.id, item_name="Palm Wine", item_type=ItemType.drink, price=2000, prep_time_minutes=2),
            MenuItem(menu_id=menu.id, item_name="Chilled Star Lager", item_type=ItemType.drink, price=1500, prep_time_minutes=1),
            MenuItem(menu_id=menu.id, item_name="Fresh Pineapple Juice", item_type=ItemType.drink, price=1600, prep_time_minutes=4),
        ]
        waiters = [
            Waiter(restaurant_id=restaurant.id, first_name="Amaka", last_name="Obi", phone_number="08011111111"),
            Waiter(restaurant_id=restaurant.id, first_name="Tunde", last_name="Bakare", phone_number="08022222222"),
        ]
        chefs = [
            Chef(restaurant_id=restaurant.id, first_name="Ifeoma", last_name="Nwosu", phone_number="08033333333"),
            Chef(restaurant_id=restaurant.id, first_name="Emeka", last_name="Uche", phone_number="08044444444"),
        ]
        bartenders = [
            Bartender(restaurant_id=restaurant.id, first_name="Bode", last_name="Ajayi", phone_number="08055555555"),
            Bartender(restaurant_id=restaurant.id, first_name="Ngozi", last_name="Eze", phone_number="08066666666"),
        ]
        db.add_all(menu_items + waiters + chefs + bartenders)
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed()
    print("Seeded database.")
