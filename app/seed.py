from .database import SessionLocal, engine, Base
from .models import MenuItem, StaffMember, MenuCategory, StaffRole


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(MenuItem).count() > 0:
            return  # already seeded

        menu_items = [
            MenuItem(name="Jollof Rice & Grilled Chicken", category=MenuCategory.food, price=4500, prep_time_minutes=18),
            MenuItem(name="Suya Platter", category=MenuCategory.food, price=3800, prep_time_minutes=15),
            MenuItem(name="Pounded Yam & Egusi Soup", category=MenuCategory.food, price=5200, prep_time_minutes=20),
            MenuItem(name="Peppered Snails", category=MenuCategory.food, price=6000, prep_time_minutes=25),
            MenuItem(name="Plantain & Fish Pepper Soup", category=MenuCategory.food, price=4200, prep_time_minutes=17),
            MenuItem(name="Chapman", category=MenuCategory.drink, price=1800, prep_time_minutes=5),
            MenuItem(name="Zobo", category=MenuCategory.drink, price=1200, prep_time_minutes=3),
            MenuItem(name="Palm Wine", category=MenuCategory.drink, price=2000, prep_time_minutes=2),
            MenuItem(name="Chilled Star Lager", category=MenuCategory.drink, price=1500, prep_time_minutes=1),
            MenuItem(name="Fresh Pineapple Juice", category=MenuCategory.drink, price=1600, prep_time_minutes=4),
        ]
        staff = [
            StaffMember(name="Amaka Obi", role=StaffRole.waiter),
            StaffMember(name="Tunde Bakare", role=StaffRole.waiter),
            StaffMember(name="Chef Ifeoma Nwosu", role=StaffRole.chef),
            StaffMember(name="Chef Emeka Uche", role=StaffRole.chef),
            StaffMember(name="Bode Ajayi", role=StaffRole.bartender),
            StaffMember(name="Ngozi Eze", role=StaffRole.bartender),
        ]
        db.add_all(menu_items + staff)
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed()
    print("Seeded database.")
