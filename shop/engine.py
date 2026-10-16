"""A deterministic shop world with atomic stock, payment and refund accounting."""

from datetime import date, timedelta
from decimal import Decimal
import hashlib
import json
import random
from shop.database import Database


class RuleError(ValueError):
    pass


def rounded(numerator, denominator=10000):
    return (numerator + denominator // 2) // denominator


class Shop:
    def __init__(self, database=None):
        self.db = database or Database()

    def initialize(self, seed=42):
        self.db.initialize()
        with self.db.transaction() as connection:
            if (
                connection.execute("SELECT 1 FROM metadata WHERE key='seed'").fetchone()
                is None
            ):
                self._seed(connection, seed)

    def _meta(self, connection, key, value=None):
        if value is not None:
            connection.execute(
                "INSERT INTO metadata(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value)),
            )
            return value
        row = connection.execute(
            "SELECT value FROM metadata WHERE key=?", (key,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def _event(self, connection, kind, message):
        connection.execute(
            "INSERT INTO events(day,kind,message) VALUES (?,?,?)",
            (self._meta(connection, "day"), kind, message),
        )

    def _ledger(self, connection, kind, amount, description):
        connection.execute(
            "INSERT INTO ledger(day,kind,amount_cents,description) VALUES (?,?,?,?)",
            (self._meta(connection, "day"), kind, amount, description),
        )

    def _inventory(self, connection, product_id, change, reason):
        connection.execute(
            "UPDATE products SET stock=stock+? WHERE id=?", (change, product_id)
        )
        connection.execute(
            "INSERT INTO inventory_logs(product_id,day,change_amount,reason) VALUES (?,?,?,?)",
            (product_id, self._meta(connection, "day"), change, reason),
        )

    def _cash(self, connection):
        return connection.execute(
            "SELECT COALESCE(SUM(amount_cents),0) FROM ledger"
        ).fetchone()[0]

    def _seed(self, connection, seed):
        rng = random.Random(seed)
        for key, value in {
            "seed": seed,
            "day": 0,
            "lost_sales": 0,
            "reputation": 80,
            "market": {
                "title": "Opening week",
                "description": "A steady start. Keep shelves stocked and orders moving.",
                "category": "All",
                "multiplier": 1.0,
                "delivery_delay": 0,
            },
        }.items():
            self._meta(connection, key, value)
        for name in [
            "Northstar Distribution",
            "Arcade Supply Co.",
            "Orbit Games Wholesale",
        ]:
            connection.execute("INSERT INTO suppliers(name) VALUES (?)", (name,))
        for name, role in [
            ("Alex Morgan", "Shop manager"),
            ("Sam Rivera", "Sales specialist"),
            ("Jordan Lee", "Warehouse lead"),
        ]:
            connection.execute(
                "INSERT INTO employees(name,role) VALUES (?,?)", (name, role)
            )
        catalog = [
            ("Nova Station Console", "Consoles", 49900, 36500, 1.0),
            ("Orbit X Console", "Consoles", 44900, 32000, 0.9),
            ("Pocket Arcade Handheld", "Consoles", 19900, 12500, 1.2),
            ("Retro Mini Console", "Consoles", 8900, 4900, 0.8),
            ("Wireless Pro Controller", "Controllers", 6900, 3500, 1.8),
            ("Arcade Fight Stick", "Controllers", 12900, 7600, 0.7),
            ("Racing Wheel Kit", "Controllers", 24900, 16100, 0.6),
            ("Controller Charging Dock", "Accessories", 2900, 1200, 1.3),
            ("Studio Gaming Headset", "Accessories", 8900, 4200, 1.5),
            ("Mechanical Pixel Keyboard", "Accessories", 11900, 6100, 0.8),
            ("Precision Gaming Mouse", "Accessories", 5900, 2700, 1.4),
            ("Desk Mat XL", "Accessories", 1900, 700, 1.6),
            ("Starfall Odyssey", "Games", 5999, 2900, 2.2),
            ("Neon Circuit Racing", "Games", 4999, 2200, 1.5),
            ("Moonlight Valley", "Games", 2999, 1000, 2.0),
            ("Castle of Echoes", "Games", 3999, 1700, 1.5),
            ("Tactical Horizon", "Games", 6999, 3500, 1.7),
            ("Pixel Party Collection", "Games", 2499, 800, 1.8),
            ("1TB Performance SSD", "Hardware", 9900, 6100, 1.0),
            ("32GB Memory Kit", "Hardware", 7900, 4800, 0.8),
            ("RGB Cooling Kit", "Hardware", 4900, 2400, 0.7),
            ("Stream Capture Card", "Hardware", 15900, 9300, 0.7),
            ("Collector Figure", "Collectibles", 4500, 1800, 1.2),
            ("Game Soundtrack Vinyl", "Collectibles", 3500, 1400, 0.6),
            ("Limited Art Book", "Collectibles", 3900, 1600, 0.8),
            ("Mystery Pin Pack", "Collectibles", 1200, 350, 1.8),
        ]
        for index, (name, category, price, cost, demand) in enumerate(catalog, 1):
            stock = rng.randint(8, 25) if category != "Consoles" else rng.randint(4, 10)
            connection.execute(
                "INSERT INTO products(name,sku,category,supplier_id,price_cents,base_price_cents,cost_cents,stock,reorder_point,demand) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    name,
                    f"PIX-{index:04d}",
                    category,
                    1 + (index % 3),
                    price,
                    price,
                    cost,
                    stock,
                    5,
                    demand,
                ),
            )
            connection.execute(
                "INSERT INTO inventory_logs(product_id,day,change_amount,reason) VALUES (?,0,?,'Opening stock')",
                (index, stock),
            )
        names = [
            "Avery Chen",
            "Riley Patel",
            "Morgan Smith",
            "Taylor Kim",
            "Jamie Garcia",
            "Casey Brooks",
            "Robin Park",
            "Drew Wilson",
            "Harper Ali",
            "Sage Miller",
            "Quinn Davis",
            "Cameron Reed",
            "Rowan Lee",
            "Emery Jones",
            "Skyler Cruz",
            "Alex Diaz",
        ]
        for index, name in enumerate(names, 1):
            connection.execute(
                "INSERT INTO customers(name,email,tier) VALUES (?,?,?)",
                (
                    name,
                    f"customer{index}@example.test",
                    "Premium" if index % 5 == 0 else "Regular",
                ),
            )
        self._ledger(connection, "opening_capital", 2500000, "Owner opening cash")
        for index in range(8):
            order_id = self._create_order(
                connection, 1 + index, [{"product_id": 5 + index, "quantity": 1}], 0
            )
            if index > 1:
                self._pay(connection, order_id, True)
            if index > 3:
                self._transition(connection, order_id, "Shipped")
            if index > 5:
                self._transition(connection, order_id, "Delivered")
        self._event(
            connection,
            "system",
            "PixelLedger opened with a stocked catalog and eight starter orders.",
        )
        self._history(connection, 0, 0)

    def _order(self, connection, order_id):
        row = connection.execute(
            "SELECT * FROM orders WHERE id=?", (order_id,)
        ).fetchone()
        if row is None:
            raise RuleError("Order not found")
        return row

    def _create_order(self, connection, customer_id, items, discount):
        if not connection.execute(
            "SELECT 1 FROM customers WHERE id=?", (customer_id,)
        ).fetchone():
            raise RuleError("Customer not found")
        if not items or len(items) > 20:
            raise RuleError("Choose between one and twenty products")
        discount_bps = int(Decimal(str(discount)) * 100)
        if not 0 <= discount_bps <= 2500:
            raise RuleError("Discount must be between 0 and 25 percent")
        quantities = {}
        for item in items:
            quantity = item["quantity"]
            if not isinstance(quantity, int) or not 1 <= quantity <= 100:
                raise RuleError("Each quantity must be between 1 and 100")
            quantities[item["product_id"]] = (
                quantities.get(item["product_id"], 0) + quantity
            )
        snapshots = []
        for product_id, quantity in quantities.items():
            product = connection.execute(
                "SELECT * FROM products WHERE id=?", (product_id,)
            ).fetchone()
            if product is None:
                raise RuleError("Product not found")
            if quantity > 100 or product["stock"] < quantity:
                raise RuleError(f"Not enough available stock for {product['name']}")
            net = rounded(product["price_cents"] * quantity * (10000 - discount_bps))
            tax = rounded(net * 800)
            snapshots.append((product, quantity, tax, net + tax))
        total = sum(item[3] for item in snapshots)
        cursor = connection.execute(
            "INSERT INTO orders(customer_id,status,payment_status,total_cents,created_day) VALUES (?,'Pending','Unpaid',?,?)",
            (customer_id, total, self._meta(connection, "day")),
        )
        order_id = cursor.lastrowid
        for product, quantity, tax, line_total in snapshots:
            connection.execute(
                "INSERT INTO order_items(order_id,product_id,product_name,quantity,unit_price_cents,cost_cents,discount_bps,tax_cents,total_cents) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    order_id,
                    product["id"],
                    product["name"],
                    quantity,
                    product["price_cents"],
                    product["cost_cents"],
                    discount_bps,
                    tax,
                    line_total,
                ),
            )
            self._inventory(
                connection, product["id"], -quantity, f"Reserved for order #{order_id}"
            )
        self._event(
            connection,
            "order",
            f"Order #{order_id} reserved {sum(quantities.values())} units. Payment is pending.",
        )
        return order_id

    def _pay(self, connection, order_id, success):
        order = self._order(connection, order_id)
        if order["status"] == "Cancelled":
            raise RuleError("Canceled orders cannot be charged")
        if order["payment_status"] == "Paid":
            return
        if order["payment_status"] in {"Refunded", "Partial refund"}:
            raise RuleError("A refunded order cannot be charged again")
        sales = connection.execute(
            "SELECT SUM(total_cents-tax_cents) FROM order_items WHERE order_id=?",
            (order_id,),
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO payments(order_id,day,kind,amount_cents,net_sales_cents) VALUES (?,?,?,?,?)",
            (
                order_id,
                self._meta(connection, "day"),
                "capture" if success else "failed",
                order["total_cents"] if success else 0,
                sales if success else 0,
            ),
        )
        if success:
            connection.execute(
                "UPDATE orders SET payment_status='Paid',status='Processing' WHERE id=?",
                (order_id,),
            )
            self._ledger(
                connection,
                "payment",
                order["total_cents"],
                f"Payment for order #{order_id}",
            )
            spent = connection.execute(
                "SELECT COALESCE(SUM(CASE WHEN p.kind='capture' THEN p.amount_cents WHEN p.kind='refund' THEN -p.amount_cents ELSE 0 END),0) FROM payments p JOIN orders o ON o.id=p.order_id WHERE o.customer_id=?",
                (order["customer_id"],),
            ).fetchone()[0]
            tier = "VIP" if spent >= 1000000 else "Premium" if spent >= 300000 else None
            if tier:
                current = connection.execute(
                    "SELECT tier FROM customers WHERE id=?", (order["customer_id"],)
                ).fetchone()[0]
                if current != "VIP":
                    connection.execute(
                        "UPDATE customers SET tier=? WHERE id=?",
                        (tier, order["customer_id"]),
                    )
            self._event(
                connection,
                "payment",
                f"Payment captured for order #{order_id}. Ready for fulfillment.",
            )
        else:
            connection.execute(
                "UPDATE orders SET payment_status='Failed' WHERE id=?", (order_id,)
            )
            self._event(
                connection,
                "payment",
                f"Payment failed for order #{order_id}. No cash was collected; it can be retried.",
            )

    def _transition(self, connection, order_id, status):
        order = self._order(connection, order_id)
        if order["status"] == status:
            return
        if status == "Cancelled":
            if order["status"] not in {"Pending", "Processing"}:
                raise RuleError("Only pending or processing orders can be canceled")
            for line in connection.execute(
                "SELECT * FROM order_items WHERE order_id=?", (order_id,)
            ).fetchall():
                self._inventory(
                    connection,
                    line["product_id"],
                    line["quantity"],
                    f"Order #{order_id} canceled",
                )
            if order["payment_status"] == "Paid":
                self._refund(
                    connection,
                    order_id,
                    order["total_cents"],
                    "Canceled order",
                    connection.execute(
                        "SELECT SUM(total_cents-tax_cents) FROM order_items WHERE order_id=?",
                        (order_id,),
                    ).fetchone()[0],
                )
                connection.execute(
                    "UPDATE order_items SET refunded_cents=total_cents WHERE order_id=?",
                    (order_id,),
                )
            connection.execute(
                "UPDATE orders SET status='Cancelled' WHERE id=?", (order_id,)
            )
            self._event(
                connection,
                "order",
                f"Order #{order_id} canceled. Reserved stock released.",
            )
            return
        allowed = {
            "Pending": "Processing",
            "Processing": "Shipped",
            "Shipped": "Delivered",
        }
        if allowed.get(order["status"]) != status:
            raise RuleError("That order status transition is not allowed")
        if order["payment_status"] != "Paid":
            raise RuleError("Capture payment before fulfillment")
        day = self._meta(connection, "day")
        connection.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
        if status == "Shipped":
            delay = self._meta(connection, "market").get("delivery_delay", 0)
            connection.execute(
                "UPDATE orders SET ship_day=?,delivery_day=? WHERE id=?",
                (day, day + 2 + delay, order_id),
            )
        elif status == "Delivered":
            connection.execute(
                "UPDATE orders SET delivery_day=? WHERE id=?", (day, order_id)
            )
            rating = 5 if day - order["created_day"] <= 4 else 3
            connection.execute(
                "INSERT OR IGNORE INTO reviews(order_id,rating,day) VALUES (?,?,?)",
                (order_id, rating, day),
            )
            average = connection.execute(
                "SELECT AVG(rating) FROM (SELECT rating FROM reviews ORDER BY id DESC LIMIT 30)"
            ).fetchone()[0]
            self._meta(connection, "reputation", round(average * 20))
        self._event(
            connection, "fulfillment", f"Order #{order_id} marked {status.lower()}."
        )

    def _refund(self, connection, order_id, amount, reason, sales_refund):
        net_paid = connection.execute(
            "SELECT COALESCE(SUM(CASE WHEN kind='capture' THEN amount_cents WHEN kind='refund' THEN -amount_cents ELSE 0 END),0) FROM payments WHERE order_id=?",
            (order_id,),
        ).fetchone()[0]
        if not 0 < amount <= net_paid:
            raise RuleError("Refund exceeds the remaining captured payment")
        connection.execute(
            "INSERT INTO payments(order_id,day,kind,amount_cents,net_sales_cents) VALUES (?,?,'refund',?,?)",
            (order_id, self._meta(connection, "day"), amount, -sales_refund),
        )
        connection.execute(
            "UPDATE orders SET payment_status=? WHERE id=?",
            ("Refunded" if amount == net_paid else "Partial refund", order_id),
        )
        self._ledger(connection, "refund", -amount, f"{reason}: order #{order_id}")

    def _return(self, connection, order_id, line_id, quantity, restock, reason):
        order = self._order(connection, order_id)
        if order["status"] != "Delivered":
            raise RuleError("Only delivered orders can be returned")
        line = connection.execute(
            "SELECT * FROM order_items WHERE id=? AND order_id=?", (line_id, order_id)
        ).fetchone()
        if line is None or not 1 <= quantity <= line["quantity"] - line["returned_qty"]:
            raise RuleError("Return quantity exceeds the remaining purchased units")
        new_quantity = line["returned_qty"] + quantity
        target = (line["total_cents"] * new_quantity) // line["quantity"]
        refund = target - line["refunded_cents"]
        tax_refund = (line["tax_cents"] * new_quantity) // line["quantity"] - (
            line["tax_cents"] * line["returned_qty"]
        ) // line["quantity"]
        self._refund(
            connection, order_id, refund, "Customer return", refund - tax_refund
        )
        connection.execute(
            "UPDATE order_items SET returned_qty=?,refunded_cents=? WHERE id=?",
            (new_quantity, target, line_id),
        )
        connection.execute(
            "INSERT INTO returns(line_id,day,quantity,refund_cents,restock,reason) VALUES (?,?,?,?,?,?)",
            (
                line_id,
                self._meta(connection, "day"),
                quantity,
                refund,
                int(restock),
                reason,
            ),
        )
        if restock:
            self._inventory(
                connection, line["product_id"], quantity, f"Return on order #{order_id}"
            )
        self._event(
            connection,
            "return",
            f"Order #{order_id}: {quantity} returned units, {'restocked' if restock else 'written off'}. Refund issued.",
        )

    def _once(self, connection, scope, request_id, payload, callback):
        if not request_id:
            return callback()
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()
        row = connection.execute(
            "SELECT * FROM requests WHERE scope=? AND request_id=?", (scope, request_id)
        ).fetchone()
        if row:
            if row["payload_hash"] != digest:
                raise RuleError("This request ID was already used for different inputs")
            return json.loads(row["result"])
        result = callback()
        connection.execute(
            "INSERT INTO requests(scope,request_id,payload_hash,result) VALUES (?,?,?,?)",
            (scope, request_id, digest, json.dumps(result)),
        )
        return result

    def create_order(self, customer_id, items, discount=0, request_id=None):
        with self.db.transaction() as connection:
            self._once(
                connection,
                "order",
                request_id,
                {"customer_id": customer_id, "items": items, "discount": str(discount)},
                lambda: self._create_order(connection, customer_id, items, discount),
            )
            self._refresh_history(connection)
        return self.state()

    def pay(self, order_id, success=True):
        with self.db.transaction() as connection:
            self._pay(connection, order_id, success)
            self._refresh_history(connection)
        return self.state()

    def transition(self, order_id, status):
        with self.db.transaction() as connection:
            self._transition(connection, order_id, status)
            self._refresh_history(connection)
        return self.state()

    def return_items(
        self, order_id, line_id, quantity, restock=True, reason="Changed mind"
    ):
        with self.db.transaction() as connection:
            self._return(connection, order_id, line_id, quantity, restock, reason)
            self._refresh_history(connection)
        return self.state()

    def set_price(self, product_id, price_cents):
        if not isinstance(price_cents, int) or not 100 <= price_cents <= 5000000:
            raise RuleError("Price must be between $1 and $50,000")
        with self.db.transaction() as connection:
            if (
                connection.execute(
                    "UPDATE products SET price_cents=? WHERE id=?",
                    (price_cents, product_id),
                ).rowcount
                != 1
            ):
                raise RuleError("Product not found")
            self._event(
                connection,
                "pricing",
                f"Product #{product_id} repriced. Existing orders keep their original prices.",
            )
        return self.state()

    def restock(self, product_id, quantity):
        if not isinstance(quantity, int) or not 1 <= quantity <= 1000:
            raise RuleError("Receive between one and 1,000 units")
        with self.db.transaction() as connection:
            product = connection.execute(
                "SELECT * FROM products WHERE id=?", (product_id,)
            ).fetchone()
            if product is None:
                raise RuleError("Product not found")
            cost = product["cost_cents"] * quantity
            if self._cash(connection) < cost:
                raise RuleError("Not enough cash to receive this stock")
            self._ledger(
                connection,
                "stock_purchase",
                -cost,
                f"Received {quantity} units of {product['name']}",
            )
            self._inventory(connection, product_id, quantity, "Stock received")
            self._event(
                connection,
                "inventory",
                f"Received {quantity} units of {product['name']}.",
            )
            self._refresh_history(connection)
        return self.state()

    def add_customer(self, name, email):
        if not name.strip() or "@" not in email or len(email) > 200:
            raise RuleError("Enter a name and valid email address")
        with self.db.transaction() as connection:
            connection.execute(
                "INSERT INTO customers(name,email) VALUES (?,?)",
                (name.strip(), email.strip().lower()),
            )
            self._event(
                connection, "customer", f"{name.strip()} joined the customer list."
            )
        return self.state()

    def _metrics(self, connection):
        gross, refunds = connection.execute(
            "SELECT COALESCE(SUM(CASE WHEN kind='capture' THEN amount_cents ELSE 0 END),0),COALESCE(SUM(CASE WHEN kind='refund' THEN amount_cents ELSE 0 END),0) FROM payments"
        ).fetchone()
        net_sales = connection.execute(
            "SELECT COALESCE(SUM(net_sales_cents),0) FROM payments"
        ).fetchone()[0]
        cogs = 0
        restocked_quantities = dict(
            connection.execute(
                "SELECT line_id,SUM(quantity) FROM returns WHERE restock=1 GROUP BY line_id"
            ).fetchall()
        )
        for line in connection.execute(
            "SELECT i.* FROM order_items i JOIN orders o ON o.id=i.order_id WHERE o.status!='Cancelled' AND EXISTS(SELECT 1 FROM payments p WHERE p.order_id=o.id AND p.kind='capture')"
        ).fetchall():
            restocked = restocked_quantities.get(line["id"], 0)
            cogs += line["cost_cents"] * (line["quantity"] - restocked)
        expenses = -connection.execute(
            "SELECT COALESCE(SUM(amount_cents),0) FROM ledger WHERE kind='operating_cost'"
        ).fetchone()[0]
        return {
            "gross_sales_cents": gross,
            "refunds_cents": refunds,
            "net_sales_cents": net_sales,
            "tax_collected_cents": gross - refunds - net_sales,
            "cogs_cents": cogs,
            "operating_cost_cents": expenses,
            "profit_cents": net_sales - cogs - expenses,
            "inventory_value_cents": connection.execute(
                "SELECT SUM(stock*cost_cents) FROM products"
            ).fetchone()[0]
            or 0,
            "orders_count": connection.execute(
                "SELECT COUNT(*) FROM orders"
            ).fetchone()[0],
            "customers_count": connection.execute(
                "SELECT COUNT(*) FROM customers"
            ).fetchone()[0],
            "low_stock_count": connection.execute(
                "SELECT COUNT(*) FROM products WHERE stock<=reorder_point"
            ).fetchone()[0],
            "lost_sales": self._meta(connection, "lost_sales"),
            "reputation": self._meta(connection, "reputation"),
        }

    def _history(self, connection, orders_count, lost_sales):
        day = self._meta(connection, "day")
        payments = connection.execute(
            "SELECT COALESCE(SUM(net_sales_cents),0) FROM payments WHERE day=?", (day,)
        ).fetchone()[0]
        orders_count = connection.execute(
            "SELECT COUNT(*) FROM orders WHERE created_day=?", (day,)
        ).fetchone()[0]
        connection.execute(
            "INSERT OR REPLACE INTO daily_history(day,net_sales_cents,orders_count,lost_sales,cash_cents) VALUES (?,?,?,?,?)",
            (day, payments, orders_count, lost_sales, self._cash(connection)),
        )

    def _advance_day(self, connection):
        day = self._meta(connection, "day") + 1
        self._meta(connection, "day", day)
        rng = random.Random(self._meta(connection, "seed") + day * 9973)
        if day % 3 == 1:
            market = rng.choice(
                [
                    {
                        "title": "Release week",
                        "description": "A new release brings more game buyers.",
                        "category": "Games",
                        "multiplier": 1.8,
                        "delivery_delay": 0,
                    },
                    {
                        "title": "Console spotlight",
                        "description": "Hardware chatter boosts interest in consoles.",
                        "category": "Consoles",
                        "multiplier": 1.7,
                        "delivery_delay": 0,
                    },
                    {
                        "title": "Creator season",
                        "description": "Streaming setups are in demand.",
                        "category": "Accessories",
                        "multiplier": 1.6,
                        "delivery_delay": 0,
                    },
                    {
                        "title": "Quiet market",
                        "description": "Demand cools. Competitive prices and good service help.",
                        "category": "All",
                        "multiplier": 0.75,
                        "delivery_delay": 0,
                    },
                    {
                        "title": "Carrier congestion",
                        "description": "New shipments take an extra day to arrive.",
                        "category": "All",
                        "multiplier": 1.0,
                        "delivery_delay": 1,
                    },
                ]
            )
            self._meta(connection, "market", market)
            self._event(
                connection, "market", market["title"] + ": " + market["description"]
            )
        # The day starts by processing existing orders, never shipping twice.
        for order in connection.execute(
            "SELECT * FROM orders WHERE status NOT IN ('Cancelled','Delivered') ORDER BY id"
        ).fetchall():
            if (
                order["payment_status"] in {"Unpaid", "Failed"}
                and day - order["created_day"] >= 2
            ):
                self._transition(connection, order["id"], "Cancelled")
            elif order["status"] == "Processing" and order["created_day"] < day:
                self._transition(connection, order["id"], "Shipped")
            elif order["status"] == "Shipped" and order["delivery_day"] <= day:
                self._transition(connection, order["id"], "Delivered")
        if rng.random() < 0.65:
            sequence = (
                connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0] + 1
            )
            name = (
                rng.choice(
                    [
                        "Avery",
                        "Riley",
                        "Morgan",
                        "Taylor",
                        "Jamie",
                        "Casey",
                        "Robin",
                        "Drew",
                    ]
                )
                + " "
                + rng.choice(["Chen", "Patel", "Brooks", "Lee", "Rivera", "Reed"])
            )
            connection.execute(
                "INSERT INTO customers(name,email) VALUES (?,?)",
                (name, f"player{sequence}@example.test"),
            )
        products = connection.execute("SELECT * FROM products ORDER BY id").fetchall()
        market = self._meta(connection, "market")
        weights = [
            p["demand"]
            * max(0.12, min(2.5, (p["base_price_cents"] / p["price_cents"]) ** 1.4))
            * (
                market["multiplier"]
                if market["category"] in {p["category"], "All"}
                else 1
            )
            for p in products
        ]
        reputation = self._meta(connection, "reputation")
        weekend = (date(2026, 1, 5) + timedelta(days=day)).weekday() >= 5
        demand_count = max(
            1, round(rng.randint(3, 8) * (reputation / 80) * (1.3 if weekend else 1))
        )
        orders_count, lost_sales = 0, 0
        customers = [
            row[0] for row in connection.execute("SELECT id FROM customers ORDER BY id")
        ]
        for _ in range(demand_count):
            product = rng.choices(products, weights=weights, k=1)[0]
            quantity = rng.choices([1, 2, 3], weights=[8, 2, 1], k=1)[0]
            available = connection.execute(
                "SELECT stock FROM products WHERE id=?", (product["id"],)
            ).fetchone()[0]
            price_factor = max(
                0.15, min(1.0, product["base_price_cents"] / product["price_cents"])
            )
            if available < quantity or rng.random() > price_factor:
                lost_sales += 1
                continue
            order_id = self._create_order(
                connection,
                rng.choice(customers),
                [{"product_id": product["id"], "quantity": quantity}],
                0,
            )
            self._pay(connection, order_id, rng.random() > 0.08)
            orders_count += 1
        self._meta(
            connection, "lost_sales", self._meta(connection, "lost_sales") + lost_sales
        )
        if lost_sales:
            self._meta(
                connection,
                "reputation",
                max(25, self._meta(connection, "reputation") - min(4, lost_sales)),
            )
        self._ledger(
            connection, "operating_cost", -18000, "Daily staffing, rent and utilities"
        )
        self._event(
            connection,
            "simulation",
            f"Day {day}: {orders_count} new orders, {lost_sales} missed purchases. Daily overhead charged.",
        )
        self._history(connection, orders_count, lost_sales)

    def advance(self, days=1, request_id=None):
        if not isinstance(days, int) or not 1 <= days <= 30:
            raise RuleError("Advance between one and thirty days")
        with self.db.transaction() as connection:

            def apply():
                for _ in range(days):
                    self._advance_day(connection)
                return {"day": self._meta(connection, "day")}

            self._once(connection, "simulation", request_id, {"days": days}, apply)
        return self.state()

    def reset(self, seed=42):
        with self.db.transaction() as connection:
            for table in [
                "requests",
                "reviews",
                "daily_history",
                "events",
                "ledger",
                "inventory_logs",
                "returns",
                "payments",
                "order_items",
                "orders",
                "products",
                "customers",
                "employees",
                "suppliers",
                "metadata",
            ]:
                connection.execute(f'DELETE FROM "{table}"')
            connection.execute(
                "DELETE FROM sqlite_sequence WHERE name IN ('reviews','events','ledger','inventory_logs','returns','payments','order_items','orders','products','customers','employees','suppliers')"
            )
            self._seed(connection, seed)
        return self.state()

    def _refresh_history(self, connection):
        row = connection.execute(
            "SELECT lost_sales FROM daily_history WHERE day=?",
            (self._meta(connection, "day"),),
        ).fetchone()
        self._history(connection, 0, row[0] if row else 0)

    def state(self):
        connection = self.db.connect()
        try:
            connection.execute("BEGIN")
            products = [
                dict(row)
                for row in connection.execute(
                    "SELECT p.*,s.name AS supplier FROM products p JOIN suppliers s ON s.id=p.supplier_id ORDER BY p.id"
                )
            ]
            customers = [
                dict(row)
                for row in connection.execute(
                    "SELECT c.*,COUNT(DISTINCT o.id) AS order_count,COALESCE(SUM(CASE WHEN p.kind='capture' THEN p.amount_cents WHEN p.kind='refund' THEN -p.amount_cents ELSE 0 END),0) AS spent_cents FROM customers c LEFT JOIN orders o ON o.customer_id=c.id LEFT JOIN payments p ON p.order_id=o.id GROUP BY c.id ORDER BY c.id"
                )
            ]
            orders = [
                dict(row)
                for row in connection.execute(
                    "SELECT o.*,c.name AS customer_name FROM orders o JOIN customers c ON c.id=o.customer_id ORDER BY o.id DESC"
                )
            ]
            grouped = {}
            for row in connection.execute("SELECT * FROM order_items ORDER BY id"):
                grouped.setdefault(row["order_id"], []).append(dict(row))
            for order in orders:
                order["items"] = grouped.get(order["id"], [])
            day = self._meta(connection, "day")
            market = self._meta(connection, "market")
            reputation = self._meta(connection, "reputation")
            for product in products:
                product["base_demand"] = product["demand"]
                product["demand"] = round(
                    product["demand"]
                    * max(
                        0.12,
                        min(
                            2.5,
                            (product["base_price_cents"] / product["price_cents"])
                            ** 1.4,
                        ),
                    )
                    * (
                        market["multiplier"]
                        if market["category"] in {product["category"], "All"}
                        else 1
                    )
                    * (reputation / 80),
                    2,
                )
            return {
                "day": day,
                "date": (date(2026, 1, 5) + timedelta(days=day)).isoformat(),
                "seed": self._meta(connection, "seed"),
                "cash_cents": self._cash(connection),
                "market": self._meta(connection, "market"),
                "metrics": self._metrics(connection),
                "products": products,
                "customers": customers,
                "orders": orders,
                "history": [
                    dict(row)
                    for row in connection.execute(
                        "SELECT * FROM daily_history ORDER BY day DESC LIMIT 30"
                    )
                ][::-1],
                "events": [
                    dict(row)
                    for row in connection.execute(
                        "SELECT * FROM events ORDER BY id DESC LIMIT 100"
                    )
                ],
                "ledger": [
                    dict(row)
                    for row in connection.execute(
                        "SELECT * FROM ledger ORDER BY id DESC LIMIT 100"
                    )
                ],
            }
        finally:
            connection.close()
