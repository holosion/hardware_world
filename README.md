# Hardware World ? simple Flask version

The `akena2` version uses **HTML, CSS, Flask, and MySQL**. It preserves the sidebar, header, cards, forms, tables, navy colours, and orange accents. Flask renders pages using Jinja. No browser JavaScript, Node, REST API, JWT, ORM, or Alembic is required.

## Features

- Login, logout, and change password.
- Add, edit, search, and delete products; manage categories and suppliers.
- Receive purchases and automatically increase stock.
- Record sales with up to three product lines, reduce stock, and view receipts.
- Dashboard totals, recent sales, and low-stock alerts.
- Admins have full access. Sales and Purchasing employees have access to their department's work.

Payroll, ledger, departments, branches, warehouses, approvals, credit accounts, automatic backups, and advanced permissions are outside this version.

## Run on Windows

Use Python 3.11+ and your existing MySQL server (MySQL 8 recommended). MySQL Workbench is the tool for viewing the database; MySQL is the server that stores the data.

From the project folder:

```powershell
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
```

Use the existing `backend/.venv` if present. Keep your existing root `.env`. Otherwise copy `.env.example` to `.env` and configure MySQL credentials, administrator username/password, and `SECRET_KEY`. Only the root `.env` is read.

An existing `DATABASE_URL` supplies the MySQL host, port, user, and password instead of the `DB_*` settings. Its database name is ignored: `SIMPLE_DB_NAME` selects the simplified schema, defaulting to `hardware_world_simple`.

```powershell
backend/.venv/Scripts/python.exe backend/main.py init-db
backend/.venv/Scripts/python.exe backend/main.py
```

Open **http://127.0.0.1:8000** and select **Administration (Admin)**, then sign in with your administrator **username** and password. Stop with Ctrl+C. Flask serves HTML and CSS together. Do not open HTML files directly or run a separate frontend server. Debug mode is off.

`init-db` creates seven tables and the first administrator from `ADMIN_NAME`, `ADMIN_USERNAME`, and `ADMIN_PASSWORD`, prompting for a missing name or password. `ADMIN_EMAIL` is optional contact information. If `ADMIN_USERNAME` is missing, the username is derived from the administrator name (lowercase, spaces replaced by underscores). Repeating it does not erase data or reset passwords. Later account changes use the Employees page.

The original ERP database is untouched. Old records are **not automatically copied** because the schemas differ. The MySQL account needs permission to create the simplified schema. Alternatively, create it and grant access in Workbench first. Do not point this version at the original ERP schema.

Set a persistent `SECRET_KEY`; otherwise sessions expire when the app restarts. Existing root `.env` credentials continue to work.

## First demonstration

1. Add a category and supplier.
2. Add a product, selling price, opening stock, and reorder level.
3. Receive a purchase: choose a supplier/product, quantity, and unit cost.
4. Record a sale and view its receipt.
5. Return to the dashboard to see totals and stock alerts.

No sample records or default accounts are hard-coded. Quantities are whole units. Currency defaults to UGX and can be changed with `CURRENCY`. A purchase records stock already received; a sale is immediately paid. Credit, refunds, taxes, and discounts are outside scope. Transaction history is read-only. Opening stock is entered once on product creation; purchases and sales then change stock.

## Seven tables

| Table | Purpose |
| --- | --- |
| employees | Full name, unique username, optional email, password hash, department role, active status |
| categories | Product groups |
| suppliers | Supplier contacts |
| products | Category, selling price, stock, reorder level |
| sales | Customer name, employee, time |
| sale_items | Products, quantities, and historical selling prices |
| purchases | Supplier, product, employee, quantity, cost, time |

In Workbench, refresh **Schemas**, expand `hardware_world_simple`, or run:

```sql
USE hardware_world_simple;
SHOW TABLES;
SELECT id, name, username, role, active FROM employees;
SELECT * FROM products;
SELECT s.id, s.customer_name, SUM(i.quantity * i.unit_price) AS total
FROM sales s JOIN sale_items i ON i.sale_id = s.id
GROUP BY s.id;
```

Sales and stock changes commit together or roll back together. Row locks prevent overselling, and foreign keys protect linked records. Money uses DECIMAL; sale items preserve historical prices. SQL uses parameters, passwords use Werkzeug hashes, and POST forms contain CSRF tokens.

## Files to understand

| File | Purpose |
| --- | --- |
| backend/main.py | Flask routes, forms, login, business logic |
| backend/db.py | MySQL connection and SQL helpers |
| backend/permissions.py | Role access table shared by routes and templates |
| backend/schema.sql | Seven tables and foreign keys |
| backend/requirements.txt | Three direct dependencies |
| backend/test_app.py | Integration tests using temporary MySQL schema |
| frontend/base.html | Shared sidebar, header, messages, layout |
| frontend/*.html | HTML page templates and forms |
| frontend/assets/css/style.css | Styling and responsive layout |
| PRESENTATION_GUIDE.md | Explanation, demo, and lecturer questions |

## Roles and departments

| Feature | Admin | Sales | Purchasing |
| --- | --- | --- | --- |
| Dashboard and own account/password | Yes | Yes | Yes |
| View/search products and stock | Yes | Yes | Yes |
| Add/edit/delete products | Yes | No | Yes |
| Manage categories and suppliers | Yes | No | Yes |
| Receive stock and view purchase history | Yes | No | Yes |
| Record sales, view sales history and receipts | Yes | Yes | No |
| Sales totals and recent sales on dashboard | Yes | Yes | No |
| Manage employees, roles, and account status | Yes | No | No |

Sign in as an Admin, open **Employees**, and choose **Sales** or **Purchasing** when creating or editing an employee. The Admin assigns a unique username and password. The employee selects their department and signs in with that username and password. The selected department must match the saved role; it never changes the employee's permissions. One role is stored directly on each employee, so no additional department or permission tables are needed.

`backend/permissions.py` contains the access table. Before each request, Flask reads the employee's current role from MySQL and checks the requested page and HTTP method. Disallowed actions return **403**, including manually typed URLs and direct form submissions. Unknown roles and unlisted routes are denied. The same access table hides navigation links and editing controls. Role changes apply to already signed-in employees on their next request. Admins cannot demote or deactivate their own account.

### Upgrade an existing installation

Run `backend/.venv/Scripts/python.exe backend/main.py init-db`, then restart Flask. This preserves existing accounts, passwords, and business records while updating the role and username columns. Existing **Staff** accounts become **Sales** accounts; an Admin can reassign purchasing employees afterward. No extra database tables are added. New installations already use the three roles.

Existing administrator usernames are derived from `ADMIN_USERNAME` if set, otherwise from each administrator's name. Other employees receive usernames based on the part of their email before `@`, or their name when no email exists. If two suggested usernames collide, an employee ID is appended. Repeating the upgrade preserves usernames already assigned. The command prints the first administrator's username; Admins can inspect/change other usernames on the Employees page. Passwords are unchanged.

### Creating an employee and signing in

1. Sign in as Admin and open **Employees**.
2. Enter the full name, unique username, department (Sales or Purchasing), and a password of at least eight characters. Email is optional.
3. Save and give the employee their department, username, and initial password.
4. The employee selects that department on the sign-in page, enters the username/password, and signs in.
5. The employee can change their own password under **My account**.

There is no public sign-up. Only Admins can create, edit, activate, or deactivate employee accounts. Usernames contain 3-50 letters/numbers/dots/underscores/hyphens, start with a letter or number, and are stored in lowercase. Passwords are stored as hashes in `employees.password_hash`, never as plain text. All credentials are checked against the MySQL `employees` table.

## Tests

```powershell
backend/.venv/Scripts/python.exe -m unittest discover -s backend -p test_app.py -v
```

Tests create and drop their own random `hw_test_*` MySQL schema. They require create/drop permission and never clear application or original ERP records. They exercise HTML forms, Flask routes, MySQL changes, and rendered pages.

References: [Flask quickstart](https://flask.palletsprojects.com/en/stable/quickstart/), [Flask templates](https://flask.palletsprojects.com/en/stable/tutorial/templates/).
