-- Run section by section in MySQL Workbench, not all at once.
-- DDL practice is isolated from hardware_world_simple.
CREATE DATABASE IF NOT EXISTS hardware_world_practice;
USE hardware_world_practice;

-- 1. Create tables. This is a teaching example, not the complete app schema.
CREATE TABLE IF NOT EXISTS categories (
 id INT AUTO_INCREMENT PRIMARY KEY,
 name VARCHAR(100) NOT NULL UNIQUE
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS products (
 id INT AUTO_INCREMENT PRIMARY KEY,
 name VARCHAR(100) NOT NULL,
 category_id INT NOT NULL,
 price DECIMAL(12,2) NOT NULL CHECK(price>=0),
 stock INT NOT NULL DEFAULT 0 CHECK(stock>=0),
 FOREIGN KEY(category_id) REFERENCES categories(id)
) ENGINE=InnoDB;

-- 2. Insert data, then select, join, filter and aggregate.
INSERT INTO categories(name) VALUES('Tools');
SET @category_id=LAST_INSERT_ID();
INSERT INTO products(name,category_id,price,stock)
VALUES('Hammer',@category_id,20000,10),('Saw',@category_id,30000,4);
SELECT * FROM products WHERE stock<5;
SELECT p.name,c.name AS category,p.price FROM products p
JOIN categories c ON c.id=p.category_id ORDER BY p.price DESC;
SELECT c.name,COUNT(p.id) AS product_count,SUM(p.price*p.stock) AS stock_value
FROM categories c LEFT JOIN products p ON p.category_id=c.id
GROUP BY c.id,c.name;

-- 3. Show atomicity: the first update is undone; the second is committed.
SET @product_id=(SELECT MIN(id) FROM products);
START TRANSACTION;
SELECT * FROM products WHERE id=@product_id FOR UPDATE;
UPDATE products SET stock=stock-2 WHERE id=@product_id AND stock>=2;
ROLLBACK;
SELECT * FROM products WHERE id=@product_id;
START TRANSACTION;
UPDATE products SET stock=stock+1 WHERE id=@product_id;
COMMIT;

-- 4. Clean a value; inspect the result before deciding to commit.
START TRANSACTION;
UPDATE products SET name=TRIM(name) WHERE id=@product_id;
SELECT name FROM products WHERE id=@product_id;
ROLLBACK;

-- 5. DELETE removes rows but retains the structure.
START TRANSACTION;
DELETE FROM products WHERE id=@product_id;
ROLLBACK;

-- 6. A real trigger demonstration on practice-only tables.
CREATE TABLE IF NOT EXISTS stock_events (
 id INT AUTO_INCREMENT PRIMARY KEY,
 product_id INT NOT NULL, old_stock INT NOT NULL, new_stock INT NOT NULL,
 changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
DROP TRIGGER IF EXISTS practice_stock_audit;
DELIMITER $$
CREATE TRIGGER practice_stock_audit AFTER UPDATE ON products
FOR EACH ROW
BEGIN
 IF OLD.stock <> NEW.stock THEN
  INSERT INTO stock_events(product_id,old_stock,new_stock)
  VALUES(NEW.id,OLD.stock,NEW.stock);
 END IF;
END$$
DELIMITER ;
UPDATE products SET stock=stock+1 WHERE id=@product_id;
SELECT * FROM stock_events;
SHOW TRIGGERS;

-- 7. Save the structure before dropping the CHILD table.
SHOW CREATE TABLE products;
-- Copy the returned CREATE TABLE statement into another Workbench tab first.
-- DROP TABLE commits implicitly and cannot be undone by ROLLBACK.
DROP TABLE products;
CREATE TABLE products (
 id INT AUTO_INCREMENT PRIMARY KEY,
 name VARCHAR(100) NOT NULL,
 category_id INT NOT NULL,
 price DECIMAL(12,2) NOT NULL CHECK(price>=0),
 stock INT NOT NULL DEFAULT 0 CHECK(stock>=0),
 FOREIGN KEY(category_id) REFERENCES categories(id)
) ENGINE=InnoDB;
SHOW TABLES;
-- Recreating a table restores its structure, not its deleted records.
-- DROP TABLE also removed its trigger: rerun section 6 to recreate it.
-- Rerunning section 2 without clearing practice data can hit the unique category name.

-- 8. Read-only queries against the actual application database.
USE hardware_world_simple;
SELECT s.id,s.customer_name,SUM(i.quantity*i.unit_price) AS total
FROM sales s JOIN sale_items i ON i.sale_id=s.id GROUP BY s.id;
SELECT e.name,SUM(i.quantity*i.unit_price) AS total_sales
FROM employees e JOIN sales s ON s.employee_id=e.id
JOIN sale_items i ON i.sale_id=s.id GROUP BY e.id,e.name;
SELECT p.name FROM products p LEFT JOIN sale_items i ON i.product_id=p.id
WHERE i.id IS NULL;
SELECT s.name AS supplier,p.name AS product,x.cost_price,x.lead_time_days
FROM supply x JOIN suppliers s ON s.id=x.supplier_id
JOIN products p ON p.id=x.product_id;
SELECT e.name AS employee,manager.name AS supervisor
FROM employees e LEFT JOIN employees manager ON manager.id=e.supervisor_id;
SELECT e.name,p.pay_month,p.gross_pay,p.deductions,p.net_pay
FROM payroll p JOIN employees e ON e.id=p.employee_id;
SELECT source_type,SUM(amount) AS total FROM ledger_entries GROUP BY source_type;
SHOW CREATE TABLE sale_items;
SHOW TRIGGERS;
