# Hardware World - database diagram

Generated from the live MySQL schema **hardware_world_simple**: **20 tables** and **28 foreign-key relationships**.

In VS Code, this file is configured to open as a visual preview. If you see the source, press **Ctrl+Shift+V**. Use the diagram controls to zoom, or hold **Alt** and scroll; Alt-drag pans.

```mermaid
erDiagram
    direction LR
    accountants {
        int employee_id PK, FK
        string certification_number
    }
    branch_managers {
        int employee_id PK, FK
        int branch_id UK, FK "optional"
        string management_level
    }
    branches {
        int id PK
        string name UK
        string location
        string contact_number
    }
    cashiers {
        int employee_id PK, FK
        string pos_terminal_id
    }
    categories {
        int id PK
        string name UK
    }
    customers {
        int id PK
        string name
        string phone
    }
    departments {
        int id PK
        int branch_id FK
        string name
    }
    employees {
        int id PK
        string name
        string username UK
        string email UK "optional"
        string password_hash
        enum role
        boolean active
        int department_id FK "optional"
        int supervisor_id FK "optional"
        string nin UK "optional"
        string phone
        date date_hired "optional"
        decimal salary
        enum job_type
    }
    hr_staff {
        int employee_id PK, FK
        string hr_role
    }
    ledger_entries {
        int id PK
        timestamp entry_date
        enum source_type
        int sale_id UK, FK "optional"
        int payroll_id UK, FK "optional"
        decimal amount
    }
    payroll {
        int id PK
        int employee_id FK
        date pay_month
        decimal gross_pay
        decimal deductions
        decimal net_pay "optional"
    }
    procurement_officers {
        int employee_id PK, FK
        decimal approval_limit
    }
    products {
        int id PK
        string name
        int category_id FK
        decimal price
        int stock
        int reorder_level
        string description
    }
    purchase_order_items {
        int order_id PK, FK
        int product_id PK, FK
        int quantity
        decimal unit_cost
    }
    purchase_orders {
        int id PK
        int supplier_id FK
        int employee_id FK
        date order_date
        enum status
    }
    purchases {
        int id PK
        int supplier_id FK
        int product_id FK
        int employee_id FK
        int quantity
        decimal unit_cost
        timestamp created_at
        int order_id FK "optional"
    }
    sale_items {
        int id PK
        int sale_id FK
        int product_id FK
        int quantity
        decimal unit_price
    }
    sales {
        int id PK
        int employee_id FK
        string customer_name
        timestamp created_at
        int customer_id FK "optional"
        int branch_id FK "optional"
    }
    suppliers {
        int id PK
        string name
        string phone
        string email
        string contact_person
        string address
    }
    supply {
        int supplier_id PK, FK
        int product_id PK, FK
        decimal cost_price
        int lead_time_days
    }
    employees ||--o| accountants : employee_id
    branches |o--o| branch_managers : branch_id
    employees ||--o| branch_managers : employee_id
    employees ||--o| cashiers : employee_id
    branches ||--o{ departments : branch_id
    departments |o--o{ employees : department_id
    employees |o--o{ employees : supervisor_id
    employees ||--o| hr_staff : employee_id
    payroll |o--o| ledger_entries : payroll_id
    sales |o--o| ledger_entries : sale_id
    employees ||--o{ payroll : employee_id
    employees ||--o| procurement_officers : employee_id
    categories ||--o{ products : category_id
    purchase_orders ||--o{ purchase_order_items : order_id
    products ||--o{ purchase_order_items : product_id
    employees ||--o{ purchase_orders : employee_id
    suppliers ||--o{ purchase_orders : supplier_id
    employees ||--o{ purchases : employee_id
    purchase_orders |o--o{ purchases : order_id
    products ||--o{ purchases : product_id
    suppliers ||--o{ purchases : supplier_id
    products ||--o{ sale_items : product_id
    sales ||--o{ sale_items : sale_id
    branches |o--o{ sales : branch_id
    customers |o--o{ sales : customer_id
    employees ||--o{ sales : employee_id
    products ||--o{ supply : product_id
    suppliers ||--o{ supply : supplier_id
```

**PK** = primary key; **FK** = foreign key; **UK** = unique field. **optional** means the field allows NULL. The forked end of a relationship means many; the double line means exactly one.

## How the tables connect

| Parent field | Referencing field |
| --- | --- |
| `employees.id` | `accountants.employee_id` |
| `branches.id` | `branch_managers.branch_id` |
| `employees.id` | `branch_managers.employee_id` |
| `employees.id` | `cashiers.employee_id` |
| `branches.id` | `departments.branch_id` |
| `departments.id` | `employees.department_id` |
| `employees.id` | `employees.supervisor_id` |
| `employees.id` | `hr_staff.employee_id` |
| `payroll.id` | `ledger_entries.payroll_id` |
| `sales.id` | `ledger_entries.sale_id` |
| `employees.id` | `payroll.employee_id` |
| `employees.id` | `procurement_officers.employee_id` |
| `categories.id` | `products.category_id` |
| `purchase_orders.id` | `purchase_order_items.order_id` |
| `products.id` | `purchase_order_items.product_id` |
| `employees.id` | `purchase_orders.employee_id` |
| `suppliers.id` | `purchase_orders.supplier_id` |
| `employees.id` | `purchases.employee_id` |
| `purchase_orders.id` | `purchases.order_id` |
| `products.id` | `purchases.product_id` |
| `suppliers.id` | `purchases.supplier_id` |
| `products.id` | `sale_items.product_id` |
| `sales.id` | `sale_items.sale_id` |
| `branches.id` | `sales.branch_id` |
| `customers.id` | `sales.customer_id` |
| `employees.id` | `sales.employee_id` |
| `products.id` | `supply.product_id` |
| `suppliers.id` | `supply.supplier_id` |

## Explain it to your lecturer

- Categories group products.
- Employees record sales and receive purchases.
- A sale contains sale items; each item points to a product.
- Each purchase links a supplier, a product, and the employee who received it.
- `products.stock` holds the current quantity; purchases increase it and sales reduce it.

## Refresh after changing table structure

In VS Code, run **Terminal -> Run Task -> Database: Refresh ER diagram**, or run:

```powershell
backend/.venv/Scripts/python.exe backend/generate_diagram.py
```

This is a schema snapshot generated locally. It reads table metadata and does not change records. Use SQLTools to browse live rows.
