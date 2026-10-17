-- Seven tables. Run through: python backend/main.py init-db
CREATE TABLE IF NOT EXISTS employees (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('Admin', 'Sales', 'Purchasing') NOT NULL DEFAULT 'Sales',
    active BOOLEAN NOT NULL DEFAULT TRUE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS categories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS suppliers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    phone VARCHAR(30) NOT NULL DEFAULT '',
    email VARCHAR(150) NOT NULL DEFAULT ''
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS products (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    category_id INT NOT NULL,
    price DECIMAL(12,2) NOT NULL,
    stock INT NOT NULL DEFAULT 0,
    reorder_level INT NOT NULL DEFAULT 5,
    FOREIGN KEY (category_id) REFERENCES categories(id),
    CHECK (price >= 0), CHECK (stock >= 0), CHECK (reorder_level >= 0)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS sales (
    id INT AUTO_INCREMENT PRIMARY KEY,
    employee_id INT NOT NULL,
    customer_name VARCHAR(100) NOT NULL DEFAULT 'Walk-in customer',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (employee_id) REFERENCES employees(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS sale_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sale_id INT NOT NULL,
    product_id INT NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(12,2) NOT NULL,
    FOREIGN KEY (sale_id) REFERENCES sales(id),
    FOREIGN KEY (product_id) REFERENCES products(id),
    CHECK (quantity > 0), CHECK (unit_price >= 0)
) ENGINE=InnoDB;

-- One purchase records delivery of one product from one supplier.
CREATE TABLE IF NOT EXISTS purchases (
    id INT AUTO_INCREMENT PRIMARY KEY,
    supplier_id INT NOT NULL,
    product_id INT NOT NULL,
    employee_id INT NOT NULL,
    quantity INT NOT NULL,
    unit_cost DECIMAL(12,2) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (supplier_id) REFERENCES suppliers(id),
    FOREIGN KEY (product_id) REFERENCES products(id),
    FOREIGN KEY (employee_id) REFERENCES employees(id),
    CHECK (quantity > 0), CHECK (unit_cost >= 0)
) ENGINE=InnoDB;
