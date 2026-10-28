# Run Hardware World on akena2

Use PowerShell in `C:\Users\AKENA\Desktop\DBMS-project`. Keep the existing root `.env`; it contains your private settings. MySQL must be running. MySQL Workbench is a database client, not the database server.

```powershell
git branch --show-current
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
backend/.venv/Scripts/python.exe backend/main.py init-db
backend/.venv/Scripts/python.exe backend/serve.py
```

If the environment already exists, skip `python -m venv`. Open **http://127.0.0.1:8000**. Use your existing username, password and access role. `init-db` preserves existing accounts and records and creates the missing tables, columns and triggers. Run it with the application stopped because MySQL schema changes commit separately. Stop the server with Ctrl+C.

For a quick local development demonstration, `backend/.venv/Scripts/python.exe backend/main.py` also works. Do not run both servers on the same port. Use `--port 8001` with `serve.py` if 8000 is occupied.

## Access from another computer on the same network

```powershell
backend/.venv/Scripts/python.exe backend/serve.py --host 0.0.0.0 --port 8000
ipconfig
```

On the other computer, open `http://YOUR-PC-IP:8000`, replacing `YOUR-PC-IP` with the host PC's Wi-Fi/Ethernet IPv4 address. Allow the server through Windows Firewall on your trusted private network if prompted. `0.0.0.0` is a listening address, not the address to type in a browser. Keep MySQL on the server PC.

VS Code's Live Server extension only serves static files. It cannot run Python, Jinja templates, login checks or SQL queries. Flask serves both the frontend and backend; use the address above. No Node or separate frontend server is needed.

These commands run a local/LAN server, not an internet deployment. Public hosting additionally needs a host, HTTPS, a persistent secret, strong credentials, restricted MySQL access, off-machine backups and `COOKIE_SECURE=true` behind HTTPS. No public hosting has been provisioned.

## First demonstration

1. Admin: add a branch and departments, then create employee accounts.
2. Admin: assign staff profiles, job types, supervisor and procurement approval limits. Existing employees initially have a provisional Cashier subtype; correct their actual jobs here.
3. Add a category, supplier and product. Sales/Purchasing roles remain unchanged.
4. Add a supplier-product catalogue entry, then create and receive a supplier order. Receiving twice is rejected.
5. Add a registered customer. Record a sale, optionally selecting the customer and branch.
6. View the receipt and download the Word document. Stock has decreased and the ledger has a positive sale entry.
7. Admin: record payroll with the first date of the month. Check calculated net pay and the negative ledger entry.
8. Admin: inspect Data quality, create a CSV backup and test restore into a separate database.

## Backup and restore

```powershell
backend/.venv/Scripts/python.exe backend/main.py create-backup
backend/.venv/Scripts/python.exe backend/main.py restore-backup "backend/backups/ACTUAL-BACKUP-FOLDER" --database hardware_world_restored
```

Replace `ACTUAL-BACKUP-FOLDER` with the real folder name. Restore requires an empty destination and will not overwrite the working database. New snapshots contain 20 CSV files and `manifest.json`. Older seven-table snapshots are accepted and upgraded. Word receipts are stored under `backend/receipts/DATABASE-NAME`; copy that folder separately if original receipt files must be retained. A missing receipt can be regenerated from sale records, although current product/employee names will be used.

## Workbench and SQL practice

Connect to the same MySQL server using the credentials in your `.env`; never paste credentials into the report or Git. Open `output/sql/practice.sql` for a separate practice database, or `output/sql/complete_schema.sql` to create the full structure in the separate `hardware_world_assignment` database. The latter has no accounts or business data. To run Flask there, set `SIMPLE_DB_NAME=hardware_world_assignment` and run `init-db` to create its first Admin, then restart the server.

```sql
USE hardware_world_simple;
SHOW TABLES;
SHOW TRIGGERS;
SELECT * FROM ledger_entries;
```

## Verify

```powershell
backend/.venv/Scripts/python.exe -m unittest discover -s backend -p test_app.py -v
backend/.venv/Scripts/python.exe backend/generate_diagram.py
```

Tests create and remove their own random `hw_test_*` databases. Do not delete or recreate application tables for practice: use the separate practice database.
