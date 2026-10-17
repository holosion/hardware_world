"""Hardware World: HTML forms -> Flask routes -> parameterized MySQL queries."""
import os
import re
import secrets
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlsplit

import click
import pymysql
from flask import Flask, abort, flash, g, redirect, render_template, request, send_file, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from db import ROOT, close_db, commit, connect, connection_settings, execute, get_db, initialize, query, username_from_name
from backup import TABLES, backup_folder, create_backup, list_backups, load_backup, restore_backup, zip_backup
from permissions import ROLES, allowed


def required(name, limit=100):
    value = request.form.get(name, '').strip()
    if not value or len(value) > limit:
        raise ValueError(f'{name.replace("_", " ").title()} is required (maximum {limit} characters).')
    return value


def valid_username(value):
    value = value.strip().lower()
    if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{2,49}', value):
        raise ValueError('Username must be 3-50 characters: letters, numbers, dots, underscores or hyphens, starting with a letter or number.')
    return value


def integer(name, minimum=0):
    try:
        value = int(request.form.get(name, ''))
    except (ValueError, TypeError):
        raise ValueError(f'{name.replace("_", " ").title()} must be a whole number.')
    if not minimum <= value <= 1000000:
        raise ValueError(f'{name.replace("_", " ").title()} must be between {minimum} and 1,000,000.')
    return value


def money(name):
    try:
        value = Decimal(request.form.get(name, ''))
        if not value.is_finite() or value < 0 or value > Decimal('9999999999.99'):
            raise InvalidOperation
        if value != value.quantize(Decimal('0.01')):
            raise InvalidOperation
        return value
    except (InvalidOperation, ValueError):
        raise ValueError(f'{name.replace("_", " ").title()} must be a positive amount or zero, with at most two decimal places.')


def create_app(test_config=None):
    app = Flask(__name__, template_folder=str(ROOT / 'frontend'),
                static_folder=str(ROOT / 'frontend' / 'assets'), static_url_path='/assets')
    app.config.update(SECRET_KEY=os.getenv('SECRET_KEY') or secrets.token_hex(32),
                      MYSQL=connection_settings(), SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE='Lax', MAX_CONTENT_LENGTH=64 * 1024,
                      SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE', 'false').lower() == 'true')
    if test_config:
        app.config.update(test_config)
    app.config.setdefault('AUTO_BACKUP', not app.testing)
    app.config.setdefault('BACKUP_DIR', os.getenv('CSV_BACKUP_DIR') or str(ROOT / 'backend' / 'backups'))
    app.teardown_appcontext(close_db)
    app.jinja_env.filters['money'] = lambda value: f'{value or 0:,.2f}'

    @app.before_request
    def load_user_and_check_form():
        g.user = None
        if request.endpoint == 'static':
            return
        session.setdefault('csrf_token', secrets.token_hex(32))
        if request.method == 'POST':
            token = request.form.get('csrf_token', '')
            if not secrets.compare_digest(token, session['csrf_token']):
                abort(400, 'The form expired. Reload the page and try again.')
        if session.get('user_id'):
            g.user = query('SELECT id, name, username, email, role FROM employees WHERE id=%s AND active=1',
                           (session['user_id'],), one=True)
            if g.user is None:
                session.clear()
        # Every matched page is protected unless explicitly public. New routes
        # also require an entry in permissions.py before anyone can use them.
        if request.endpoint not in (None, 'login', 'logout'):
            if g.user is None:
                return redirect(url_for('login'))
            if not allowed(g.user['role'], request.endpoint, request.method):
                abort(403, 'Your department does not have access to this action.')

    def can_access(endpoint, method='GET'):
        return bool(getattr(g, 'user', None) and allowed(g.user['role'], endpoint, method))

    @app.after_request
    def backup_changes_and_secure_response(response):
        if getattr(g, 'committed_change', False) and response.status_code < 400 and app.config['AUTO_BACKUP']:
            try:
                create_backup(app.config['MYSQL'], app.config['BACKUP_DIR'])
            except (OSError, ValueError, pymysql.MySQLError) as error:
                # A disk/backup error must not undo or disguise a committed sale.
                app.logger.error('Automatic CSV backup failed: %s', type(error).__name__)
                flash('Your changes were saved, but the CSV backup failed. Ask an Admin to retry on the Backups page.', 'error')
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'none'; style-src 'self'; "
            "img-src 'self' data:; form-action 'self'; frame-ancestors 'none'; base-uri 'self'")
        if request.endpoint != 'static':
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.context_processor
    def shared_template_values():
        return {'user': getattr(g, 'user', None), 'currency': os.getenv('CURRENCY', 'UGX'),
                'can_access': can_access, 'roles': ROLES}

    @app.errorhandler(pymysql.IntegrityError)
    def invalid_relationship(error):
        get_db().rollback()
        return render_template('error.html', title='Cannot save this change',
                               message='A value is already in use, or this record is linked to other records. Check your entries. Remove related records only if they are no longer needed.'), 400

    @app.errorhandler(pymysql.MySQLError)
    def database_error(error):
        if 'db' in g:
            get_db().rollback()
        app.logger.error('MySQL request failed (error code %s)', error.args[0] if error.args else 'unknown')
        return render_template('error.html', title='Database unavailable',
                               message='Check that MySQL is running and that the simplified database has been initialized. See the README setup instructions.'), 503

    @app.errorhandler(ValueError)
    def invalid_form(error):
        if 'db' in g:
            get_db().rollback()
        return render_template('error.html', title='Check your entries', message=str(error)), 400

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    def request_error(error):
        return render_template('error.html', title=f'Error {error.code}', message=error.description), error.code

    @app.route('/login', methods=['GET', 'POST'])
    @app.route('/login.html', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            username = request.form.get('username', '').strip().lower()
            department = request.form.get('department', '')
            employee = query('SELECT * FROM employees WHERE username=%s AND active=1', (username,), one=True)
            if (employee and department in ROLES and employee['role'] == department
                    and check_password_hash(employee['password_hash'], request.form.get('password', ''))):
                session.clear()
                session['user_id'] = employee['id']
                session['csrf_token'] = secrets.token_hex(32)
                return redirect(url_for('dashboard'))
            flash('Incorrect department, username, or password.', 'error')
        return render_template('login.html', title='Sign in')

    @app.post('/logout')
    def logout():
        session.clear()
        return redirect(url_for('login'))

    @app.get('/')
    @app.get('/index.html')
    def dashboard():
        counts = query('SELECT COUNT(*) AS products, COALESCE(SUM(stock),0) AS units, '
                       'COALESCE(SUM(stock <= reorder_level),0) AS low_stock FROM products', one=True)
        low_stock = query('SELECT * FROM products WHERE stock <= reorder_level ORDER BY stock, name LIMIT 8')
        totals, recent = None, []
        if can_access('sales'):
            totals = query('SELECT COALESCE(SUM(si.quantity*si.unit_price),0) AS revenue, '
                           'COUNT(DISTINCT s.id) AS sales FROM sales s JOIN sale_items si ON si.sale_id=s.id', one=True)
            recent = query('SELECT s.id, s.customer_name, s.created_at, SUM(si.quantity*si.unit_price) AS total '
                           'FROM sales s JOIN sale_items si ON si.sale_id=s.id GROUP BY s.id ORDER BY s.id DESC LIMIT 5')
        return render_template('index.html', title='Dashboard', counts=counts, totals=totals,
                               low_stock=low_stock, recent=recent)

    @app.route('/categories.html', methods=['GET', 'POST'])
    def categories():
        if request.method == 'POST':
            name = required('name')
            record_id = request.form.get('id')
            if record_id:
                execute('UPDATE categories SET name=%s WHERE id=%s', (name, int(record_id)))
            else:
                execute('INSERT INTO categories (name) VALUES (%s)', (name,))
            commit()
            flash('Category saved.', 'success')
            return redirect(url_for('categories'))
        editing = query('SELECT * FROM categories WHERE id=%s', (request.args.get('edit'),), one=True) if request.args.get('edit') else None
        rows = query('SELECT c.*, COUNT(p.id) AS product_count FROM categories c LEFT JOIN products p '
                     'ON p.category_id=c.id GROUP BY c.id ORDER BY c.name')
        return render_template('categories.html', title='Categories', rows=rows, editing=editing)

    @app.post('/categories/<int:record_id>/delete')
    def delete_category(record_id):
        execute('DELETE FROM categories WHERE id=%s', (record_id,))
        commit()
        flash('Category deleted.', 'success')
        return redirect(url_for('categories'))

    @app.route('/suppliers.html', methods=['GET', 'POST'])
    def suppliers():
        if request.method == 'POST':
            values = (required('name'), request.form.get('phone', '').strip(), request.form.get('email', '').strip())
            if len(values[1]) > 30 or len(values[2]) > 150:
                raise ValueError('Phone or email is too long.')
            if request.form.get('id'):
                execute('UPDATE suppliers SET name=%s, phone=%s, email=%s WHERE id=%s', values + (integer('id', 1),))
            else:
                execute('INSERT INTO suppliers (name,phone,email) VALUES (%s,%s,%s)', values)
            commit()
            flash('Supplier saved.', 'success')
            return redirect(url_for('suppliers'))
        editing = query('SELECT * FROM suppliers WHERE id=%s', (request.args.get('edit'),), one=True) if request.args.get('edit') else None
        return render_template('suppliers.html', title='Suppliers', rows=query('SELECT * FROM suppliers ORDER BY name'), editing=editing)

    @app.post('/suppliers/<int:record_id>/delete')
    def delete_supplier(record_id):
        execute('DELETE FROM suppliers WHERE id=%s', (record_id,))
        commit()
        flash('Supplier deleted.', 'success')
        return redirect(url_for('suppliers'))

    @app.route('/products.html', methods=['GET', 'POST'])
    def products():
        if request.method == 'POST':
            values = (required('name'), integer('category_id', 1), money('price'), integer('reorder_level'))
            if request.form.get('id'):
                execute('UPDATE products SET name=%s, category_id=%s, price=%s, reorder_level=%s WHERE id=%s',
                        values + (integer('id', 1),))
            else:
                execute('INSERT INTO products (name,category_id,price,reorder_level,stock) VALUES (%s,%s,%s,%s,%s)',
                        values + (integer('stock'),))
            commit()
            flash('Product saved.', 'success')
            return redirect(url_for('products'))
        search = request.args.get('q', '').strip()
        rows = query('SELECT p.*, c.name AS category FROM products p JOIN categories c ON c.id=p.category_id '
                     'WHERE p.name LIKE %s ORDER BY p.name', ('%' + search + '%',))
        editing = query('SELECT * FROM products WHERE id=%s', (request.args.get('edit'),), one=True) if request.args.get('edit') and can_access('products', 'POST') else None
        return render_template('products.html', title='Products & inventory', rows=rows, editing=editing,
                               categories=query('SELECT * FROM categories ORDER BY name'), search=search)

    @app.post('/products/<int:record_id>/delete')
    def delete_product(record_id):
        execute('DELETE FROM products WHERE id=%s', (record_id,))
        commit()
        flash('Product deleted.', 'success')
        return redirect(url_for('products'))

    @app.route('/sales.html', methods=['GET', 'POST'])
    def sales():
        if request.method == 'POST':
            # Combine repeated products before checking stock. Lock rows in ID order.
            cart = {}
            product_ids, quantities = request.form.getlist('product_id'), request.form.getlist('quantity')
            if len(product_ids) != len(quantities) or len(product_ids) > 10:
                raise ValueError('Invalid sale items.')
            for product_id, quantity in zip(product_ids, quantities):
                if not product_id:
                    continue
                try:
                    product_id, quantity = int(product_id), int(quantity)
                except ValueError:
                    raise ValueError('Select a product and enter a whole-number quantity.')
                if quantity < 1 or quantity > 1000000:
                    raise ValueError('Sale quantities must be between 1 and 1,000,000.')
                cart[product_id] = cart.get(product_id, 0) + quantity
            if not cart:
                raise ValueError('Select at least one product.')
            customer = request.form.get('customer_name', '').strip() or 'Walk-in customer'
            if len(customer) > 100:
                raise ValueError('Customer name is too long.')
            sale_id = execute('INSERT INTO sales (employee_id,customer_name) VALUES (%s,%s)', (g.user['id'], customer))
            for product_id, quantity in sorted(cart.items()):
                product = query('SELECT * FROM products WHERE id=%s FOR UPDATE', (product_id,), one=True)
                if not product or product['stock'] < quantity:
                    raise ValueError('Insufficient stock for one of the selected products. No sale was saved.')
                execute('INSERT INTO sale_items (sale_id,product_id,quantity,unit_price) VALUES (%s,%s,%s,%s)',
                        (sale_id, product_id, quantity, product['price']))
                execute('UPDATE products SET stock=stock-%s WHERE id=%s', (quantity, product_id))
            commit()
            flash(f'Sale #{sale_id} saved. Stock has been reduced.', 'success')
            return redirect(url_for('receipt', sale_id=sale_id))
        rows = query('SELECT s.*, e.name AS employee, SUM(si.quantity*si.unit_price) AS total '
                     'FROM sales s JOIN employees e ON e.id=s.employee_id JOIN sale_items si ON si.sale_id=s.id '
                     'GROUP BY s.id ORDER BY s.id DESC')
        return render_template('sales.html', title='Sales', rows=rows,
                               products=query('SELECT * FROM products WHERE stock>0 ORDER BY name'))

    @app.get('/sales/<int:sale_id>')
    def receipt(sale_id):
        sale = query('SELECT s.*, e.name AS employee FROM sales s JOIN employees e ON e.id=s.employee_id '
                     'WHERE s.id=%s', (sale_id,), one=True)
        if not sale:
            abort(404)
        items = query('SELECT si.*, p.name, si.quantity*si.unit_price AS total FROM sale_items si '
                      'JOIN products p ON p.id=si.product_id WHERE si.sale_id=%s', (sale_id,))
        return render_template('receipt.html', title=f'Sale #{sale_id}', sale=sale, items=items,
                               total=sum(item['total'] for item in items))

    @app.route('/purchase-orders.html', methods=['GET', 'POST'])
    def purchases():
        if request.method == 'POST':
            product_id, supplier_id = integer('product_id', 1), integer('supplier_id', 1)
            quantity, unit_cost = integer('quantity', 1), money('unit_cost')
            product = query('SELECT id FROM products WHERE id=%s FOR UPDATE', (product_id,), one=True)
            if not product:
                raise ValueError('Choose an existing product.')
            execute('INSERT INTO purchases (supplier_id,product_id,employee_id,quantity,unit_cost) VALUES (%s,%s,%s,%s,%s)',
                    (supplier_id, product_id, g.user['id'], quantity, unit_cost))
            execute('UPDATE products SET stock=stock+%s WHERE id=%s', (quantity, product_id))
            commit()
            flash('Purchase received. Stock has been increased.', 'success')
            return redirect(url_for('purchases'))
        rows = query('SELECT pu.*, p.name AS product, s.name AS supplier, e.name AS employee, '
                     'pu.quantity*pu.unit_cost AS total FROM purchases pu JOIN products p ON p.id=pu.product_id '
                     'JOIN suppliers s ON s.id=pu.supplier_id JOIN employees e ON e.id=pu.employee_id ORDER BY pu.id DESC')
        return render_template('purchase-orders.html', title='Purchases', rows=rows,
                               products=query('SELECT * FROM products ORDER BY name'),
                               suppliers=query('SELECT * FROM suppliers ORDER BY name'))

    @app.route('/employees.html', methods=['GET', 'POST'])
    def employees():
        if request.method == 'POST':
            name, role = required('name'), required('role')
            username = valid_username(required('username', 50))
            email = request.form.get('email', '').strip() or None
            if (email and ('@' not in email or len(email) > 150)) or role not in ROLES:
                raise ValueError('Choose Admin, Sales, or Purchasing and provide a valid email if used.')
            record_id = integer('id', 1) if request.form.get('id') else None
            duplicate = query('SELECT id FROM employees WHERE username=%s', (username,), one=True)
            if duplicate and duplicate['id'] != record_id:
                raise ValueError('That username is already in use. Choose another username.')
            password = request.form.get('password', '')
            if password and len(password) < 8:
                raise ValueError('Passwords must contain at least eight characters.')
            if record_id:
                if record_id == g.user['id'] and role != 'Admin':
                    raise ValueError('You cannot remove your own administrator access.')
                execute('UPDATE employees SET name=%s, username=%s, email=%s, role=%s WHERE id=%s',
                        (name, username, email, role, record_id))
                if password:
                    execute('UPDATE employees SET password_hash=%s WHERE id=%s', (generate_password_hash(password), record_id))
            else:
                if not password:
                    raise ValueError('A password is required for a new employee.')
                execute('INSERT INTO employees (name,username,email,role,password_hash) VALUES (%s,%s,%s,%s,%s)',
                        (name, username, email, role, generate_password_hash(password)))
            commit()
            flash('Employee saved.', 'success')
            return redirect(url_for('employees'))
        editing = query('SELECT id,name,username,email,role FROM employees WHERE id=%s', (request.args.get('edit'),), one=True) if request.args.get('edit') else None
        return render_template('employees.html', title='Employees', editing=editing,
                               rows=query('SELECT id,name,username,email,role,active FROM employees ORDER BY name'))

    @app.post('/employees/<int:record_id>/toggle')
    def toggle_employee(record_id):
        if record_id == g.user['id']:
            raise ValueError('You cannot deactivate your own account.')
        execute('UPDATE employees SET active=NOT active WHERE id=%s', (record_id,))
        commit()
        flash('Employee status updated.', 'success')
        return redirect(url_for('employees'))

    @app.route('/settings.html', methods=['GET', 'POST'])
    def settings():
        if request.method == 'POST':
            row = query('SELECT password_hash FROM employees WHERE id=%s', (g.user['id'],), one=True)
            if not check_password_hash(row['password_hash'], request.form.get('current_password', '')):
                raise ValueError('Your current password is incorrect.')
            password = request.form.get('password', '')
            if len(password) < 8 or password != request.form.get('confirm_password'):
                raise ValueError('Use at least eight characters and make sure the new passwords match.')
            execute('UPDATE employees SET password_hash=%s WHERE id=%s', (generate_password_hash(password), g.user['id']))
            commit()
            flash('Password changed.', 'success')
            return redirect(url_for('settings'))
        return render_template('settings.html', title='My account')

    @app.get('/backups.html')
    def backups():
        return render_template('backups.html', title='CSV backups', tables=TABLES,
                               snapshots=list_backups(app.config['BACKUP_DIR'])[:10],
                               backup_location=str(Path(app.config['BACKUP_DIR']).resolve()))

    @app.post('/backups/create')
    def create_snapshot():
        try:
            folder = create_backup(app.config['MYSQL'], app.config['BACKUP_DIR'])
        except OSError:
            flash('Could not write the backup. Check available disk space and folder permissions.', 'error')
            return redirect(url_for('backups'))
        flash('CSV backup created: ' + folder.name, 'success')
        return redirect(url_for('backups'))

    @app.get('/backups/<name>/download')
    def download_backup(name):
        folder = backup_folder(app.config['BACKUP_DIR'], name)
        return send_file(zip_backup(folder), mimetype='application/zip', as_attachment=True,
                         download_name=name + '.zip', max_age=0)

    @app.get('/backups/<name>/<table>.csv')
    def download_csv(name, table):
        if table not in TABLES:
            abort(404)
        folder = backup_folder(app.config['BACKUP_DIR'], name)
        load_backup(folder)
        return send_file(folder / (table + '.csv'), mimetype='text/csv', as_attachment=True,
                         download_name=table + '.csv', max_age=0)

    @app.cli.command('create-backup')
    def create_backup_command():
        """Save seven CSV files and a checksum manifest on this computer."""
        folder = create_backup(app.config['MYSQL'], app.config['BACKUP_DIR'])
        click.echo('CSV backup saved to: ' + str(folder))

    @app.cli.command('restore-backup')
    @click.argument('folder', type=click.Path(exists=True, file_okay=False, path_type=Path))
    @click.option('--database', required=True, help='A separate empty MySQL database to restore into.')
    def restore_backup_command(folder, database):
        """Restore all seven CSV files together, without overwriting existing data."""
        original = urlsplit(os.getenv('DATABASE_URL', '')).path.strip('/')
        if database.lower() in (app.config['MYSQL']['database'].lower(), original.lower()):
            raise click.ClickException('Choose a separate empty database; the working databases are protected.')
        try:
            load_backup(folder)
            target = dict(app.config['MYSQL'], database=database)
            if not re.fullmatch(r'[A-Za-z0-9_]+', database):
                raise ValueError('Use only letters, numbers and underscores in the database name.')
            try:
                with connect(target) as connection:
                    with connection.cursor() as cursor:
                        cursor.execute('SHOW TABLES')
                        existing = {next(iter(row.values())) for row in cursor.fetchall()}
                if existing and existing != set(TABLES):
                    raise ValueError('The destination contains unrelated tables. Choose a new empty database.')
                if not existing:
                    initialize(target)
            except pymysql.OperationalError as error:
                if error.args[0] != 1049:
                    raise
                initialize(target)
            counts = restore_backup(folder, target)
        except ValueError as error:
            raise click.ClickException(str(error)) from error
        except pymysql.MySQLError as error:
            raise click.ClickException('Restore failed. No rows were committed. Check database permissions, relationships, and constraints.') from error
        click.echo(f'Restored {sum(counts.values())} rows into {database}. The working database is unchanged.')

    @app.cli.command('init-db')
    def init_db_command():
        """Create the seven tables and first administrator; never erase data."""
        initialize(app.config['MYSQL'])
        if not query('SELECT id FROM employees WHERE role=%s AND active=1 LIMIT 1', ('Admin',), one=True):
            name = os.getenv('ADMIN_NAME') or click.prompt('Administrator name')
            username = valid_username(os.getenv('ADMIN_USERNAME') or username_from_name(name))
            email = os.getenv('ADMIN_EMAIL') or None
            password = os.getenv('ADMIN_PASSWORD') or click.prompt('Administrator password', hide_input=True, confirmation_prompt=True)
            if len(password) < 8 or (email and '@' not in email):
                raise click.ClickException('Use an ADMIN_PASSWORD of at least eight characters and a valid ADMIN_EMAIL if provided.')
            execute('INSERT INTO employees (name,username,email,password_hash,role) VALUES (%s,%s,%s,%s,%s)',
                    (name, username, email, generate_password_hash(password), 'Admin'))
            commit()
        click.echo('Simplified MySQL database ready: ' + app.config['MYSQL']['database'])
        admin = query("SELECT username FROM employees WHERE role='Admin' AND active=1 ORDER BY id LIMIT 1", one=True)
        click.echo('Sign in with department Admin and username: ' + admin['username'])

    return app


app = create_app()

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        from flask.cli import ScriptInfo
        app.cli.main(args=sys.argv[1:], prog_name='python backend/main.py',
                     obj=ScriptInfo(create_app=lambda: app))
    else:
        app.run(host='127.0.0.1', port=int(os.getenv('APP_PORT', '8000')), debug=False)
