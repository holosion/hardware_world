-- Run in MySQL Workbench to create a separate assignment database.

-- Existing live hardware_world_simple records are not modified.

CREATE DATABASE IF NOT EXISTS hardware_world_assignment CHARACTER SET utf8mb4;

USE hardware_world_assignment;

CREATE TABLE IF NOT EXISTS `branches` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `location` varchar(150) NOT NULL,
  `contact_number` varchar(30) NOT NULL DEFAULT '',
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `departments` (
  `id` int NOT NULL AUTO_INCREMENT,
  `branch_id` int NOT NULL,
  `name` varchar(100) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `branch_id` (`branch_id`,`name`),
  CONSTRAINT `departments_ibfk_1` FOREIGN KEY (`branch_id`) REFERENCES `branches` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `customers` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `phone` varchar(30) NOT NULL DEFAULT '',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `employees` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `username` varchar(50) NOT NULL,
  `email` varchar(150) DEFAULT NULL,
  `password_hash` varchar(255) NOT NULL,
  `role` enum('Admin','Sales','Purchasing') NOT NULL DEFAULT 'Sales',
  `active` tinyint(1) NOT NULL DEFAULT '1',
  `department_id` int DEFAULT NULL,
  `supervisor_id` int DEFAULT NULL,
  `nin` varchar(30) DEFAULT NULL,
  `phone` varchar(30) NOT NULL DEFAULT '',
  `date_hired` date DEFAULT NULL,
  `salary` decimal(12,2) NOT NULL DEFAULT '0.00',
  `job_type` enum('Cashier','ProcurementOfficer','Accountant','HRStaff','BranchManager') NOT NULL DEFAULT 'Cashier',
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`),
  UNIQUE KEY `email` (`email`),
  UNIQUE KEY `nin` (`nin`),
  KEY `fk_employees_department_id` (`department_id`),
  KEY `fk_employees_supervisor_id` (`supervisor_id`),
  CONSTRAINT `fk_employees_department_id` FOREIGN KEY (`department_id`) REFERENCES `departments` (`id`),
  CONSTRAINT `fk_employees_supervisor_id` FOREIGN KEY (`supervisor_id`) REFERENCES `employees` (`id`),
  CONSTRAINT `employees_chk_1` CHECK ((`salary` >= 0))
) ENGINE=InnoDB  DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `categories` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`)
) ENGINE=InnoDB  DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `suppliers` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `phone` varchar(30) NOT NULL DEFAULT '',
  `email` varchar(150) NOT NULL DEFAULT '',
  `contact_person` varchar(100) NOT NULL DEFAULT '',
  `address` varchar(200) NOT NULL DEFAULT '',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB  DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `products` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `category_id` int NOT NULL,
  `price` decimal(12,2) NOT NULL,
  `stock` int NOT NULL DEFAULT '0',
  `reorder_level` int NOT NULL DEFAULT '5',
  `description` varchar(500) NOT NULL DEFAULT '',
  PRIMARY KEY (`id`),
  KEY `category_id` (`category_id`),
  CONSTRAINT `products_ibfk_1` FOREIGN KEY (`category_id`) REFERENCES `categories` (`id`),
  CONSTRAINT `products_chk_1` CHECK ((`price` >= 0)),
  CONSTRAINT `products_chk_2` CHECK ((`stock` >= 0)),
  CONSTRAINT `products_chk_3` CHECK ((`reorder_level` >= 0))
) ENGINE=InnoDB  DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `sales` (
  `id` int NOT NULL AUTO_INCREMENT,
  `employee_id` int NOT NULL,
  `customer_name` varchar(100) NOT NULL DEFAULT 'Walk-in customer',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `customer_id` int DEFAULT NULL,
  `branch_id` int DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `employee_id` (`employee_id`),
  KEY `fk_sales_customer_id` (`customer_id`),
  KEY `fk_sales_branch_id` (`branch_id`),
  CONSTRAINT `fk_sales_branch_id` FOREIGN KEY (`branch_id`) REFERENCES `branches` (`id`),
  CONSTRAINT `fk_sales_customer_id` FOREIGN KEY (`customer_id`) REFERENCES `customers` (`id`),
  CONSTRAINT `sales_ibfk_1` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`id`)
) ENGINE=InnoDB  DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `sale_items` (
  `id` int NOT NULL AUTO_INCREMENT,
  `sale_id` int NOT NULL,
  `product_id` int NOT NULL,
  `quantity` int NOT NULL,
  `unit_price` decimal(12,2) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_sale_product` (`sale_id`,`product_id`),
  KEY `product_id` (`product_id`),
  CONSTRAINT `sale_items_ibfk_1` FOREIGN KEY (`sale_id`) REFERENCES `sales` (`id`),
  CONSTRAINT `sale_items_ibfk_2` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`),
  CONSTRAINT `sale_items_chk_1` CHECK ((`quantity` > 0)),
  CONSTRAINT `sale_items_chk_2` CHECK ((`unit_price` >= 0))
) ENGINE=InnoDB  DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `cashiers` (
  `employee_id` int NOT NULL,
  `pos_terminal_id` varchar(50) NOT NULL DEFAULT '',
  PRIMARY KEY (`employee_id`),
  CONSTRAINT `cashiers_ibfk_1` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `procurement_officers` (
  `employee_id` int NOT NULL,
  `approval_limit` decimal(12,2) NOT NULL DEFAULT '0.00',
  PRIMARY KEY (`employee_id`),
  CONSTRAINT `procurement_officers_ibfk_1` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`id`) ON DELETE CASCADE,
  CONSTRAINT `procurement_officers_chk_1` CHECK ((`approval_limit` >= 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `accountants` (
  `employee_id` int NOT NULL,
  `certification_number` varchar(100) NOT NULL DEFAULT '',
  PRIMARY KEY (`employee_id`),
  CONSTRAINT `accountants_ibfk_1` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `hr_staff` (
  `employee_id` int NOT NULL,
  `hr_role` varchar(100) NOT NULL DEFAULT '',
  PRIMARY KEY (`employee_id`),
  CONSTRAINT `hr_staff_ibfk_1` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `branch_managers` (
  `employee_id` int NOT NULL,
  `branch_id` int DEFAULT NULL,
  `management_level` varchar(100) NOT NULL DEFAULT '',
  PRIMARY KEY (`employee_id`),
  UNIQUE KEY `branch_id` (`branch_id`),
  CONSTRAINT `branch_managers_ibfk_1` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`id`) ON DELETE CASCADE,
  CONSTRAINT `branch_managers_ibfk_2` FOREIGN KEY (`branch_id`) REFERENCES `branches` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `supply` (
  `supplier_id` int NOT NULL,
  `product_id` int NOT NULL,
  `cost_price` decimal(12,2) NOT NULL,
  `lead_time_days` int NOT NULL DEFAULT '0',
  PRIMARY KEY (`supplier_id`,`product_id`),
  KEY `product_id` (`product_id`),
  CONSTRAINT `supply_ibfk_1` FOREIGN KEY (`supplier_id`) REFERENCES `suppliers` (`id`),
  CONSTRAINT `supply_ibfk_2` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`),
  CONSTRAINT `supply_chk_1` CHECK ((`cost_price` >= 0)),
  CONSTRAINT `supply_chk_2` CHECK ((`lead_time_days` >= 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `purchase_orders` (
  `id` int NOT NULL AUTO_INCREMENT,
  `supplier_id` int NOT NULL,
  `employee_id` int NOT NULL,
  `order_date` date NOT NULL,
  `status` enum('Pending','Received') NOT NULL DEFAULT 'Pending',
  PRIMARY KEY (`id`),
  KEY `supplier_id` (`supplier_id`),
  KEY `employee_id` (`employee_id`),
  CONSTRAINT `purchase_orders_ibfk_1` FOREIGN KEY (`supplier_id`) REFERENCES `suppliers` (`id`),
  CONSTRAINT `purchase_orders_ibfk_2` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `purchase_order_items` (
  `order_id` int NOT NULL,
  `product_id` int NOT NULL,
  `quantity` int NOT NULL,
  `unit_cost` decimal(12,2) NOT NULL,
  PRIMARY KEY (`order_id`,`product_id`),
  KEY `product_id` (`product_id`),
  CONSTRAINT `purchase_order_items_ibfk_1` FOREIGN KEY (`order_id`) REFERENCES `purchase_orders` (`id`),
  CONSTRAINT `purchase_order_items_ibfk_2` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`),
  CONSTRAINT `purchase_order_items_chk_1` CHECK ((`quantity` > 0)),
  CONSTRAINT `purchase_order_items_chk_2` CHECK ((`unit_cost` >= 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `payroll` (
  `id` int NOT NULL AUTO_INCREMENT,
  `employee_id` int NOT NULL,
  `pay_month` date NOT NULL,
  `gross_pay` decimal(12,2) NOT NULL,
  `deductions` decimal(12,2) NOT NULL DEFAULT '0.00',
  `net_pay` decimal(12,2) GENERATED ALWAYS AS ((`gross_pay` - `deductions`)) STORED,
  PRIMARY KEY (`id`),
  UNIQUE KEY `employee_id` (`employee_id`,`pay_month`),
  CONSTRAINT `payroll_ibfk_1` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`id`),
  CONSTRAINT `payroll_chk_1` CHECK ((dayofmonth(`pay_month`) = 1)),
  CONSTRAINT `payroll_chk_2` CHECK ((`gross_pay` >= 0)),
  CONSTRAINT `payroll_chk_3` CHECK (((`deductions` >= 0) and (`deductions` <= `gross_pay`)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `ledger_entries` (
  `id` int NOT NULL AUTO_INCREMENT,
  `entry_date` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `source_type` enum('Sale','Payroll') NOT NULL,
  `sale_id` int DEFAULT NULL,
  `payroll_id` int DEFAULT NULL,
  `amount` decimal(16,2) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `sale_id` (`sale_id`),
  UNIQUE KEY `payroll_id` (`payroll_id`),
  CONSTRAINT `ledger_entries_ibfk_1` FOREIGN KEY (`sale_id`) REFERENCES `sales` (`id`),
  CONSTRAINT `ledger_entries_ibfk_2` FOREIGN KEY (`payroll_id`) REFERENCES `payroll` (`id`),
  CONSTRAINT `ledger_entries_chk_1` CHECK ((((`source_type` = _utf8mb4'Sale') and (`sale_id` is not null) and (`payroll_id` is null) and (`amount` >= 0)) or ((`source_type` = _utf8mb4'Payroll') and (`payroll_id` is not null) and (`sale_id` is null) and (`amount` <= 0))))
) ENGINE=InnoDB  DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `purchases` (
  `id` int NOT NULL AUTO_INCREMENT,
  `supplier_id` int NOT NULL,
  `product_id` int NOT NULL,
  `employee_id` int NOT NULL,
  `quantity` int NOT NULL,
  `unit_cost` decimal(12,2) NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `order_id` int DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `supplier_id` (`supplier_id`),
  KEY `product_id` (`product_id`),
  KEY `employee_id` (`employee_id`),
  KEY `fk_purchases_order_id` (`order_id`),
  CONSTRAINT `fk_purchases_order_id` FOREIGN KEY (`order_id`) REFERENCES `purchase_orders` (`id`),
  CONSTRAINT `purchases_ibfk_1` FOREIGN KEY (`supplier_id`) REFERENCES `suppliers` (`id`),
  CONSTRAINT `purchases_ibfk_2` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`),
  CONSTRAINT `purchases_ibfk_3` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`id`),
  CONSTRAINT `purchases_chk_1` CHECK ((`quantity` > 0)),
  CONSTRAINT `purchases_chk_2` CHECK ((`unit_cost` >= 0))
) ENGINE=InnoDB  DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

DELIMITER $$

DROP TRIGGER IF EXISTS employee_subtype_insert$$

CREATE TRIGGER employee_subtype_insert AFTER INSERT ON employees FOR EACH ROW BEGIN IF COALESCE(@restoring_snapshot,0)=0 THEN INSERT IGNORE INTO cashiers(employee_id) SELECT NEW.id WHERE NEW.job_type='Cashier'; INSERT IGNORE INTO procurement_officers(employee_id) SELECT NEW.id WHERE NEW.job_type='ProcurementOfficer'; INSERT IGNORE INTO accountants(employee_id) SELECT NEW.id WHERE NEW.job_type='Accountant'; INSERT IGNORE INTO hr_staff(employee_id) SELECT NEW.id WHERE NEW.job_type='HRStaff'; INSERT IGNORE INTO branch_managers(employee_id) SELECT NEW.id WHERE NEW.job_type='BranchManager'; END IF; END$$

DROP TRIGGER IF EXISTS employee_subtype_update$$

CREATE TRIGGER employee_subtype_update AFTER UPDATE ON employees FOR EACH ROW BEGIN IF COALESCE(@restoring_snapshot,0)=0 THEN DELETE FROM cashiers WHERE employee_id=NEW.id AND NEW.job_type<>'Cashier'; INSERT IGNORE INTO cashiers(employee_id) SELECT NEW.id WHERE NEW.job_type='Cashier'; DELETE FROM procurement_officers WHERE employee_id=NEW.id AND NEW.job_type<>'ProcurementOfficer'; INSERT IGNORE INTO procurement_officers(employee_id) SELECT NEW.id WHERE NEW.job_type='ProcurementOfficer'; DELETE FROM accountants WHERE employee_id=NEW.id AND NEW.job_type<>'Accountant'; INSERT IGNORE INTO accountants(employee_id) SELECT NEW.id WHERE NEW.job_type='Accountant'; DELETE FROM hr_staff WHERE employee_id=NEW.id AND NEW.job_type<>'HRStaff'; INSERT IGNORE INTO hr_staff(employee_id) SELECT NEW.id WHERE NEW.job_type='HRStaff'; DELETE FROM branch_managers WHERE employee_id=NEW.id AND NEW.job_type<>'BranchManager'; INSERT IGNORE INTO branch_managers(employee_id) SELECT NEW.id WHERE NEW.job_type='BranchManager'; END IF; END$$

DROP TRIGGER IF EXISTS sale_ledger_insert$$

CREATE TRIGGER sale_ledger_insert AFTER INSERT ON sale_items FOR EACH ROW
      BEGIN IF COALESCE(@restoring_snapshot,0)=0 THEN
        INSERT INTO ledger_entries(source_type,sale_id,amount)
        VALUES('Sale',NEW.sale_id,NEW.quantity*NEW.unit_price)
        ON DUPLICATE KEY UPDATE amount=amount+NEW.quantity*NEW.unit_price;
      END IF; END$$

DROP TRIGGER IF EXISTS payroll_ledger_insert$$

CREATE TRIGGER payroll_ledger_insert AFTER INSERT ON payroll FOR EACH ROW
      BEGIN IF COALESCE(@restoring_snapshot,0)=0 THEN
        INSERT INTO ledger_entries(source_type,payroll_id,amount)
        VALUES('Payroll',NEW.id,-NEW.net_pay);
      END IF; END$$

DROP TRIGGER IF EXISTS sale_ledger_update$$

CREATE TRIGGER sale_ledger_update AFTER UPDATE ON sale_items FOR EACH ROW
      BEGIN IF COALESCE(@restoring_snapshot,0)=0 THEN
        UPDATE ledger_entries SET amount=amount-OLD.quantity*OLD.unit_price WHERE sale_id=OLD.sale_id;
        INSERT INTO ledger_entries(source_type,sale_id,amount) VALUES('Sale',NEW.sale_id,NEW.quantity*NEW.unit_price)
        ON DUPLICATE KEY UPDATE amount=amount+NEW.quantity*NEW.unit_price;
      END IF; END$$

DROP TRIGGER IF EXISTS sale_ledger_delete$$

CREATE TRIGGER sale_ledger_delete AFTER DELETE ON sale_items FOR EACH ROW
      BEGIN IF COALESCE(@restoring_snapshot,0)=0 THEN
        UPDATE ledger_entries SET amount=amount-OLD.quantity*OLD.unit_price WHERE sale_id=OLD.sale_id;
      END IF; END$$

DROP TRIGGER IF EXISTS payroll_ledger_update$$

CREATE TRIGGER payroll_ledger_update AFTER UPDATE ON payroll FOR EACH ROW
      BEGIN IF COALESCE(@restoring_snapshot,0)=0 THEN
        UPDATE ledger_entries SET amount=-NEW.net_pay WHERE payroll_id=NEW.id;
      END IF; END$$

DROP TRIGGER IF EXISTS payroll_ledger_delete$$

CREATE TRIGGER payroll_ledger_delete BEFORE DELETE ON payroll FOR EACH ROW
      BEGIN IF COALESCE(@restoring_snapshot,0)=0 THEN
        DELETE FROM ledger_entries WHERE payroll_id=OLD.id;
      END IF; END$$

DELIMITER ;