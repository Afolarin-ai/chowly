"""
Automated tests for Chowly's API. Run with:  pytest tests/ -v

These formalize what had previously only been verified by hand (curl
during development, clicking through the live app). Each test is
independent — the clean_db fixture in conftest.py resets the database
before every one, so order IDs and counts are predictable.
"""

JOLLOF_RICE = 1   # food
CHAPMAN = 6       # drink
PALM_WINE = 8     # drink

WAITER_AMAKA = 1
CHEF_IFEOMA = 1
BARTENDER_BODE = 1


def make_order(client, table_number=5, items=None, phone=None):
    if items is None:
        items = [{"menu_item_id": JOLLOF_RICE, "quantity": 1}]
    payload = {
        "table_number": table_number,
        "customer": {"first_name": "Test", "last_name": "User", "phone_number": phone},
        "items": items,
    }
    return client.post("/api/orders", json=payload)


# ---------------------------------------------------------------------
# Menu & staff
# ---------------------------------------------------------------------
def test_menu_returns_seeded_items(client):
    res = client.get("/api/menu")
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 10
    assert any(i["item_name"] == "Jollof Rice & Grilled Chicken" for i in items)


def test_staff_returns_waiters_chefs_bartenders(client):
    res = client.get("/api/staff")
    assert res.status_code == 200
    data = res.json()
    assert len(data["waiters"]) == 2
    assert len(data["chefs"]) == 2
    assert len(data["bartenders"]) == 2


# ---------------------------------------------------------------------
# Order placement
# ---------------------------------------------------------------------
def test_create_order_computes_total_and_waiting_time(client):
    res = make_order(client, items=[
        {"menu_item_id": JOLLOF_RICE, "quantity": 2},  # 4500 * 2, 18 min
        {"menu_item_id": CHAPMAN, "quantity": 1},       # 1800, 5 min
    ])
    assert res.status_code == 200
    order = res.json()
    assert order["total_amount"] == 4500 * 2 + 1800
    assert order["estimated_waiting_time_minutes"] == 18  # max, not sum
    assert order["status"] == "placed"
    assert len(order["preparations"]) == 2


def test_create_order_rejects_empty_items(client):
    res = make_order(client, items=[])
    assert res.status_code == 400


def test_create_order_rejects_unknown_menu_item(client):
    res = make_order(client, items=[{"menu_item_id": 9999, "quantity": 1}])
    assert res.status_code == 400


def test_phone_number_is_optional(client):
    res = make_order(client, phone=None)
    assert res.status_code == 200
    assert res.json()["customer"]["phone_number"] is None


def test_returning_customer_recognized_by_phone(client):
    r1 = make_order(client, phone="08011112222")
    r2 = make_order(client, phone="08011112222")
    assert r1.json()["customer"]["id"] == r2.json()["customer"]["id"]


def test_omitted_phone_creates_separate_customers(client):
    r1 = make_order(client, phone=None)
    r2 = make_order(client, phone=None)
    assert r1.json()["customer"]["id"] != r2.json()["customer"]["id"]


# ---------------------------------------------------------------------
# Assignment and preparation
# ---------------------------------------------------------------------
def test_assign_sets_waiter_and_status(client):
    order_id = make_order(client).json()["id"]
    res = client.post(f"/api/orders/{order_id}/assign", json={"waiter_id": WAITER_AMAKA})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "assigned"
    assert body["waiter"]["id"] == WAITER_AMAKA


def test_prepare_rejects_bartender_on_food_item(client):
    order_id = make_order(client, items=[{"menu_item_id": JOLLOF_RICE, "quantity": 1}]).json()["id"]
    client.post(f"/api/orders/{order_id}/assign", json={"waiter_id": WAITER_AMAKA})
    order = client.get(f"/api/orders/{order_id}").json()
    item_id = order["preparations"][0]["order_item_id"]
    res = client.post(f"/api/orders/{order_id}/items/{item_id}/prepare", json={"bartender_id": BARTENDER_BODE})
    assert res.status_code == 400


def test_prepare_rejects_chef_on_drink_item(client):
    order_id = make_order(client, items=[{"menu_item_id": CHAPMAN, "quantity": 1}]).json()["id"]
    client.post(f"/api/orders/{order_id}/assign", json={"waiter_id": WAITER_AMAKA})
    order = client.get(f"/api/orders/{order_id}").json()
    item_id = order["preparations"][0]["order_item_id"]
    res = client.post(f"/api/orders/{order_id}/items/{item_id}/prepare", json={"chef_id": CHEF_IFEOMA})
    assert res.status_code == 400


def test_serve_blocked_until_every_item_prepared(client):
    order_id = make_order(client, items=[
        {"menu_item_id": JOLLOF_RICE, "quantity": 1},
        {"menu_item_id": CHAPMAN, "quantity": 1},
    ]).json()["id"]
    client.post(f"/api/orders/{order_id}/assign", json={"waiter_id": WAITER_AMAKA})
    order = client.get(f"/api/orders/{order_id}").json()
    food_item_id = order["preparations"][0]["order_item_id"]

    # only prepare one of the two items
    client.post(f"/api/orders/{order_id}/items/{food_item_id}/prepare", json={"chef_id": CHEF_IFEOMA})
    res = client.post(f"/api/orders/{order_id}/serve")
    assert res.status_code == 400

    # prepare the second item, then serving should succeed
    drink_item_id = order["preparations"][1]["order_item_id"]
    client.post(f"/api/orders/{order_id}/items/{drink_item_id}/prepare", json={"bartender_id": BARTENDER_BODE})
    res = client.post(f"/api/orders/{order_id}/serve")
    assert res.status_code == 200
    assert res.json()["status"] == "served"


# ---------------------------------------------------------------------
# Cancellation eligibility — the three states that matter
# ---------------------------------------------------------------------
def test_cancel_succeeds_while_placed(client):
    order_id = make_order(client).json()["id"]
    res = client.post(f"/api/orders/{order_id}/cancel")
    assert res.status_code == 200
    assert res.json()["status"] == "cancelled"


def test_cancel_succeeds_after_assign_before_prep(client):
    order_id = make_order(client).json()["id"]
    client.post(f"/api/orders/{order_id}/assign", json={"waiter_id": WAITER_AMAKA})
    res = client.post(f"/api/orders/{order_id}/cancel")
    assert res.status_code == 200


def test_cancel_rejected_once_prep_started(client):
    order_id = make_order(client).json()["id"]
    client.post(f"/api/orders/{order_id}/assign", json={"waiter_id": WAITER_AMAKA})
    order = client.get(f"/api/orders/{order_id}").json()
    item_id = order["preparations"][0]["order_item_id"]
    client.post(f"/api/orders/{order_id}/items/{item_id}/prepare", json={"chef_id": CHEF_IFEOMA})

    res = client.post(f"/api/orders/{order_id}/cancel")
    assert res.status_code == 400


# ---------------------------------------------------------------------
# Payment, rating, complaint
# ---------------------------------------------------------------------
def _serve_order(client, order_id, item_type="food"):
    client.post(f"/api/orders/{order_id}/assign", json={"waiter_id": WAITER_AMAKA})
    order = client.get(f"/api/orders/{order_id}").json()
    item_id = order["preparations"][0]["order_item_id"]
    payload = {"chef_id": CHEF_IFEOMA} if item_type == "food" else {"bartender_id": BARTENDER_BODE}
    client.post(f"/api/orders/{order_id}/items/{item_id}/prepare", json=payload)
    client.post(f"/api/orders/{order_id}/serve")


def test_pay_creates_payment_with_pretend_reference(client):
    order_id = make_order(client).json()["id"]
    _serve_order(client, order_id)
    res = client.post(f"/api/orders/{order_id}/pay")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "paid"
    assert body["payment"]["transaction_reference"].startswith("PRETEND-")
    assert body["payment"]["tip_amount"] == 0.0  # no tip given -> defaults to 0


def test_pay_with_tip_adds_to_total(client):
    order_id = make_order(client, items=[{"menu_item_id": JOLLOF_RICE, "quantity": 1}]).json()["id"]
    _serve_order(client, order_id)
    res = client.post(f"/api/orders/{order_id}/pay", json={"tip_amount": 675})
    assert res.status_code == 200
    payment = res.json()["payment"]
    assert payment["tip_amount"] == 675.0
    assert payment["amount"] == 4500.0 + 675.0  # subtotal + tip


def test_stats_exclude_tips_from_revenue(client):
    order_id = make_order(client, items=[{"menu_item_id": JOLLOF_RICE, "quantity": 1}]).json()["id"]
    _serve_order(client, order_id)
    client.post(f"/api/orders/{order_id}/pay", json={"tip_amount": 500})

    stats = client.get("/api/stats/today").json()
    assert stats["tips_today"] == 500.0
    # Revenue is food/drink sales only -- tips are a pass-through to
    # staff, not restaurant revenue, even though they were part of what
    # was actually charged (that full amount lives on Payment.amount).
    assert stats["revenue_today"] == 4500.0


def test_pay_rejects_double_payment(client):
    order_id = make_order(client).json()["id"]
    _serve_order(client, order_id)
    client.post(f"/api/orders/{order_id}/pay")
    res = client.post(f"/api/orders/{order_id}/pay")
    assert res.status_code == 400


def test_rating_and_complaint_are_independent(client):
    order_id = make_order(client).json()["id"]
    _serve_order(client, order_id)

    res = client.post(f"/api/orders/{order_id}/rating", json={"rating_value": 5, "comment": "Great"})
    assert res.status_code == 200
    assert res.json()["complaint"] is None  # rating alone doesn't create a complaint

    res = client.post(f"/api/orders/{order_id}/complaint", json={"description": "Still, a bit slow"})
    assert res.status_code == 200
    body = res.json()
    assert body["rating"]["rating_value"] == 5
    assert body["complaint"]["description"] == "Still, a bit slow"


def test_rating_can_only_be_filed_once(client):
    order_id = make_order(client).json()["id"]
    _serve_order(client, order_id)
    client.post(f"/api/orders/{order_id}/rating", json={"rating_value": 4})
    res = client.post(f"/api/orders/{order_id}/rating", json={"rating_value": 2})
    assert res.status_code == 400


# ---------------------------------------------------------------------
# 86 an item
# ---------------------------------------------------------------------
def test_toggle_availability_flips_status(client):
    res = client.post(f"/api/menu/{JOLLOF_RICE}/toggle-availability")
    assert res.status_code == 200
    assert res.json()["availability_status"] == "sold_out"

    res = client.post(f"/api/menu/{JOLLOF_RICE}/toggle-availability")
    assert res.json()["availability_status"] == "available"


# ---------------------------------------------------------------------
# Stats correctly exclude cancelled orders
# ---------------------------------------------------------------------
def test_stats_exclude_cancelled_orders(client):
    # a cancelled order for 3x Palm Wine — should NOT count or win top seller
    cancelled_id = make_order(client, items=[{"menu_item_id": PALM_WINE, "quantity": 3}]).json()["id"]
    client.post(f"/api/orders/{cancelled_id}/cancel")

    # a real, paid order for 1x Jollof Rice
    paid_id = make_order(client, items=[{"menu_item_id": JOLLOF_RICE, "quantity": 1}]).json()["id"]
    _serve_order(client, paid_id)
    client.post(f"/api/orders/{paid_id}/pay")

    stats = client.get("/api/stats/today").json()
    assert stats["orders_today"] == 1
    assert stats["top_item"] == "Jollof Rice & Grilled Chicken"
    assert stats["revenue_today"] == 4500.0


# ---------------------------------------------------------------------
# QR codes
# ---------------------------------------------------------------------
def test_qr_endpoint_returns_valid_png(client):
    res = client.get("/api/qr/5")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    assert res.content[:8] == b"\x89PNG\r\n\x1a\n"  # PNG file signature


def test_qr_sheet_page_loads(client):
    res = client.get("/qr?count=6")
    assert res.status_code == 200
    assert "Table 6" in res.text
    assert "Table 7" not in res.text