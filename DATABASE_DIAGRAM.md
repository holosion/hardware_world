# Hardware World - database diagram

Generated from the live MySQL schema **hardware_world_simple**: **7 tables** and **7 foreign-key relationships**.

In VS Code, this file is configured to open as a visual preview. If you see the source, press **Ctrl+Shift+V**. Use the diagram controls to zoom, or hold **Alt** and scroll; Alt-drag pans.

```mermaid
erDiagram
    direction LR
    categories {
        int id PK
        string name UK
    }
    employees {
        int id PK
        string name
        string username UK
        string email UK "optional"
        string password_hash
        enum role
        boolean active
    }
    products {
        int id PK
        string name
        int category_id FK
        decimal price
        int stock
        int reorder_level
    }
    purchases {
        int id PK
        int supplier_id FK
        int product_id FK
        int employee_id FK
        int quantity
        decimal unit_cost
        timestamp created_at
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
    }
    suppliers {
        int id PK
        string name
        string phone
        string email
    }
    categories ||--o{ products : category_id
    employees ||--o{ purchases : employee_id
    products ||--o{ purchases : product_id
    suppliers ||--o{ purchases : supplier_id
    products ||--o{ sale_items : product_id
    sales ||--o{ sale_items : sale_id
    employees ||--o{ sales : employee_id
```

**PK** = primary key; **FK** = foreign key; **UK** = unique field. **optional** means the field allows NULL. The forked end of a relationship means many; the double line means exactly one.

## How the tables connect

| Parent field | Referencing field |
| --- | --- |
| `categories.id` | `products.category_id` |
| `employees.id` | `purchases.employee_id` |
| `products.id` | `purchases.product_id` |
| `suppliers.id` | `purchases.supplier_id` |
| `products.id` | `sale_items.product_id` |
| `sales.id` | `sale_items.sale_id` |
| `employees.id` | `sales.employee_id` |

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
