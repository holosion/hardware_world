-- Assignment entities added without replacing the existing Flask tables.
CREATE TABLE IF NOT EXISTS branches (
 id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(100) NOT NULL UNIQUE,
 location VARCHAR(150) NOT NULL, contact_number VARCHAR(30) NOT NULL DEFAULT ''
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS departments (
 id INT AUTO_INCREMENT PRIMARY KEY, branch_id INT NOT NULL,
 name VARCHAR(100) NOT NULL, UNIQUE(branch_id,name),
 FOREIGN KEY(branch_id) REFERENCES branches(id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS customers (
 id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(100) NOT NULL,
 phone VARCHAR(30) NOT NULL DEFAULT ''
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS cashiers (
 employee_id INT PRIMARY KEY, pos_terminal_id VARCHAR(50) NOT NULL DEFAULT '',
 FOREIGN KEY(employee_id) REFERENCES employees(id) ON DELETE CASCADE
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS procurement_officers (
 employee_id INT PRIMARY KEY, approval_limit DECIMAL(12,2) NOT NULL DEFAULT 0,
 CHECK(approval_limit>=0), FOREIGN KEY(employee_id) REFERENCES employees(id) ON DELETE CASCADE
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS accountants (
 employee_id INT PRIMARY KEY, certification_number VARCHAR(100) NOT NULL DEFAULT '',
 FOREIGN KEY(employee_id) REFERENCES employees(id) ON DELETE CASCADE
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS hr_staff (
 employee_id INT PRIMARY KEY, hr_role VARCHAR(100) NOT NULL DEFAULT '',
 FOREIGN KEY(employee_id) REFERENCES employees(id) ON DELETE CASCADE
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS branch_managers (
 employee_id INT PRIMARY KEY, branch_id INT NULL UNIQUE,
 management_level VARCHAR(100) NOT NULL DEFAULT '',
 FOREIGN KEY(employee_id) REFERENCES employees(id) ON DELETE CASCADE,
 FOREIGN KEY(branch_id) REFERENCES branches(id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS supply (
 supplier_id INT NOT NULL, product_id INT NOT NULL,
 cost_price DECIMAL(12,2) NOT NULL, lead_time_days INT NOT NULL DEFAULT 0,
 PRIMARY KEY(supplier_id,product_id), CHECK(cost_price>=0), CHECK(lead_time_days>=0),
 FOREIGN KEY(supplier_id) REFERENCES suppliers(id), FOREIGN KEY(product_id) REFERENCES products(id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS purchase_orders (
 id INT AUTO_INCREMENT PRIMARY KEY, supplier_id INT NOT NULL, employee_id INT NOT NULL,
 order_date DATE NOT NULL, status ENUM('Pending','Received') NOT NULL DEFAULT 'Pending',
 FOREIGN KEY(supplier_id) REFERENCES suppliers(id), FOREIGN KEY(employee_id) REFERENCES employees(id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS purchase_order_items (
 order_id INT NOT NULL, product_id INT NOT NULL, quantity INT NOT NULL,
 unit_cost DECIMAL(12,2) NOT NULL, PRIMARY KEY(order_id,product_id),
 CHECK(quantity>0), CHECK(unit_cost>=0),
 FOREIGN KEY(order_id) REFERENCES purchase_orders(id), FOREIGN KEY(product_id) REFERENCES products(id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS payroll (
 id INT AUTO_INCREMENT PRIMARY KEY, employee_id INT NOT NULL,
 pay_month DATE NOT NULL, gross_pay DECIMAL(12,2) NOT NULL, deductions DECIMAL(12,2) NOT NULL DEFAULT 0,
 net_pay DECIMAL(12,2) GENERATED ALWAYS AS (gross_pay-deductions) STORED,
 UNIQUE(employee_id,pay_month), CHECK(DAY(pay_month)=1),
 CHECK(gross_pay>=0), CHECK(deductions>=0 AND deductions<=gross_pay),
 FOREIGN KEY(employee_id) REFERENCES employees(id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS ledger_entries (
 id INT AUTO_INCREMENT PRIMARY KEY, entry_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 source_type ENUM('Sale','Payroll') NOT NULL, sale_id INT NULL UNIQUE, payroll_id INT NULL UNIQUE,
 amount DECIMAL(16,2) NOT NULL,
 CHECK((source_type='Sale' AND sale_id IS NOT NULL AND payroll_id IS NULL AND amount>=0)
 OR (source_type='Payroll' AND payroll_id IS NOT NULL AND sale_id IS NULL AND amount<=0)),
 FOREIGN KEY(sale_id) REFERENCES sales(id), FOREIGN KEY(payroll_id) REFERENCES payroll(id)
) ENGINE=InnoDB;
