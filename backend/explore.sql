-- VS Code: connect to "Hardware World - MySQL" using SQLTools first.
-- Select a statement, right-click, then choose "Run Selected Query".
-- These queries only read data; they do not change your records.

USE hardware_world_simple;

-- 1. Confirm the server and selected database.
SELECT VERSION() AS mysql_version, DATABASE() AS database_name;

-- 2. See all project tables.
SHOW TABLES;

-- 3. Employee accounts (password hashes are deliberately excluded).
SELECT id, name, username, role AS department, active
FROM employees
ORDER BY id;

-- 4. Products and their categories.
SELECT p.id, p.name, c.name AS category, p.price, p.stock, p.reorder_level
FROM products p
JOIN categories c ON c.id = p.category_id
ORDER BY p.name;

-- 5. Low-stock alerts.
SELECT name, stock, reorder_level
FROM products
WHERE stock <= reorder_level
ORDER BY stock, name;

-- 6. Supplier contacts.
SELECT id, name, phone, email
FROM suppliers
ORDER BY name;

-- 7. Sales totals, demonstrating JOIN, SUM and GROUP BY.
SELECT s.id, s.created_at, s.customer_name, e.name AS employee,
       SUM(i.quantity * i.unit_price) AS total
FROM sales s
JOIN employees e ON e.id = s.employee_id
JOIN sale_items i ON i.sale_id = s.id
GROUP BY s.id, s.created_at, s.customer_name, e.name
ORDER BY s.id DESC;

-- 8. Received purchases.
SELECT pu.id, pu.created_at, p.name AS product, su.name AS supplier,
       pu.quantity, pu.unit_cost, pu.quantity * pu.unit_cost AS total
FROM purchases pu
JOIN products p ON p.id = pu.product_id
JOIN suppliers su ON su.id = pu.supplier_id
ORDER BY pu.id DESC;
