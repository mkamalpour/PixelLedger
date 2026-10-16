from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import sqlite3
import pytest
from shop.database import Database
from shop.engine import Shop, RuleError


def make_order(shop, quantity=3, product_id=13, discount="12.5", request_id=None):
    return shop.create_order(
        1,
        [{"product_id": product_id, "quantity": quantity}],
        Decimal(discount),
        request_id,
    )["orders"][0]


def test_seed_is_realistic_and_reproducible(shop, tmp_path):
    second = Shop(Database(tmp_path / "other.db"))
    second.initialize(42)
    assert shop.state() == second.state()
    assert len(shop.state()["products"]) == 26
    assert len(shop.state()["orders"]) == 8
    assert all(product["stock"] >= 0 for product in shop.state()["products"])


def test_order_calculates_snapshot_discount_tax_and_reserves_stock(shop):
    initial = shop.state()
    product = next(p for p in initial["products"] if p["id"] == 13)
    order = make_order(shop)
    line = order["items"][0]
    base = (product["price_cents"] * 3 * 8750 + 5000) // 10000
    tax = (base * 800 + 5000) // 10000
    assert order["total_cents"] == base + tax
    assert line["tax_cents"] == tax and line["discount_bps"] == 1250
    assert shop.state()["products"][12]["stock"] == product["stock"] - 3
    shop.set_price(13, 19999)
    assert (
        shop.state()["orders"][0]["items"][0]["unit_price_cents"]
        == product["price_cents"]
    )


def test_failed_payment_can_retry_but_cannot_double_capture(shop):
    order = make_order(shop)
    before = shop.state()["cash_cents"]
    shop.pay(order["id"], False)
    assert shop.state()["cash_cents"] == before
    assert shop.state()["orders"][0]["payment_status"] == "Failed"
    paid = shop.pay(order["id"], True)
    assert paid["cash_cents"] == before + order["total_cents"]
    assert paid["orders"][0]["status"] == "Processing"
    shop.pay(order["id"], True)
    assert shop.state()["cash_cents"] == paid["cash_cents"]
    assert shop.db.query(
        f"SELECT COUNT(*) FROM payments WHERE order_id={order['id']} AND kind='capture'"
    )["rows"] == [[1]]


def test_fulfillment_requires_payment_and_valid_transitions(shop):
    order = make_order(shop)
    with pytest.raises(RuleError):
        shop.transition(order["id"], "Shipped")
    with pytest.raises(RuleError):
        shop.transition(order["id"], "Delivered")
    shop.pay(order["id"])
    shop.transition(order["id"], "Shipped")
    with pytest.raises(RuleError):
        shop.transition(order["id"], "Cancelled")
    shop.transition(order["id"], "Delivered")
    assert shop.state()["orders"][0]["status"] == "Delivered"


def test_paid_cancel_reverses_stock_cash_revenue_and_cost(shop):
    baseline = shop.state()
    order = make_order(shop)
    shop.pay(order["id"])
    result = shop.transition(order["id"], "Cancelled")
    assert result["cash_cents"] == baseline["cash_cents"]
    assert result["products"][12]["stock"] == baseline["products"][12]["stock"]
    for name in [
        "net_sales_cents",
        "cogs_cents",
        "profit_cents",
        "tax_collected_cents",
    ]:
        assert result["metrics"][name] == baseline["metrics"][name]
    shop.transition(order["id"], "Cancelled")
    assert shop.state()["cash_cents"] == baseline["cash_cents"]
    with pytest.raises(RuleError):
        shop.pay(order["id"])


def test_partial_returns_refund_exact_total_and_restore_only_returned_stock(shop):
    baseline = shop.state()
    order = make_order(shop, quantity=3, discount="17.33")
    shop.pay(order["id"])
    shop.transition(order["id"], "Shipped")
    shop.transition(order["id"], "Delivered")
    line = order["items"][0]
    for expected in [1, 2, 3]:
        result = shop.return_items(order["id"], line["id"], 1, True, "Changed mind")
        latest = result["orders"][0]["items"][0]
        assert latest["returned_qty"] == expected
        assert latest["refunded_cents"] == (line["total_cents"] * expected) // 3
    assert result["cash_cents"] == baseline["cash_cents"]
    assert result["products"][12]["stock"] == baseline["products"][12]["stock"]
    assert (
        result["metrics"]["net_sales_cents"] == baseline["metrics"]["net_sales_cents"]
    )
    assert (
        result["metrics"]["tax_collected_cents"]
        == baseline["metrics"]["tax_collected_cents"]
    )
    assert result["metrics"]["cogs_cents"] == baseline["metrics"]["cogs_cents"]
    with pytest.raises(RuleError):
        shop.return_items(order["id"], line["id"], 1)


def test_damaged_return_is_refunded_without_recreating_inventory_or_reversing_cogs(
    shop,
):
    baseline = shop.state()
    order = make_order(shop, quantity=1)
    shop.pay(order["id"])
    shop.transition(order["id"], "Shipped")
    shop.transition(order["id"], "Delivered")
    result = shop.return_items(
        order["id"], order["items"][0]["id"], 1, False, "Damaged"
    )
    assert result["products"][12]["stock"] == baseline["products"][12]["stock"] - 1
    assert result["cash_cents"] == baseline["cash_cents"]
    assert (
        result["metrics"]["cogs_cents"]
        == baseline["metrics"]["cogs_cents"] + order["items"][0]["cost_cents"]
    )


def test_return_line_must_belong_to_delivered_order(shop):
    first = make_order(shop, quantity=1)
    second = make_order(shop, quantity=1)
    with pytest.raises(RuleError):
        shop.return_items(second["id"], first["items"][0]["id"], 1)
    shop.pay(second["id"])
    shop.transition(second["id"], "Shipped")
    shop.transition(second["id"], "Delivered")
    with pytest.raises(RuleError):
        shop.return_items(second["id"], first["items"][0]["id"], 1)


def test_out_of_stock_order_is_atomic(shop):
    before = shop.state()
    with pytest.raises(RuleError):
        shop.create_order(
            1, [{"product_id": 1, "quantity": 1}, {"product_id": 13, "quantity": 100}]
        )
    after = shop.state()
    assert after == before


def test_parallel_orders_cannot_oversell_last_unit(shop):
    with shop.db.transaction() as connection:
        connection.execute("UPDATE products SET stock=1 WHERE id=13")

    def buy():
        try:
            make_order(shop, quantity=1)
            return True
        except RuleError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: buy(), range(2)))
    assert results.count(True) == 1
    assert shop.state()["products"][12]["stock"] == 0


def test_restock_updates_cash_stock_and_rejects_unaffordable_purchase(shop):
    before = shop.state()
    product = before["products"][0]
    after = shop.restock(product["id"], 2)
    assert after["cash_cents"] == before["cash_cents"] - 2 * product["cost_cents"]
    assert after["products"][0]["stock"] == product["stock"] + 2
    with pytest.raises(RuleError):
        shop.restock(product["id"], 1000)
    assert shop.state() == after


def test_price_changes_relative_demand_and_simulation_trajectory(shop, tmp_path):
    other = Shop(Database(tmp_path / "comparison.db"))
    other.initialize(42)
    before = shop.state()["products"][12]
    shop.set_price(13, before["price_cents"] * 2)
    assert shop.state()["products"][12]["demand"] < before["demand"]
    assert shop.advance(5)["orders"] != other.advance(5)["orders"]


def test_simulation_is_deterministic_chunk_independent_and_idempotent(shop, tmp_path):
    other = Shop(Database(tmp_path / "comparison.db"))
    other.initialize(42)
    result = shop.advance(7, "week-request")
    for _ in range(7):
        other.advance(1)
    assert result == other.state()
    assert shop.advance(7, "week-request") == result
    with pytest.raises(RuleError):
        shop.advance(1, "week-request")


def test_order_request_id_prevents_duplicate_and_rejects_changed_payload(shop):
    make_order(shop, quantity=1, request_id="checkout")
    before = shop.state()
    make_order(shop, quantity=1, request_id="checkout")
    assert shop.state() == before
    with pytest.raises(RuleError):
        make_order(shop, quantity=2, request_id="checkout")


def test_unpaid_orders_expire_and_release_reservations(shop):
    order = make_order(shop, quantity=1)
    result = shop.advance(2)
    expired = next(item for item in result["orders"] if item["id"] == order["id"])
    assert expired["status"] == "Cancelled"
    assert shop.db.query(
        f"SELECT COUNT(*) FROM inventory_logs WHERE product_id=13 AND reason='Order #{order['id']} canceled'"
    )["rows"] == [[1]]


def test_long_simulation_preserves_business_invariants(shop):
    result = shop.advance(30)
    assert all(product["stock"] >= 0 for product in result["products"])
    assert all(
        order["total_cents"] == sum(line["total_cents"] for line in order["items"])
        for order in result["orders"]
    )
    for product in result["products"]:
        total = shop.db.query(
            f"SELECT SUM(change_amount) FROM inventory_logs WHERE product_id={product['id']}"
        )["rows"][0][0]
        assert total == product["stock"]
    assert (
        result["metrics"]["net_sales_cents"]
        == sum(day["net_sales_cents"] for day in shop.state()["history"])
        + shop.db.query("SELECT net_sales_cents FROM daily_history WHERE day=0")[
            "rows"
        ][0][0]
    )


def test_manual_payment_updates_today_chart(shop):
    order = make_order(shop, quantity=1)
    before = shop.state()["history"][-1]["net_sales_cents"]
    after = shop.pay(order["id"])
    assert (
        after["history"][-1]["net_sales_cents"]
        == before + order["items"][0]["total_cents"] - order["items"][0]["tax_cents"]
    )


def test_reset_is_reproducible_and_does_not_touch_unrelated_tables(shop):
    baseline = shop.state()
    with shop.db.transaction() as connection:
        connection.execute(
            "CREATE TABLE unrelated(id INTEGER PRIMARY KEY AUTOINCREMENT, value TEXT)"
        )
        connection.execute("INSERT INTO unrelated(value) VALUES ('Keep me')")
    shop.advance(5)
    assert shop.reset(42) == baseline
    assert shop.db.query("SELECT value FROM unrelated")["rows"] == [["Keep me"]]
    with shop.db.transaction() as connection:
        assert (
            connection.execute(
                "INSERT INTO unrelated(value) VALUES ('Second')"
            ).lastrowid
            == 2
        )


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM products",
        "UPDATE products SET stock=99",
        "DROP TABLE products",
        "ATTACH DATABASE ':memory:' AS extra",
        "PRAGMA table_info(products)",
        "SELECT load_extension('bad')",
        "SELECT * FROM requests",
        "SELECT 1; DELETE FROM orders",
    ],
)
def test_sql_lab_cannot_mutate_or_escape_database(shop, sql):
    before = shop.state()
    with pytest.raises((sqlite3.Error, ValueError)):
        shop.db.query(sql)
    assert shop.state() == before


def test_sql_lab_supports_reporting_caps_rows_and_stops_unbounded_work(shop):
    result = shop.db.query(
        "SELECT category,COUNT(*) AS products,ROUND(AVG(price_cents)/100.0,2) AS average_price FROM products GROUP BY category ORDER BY category"
    )
    assert (
        result["columns"] == ["category", "products", "average_price"]
        and result["rows"]
    )
    limited = shop.db.query("SELECT a.id,b.id FROM products a CROSS JOIN products b")
    assert len(limited["rows"]) == 200 and limited["truncated"] is True


def test_customer_email_uniqueness_and_spending(shop):
    after = shop.add_customer("New Player", "player@example.test")
    assert after["customers"][-1]["email"] == "player@example.test"
    with pytest.raises(sqlite3.IntegrityError):
        shop.add_customer("Duplicate", "PLAYER@example.test")
    customer = after["customers"][-1]
    order = shop.create_order(customer["id"], [{"product_id": 1, "quantity": 1}])[
        "orders"
    ][0]
    paid = shop.pay(order["id"])
    updated = next(item for item in paid["customers"] if item["id"] == customer["id"])
    assert (
        updated["spent_cents"] == order["total_cents"] and updated["order_count"] == 1
    )


def test_api_validation_authentication_and_reset_confirmation(client, monkeypatch):
    from shop import api

    assert client.get("/api/state").status_code == 200
    for path, payload in [
        ("/api/simulate", {"days": 0}),
        ("/api/reset", {"confirmation": "yes"}),
        ("/api/orders", {"customer_id": 1, "items": []}),
        ("/api/customers", {"name": "", "email": "invalid"}),
        ("/api/products/1", {"price_cents": 1.5}),
    ]:
        response = (
            client.patch(path, json=payload)
            if path.startswith("/api/products")
            else client.post(path, json=payload)
        )
        assert response.status_code == 422
    assert (
        client.post(
            "/api/reset", json={"confirmation": "RESET SHOP", "seed": 42}
        ).status_code
        == 200
    )
    assert client.get("/", headers={"Host": "untrusted.example"}).status_code == 400
    assert (
        client.post(
            "/api/simulate",
            json={"days": 1},
            headers={"Origin": "https://untrusted.example"},
        ).status_code
        == 403
    )
    monkeypatch.setattr(api, "API_KEY", "test-key")
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/state").status_code == 401
    assert (
        client.get("/api/state", headers={"X-API-Key": "test-key"}).status_code == 200
    )


def test_api_workflow_and_safe_runtime_key(client, monkeypatch):
    from shop import api

    response = client.post(
        "/api/orders",
        json={
            "customer_id": 1,
            "items": [{"product_id": 13, "quantity": 1}],
            "request_id": "api-order",
        },
    )
    assert response.status_code == 200, response.text
    order = response.json()["orders"][0]
    for path, payload in [
        (f"/api/orders/{order['id']}/pay", {"success": True}),
        (f"/api/orders/{order['id']}/status", {"status": "Shipped"}),
        (f"/api/orders/{order['id']}/status", {"status": "Delivered"}),
        (
            f"/api/orders/{order['id']}/returns",
            {"line_id": order["items"][0]["id"], "quantity": 1, "restock": True},
        ),
    ]:
        result = client.post(path, json=payload)
        assert result.status_code == 200, result.text
    assert (
        client.post(
            "/api/query", json={"sql": "SELECT COUNT(*) FROM orders"}
        ).status_code
        == 200
    )
    assert (
        client.post("/api/query", json={"sql": "DELETE FROM orders"}).status_code == 422
    )
    monkeypatch.setattr(api, "API_KEY", "</script><script>alert(1)</script>")
    response = client.get("/")
    assert "</script><script>alert(1)</script>" not in response.text
    assert response.headers["cache-control"] == "no-store"


def test_expensive_sql_stops_at_query_budget(shop, monkeypatch):
    from types import SimpleNamespace
    from shop import database

    clock = iter([0.0, 3.0])
    monkeypatch.setattr(
        database, "time", SimpleNamespace(monotonic=lambda: next(clock))
    )
    with pytest.raises(sqlite3.OperationalError, match="interrupted"):
        shop.db.query(
            "WITH RECURSIVE numbers(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM numbers WHERE x<1000000000) SELECT SUM(x) FROM numbers"
        )


def test_remote_hostname_never_receives_shared_key_even_through_loopback_proxy(
    client, monkeypatch
):
    from shop import api
    from starlette.requests import Request

    monkeypatch.setattr(api, "API_KEY", "network-key")
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"host", b"shop.example")],
            "scheme": "http",
            "server": ("127.0.0.1", 8000),
            "client": ("127.0.0.1", 1234),
            "query_string": b"",
        }
    )
    assert b"network-key" not in api.index(request).body
