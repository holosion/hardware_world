# Hardware World Flask database project

The `akena2` branch uses Flask, HTML, CSS and MySQL. It keeps the existing backend and frontend folders, Jinja templates, navy sidebar and orange accents. No Node, browser JavaScript framework or ORM is required.

## Start here

- [Run the complete system](RUN_SYSTEM.md)
- [Final PDF report](output/pdf/Hardware_World_Final_Report.pdf)
- [Report text](output/Hardware_World_Report.md)
- [SQL practice with answers and table recreation](output/sql/practice.sql)
- [Complete Workbench schema and triggers](output/sql/complete_schema.sql)
- [Live-schema relationship diagram](DATABASE_DIAGRAM.md)

```powershell
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
backend/.venv/Scripts/python.exe backend/main.py init-db
backend/.venv/Scripts/python.exe backend/serve.py
```

Open http://127.0.0.1:8000. If you need to create the Python environment first, follow RUN_SYSTEM.md. Preserve your root `.env`; do not replace existing credentials. `SIMPLE_DB_NAME` chooses the working schema. An existing `DATABASE_URL` supplies connection credentials but does not override that database name. Only the root `.env` is read.

## Assignment coverage

All 18 assignment entities now have tables: branches, departments, employees, cashiers, procurement_officers, accountants, hr_staff, branch_managers, categories, products, suppliers, supply, customers, sales, sale_items, purchase_orders, payroll and ledger_entries.

Two further implementation tables make 20 in total: purchase_order_items stores order lines; purchases retains actual stock deliveries from the original system. Four additional work-management tables bring the initialized schema to 24 tables. No old business records or passwords are reset by initialization. Missing historical department/branch/NIN values remain unknown. Existing employees receive a provisional Cashier subtype until an Admin assigns their actual job on Staff profiles.

Department job management adds database-backed departments, employee department membership history, job assignments, status activity history, and in-app notifications. Admins use **Departments & jobs** to assign work and monitor department performance; every signed-in employee can use **My jobs** to start and complete only their own assignments. Run `init-db` again to apply these additive schema upgrades without deleting existing records.

Company funds are stored in the `company_finance` singleton and are seeded to UGX 800,000,000 only when the account does not exist. Employee monthly salaries are stored on `employees`. Admins can pay an employee from the Employees page or process the current month in Payroll; each payment creates the existing payroll/ledger record and deducts the net amount transactionally, with duplicate-month payments rejected. Employees with no linked business history can be deleted; employees referenced by historical records are deactivated instead so audit and business history remain intact.

The source diagrams are reproduced unchanged in the PDF, with corrections explained separately. The physical model and complete SQL export reflect the actual database. In particular, supply has a composite primary key; sale_items retains its existing ID and adds a unique sale/product pair; payroll has one employee/month pair.

## Features

- Products, categories, suppliers and registered customers.
- Branches, departments, employee profiles, supervision and five job subtypes.
- Sales with atomic stock deduction, a sales ledger trigger, HTML receipts and saved Word receipts.
- Supplier-product costs and lead times, pending orders, approval limits and one-time receiving.
- Monthly payroll, generated net pay and payroll ledger triggers.
- A shared sales/payroll ledger and a data quality review page.
- Complete automatic/manual CSV snapshots and transactional restores, including older seven-table backups.

## Access roles

Admin can use every module, including HR and accounting. Sales can view products, register customers, record sales and access receipts. Purchasing can manage products/categories/suppliers, supplier catalogues, orders and deliveries. All roles can change their own password. Permissions are checked on the server for every route and method, and organizational records have entity-specific checks.

Business job subtypes and access roles are separate. An Accountant job does not automatically gain Admin access. The three existing access roles are retained to keep the system simple.

The Employees form starts with a required Department. Click Show jobs to load only that department's supported jobs, then select a required Job and a separate System access role. The department/job pairing is validated on the server. Choosing Accountant creates the corresponding accountants row through the existing MySQL trigger. Staff profiles holds job-specific details such as certification numbers and procurement approval limits. Changing jobs removes the previous subtype row and its job-specific details; keeping the same job preserves those details.

## Important implementation details

Flask performs stock changes in transactions with product row locks. MySQL triggers maintain sale/payroll ledger amounts and employee subtype rows. Word generation and CSV backup run after commit; failures warn the user without undoing a completed sale. Word receipts are saved under `backend/receipts/DATABASE-NAME/` and served on later downloads. Missing files can be regenerated using current product/employee names and historical quantities/prices.

CSV snapshots contain 20 files and a checksum manifest. Generated payroll net pay is recalculated on restore. The restore connection suppresses generated subtype/ledger inserts while restoring those saved rows, but keeps foreign keys enabled. Older seven-table snapshots are expanded during restore. Restore only accepts a separate empty database; never use working data for destructive SQL practice. Copy Word receipts and project/schema files separately from CSV data backups.

The project intentionally uses global stock rather than stock per branch. Branch/department assignment may remain NULL during migration or setup. The Data quality page identifies missing information. The ledger is a simple cash movement ledger, not double-entry accounting. The order UI creates one line per order although the schema and receiving workflow support multiple lines. Refunds, tax, credit, statutory payroll and internet hosting are outside this implementation.

## Files and verification

`backend/main.py` contains the original routes and application setup. `business_routes.py` adds the assignment modules. `db.py` and `business.py` initialize and upgrade the schema. `schema.sql` and `business_schema.sql` define tables. `permissions.py`, `backup.py` and `receipts.py` handle their named functions. `serve.py` runs Waitress. `frontend/*.html` and `frontend/assets/css/style.css` implement presentation.

```powershell
backend/.venv/Scripts/python.exe -m unittest discover -s backend -p test_app.py -v
backend/.venv/Scripts/python.exe backend/generate_diagram.py
```

Tests use disposable `hw_test_*` MySQL schemas and require create/drop privileges. They do not clear working records. Read RUN_SYSTEM.md for LAN access, backup/restore commands and demonstration steps.
