"""Hardware World: HTML forms -> Flask routes -> parameterized MySQL queries."""
import os
import secrets
from decimal import Decimal, InvalidOperation

import click
import pymysql
from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from db import ROOT, close_db, connection_settings, execute, get_db, initialize, query
from permissions import ROLES, allowed


def required(name, limit=100):
    value = request.form.get(name, '').strip()
    if not value or len(value) > limit:
        raise ValueError(f'{name.replace("_", " ").title()} is required (maximum {limit} characters).')
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
            g.user = query('SELECT id, name, email, role FROM employees WHERE id=%s AND active=1',
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
            email = required('email', 150)
            employee = query('SELECT * FROM employees WHERE email=%s AND active=1', (email,), one=True)
            if employee and check_password_hash(employee['password_hash'], request.form.get('password', '')):
                session.clear()
                session['user_id'] = employee['id']
                session['csrf_token'] = secrets.token_hex(32)
                return redirect(url_for('dashboard'))
            flash('Incorrect email or password.', 'error')
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
            get_db().commit()
            flash('Category saved.', 'success')
            return redirect(url_for('categories'))
        editing = query('SELECT * FROM categories WHERE id=%s', (request.args.get('edit'),), one=True) if request.args.get('edit') else None
        rows = query('SELECT c.*, COUNT(p.id) AS product_count FROM categories c LEFT JOIN products p '
                     'ON p.category_id=c.id GROUP BY c.id ORDER BY c.name')
        return render_template('categories.html', title='Categories', rows=rows, editing=editing)

    @app.post('/categories/<int:record_id>/delete')
    def delete_category(record_id):
        execute('DELETE FROM categories WHERE id=%s', (record_id,))
        get_db().commit()
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
            get_db().commit()
            flash('Supplier saved.', 'success')
            return redirect(url_for('suppliers'))
        editing = query('SELECT * FROM suppliers WHERE id=%s', (request.args.get('edit'),), one=True) if request.args.get('edit') else None
        return render_template('suppliers.html', title='Suppliers', rows=query('SELECT * FROM suppliers ORDER BY name'), editing=editing)

    @app.post('/suppliers/<int:record_id>/delete')
    def delete_supplier(record_id):
        execute('DELETE FROM suppliers WHERE id=%s', (record_id,))
        get_db().commit()
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
            get_db().commit()
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
        get_db().commit()
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
            get_db().commit()
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
            get_db().commit()
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
            name, email, role = required('name'), required('email', 150), required('role')
            if '@' not in email or role not in ROLES:
                raise ValueError('Provide a valid email and choose Admin, Sales, or Purchasing.')
            password = request.form.get('password', '')
            record_id = request.form.get('id')
            if password and len(password) < 8:
                raise ValueError('Passwords must contain at least eight characters.')
            if record_id:
                record_id = integer('id', 1)
                if record_id == g.user['id'] and role != 'Admin':
                    raise ValueError('You cannot remove your own administrator access.')
                execute('UPDATE employees SET name=%s, email=%s, role=%s WHERE id=%s', (name, email, role, record_id))
                if password:
                    execute('UPDATE employees SET password_hash=%s WHERE id=%s', (generate_password_hash(password), record_id))
            else:
                if not password:
                    raise ValueError('A password is required for a new employee.')
                execute('INSERT INTO employees (name,email,role,password_hash) VALUES (%s,%s,%s,%s)',
                        (name, email, role, generate_password_hash(password)))
            get_db().commit()
            flash('Employee saved.', 'success')
            return redirect(url_for('employees'))
        editing = query('SELECT id,name,email,role FROM employees WHERE id=%s', (request.args.get('edit'),), one=True) if request.args.get('edit') else None
        return render_template('employees.html', title='Employees', editing=editing,
                               rows=query('SELECT id,name,email,role,active FROM employees ORDER BY name'))

    @app.post('/employees/<int:record_id>/toggle')
    def toggle_employee(record_id):
        if record_id == g.user['id']:
            raise ValueError('You cannot deactivate your own account.')
        execute('UPDATE employees SET active=NOT active WHERE id=%s', (record_id,))
        get_db().commit()
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
            get_db().commit()
            flash('Password changed.', 'success')
            return redirect(url_for('settings'))
        return render_template('settings.html', title='My account')

    @app.cli.command('init-db')
    def init_db_command():
        """Create the seven tables and first administrator; never erase data."""
        initialize(app.config['MYSQL'])
        if not query('SELECT id FROM employees WHERE role=%s AND active=1 LIMIT 1', ('Admin',), one=True):
            name = os.getenv('ADMIN_NAME') or click.prompt('Administrator name')
            email = os.getenv('ADMIN_EMAIL') or click.prompt('Administrator email')
            password = os.getenv('ADMIN_PASSWORD') or click.prompt('Administrator password', hide_input=True, confirmation_prompt=True)
            if len(password) < 8 or '@' not in email:
                raise click.ClickException('Set a valid ADMIN_EMAIL and an ADMIN_PASSWORD of at least eight characters.')
            execute('INSERT INTO employees (name,email,password_hash,role) VALUES (%s,%s,%s,%s)',
                    (name, email, generate_password_hash(password), 'Admin'))
            get_db().commit()
        click.echo('Simplified MySQL database ready: ' + app.config['MYSQL']['database'])

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
