"""Real Flask/MySQL integration tests in a disposable, isolated schema."""
import re
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from werkzeug.security import generate_password_hash

from db import connect, connection_settings, execute, get_db, initialize, query
from main import create_app


class StoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mysql = connection_settings()
        cls.mysql['database'] = 'hw_test_' + uuid.uuid4().hex[:12]
        initialize(cls.mysql)
        cls.app = create_app({'TESTING': True, 'SECRET_KEY': 'integration-test-key', 'MYSQL': cls.mysql})

    @classmethod
    def tearDownClass(cls):
        name = cls.mysql['database']
        assert re.fullmatch(r'hw_test_[a-f0-9]{12}', name)
        with connect(cls.mysql) as connection:
            with connection.cursor() as cursor:
                cursor.execute(f'DROP DATABASE `{name}`')

    def setUp(self):
        self.client = self.app.test_client()
        with self.app.app_context():
            for table in ('sale_items', 'sales', 'purchases', 'products', 'categories', 'suppliers', 'employees'):
                execute(f'DELETE FROM {table}')
            self.admin = execute('INSERT INTO employees (name,email,password_hash,role) VALUES (%s,%s,%s,%s)',
                                 ('Test Admin', 'admin@example.test', generate_password_hash('test-password'), 'Admin'))
            self.staff = execute('INSERT INTO employees (name,email,password_hash,role) VALUES (%s,%s,%s,%s)',
                                 ('Test Staff', 'staff@example.test', generate_password_hash('test-password'), 'Sales'))
            self.category = execute('INSERT INTO categories (name) VALUES (%s)', ('Tools',))
            self.supplier = execute('INSERT INTO suppliers (name) VALUES (%s)', ('Test Supplier',))
            self.product = execute('INSERT INTO products (name,category_id,price,stock) VALUES (%s,%s,%s,%s)',
                                   ('Hammer', self.category, Decimal('20.50'), 10))
            self.second = execute('INSERT INTO products (name,category_id,price,stock) VALUES (%s,%s,%s,%s)',
                                  ('Saw', self.category, Decimal('35.00'), 1))
            get_db().commit()
        self.login()

    def post(self, path, data=None, follow_redirects=False):
        self.client.get('/login')
        with self.client.session_transaction() as session:
            token = session['csrf_token']
        values = dict(data or {})
        values['csrf_token'] = token
        return self.client.post(path, data=values, follow_redirects=follow_redirects)

    def login(self, email='admin@example.test', password='test-password'):
        return self.post('/login', {'email': email, 'password': password})

    def read(self, sql, params=()):
        with self.app.app_context():
            return query(sql, params, one=True)

    def test_all_pages_render_without_javascript(self):
        for path in ('/', '/index.html', '/products.html', '/categories.html', '/suppliers.html',
                     '/purchase-orders.html', '/sales.html', '/employees.html', '/settings.html'):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertNotIn(b'<script', response.data)
        with self.client.get('/assets/css/style.css') as response:
            self.assertEqual(response.status_code, 200)
        self.assertIn(b'<option selected>Sales</option>', self.client.get('/employees.html').data)
        with self.app.app_context():
            self.assertEqual(len(query('SHOW TABLES')), 7)

    def test_purchase_then_sale_updates_stock_receipt_and_dashboard(self):
        response = self.post('/purchase-orders.html', {'supplier_id': self.supplier,
                             'product_id': self.product, 'quantity': 5, 'unit_cost': '12.25'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.read('SELECT stock FROM products WHERE id=%s', (self.product,))['stock'], 15)
        response = self.post('/sales.html', {'product_id': [str(self.product), '', ''],
                             'quantity': ['3', '1', '1'], 'customer_name': 'Jane'}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'61.50', response.data)
        self.assertIn(b'Jane', response.data)
        self.assertEqual(self.read('SELECT stock FROM products WHERE id=%s', (self.product,))['stock'], 12)
        self.assertIn(b'61.50', self.client.get('/').data)
        with self.app.app_context():
            execute('UPDATE products SET price=99 WHERE id=%s', (self.product,))
            get_db().commit()
        self.assertEqual(self.read('SELECT unit_price FROM sale_items')['unit_price'], Decimal('20.50'))

    def test_sale_rolls_back_all_items_when_one_is_out_of_stock(self):
        response = self.post('/sales.html', {'product_id': [str(self.product), str(self.second)],
                             'quantity': ['2', '5']})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.read('SELECT COUNT(*) AS n FROM sales')['n'], 0)
        self.assertEqual(self.read('SELECT COUNT(*) AS n FROM sale_items')['n'], 0)
        self.assertEqual(self.read('SELECT stock FROM products WHERE id=%s', (self.product,))['stock'], 10)

    def test_repeated_product_cannot_bypass_stock_check(self):
        response = self.post('/sales.html', {'product_id': [str(self.product), str(self.product)],
                             'quantity': ['6', '6']})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.read('SELECT COUNT(*) AS n FROM sales')['n'], 0)

    def test_two_simultaneous_sales_cannot_oversell(self):
        def sell():
            with self.app.test_client() as client:
                with client.session_transaction() as session:
                    session['user_id'] = self.staff
                    session['csrf_token'] = 'test-sale-token'
                return client.post('/sales.html', data={'csrf_token': 'test-sale-token',
                                   'product_id': str(self.product), 'quantity': '7'}).status_code
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(lambda _: sell(), range(2)))
        self.assertEqual(sorted(results), [302, 400])
        self.assertEqual(self.read('SELECT stock FROM products WHERE id=%s', (self.product,))['stock'], 3)
        self.assertEqual(self.read('SELECT COUNT(*) AS n FROM sales')['n'], 1)

    def test_init_command_preserves_existing_data(self):
        result = self.app.test_cli_runner().invoke(args=['init-db'])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(self.read('SELECT stock FROM products WHERE id=%s', (self.product,))['stock'], 10)
        self.assertEqual(self.read('SELECT COUNT(*) AS n FROM employees')['n'], 2)

    def test_product_crud_search_and_category_protection(self):
        response = self.post('/products.html', {'name': 'Nails', 'category_id': self.category,
                             'price': '2.00', 'stock': 20, 'reorder_level': 5})
        self.assertEqual(response.status_code, 302)
        product = self.read('SELECT * FROM products WHERE name=%s', ('Nails',))
        response = self.post('/products.html', {'id': product['id'], 'name': 'Steel nails',
                             'category_id': self.category, 'price': '2.50', 'reorder_level': 4})
        self.assertEqual(response.status_code, 302)
        self.assertIn(b'Steel nails', self.client.get('/products.html?q=Steel').data)
        self.assertEqual(self.post(f'/categories/{self.category}/delete').status_code, 400)
        self.assertEqual(self.post(f'/products/{product["id"]}/delete').status_code, 302)

    def test_invalid_money_quantity_and_foreign_keys_do_not_change_stock(self):
        for quantity, cost in [('-1', '1'), ('1.5', '1'), ('1', 'NaN'), ('1', '0.001')]:
            with self.subTest(quantity=quantity, cost=cost):
                response = self.post('/purchase-orders.html', {'supplier_id': self.supplier,
                                     'product_id': self.product, 'quantity': quantity, 'unit_cost': cost})
                self.assertEqual(response.status_code, 400)
        response = self.post('/purchase-orders.html', {'supplier_id': 999999,
                             'product_id': self.product, 'quantity': 1, 'unit_cost': '1'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.read('SELECT stock FROM products WHERE id=%s', (self.product,))['stock'], 10)

    def test_login_csrf_and_staff_authorization(self):
        self.post('/logout')
        self.assertEqual(self.client.get('/products.html').status_code, 302)
        response = self.login(password='wrong')
        self.assertIn(b'Incorrect email or password', response.data)
        self.assertEqual(self.client.post('/login', data={'email': 'admin@example.test'}).status_code, 400)
        self.login('staff@example.test')
        self.assertEqual(self.client.get('/employees.html').status_code, 403)
        self.assertEqual(self.post(f'/employees/{self.admin}/toggle').status_code, 403)
        self.assertEqual(self.client.get('/sales.html').status_code, 200)

    def test_deactivation_blocks_existing_session_and_self_deactivation_is_rejected(self):
        self.assertEqual(self.post(f'/employees/{self.admin}/toggle').status_code, 400)
        self.login('staff@example.test')
        with self.app.app_context():
            execute('UPDATE employees SET active=0 WHERE id=%s', (self.staff,))
            get_db().commit()
        self.assertEqual(self.client.get('/sales.html').status_code, 302)

    def test_password_change_and_old_password_rejected(self):
        response = self.post('/settings.html', {'current_password': 'test-password',
                             'password': 'a-new-password', 'confirm_password': 'a-new-password'})
        self.assertEqual(response.status_code, 302)
        self.post('/logout')
        self.assertIn(b'Incorrect email or password', self.login().data)
        self.assertEqual(self.login(password='a-new-password').status_code, 302)

    def test_supplier_and_category_forms_and_employee_creation(self):
        self.assertEqual(self.post('/categories.html', {'name': 'Plumbing'}).status_code, 302)
        self.assertEqual(self.post('/suppliers.html', {'name': 'New Supplier', 'phone': '0700000000',
                                                     'email': 'supplier@example.test'}).status_code, 302)
        self.assertEqual(self.post('/employees.html', {'name': 'New Staff', 'email': 'new@example.test',
                             'role': 'Sales', 'password': 'new-password'}).status_code, 302)
        employee = self.read('SELECT * FROM employees WHERE email=%s', ('new@example.test',))
        self.assertNotEqual(employee['password_hash'], 'new-password')

    def test_html_is_escaped_and_sql_input_is_only_data(self):
        response = self.post('/categories.html', {'name': '<script>alert(1)</script>'}, follow_redirects=True)
        self.assertIn(b'&lt;script&gt;', response.data)
        self.assertNotIn(b'<script>', response.data)
        self.assertEqual(self.client.get("/products.html?q=' OR 1=1 --").status_code, 200)
        self.assertEqual(self.read('SELECT COUNT(*) AS n FROM employees')['n'], 2)

    def test_sales_cannot_manage_stock_purchases_or_accounts(self):
        self.login('staff@example.test')
        page = self.client.get('/products.html?edit=' + str(self.product))
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(b'Save product', page.data)
        self.assertNotIn(b'>Edit</a>', page.data)
        self.assertNotIn(b'Delete</button>', page.data)
        self.assertNotIn(b'href="/suppliers.html"', page.data)
        self.assertNotIn(b'href="/purchase-orders.html"', page.data)
        for path in ('/categories.html', '/suppliers.html', '/purchase-orders.html', '/employees.html'):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 403)
                self.assertEqual(self.post(path, {'role': 'Admin'}).status_code, 403)
        for path in ('/products.html', f'/products/{self.product}/delete',
                     f'/categories/{self.category}/delete', f'/suppliers/{self.supplier}/delete',
                     f'/employees/{self.admin}/toggle'):
            self.assertEqual(self.post(path, {'name': 'Changed', 'price': '0'}).status_code, 403)
        self.assertEqual(self.read('SELECT stock FROM products WHERE id=%s', (self.product,))['stock'], 10)
        self.assertEqual(self.read('SELECT name FROM products WHERE id=%s', (self.product,))['name'], 'Hammer')
        self.assertEqual(self.read('SELECT role FROM employees WHERE id=%s', (self.staff,))['role'], 'Sales')
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertEqual(self.client.get('/settings.html').status_code, 200)

    def test_purchasing_can_receive_stock_but_cannot_access_sales(self):
        self.post('/sales.html', {'product_id': str(self.product), 'quantity': '1'})
        sale_id = self.read('SELECT id FROM sales')['id']
        self.assertEqual(self.post('/employees.html', {'name': 'Buyer', 'email': 'buyer@example.test',
                             'role': 'Purchasing', 'password': 'buyer-password'}).status_code, 302)
        self.assertEqual(self.login('buyer@example.test', 'buyer-password').status_code, 302)
        dashboard = self.client.get('/')
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn(b'Purchasing workspace', dashboard.data)
        self.assertNotIn(b'Recent sales', dashboard.data)
        self.assertNotIn(b'Total sales revenue', dashboard.data)
        self.assertNotIn(b'href="/sales.html"', dashboard.data)
        for path in ('/products.html', '/categories.html', '/suppliers.html', '/purchase-orders.html', '/settings.html'):
            self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.client.get('/sales.html').status_code, 403)
        self.assertEqual(self.client.get(f'/sales/{sale_id}').status_code, 403)
        self.assertEqual(self.post('/sales.html', {'product_id': self.product, 'quantity': '1'}).status_code, 403)
        self.assertEqual(self.client.get('/employees.html').status_code, 403)
        self.assertEqual(self.post('/employees.html', {'role': 'Admin'}).status_code, 403)
        self.assertEqual(self.post('/categories.html', {'name': 'New category'}).status_code, 302)
        self.assertEqual(self.post('/suppliers.html', {'name': 'Another supplier'}).status_code, 302)
        self.assertEqual(self.post('/products.html', {'id': self.product, 'name': 'Hammer',
                         'category_id': self.category, 'price': '22.00', 'reorder_level': 3}).status_code, 302)
        self.assertEqual(self.post('/purchase-orders.html', {'supplier_id': self.supplier,
                         'product_id': self.product, 'quantity': 5, 'unit_cost': '12.00'}).status_code, 302)
        self.assertEqual(self.read('SELECT stock FROM products WHERE id=%s', (self.product,))['stock'], 14)
        self.assertEqual(self.read('SELECT COUNT(*) AS n FROM sales')['n'], 1)

    def test_admin_role_change_takes_effect_in_existing_session(self):
        department_client = self.app.test_client()
        with department_client.session_transaction() as session:
            session['user_id'] = self.staff
        self.assertEqual(department_client.get('/sales.html').status_code, 200)
        self.assertEqual(self.post('/employees.html', {'id': self.staff, 'name': 'Buyer',
                         'email': 'staff@example.test', 'role': 'Purchasing'}).status_code, 302)
        self.assertEqual(department_client.get('/sales.html').status_code, 403)
        self.assertEqual(department_client.get('/purchase-orders.html').status_code, 200)
        self.assertEqual(self.post('/employees.html', {'id': self.admin, 'name': 'Admin',
                         'email': 'admin@example.test', 'role': 'Sales'}).status_code, 400)
        self.assertEqual(self.post('/employees.html', {'name': 'Invalid', 'email': 'invalid@example.test',
                         'role': 'Owner', 'password': 'test-password'}).status_code, 400)

    def test_legacy_staff_upgrade_preserves_accounts_and_business_records(self):
        with self.app.app_context():
            execute("ALTER TABLE employees MODIFY role ENUM('Admin','Staff','Sales','Purchasing') NOT NULL DEFAULT 'Staff'")
            execute("UPDATE employees SET role='Staff' WHERE id=%s", (self.staff,))
            get_db().commit()
        for _ in range(2):
            result = self.app.test_cli_runner().invoke(args=['init-db'])
            self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(self.read('SELECT role FROM employees WHERE id=%s', (self.staff,))['role'], 'Sales')
        self.assertEqual(self.read('SELECT COUNT(*) AS n FROM employees')['n'], 2)
        self.assertEqual(self.read('SELECT stock FROM products WHERE id=%s', (self.product,))['stock'], 10)

    def test_unknown_roles_and_unlisted_endpoints_are_denied(self):
        from permissions import allowed
        self.assertFalse(allowed('Staff', 'sales'))
        self.assertFalse(allowed('Owner', 'employees', 'POST'))
        app = create_app({'TESTING': True, 'SECRET_KEY': 'test', 'MYSQL': self.mysql})

        @app.get('/unlisted')
        def unlisted():
            return 'This must not be accessible.'

        with app.test_client() as client:
            with client.session_transaction() as session:
                session['user_id'] = self.admin
            self.assertEqual(client.get('/unlisted').status_code, 403)


if __name__ == '__main__':
    unittest.main()
