# Using this project's MySQL database in VS Code

Your MySQL server is already installed and running as the Windows **MySQL80** service, configured to start automatically. VS Code connects to that same server. The database is stored by MySQL, not inside a VS Code extension or the HTML files.

## What is configured on this computer

- Existing extensions: **SQLTools** and **SQLTools MySQL/MariaDB/TiDB**.
- A workspace connection called **Hardware World - MySQL**.
- Host `127.0.0.1`, port `3306`, database `hardware_world_simple`, MySQL user `root`.
- The connection asks for the MySQL password instead of storing it in VS Code settings.
- Two terminal tasks: **MySQL: Open SQL console** and **MySQL: Check server status**.

The local configuration is in `.vscode/settings.json` and `.vscode/tasks.json`. These files and `login.txt` are excluded from Git. Database credentials are in the **MYSQL DATABASE CONNECTION FOR VS CODE** section of your local `login.txt`. The database password is separate from the website's admin/sales passwords.

## Browse tables and run SQL

1. Open this project folder in VS Code.
2. Click the **SQLTools** icon in the Activity Bar. If it is hidden, use the Command Palette and search for SQLTools.
3. Find **Hardware World - MySQL** under **DBMS project** and connect.
4. Enter the **MySQL password** from the database section of `login.txt` when prompted.
5. Expand `hardware_world_simple` to browse its tables. Right-click a table and choose **Show Table Records**.
6. Open `backend/explore.sql`. Select a query, right-click, and choose **Run Selected Query**. Results appear inside VS Code.

If the new profile is not visible yet, run **Developer: Reload Window** from Ctrl+Shift+P. Do not run `schema.sql` just to view data; it defines tables. `explore.sql` contains read-only queries for the existing database, including employee usernames, product stock, suppliers, purchases, and sales totals.

## Visualize the table relationships

Open [DATABASE_DIAGRAM.md](DATABASE_DIAGRAM.md). This computer is configured to open it in **Markdown Preview**, displaying the seven tables as boxes joined by their foreign-key relationships. If the source appears, press **Ctrl+Shift+V**, or use **Reopen Editor With -> Markdown Preview**. VS Code's built-in Mermaid support renders it locally.

Use the on-diagram zoom controls, or hold **Alt** and scroll to zoom; Alt-drag pans. PK means primary key, FK means foreign key, and UK means unique field.

The diagram is generated from live MySQL metadata, and is a snapshot of the table structure. To refresh it after changing the schema, choose **Terminal -> Run Task -> Database: Refresh ER diagram**, or run:

```powershell
backend/.venv/Scripts/python.exe backend/generate_diagram.py
```

The generator reads schema metadata without changing records. SQLTools continues to show live rows. See [VS Code's Markdown documentation](https://code.visualstudio.com/docs/languages/markdown#_mermaid-diagram-rendering) for preview and pan/zoom controls.

## Use the MySQL terminal inside VS Code

1. Select **Terminal -> Run Task**.
2. Choose **MySQL: Open SQL console**.
3. Enter the MySQL password when the terminal prompts. The terminal hides it as you type.
4. At the `mysql>` prompt, run:

```sql
SHOW TABLES;
SELECT id, name, stock FROM products;
exit;
```

Use **MySQL: Check server status** to check the Windows service. It is already running; neither a second server nor Docker is required for this setup.

## About the recent Oracle update

Oracle's September 10, 2026 announcement says **MySQL Shell for VS Code was discontinued**, with its capabilities carried into the new **MySQL Workbench 26**. Workbench 26 officially supports MySQL 8.4 and newer; this computer currently runs MySQL 8.0.46. We have configured your already installed SQLTools extensions and left the database server unchanged.

Source: [Oracle: Introducing MySQL Workbench 26](https://blogs.oracle.com/mysql/introducing-mysql-workbench-26).

This setup lets you use the existing MySQL database from VS Code while continuing to run the Flask application normally. For your presentation, show a SQL query in `explore.sql`, its result grid, and the matching records in the website.
