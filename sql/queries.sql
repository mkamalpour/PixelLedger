-- Examples for the application's read-only SQLite SQL lab.
-- Money is stored in integer cents; divide by 100.0 for display only.

SELECT category, COUNT(*) AS products, SUM(stock) AS available_units
FROM products GROUP BY category ORDER BY category;

SELECT name, stock, reorder_point, ROUND(price_cents/100.0, 2) AS price
FROM products WHERE stock <= reorder_point ORDER BY stock, name;

SELECT * FROM order_summary ORDER BY id DESC LIMIT 25;

SELECT day, ROUND(SUM(net_sales_cents)/100.0, 2) AS net_sales_excluding_tax
FROM payments GROUP BY day ORDER BY day;

SELECT c.name, COUNT(DISTINCT o.id) AS orders,
       ROUND(SUM(CASE WHEN p.kind='capture' THEN p.amount_cents
                      WHEN p.kind='refund' THEN -p.amount_cents ELSE 0 END)/100.0,2) AS net_paid
FROM customers c LEFT JOIN orders o ON o.customer_id=c.id
LEFT JOIN payments p ON p.order_id=o.id GROUP BY c.id, c.name ORDER BY net_paid DESC;
