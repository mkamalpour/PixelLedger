CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS suppliers (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS employees (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, role TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS customers (
 id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
 tier TEXT NOT NULL DEFAULT 'Regular' CHECK(tier IN ('Regular','VIP','Premium','Guest')));
CREATE TABLE IF NOT EXISTS products (
 id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, sku TEXT NOT NULL UNIQUE,
 category TEXT NOT NULL, supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
 price_cents INTEGER NOT NULL CHECK(price_cents>0), base_price_cents INTEGER NOT NULL CHECK(base_price_cents>0),
 cost_cents INTEGER NOT NULL CHECK(cost_cents>=0), stock INTEGER NOT NULL CHECK(stock>=0),
 reorder_point INTEGER NOT NULL DEFAULT 5 CHECK(reorder_point>=0), demand REAL NOT NULL CHECK(demand>0));
CREATE TABLE IF NOT EXISTS orders (
 id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER NOT NULL REFERENCES customers(id),
 status TEXT NOT NULL CHECK(status IN ('Pending','Processing','Shipped','Delivered','Cancelled')),
 payment_status TEXT NOT NULL CHECK(payment_status IN ('Unpaid','Failed','Paid','Partial refund','Refunded')),
 total_cents INTEGER NOT NULL CHECK(total_cents>0), created_day INTEGER NOT NULL,
 ship_day INTEGER, delivery_day INTEGER);
CREATE TABLE IF NOT EXISTS order_items (
 id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL REFERENCES orders(id),
 product_id INTEGER NOT NULL REFERENCES products(id), product_name TEXT NOT NULL,
 quantity INTEGER NOT NULL CHECK(quantity>0), unit_price_cents INTEGER NOT NULL CHECK(unit_price_cents>0),
 cost_cents INTEGER NOT NULL CHECK(cost_cents>=0), discount_bps INTEGER NOT NULL CHECK(discount_bps BETWEEN 0 AND 2500),
 tax_cents INTEGER NOT NULL CHECK(tax_cents>=0), total_cents INTEGER NOT NULL CHECK(total_cents>0),
 returned_qty INTEGER NOT NULL DEFAULT 0 CHECK(returned_qty BETWEEN 0 AND quantity),
 refunded_cents INTEGER NOT NULL DEFAULT 0 CHECK(refunded_cents BETWEEN 0 AND total_cents));
CREATE TABLE IF NOT EXISTS payments (
 id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL REFERENCES orders(id),
 day INTEGER NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('capture','failed','refund')),
 amount_cents INTEGER NOT NULL CHECK(amount_cents>=0), net_sales_cents INTEGER NOT NULL DEFAULT 0);
CREATE UNIQUE INDEX IF NOT EXISTS one_capture_per_order ON payments(order_id) WHERE kind='capture';
CREATE TABLE IF NOT EXISTS returns (
 id INTEGER PRIMARY KEY AUTOINCREMENT, line_id INTEGER NOT NULL REFERENCES order_items(id),
 day INTEGER NOT NULL, quantity INTEGER NOT NULL CHECK(quantity>0), refund_cents INTEGER NOT NULL CHECK(refund_cents>0),
 restock INTEGER NOT NULL CHECK(restock IN (0,1)), reason TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS inventory_logs (
 id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER NOT NULL REFERENCES products(id),
 day INTEGER NOT NULL, change_amount INTEGER NOT NULL, reason TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ledger (
 id INTEGER PRIMARY KEY AUTOINCREMENT, day INTEGER NOT NULL, kind TEXT NOT NULL,
 amount_cents INTEGER NOT NULL, description TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, day INTEGER NOT NULL, kind TEXT NOT NULL, message TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS daily_history (
 day INTEGER PRIMARY KEY, net_sales_cents INTEGER NOT NULL, orders_count INTEGER NOT NULL,
 lost_sales INTEGER NOT NULL, cash_cents INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS reviews (
 id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL UNIQUE REFERENCES orders(id),
 rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5), day INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS requests (
 scope TEXT NOT NULL, request_id TEXT NOT NULL, payload_hash TEXT NOT NULL, result TEXT NOT NULL,
 PRIMARY KEY(scope,request_id));
CREATE INDEX IF NOT EXISTS orders_by_customer ON orders(customer_id);
CREATE INDEX IF NOT EXISTS orders_by_status ON orders(status);
CREATE INDEX IF NOT EXISTS lines_by_order ON order_items(order_id);
CREATE INDEX IF NOT EXISTS payments_by_order ON payments(order_id);
CREATE INDEX IF NOT EXISTS inventory_by_product ON inventory_logs(product_id);
CREATE INDEX IF NOT EXISTS ledger_by_day ON ledger(day);
CREATE VIEW IF NOT EXISTS order_summary AS
 SELECT o.id, c.name AS customer, o.status, o.payment_status, o.total_cents,
 o.created_day, COALESCE(SUM(i.quantity),0) AS units
 FROM orders o JOIN customers c ON c.id=o.customer_id LEFT JOIN order_items i ON i.order_id=o.id
 GROUP BY o.id,c.name,o.status,o.payment_status,o.total_cents,o.created_day;
