"""Small, additive schema upgrade and actual MySQL trigger definitions."""
from pathlib import Path

SUBTYPES = {'Cashier': 'cashiers', 'ProcurementOfficer': 'procurement_officers',
            'Accountant': 'accountants', 'HRStaff': 'hr_staff', 'BranchManager': 'branch_managers'}


def upgrade(cursor):
    for statement in Path(__file__).with_name('business_schema.sql').read_text().split(';'):
        if statement.strip():
            cursor.execute(statement)
    additions = {
        'employees': {
            'department_id': 'INT NULL REFERENCES departments(id)',
            'supervisor_id': 'INT NULL REFERENCES employees(id)',
            'nin': 'VARCHAR(30) NULL UNIQUE', 'phone': "VARCHAR(30) NOT NULL DEFAULT ''",
            'date_hired': 'DATE NULL', 'salary': 'DECIMAL(12,2) NOT NULL DEFAULT 0 CHECK(salary>=0)',
            'job_type': "ENUM('Cashier','ProcurementOfficer','Accountant','HRStaff','BranchManager') NOT NULL DEFAULT 'Cashier'",
        },
        'suppliers': {'contact_person': "VARCHAR(100) NOT NULL DEFAULT ''", 'address': "VARCHAR(200) NOT NULL DEFAULT ''"},
        'products': {'description': "VARCHAR(500) NOT NULL DEFAULT ''"},
        'sales': {'customer_id': 'INT NULL REFERENCES customers(id)', 'branch_id': 'INT NULL REFERENCES branches(id)'},
        'purchases': {'order_id': 'INT NULL REFERENCES purchase_orders(id)'},
    }
    for table, columns in additions.items():
        cursor.execute(f'SHOW COLUMNS FROM {table}')
        existing = {r['Field'] for r in cursor.fetchall()}
        for name, definition in columns.items():
            if name not in existing:
                # MySQL does not enforce inline REFERENCES; add named constraints below.
                cursor.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition.split(" REFERENCES")[0]}')
    for table, column, parent in [('employees','department_id','departments'), ('employees','supervisor_id','employees'),
                                   ('sales','customer_id','customers'), ('sales','branch_id','branches'),
                                   ('purchases','order_id','purchase_orders')]:
        name = f'fk_{table}_{column}'
        cursor.execute('SELECT CONSTRAINT_NAME FROM information_schema.TABLE_CONSTRAINTS WHERE '
                       'CONSTRAINT_SCHEMA=DATABASE() AND TABLE_NAME=%s AND CONSTRAINT_NAME=%s', (table,name))
        if not cursor.fetchone():
            cursor.execute(f'ALTER TABLE {table} ADD CONSTRAINT {name} FOREIGN KEY ({column}) REFERENCES {parent}(id)')
    # Department work management is additive so existing accounts and records remain intact.
    department_columns = {
        'description': "VARCHAR(500) NOT NULL DEFAULT ''",
        'manager_id': 'INT NULL',
        'status': "ENUM('Active','Inactive') NOT NULL DEFAULT 'Active'",
        'created_at': 'TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP',
        'updated_at': 'TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP',
    }
    cursor.execute('SHOW COLUMNS FROM departments')
    existing = {row['Field'] for row in cursor.fetchall()}
    for name, definition in department_columns.items():
        if name not in existing:
            cursor.execute(f'ALTER TABLE departments ADD COLUMN {name} {definition}')
    for statement in (
        """CREATE TABLE IF NOT EXISTS company_finance (
            id TINYINT PRIMARY KEY,
            balance DECIMAL(16,2) NOT NULL,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            CHECK(balance >= 0)
        ) ENGINE=InnoDB""",
        """CREATE TABLE IF NOT EXISTS employee_department_memberships (
            id INT AUTO_INCREMENT PRIMARY KEY,
            employee_id INT NOT NULL,
            department_id INT NOT NULL,
            assigned_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            assigned_by INT NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            FOREIGN KEY (employee_id) REFERENCES employees(id),
            FOREIGN KEY (department_id) REFERENCES departments(id),
            FOREIGN KEY (assigned_by) REFERENCES employees(id),
            INDEX ix_membership_employee_active (employee_id,is_active),
            INDEX ix_membership_department_active (department_id,is_active)
        ) ENGINE=InnoDB""",
        """CREATE TABLE IF NOT EXISTS job_assignments (
            id INT AUTO_INCREMENT PRIMARY KEY,
            department_id INT NOT NULL,
            employee_id INT NOT NULL,
            title VARCHAR(150) NOT NULL,
            description VARCHAR(2000) NOT NULL DEFAULT '',
            priority ENUM('Low','Medium','High','Urgent') NOT NULL DEFAULT 'Medium',
            status ENUM('Pending','In Progress','Completed','Cancelled') NOT NULL DEFAULT 'Pending',
            assigned_by INT NOT NULL,
            assigned_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            due_date DATE NULL,
            started_at TIMESTAMP NULL,
            completed_at TIMESTAMP NULL,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (department_id) REFERENCES departments(id),
            FOREIGN KEY (employee_id) REFERENCES employees(id),
            FOREIGN KEY (assigned_by) REFERENCES employees(id),
            INDEX ix_jobs_employee_status (employee_id,status),
            INDEX ix_jobs_department_status (department_id,status),
            INDEX ix_jobs_due_date (due_date)
        ) ENGINE=InnoDB""",
        """CREATE TABLE IF NOT EXISTS job_activity_history (
            id INT AUTO_INCREMENT PRIMARY KEY,
            job_id INT NOT NULL,
            actor_id INT NOT NULL,
            action VARCHAR(50) NOT NULL,
            previous_status VARCHAR(30) NULL,
            new_status VARCHAR(30) NULL,
            comment VARCHAR(1000) NOT NULL DEFAULT '',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (job_id) REFERENCES job_assignments(id) ON DELETE CASCADE,
            FOREIGN KEY (actor_id) REFERENCES employees(id),
            INDEX ix_job_activity_job_created (job_id,created_at)
        ) ENGINE=InnoDB""",
        """CREATE TABLE IF NOT EXISTS notifications (
            id INT AUTO_INCREMENT PRIMARY KEY,
            employee_id INT NOT NULL,
            job_id INT NULL,
            message VARCHAR(500) NOT NULL,
            is_read BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE,
            FOREIGN KEY (job_id) REFERENCES job_assignments(id) ON DELETE SET NULL,
            INDEX ix_notifications_employee_read (employee_id,is_read,created_at)
        ) ENGINE=InnoDB""",
    ):
        cursor.execute(statement)
    cursor.execute(
        "INSERT IGNORE INTO company_finance(id,balance) VALUES(1,800000000.00)")
    # Existing department assignments become the first membership record.
    cursor.execute(
        """INSERT INTO employee_department_memberships
           (employee_id,department_id,assigned_by)
           SELECT e.id,e.department_id,e.id FROM employees e
           LEFT JOIN employee_department_memberships m
             ON m.employee_id=e.id AND m.department_id=e.department_id AND m.is_active=1
           WHERE e.department_id IS NOT NULL AND m.id IS NULL""")
    cursor.execute("SHOW INDEX FROM sale_items WHERE Key_name='uq_sale_product'")
    if not cursor.fetchone():
        cursor.execute('ALTER TABLE sale_items ADD CONSTRAINT uq_sale_product UNIQUE(sale_id,product_id)')
    # Existing employees receive exactly one subtype, preserving IDs and credentials.
    for job, table in SUBTYPES.items():
        cursor.execute(f'INSERT IGNORE INTO {table}(employee_id) SELECT id FROM employees WHERE job_type=%s', (job,))
    install_triggers(cursor)
    # Existing sales become visible in the ledger on the first upgrade.
    cursor.execute("INSERT IGNORE INTO ledger_entries(source_type,sale_id,amount,entry_date) "
                   "SELECT 'Sale',s.id,SUM(i.quantity*i.unit_price),s.created_at FROM sales s "
                   "JOIN sale_items i ON i.sale_id=s.id GROUP BY s.id")
    cursor.execute("INSERT IGNORE INTO ledger_entries(source_type,payroll_id,amount,entry_date) "
                   "SELECT 'Payroll',id,-net_pay,pay_month FROM payroll")


def trigger_definitions():
    result = {}
    for event in ('INSERT', 'UPDATE'):
        statements = []
        for job, table in SUBTYPES.items():
            if event == 'UPDATE':
                statements.append(f"DELETE FROM {table} WHERE employee_id=NEW.id AND NEW.job_type<>'{job}';")
            statements.append(f"INSERT IGNORE INTO {table}(employee_id) SELECT NEW.id WHERE NEW.job_type='{job}';")
        result['employee_subtype_' + event.lower()] = (
            f"AFTER {event} ON employees FOR EACH ROW BEGIN IF COALESCE(@restoring_snapshot,0)=0 THEN "
            + ' '.join(statements) + ' END IF; END')
    result['sale_ledger_insert'] = """AFTER INSERT ON sale_items FOR EACH ROW
      BEGIN IF COALESCE(@restoring_snapshot,0)=0 THEN
        INSERT INTO ledger_entries(source_type,sale_id,amount)
        VALUES('Sale',NEW.sale_id,NEW.quantity*NEW.unit_price)
        ON DUPLICATE KEY UPDATE amount=amount+NEW.quantity*NEW.unit_price;
      END IF; END"""
    result['payroll_ledger_insert'] = """AFTER INSERT ON payroll FOR EACH ROW
      BEGIN IF COALESCE(@restoring_snapshot,0)=0 THEN
        INSERT INTO ledger_entries(source_type,payroll_id,amount)
        VALUES('Payroll',NEW.id,-NEW.net_pay);
      END IF; END"""
    # Keep ledger amounts correct for SQL demonstrations of UPDATE / DELETE too.
    result['sale_ledger_update'] = """AFTER UPDATE ON sale_items FOR EACH ROW
      BEGIN IF COALESCE(@restoring_snapshot,0)=0 THEN
        UPDATE ledger_entries SET amount=amount-OLD.quantity*OLD.unit_price WHERE sale_id=OLD.sale_id;
        INSERT INTO ledger_entries(source_type,sale_id,amount) VALUES('Sale',NEW.sale_id,NEW.quantity*NEW.unit_price)
        ON DUPLICATE KEY UPDATE amount=amount+NEW.quantity*NEW.unit_price;
      END IF; END"""
    result['sale_ledger_delete'] = """AFTER DELETE ON sale_items FOR EACH ROW
      BEGIN IF COALESCE(@restoring_snapshot,0)=0 THEN
        UPDATE ledger_entries SET amount=amount-OLD.quantity*OLD.unit_price WHERE sale_id=OLD.sale_id;
      END IF; END"""
    result['payroll_ledger_update'] = """AFTER UPDATE ON payroll FOR EACH ROW
      BEGIN IF COALESCE(@restoring_snapshot,0)=0 THEN
        UPDATE ledger_entries SET amount=-NEW.net_pay WHERE payroll_id=NEW.id;
      END IF; END"""
    result['payroll_ledger_delete'] = """BEFORE DELETE ON payroll FOR EACH ROW
      BEGIN IF COALESCE(@restoring_snapshot,0)=0 THEN
        DELETE FROM ledger_entries WHERE payroll_id=OLD.id;
      END IF; END"""
    return result


def install_triggers(cursor):
    for name, body in trigger_definitions().items():
        cursor.execute(f'DROP TRIGGER IF EXISTS {name}')
        cursor.execute(f'CREATE TRIGGER {name} {body}')
