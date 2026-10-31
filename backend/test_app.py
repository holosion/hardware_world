"""Real Flask/MySQL integration tests in a disposable, isolated schema."""
import re
import csv
import hashlib
import io
import json
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from db import connect, connection_settings, execute, get_db, initialize, query
from main import create_app


class StoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mysql = connection_settings()
        cls.mysql['database'] = 'hw_test_' + uuid.uuid4().hex[:12]
        initialize(cls.mysql)
        cls.receipts = tempfile.TemporaryDirectory()
        cls.app = create_app({'TESTING': True, 'SECRET_KEY': 'integration-test-key', 'MYSQL': cls.mysql,
                             'RECEIPT_DIR': cls.receipts.name})

    @classmethod
    def tearDownClass(cls):
        cls.receipts.cleanup()
        name = cls.mysql['database']
        assert re.fullmatch(r'hw_test_[a-f0-9]{12}', name)
        with connect(cls.mysql) as connection:
            with connection.cursor() as cursor:
                cursor.execute(f'DROP DATABASE `{name}`')

    def setUp(self):
        for receipt in Path(self.receipts.name).glob('sale-*.docx'):
            receipt.unlink()
        self.client = self.app.test_client()
        with self.app.app_context():
            from backup import TABLES
            execute('SET @restoring_snapshot=1')
            execute('UPDATE employees SET supervisor_id=NULL')
            for table in reversed(TABLES):
                execute(f'DELETE FROM {table}')
            execute('SET @restoring_snapshot=0')
            from department_jobs import DEPARTMENT_JOBS
            branch = execute('INSERT INTO branches(name,location) VALUES(%s,%s)', ('Fixture Branch','Kampala'))
            self.job_departments = {}
            for department_name, jobs in DEPARTMENT_JOBS.items():
                department_id = execute('INSERT INTO departments(branch_id,name) VALUES(%s,%s)', (branch,department_name))
                for job in jobs:
                    self.job_departments[job] = department_id
            self.admin = execute('INSERT INTO employees (name,username,email,password_hash,role) VALUES (%s,%s,%s,%s,%s)',
                                 ('Test Admin', 'admin', 'admin@example.test', generate_password_hash('test-password'), 'Admin'))
            self.staff = execute('INSERT INTO employees (name,username,email,password_hash,role) VALUES (%s,%s,%s,%s,%s)',
                                 ('Test Staff', 'staff', 'staff@example.test', generate_password_hash('test-password'), 'Sales'))
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
        if path == '/employees.html':
            # Simulate a selected job in the employee form for existing account tests.
            values.setdefault('job_type', 'Cashier')
        if path in ('/employees.html', '/staff-profiles.html'):
            values.setdefault('department_id', self.job_departments.get(values.get('job_type'), ''))
        values['csrf_token'] = token
        return self.client.post(path, data=values, follow_redirects=follow_redirects)

    def login(self, username='admin', password='test-password', department=None):
        department = department or ('Admin' if username == 'admin' else 'Purchasing' if username == 'buyer' else 'Sales')
        return self.post('/login', {'username': username, 'password': password, 'department': department})

    def read(self, sql, params=()):
        with self.app.app_context():
            return query(sql, params, one=True)

    def test_hiring_each_job_creates_its_subtype(self):
        from business import SUBTYPES
        for index, (job, table) in enumerate(SUBTYPES.items()):
            response = self.post('/employees.html', {'name': 'Job Test', 'username': f'job{index}',
                'role': 'Sales', 'job_type': job, 'password': 'test-password'})
            self.assertEqual(response.status_code, 302)
            employee = self.read('SELECT id,job_type,role FROM employees WHERE username=%s', (f'job{index}',))
            self.assertEqual(employee['job_type'], job)
            self.assertEqual(employee['role'], 'Sales')
            for subtype in SUBTYPES.values():
                self.assertEqual(self.read(f'SELECT COUNT(*) AS n FROM {subtype} WHERE employee_id=%s',
                                          (employee['id'],))['n'], int(subtype == table))
        self.assertIn(b'Accountant', self.client.get('/employees.html').data)

    def test_employee_job_edit_preserves_login_and_synchronizes_subtypes(self):
        before = self.read('SELECT password_hash FROM employees WHERE id=%s', (self.staff,))
        response = self.post('/employees.html', {'id': self.staff, 'name':'Test Staff',
            'username':'staff', 'role':'Sales', 'job_type':'Accountant'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(self.read('SELECT COUNT(*) AS n FROM accountants WHERE employee_id=%s',(self.staff,))['n'],1)
        self.assertEqual(self.read('SELECT COUNT(*) AS n FROM cashiers WHERE employee_id=%s',(self.staff,))['n'],0)
        self.assertEqual(self.read('SELECT password_hash FROM employees WHERE id=%s',(self.staff,)),before)
        self.assertIn(b'value="Accountant" selected',self.client.get(f'/employees.html?edit={self.staff}').data)
        self.assertEqual(self.login('staff').status_code,302)

    def test_employee_job_and_department_validation(self):
        data={'name':'New Accountant','username':'new.accountant','role':'Sales','password':'test-password','job_type':'Accountant'}
        for job in ('', 'Unknown'):
            self.assertEqual(self.post('/employees.html',dict(data,job_type=job)).status_code,400)
        with self.client.session_transaction() as session:
            token=session['csrf_token']
        missing=dict(data,csrf_token=token)
        del missing['job_type']
        self.assertEqual(self.client.post('/employees.html',data=missing).status_code,400)
        self.assertEqual(self.post('/employees.html',dict(data,department_id=999999)).status_code,400)
        self.assertEqual(self.read('SELECT COUNT(*) AS n FROM accountants')['n'],0)
        with self.app.app_context():
            branch=execute('INSERT INTO branches(name,location) VALUES(%s,%s)',('Test Branch','Kampala'))
            department=execute('INSERT INTO departments(branch_id,name) VALUES(%s,%s)',(branch,'Accounting'))
            get_db().commit()
        self.assertEqual(self.post('/employees.html',dict(data,department_id=department)).status_code,302)
        self.assertEqual(self.read('SELECT department_id FROM employees WHERE username=%s',('new.accountant',))['department_id'],department)

    def test_department_first_form_filters_jobs_and_rejects_mismatch(self):
        initial = self.client.get('/employees.html').data
        self.assertIn(b'Choose a department first', initial)
        self.assertNotIn(b'<option value="Accountant"', initial)
        for job, department in self.job_departments.items():
            page = self.client.get(f'/employees.html?department_id={department}').data
            self.assertIn(f'<option value="{job}"'.encode(), page)
            for other in self.job_departments:
                if other != job:
                    self.assertNotIn(f'<option value="{other}"'.encode(), page)
            self.assertLess(page.index(b'1. Department'), page.index(b'2. Job'))
        data = {'name':'Wrong Job', 'username':'wrong.job', 'role':'Sales', 'job_type':'Accountant',
                'department_id':self.job_departments['Cashier'], 'password':'test-password'}
        self.assertEqual(self.post('/employees.html',data).status_code,400)
        self.assertIsNone(self.read('SELECT id FROM employees WHERE username=%s',('wrong.job',)))
        self.assertEqual(self.post('/employees.html',dict(data,department_id='')).status_code,400)
        self.assertEqual(self.post('/staff-profiles.html',{'employee_id':self.staff,'job_type':'Accountant',
            'department_id':self.job_departments['Cashier'],'salary':'0','detail':'CPA'}).status_code,400)
        self.assertEqual(self.read('SELECT job_type FROM employees WHERE id=%s',(self.staff,))['job_type'],'Cashier')

    def test_department_choices_are_limited_to_supported_jobs(self):
        page = self.client.get('/business/departments').data
        self.assertIn(b'<option value="Accounting"',page)
        branch = self.read('SELECT id FROM branches LIMIT 1')['id']
        self.assertEqual(self.post('/business/departments',{'branch_id':branch,'name':'Unknown Department'}).status_code,400)

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
            self.assertEqual(len(query('SHOW TABLES')), 24)

    def test_department_job_lifecycle_and_ownership(self):
        department = self.job_departments['Cashier']
        self.assertEqual(self.post('/departments/assign', {
            'employee_id': self.staff, 'department_id': department}).status_code, 302)
        self.assertEqual(self.post('/jobs/create', {
            'department_id': department, 'employee_id': self.staff,
            'title': 'Verify cement stock', 'description': 'Reconcile physical quantities.',
            'priority': 'High', 'due_date': '2026-11-05'}).status_code, 302)
        job = self.read('SELECT * FROM job_assignments WHERE employee_id=%s', (self.staff,))
        self.assertEqual(job['status'], 'Pending')
        self.assertEqual(self.login('staff').status_code, 302)
        self.assertIn(b'Verify cement stock', self.client.get('/my-jobs.html').data)
        self.assertEqual(self.post(f'/jobs/{job["id"]}/employee-action', {'action': 'start'}).status_code, 302)
        self.assertEqual(self.post(f'/jobs/{job["id"]}/employee-action', {'action': 'complete'}).status_code, 302)
        self.assertEqual(self.read('SELECT status FROM job_assignments WHERE id=%s', (job['id'],))['status'], 'Completed')
        self.assertEqual(self.read('SELECT COUNT(*) AS n FROM job_activity_history WHERE job_id=%s',
                                   (job['id'],))['n'], 3)
        self.assertEqual(self.post(f'/jobs/{job["id"]}/admin-action', {'action': 'cancel'}).status_code, 403)

    def test_assignment_pages_and_entity_permissions(self):
        for path in ('/staff-profiles.html','/payroll.html','/ledger.html','/data-quality.html','/orders.html',
                     '/business/branches','/business/departments','/business/customers','/business/supply'):
            self.assertEqual(self.client.get(path).status_code,200,path)
        self.login('staff')
        for path in ('/payroll.html','/staff-profiles.html','/ledger.html','/business/branches','/business/supply'):
            self.assertEqual(self.client.get(path).status_code,403,path)
        self.assertEqual(self.post('/business/customers',{'name':' Client ','phone':'0700000000'}).status_code,302)
        self.assertEqual(self.read('SELECT name FROM customers')['name'],'Client')

    def test_payroll_trigger_computed_net_and_duplicate_month(self):
        data = {'employee_id':self.staff,'pay_month':'2026-10-01','gross_pay':'1000','deductions':'150'}
        self.assertEqual(self.post('/payroll.html',data).status_code,302)
        self.assertEqual(self.read('SELECT net_pay FROM payroll')['net_pay'],Decimal('850'))
        self.assertEqual(self.read("SELECT amount FROM ledger_entries WHERE source_type='Payroll'")['amount'],Decimal('-850'))
        self.assertEqual(self.post('/payroll.html',data).status_code,400)
        self.assertEqual(self.post('/payroll.html',dict(data,pay_month='2026-11-01',deductions='1001')).status_code,400)
        self.assertEqual(self.read('SELECT COUNT(*) AS n FROM payroll')['n'],1)

    def test_subtypes_and_recursive_supervision(self):
        data = {'employee_id':self.staff,'job_type':'ProcurementOfficer','salary':'500','detail':'1000','supervisor_id':self.admin}
        self.assertEqual(self.post('/staff-profiles.html',data).status_code,302)
        self.assertEqual(self.read('SELECT approval_limit FROM procurement_officers WHERE employee_id=%s',(self.staff,))['approval_limit'],Decimal('1000'))
        self.assertEqual(self.read('SELECT COUNT(*) AS n FROM cashiers WHERE employee_id=%s',(self.staff,))['n'],0)
        self.assertEqual(self.post('/staff-profiles.html',dict(data,employee_id=self.admin,supervisor_id=self.staff)).status_code,400)
        self.assertIsNone(self.read('SELECT supervisor_id FROM employees WHERE id=%s',(self.admin,))['supervisor_id'])

    def test_order_receiving_is_atomic_and_once_only(self):
        data={'supplier_id':self.supplier,'product_id':self.product,'quantity':'4','unit_cost':'10'}
        self.assertEqual(self.post('/orders.html',data).status_code,302)
        order=self.read('SELECT id FROM purchase_orders')['id']
        self.assertEqual(self.read('SELECT stock FROM products WHERE id=%s',(self.product,))['stock'],10)
        self.assertEqual(self.post(f'/orders/{order}/receive').status_code,302)
        self.assertEqual(self.post(f'/orders/{order}/receive').status_code,400)
        self.assertEqual(self.read('SELECT stock FROM products WHERE id=%s',(self.product,))['stock'],14)
        self.assertEqual(self.read('SELECT COUNT(*) AS n FROM purchases')['n'],1)

    def test_word_receipt_and_ledger_follow_committed_sale(self):
        import zipfile
        response=self.post('/sales.html',{'product_id':self.product,'quantity':'2'})
        self.assertEqual(response.status_code,302)
        sale=self.read('SELECT id FROM sales')['id']
        self.assertEqual(self.read('SELECT amount FROM ledger_entries WHERE sale_id=%s',(sale,))['amount'],Decimal('41'))
        self.assertTrue((Path(self.receipts.name)/f'sale-{sale}.docx').is_file())
        with self.client.get(f'/sales/{sale}/receipt.docx') as response:
            self.assertEqual(response.status_code,200)
            with zipfile.ZipFile(io.BytesIO(response.data)) as z:
                content=z.read('word/document.xml')
                self.assertIn(b'41.00',content)
                self.assertIn(b'Hammer',content)
        self.post('/sales.html',{'product_id':self.second,'quantity':'3'})
        self.assertEqual(self.read('SELECT COUNT(*) AS n FROM ledger_entries')['n'],1)

    def test_receipt_failure_does_not_undo_sale(self):
        with patch('receipts.save_receipt',side_effect=OSError('disk full')):
            response=self.post('/sales.html',{'product_id':self.product,'quantity':'1'},follow_redirects=True)
        self.assertEqual(response.status_code,200)
        self.assertIn(b'Word receipt could not be saved',response.data)
        sale=self.read('SELECT id FROM sales')['id']
        with self.client.get(f'/sales/{sale}/receipt.docx') as response:
            self.assertEqual(response.status_code,200)

    def test_assignment_backup_with_subtype_payroll_and_forward_supervisor(self):
        from backup import create_backup,load_backup,restore_backup
        self.post('/staff-profiles.html',{'employee_id':self.admin,'job_type':'Accountant','salary':'1000','detail':'CPA','supervisor_id':self.staff})
        self.post('/payroll.html',{'employee_id':self.admin,'pay_month':'2026-10-01','gross_pay':'1000','deductions':'100'})
        target=dict(self.mysql,database='hw_test_'+uuid.uuid4().hex[:12])
        initialize(target)
        try:
            with tempfile.TemporaryDirectory() as directory:
                folder=create_backup(self.mysql,directory)
                restore_backup(folder,target)
                restored=create_backup(target,directory)
                self.assertEqual(load_backup(folder),load_backup(restored))
        finally:
            with connect(target) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(f'DROP DATABASE `{target["database"]}`')

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
        self.assertIn(b'Incorrect department, username, or password', response.data)
        self.assertEqual(self.client.post('/login', data={'username': 'admin', 'department': 'Admin'}).status_code, 400)
        self.login('staff')
        self.assertEqual(self.client.get('/employees.html').status_code, 403)
        self.assertEqual(self.post(f'/employees/{self.admin}/toggle').status_code, 403)
        self.assertEqual(self.client.get('/sales.html').status_code, 200)

    def test_deactivation_blocks_existing_session_and_self_deactivation_is_rejected(self):
        self.assertEqual(self.post(f'/employees/{self.admin}/toggle').status_code, 400)
        self.login('staff')
        with self.app.app_context():
            execute('UPDATE employees SET active=0 WHERE id=%s', (self.staff,))
            get_db().commit()
        self.assertEqual(self.client.get('/sales.html').status_code, 302)

    def test_password_change_and_old_password_rejected(self):
        response = self.post('/settings.html', {'current_password': 'test-password',
                             'password': 'a-new-password', 'confirm_password': 'a-new-password'})
        self.assertEqual(response.status_code, 302)
        self.post('/logout')
        self.assertIn(b'Incorrect department, username, or password', self.login().data)
        self.assertEqual(self.login(password='a-new-password').status_code, 302)

    def test_supplier_and_category_forms_and_employee_creation(self):
        self.assertEqual(self.post('/categories.html', {'name': 'Plumbing'}).status_code, 302)
        self.assertEqual(self.post('/suppliers.html', {'name': 'New Supplier', 'phone': '0700000000',
                                                     'email': 'supplier@example.test'}).status_code, 302)
        self.assertEqual(self.post('/employees.html', {'name': 'New Staff', 'username': 'newstaff', 'email': 'new@example.test',
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
        self.login('staff')
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
        self.assertEqual(self.post('/employees.html', {'name': 'Buyer', 'username': 'buyer', 'email': 'buyer@example.test',
                             'role': 'Purchasing', 'password': 'buyer-password'}).status_code, 302)
        self.assertEqual(self.login('buyer', 'buyer-password').status_code, 302)
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
        self.assertEqual(self.post('/employees.html', {'id': self.staff, 'name': 'Buyer', 'username': 'staff',
                         'email': 'staff@example.test', 'role': 'Purchasing'}).status_code, 302)
        self.assertEqual(department_client.get('/sales.html').status_code, 403)
        self.assertEqual(department_client.get('/purchase-orders.html').status_code, 200)
        self.assertEqual(self.post('/employees.html', {'id': self.admin, 'name': 'Admin', 'username': 'admin',
                         'email': 'admin@example.test', 'role': 'Sales'}).status_code, 400)
        self.assertEqual(self.post('/employees.html', {'name': 'Invalid', 'username': 'invalid', 'email': 'invalid@example.test',
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

    def test_department_username_and_password_must_all_match(self):
        self.post('/logout')
        for data in (
            {'username': 'staff', 'department': 'Admin', 'password': 'test-password'},
            {'username': 'admin', 'department': 'Sales', 'password': 'test-password'},
            {'username': 'staff', 'department': 'Purchasing', 'password': 'test-password'},
            {'username': 'staff', 'department': 'Sales', 'password': 'wrong'},
            {'username': 'admin', 'password': 'test-password'},
            {'department': 'Admin', 'password': 'test-password'},
            {'email': 'admin@example.test', 'department': 'Admin', 'password': 'test-password'},
        ):
            with self.subTest(data={key: value for key, value in data.items() if key != 'password'}):
                response = self.post('/login', data)
                self.assertEqual(response.status_code, 200)
                self.assertIn(b'Incorrect department, username, or password', response.data)
                with self.client.session_transaction() as session:
                    self.assertNotIn('user_id', session)
        self.assertEqual(self.login(' STAFF ', department='Sales').status_code, 302)
        self.assertEqual(self.client.get('/sales.html').status_code, 200)

    def test_admin_creates_username_account_without_email(self):
        response = self.post('/employees.html', {'name': 'New Buyer', 'username': 'New.Buyer',
                             'role': 'Purchasing', 'password': 'buyer-password'})
        self.assertEqual(response.status_code, 302)
        employee = self.read('SELECT * FROM employees WHERE username=%s', ('new.buyer',))
        self.assertIsNone(employee['email'])
        self.assertNotEqual(employee['password_hash'], 'buyer-password')
        self.assertEqual(self.post('/employees.html', {'name': 'Second Buyer', 'username': 'buyer_two',
                             'role': 'Purchasing', 'password': 'buyer-password'}).status_code, 302)
        self.post('/logout')
        self.assertEqual(self.login('NEW.BUYER', 'buyer-password', 'Purchasing').status_code, 302)
        self.assertEqual(self.client.get('/purchase-orders.html').status_code, 200)
        self.assertEqual(self.post('/employees.html', {'name': 'Forbidden', 'username': 'forbidden',
                             'role': 'Admin', 'password': 'test-password'}).status_code, 403)
        self.assertEqual(self.client.get('/signup.html').status_code, 404)
        self.assertEqual(self.post('/signup.html', {'username': 'forbidden'}).status_code, 404)
        self.assertEqual(self.read('SELECT COUNT(*) AS n FROM employees')['n'], 4)

    def test_invalid_and_duplicate_usernames_are_rejected(self):
        for username in ('ad', 'bad username', '@admin', 'a'*51, 'ADMIN'):
            with self.subTest(username=username):
                response = self.post('/employees.html', {'name': 'Test', 'username': username,
                                     'role': 'Sales', 'password': 'test-password'})
                self.assertEqual(response.status_code, 400)
        response = self.post('/employees.html', {'id': self.staff, 'name': 'Changed', 'username': 'admin',
                             'role': 'Sales'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.read('SELECT username FROM employees WHERE id=%s', (self.staff,))['username'], 'staff')
        self.assertEqual(self.read('SELECT COUNT(*) AS n FROM employees')['n'], 2)

    def test_username_change_and_deactivation_control_future_logins(self):
        self.assertEqual(self.post('/employees.html', {'id': self.staff, 'name': 'Test Staff',
                             'username': 'new.staff', 'role': 'Sales'}).status_code, 302)
        self.post('/logout')
        self.assertIn(b'Incorrect department', self.login('staff').data)
        self.assertEqual(self.login('new.staff').status_code, 302)
        self.assertIn(b'new.staff', self.client.get('/settings.html').data)
        self.login('admin')
        self.assertEqual(self.post(f'/employees/{self.staff}/toggle').status_code, 302)
        self.post('/logout')
        self.assertIn(b'Incorrect department', self.login('new.staff').data)
        with self.client.session_transaction() as session:
            self.assertNotIn('user_id', session)

    def test_username_upgrade_preserves_passwords_and_resolves_collisions(self):
        with self.app.app_context():
            extra_id = execute('INSERT INTO employees (name,username,email,password_hash,role) VALUES (%s,%s,%s,%s,%s)',
                               ('Other Staff', 'other', 'staff@other.test', generate_password_hash('other-password'), 'Sales'))
            get_db().commit()
            hashes = {row['id']: row['password_hash'] for row in query('SELECT id,password_hash FROM employees')}
            execute('ALTER TABLE employees DROP COLUMN username')
            execute('ALTER TABLE employees MODIFY email VARCHAR(150) NOT NULL')
        with patch.dict('os.environ', {'ADMIN_USERNAME': 'admin'}):
            for _ in range(2):
                result = self.app.test_cli_runner().invoke(args=['init-db'])
                self.assertEqual(result.exit_code, 0, result.output)
        with self.app.app_context():
            rows = query('SELECT id,username,password_hash FROM employees')
            self.assertEqual({row['id']: row['password_hash'] for row in rows}, hashes)
            self.assertEqual(len({row['username'] for row in rows}), 3)
            self.assertTrue(query('SELECT username FROM employees WHERE id=%s', (extra_id,), one=True)['username'].startswith('staff_'))
            self.assertEqual(query("SHOW COLUMNS FROM employees LIKE 'username'", one=True)['Null'], 'NO')
            self.assertEqual(query("SHOW COLUMNS FROM employees LIKE 'email'", one=True)['Null'], 'YES')
        self.post('/logout')
        self.assertEqual(self.login('staff').status_code, 302)
        self.assertEqual(self.read('SELECT stock FROM products WHERE id=%s', (self.product,))['stock'], 10)

    def test_first_admin_is_created_with_username_and_optional_email(self):
        with self.app.app_context():
            execute('DELETE FROM employees')
            get_db().commit()
        with patch.dict('os.environ', {'ADMIN_NAME': 'Bootstrap Admin', 'ADMIN_USERNAME': 'setup.admin',
                                      'ADMIN_PASSWORD': 'bootstrap-password', 'ADMIN_EMAIL': ''}):
            result = self.app.test_cli_runner().invoke(args=['init-db'])
        self.assertEqual(result.exit_code, 0, result.output)
        employee = self.read('SELECT * FROM employees WHERE username=%s', ('setup.admin',))
        self.assertEqual(employee['role'], 'Admin')
        self.assertIsNone(employee['email'])
        self.assertNotEqual(employee['password_hash'], 'bootstrap-password')
        with self.client.session_transaction() as session:
            session.clear()
        self.assertEqual(self.login('setup.admin', 'bootstrap-password', 'Admin').status_code, 302)
        self.assertEqual(self.client.get('/employees.html').status_code, 200)

    def test_demo_seed_preserves_records_balances_stock_and_skips_repeat(self):
        from seed_demo import seed_demo
        with patch('seed_demo.connection_settings', return_value=self.mysql):
            seed_demo()
            with self.app.app_context():
                before = {table: query(f'SELECT COUNT(*) AS n FROM {table}', one=True)['n']
                          for table in ('employees', 'categories', 'suppliers', 'products', 'purchases', 'sales', 'sale_items')}
                self.assertEqual(before['products'], 14)
                self.assertEqual(before['employees'], 2)
                self.assertEqual(before['purchases'], 12)
                self.assertEqual(before['sales'], 8)
                rows = query("SELECT p.stock, (SELECT SUM(quantity) FROM purchases WHERE product_id=p.id) AS received, "
                             "(SELECT COALESCE(SUM(quantity),0) FROM sale_items WHERE product_id=p.id) AS sold "
                             "FROM products p WHERE p.name LIKE %s", ('% (Demo)',))
                self.assertEqual(len(rows), 12)
                for row in rows:
                    self.assertEqual(row['stock'], row['received'] - row['sold'])
            seed_demo()
            with self.app.app_context():
                after = {table: query(f'SELECT COUNT(*) AS n FROM {table}', one=True)['n'] for table in before}
                self.assertEqual(before, after)
        self.assertEqual(self.read('SELECT stock FROM products WHERE id=%s', (self.product,))['stock'], 10)

    def test_backup_restore_round_trip_and_atomic_failure(self):
        import pymysql
        from backup import TABLES, create_backup, load_backup, restore_backup
        self.post('/purchase-orders.html', {'product_id': self.product, 'supplier_id': self.supplier,
                                           'quantity': '2', 'unit_cost': '12.00'})
        self.post('/sales.html', {'product_id': self.product, 'quantity': '3'})
        with self.app.app_context():
            execute('INSERT INTO categories (name) VALUES (%s)', ('=formula, "quote"\nNairobi \u2713',))
            execute('UPDATE employees SET email=NULL WHERE id=%s', (self.staff,))
            execute('UPDATE suppliers SET phone=%s WHERE id=%s', ('\\N', self.supplier))
            get_db().commit()
        target = dict(self.mysql, database='hw_test_' + uuid.uuid4().hex[:12])
        initialize(target)
        try:
            with tempfile.TemporaryDirectory() as temporary:
                folder = create_backup(self.mysql, temporary)
                expected = load_backup(folder)
                counts = restore_backup(folder, target)
                self.assertEqual(counts['sales'], 1)
                restored = create_backup(target, temporary)
                self.assertEqual(load_backup(restored), expected)
                with self.assertRaisesRegex(ValueError, 'empty database'):
                    restore_backup(folder, target)
                with connect(target) as connection:
                    with connection.cursor() as cursor:
                        cursor.execute('SET @restoring_snapshot=1')
                        for table in reversed(TABLES):
                            cursor.execute(f'DELETE FROM {table}')
                    connection.commit()
                # Even with a recomputed checksum, a broken FK rolls back ALL tables.
                path = folder / 'sale_items.csv'
                with path.open(encoding='utf-8', newline='') as handle:
                    rows = list(csv.reader(handle))
                rows[1][2] = '999999'
                with path.open('w', encoding='utf-8', newline='') as handle:
                    csv.writer(handle).writerows(rows)
                manifest_path = folder / 'manifest.json'
                manifest = json.loads(manifest_path.read_text())
                manifest['tables']['sale_items']['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
                manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
                with self.assertRaises(pymysql.IntegrityError):
                    restore_backup(folder, target)
                with connect(target) as connection:
                    with connection.cursor() as cursor:
                        for table in TABLES:
                            cursor.execute(f'SELECT COUNT(*) AS n FROM {table}')
                            self.assertEqual(cursor.fetchone()['n'], 0)
                path.write_text('corrupted file', encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'checksum'):
                    restore_backup(folder, target)
        finally:
            assert re.fullmatch(r'hw_test_[a-f0-9]{12}', target['database'])
            with connect(target) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(f'DROP DATABASE `{target["database"]}`')

    def test_backup_page_downloads_are_admin_only_and_paths_are_restricted(self):
        import zipfile
        from backup import create_backup
        with tempfile.TemporaryDirectory() as temporary, patch.dict(self.app.config, {'BACKUP_DIR': temporary}):
            folder = create_backup(self.mysql, temporary)
            self.assertEqual(self.client.get('/backups.html').status_code, 200)
            with self.client.get(f'/backups/{folder.name}/products.csv') as response:
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.data.startswith(b'id,name,category_id'))
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
            with self.client.get(f'/backups/{folder.name}/download') as response:
                with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
                    self.assertIn('products.csv', archive.namelist())
                    self.assertIn('manifest.json', archive.namelist())
                    self.assertEqual(len(archive.namelist()), 25)
            self.assertEqual(self.client.get(f'/backups/{folder.name}/secret.csv').status_code, 404)
            self.assertEqual(self.client.get('/backups/invalid/products.csv').status_code, 400)
            self.login('staff')
            for path in ('/backups.html', f'/backups/{folder.name}/products.csv', f'/backups/{folder.name}/download'):
                self.assertEqual(self.client.get(path).status_code, 403)
            self.assertEqual(self.post('/backups/create').status_code, 403)
            self.post('/logout')
            self.assertEqual(self.client.get(f'/backups/{folder.name}/employees.csv').status_code, 302)

    def test_automatic_backup_only_after_commit_and_failure_preserves_saved_sale(self):
        with patch.dict(self.app.config, {'AUTO_BACKUP': True}), patch('main.create_backup') as snapshot:
            self.client.get('/')
            snapshot.assert_not_called()
            self.post('/sales.html', {'product_id': self.product, 'quantity': '99999'})
            snapshot.assert_not_called()
            self.post('/sales.html', {'product_id': self.product, 'quantity': '2'})
            snapshot.assert_called_once()
        with patch.dict(self.app.config, {'AUTO_BACKUP': True}), patch('main.create_backup', side_effect=OSError('Disk full')):
            response = self.post('/sales.html', {'product_id': self.product, 'quantity': '1'}, follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'CSV backup failed', response.data)
        self.assertEqual(self.read('SELECT COUNT(*) AS n FROM sales')['n'], 2)
        self.assertEqual(self.read('SELECT stock FROM products WHERE id=%s', (self.product,))['stock'], 7)

    def test_successful_sale_creates_real_csv_snapshot(self):
        from backup import list_backups, load_backup
        with tempfile.TemporaryDirectory() as temporary, patch.dict(self.app.config, {'AUTO_BACKUP': True, 'BACKUP_DIR': temporary}):
            response = self.post('/sales.html', {'product_id': self.product, 'quantity': '2'})
            self.assertEqual(response.status_code, 302)
            folders = list_backups(temporary)
            self.assertEqual(len(folders), 1)
            rows = load_backup(Path(temporary) / folders[0])
            self.assertEqual(len(rows['sales']), 1)
            product = next(row for row in rows['products'] if row[0] == str(self.product))
            self.assertEqual(product[4], '8')
            self.assertNotIn('test-password', (Path(temporary) / folders[0] / 'employees.csv').read_text())

    def test_security_headers_and_purchase_failure_roll_back(self):
        import pymysql
        from db import execute as real_execute
        response = self.client.get('/')
        self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(response.headers['X-Frame-Options'], 'DENY')
        self.assertIn("script-src 'none'", response.headers['Content-Security-Policy'])
        self.assertEqual(response.headers['Cache-Control'], 'no-store')

        def fail_stock_update(sql, params=()):
            if sql.startswith('UPDATE products SET stock=stock+'):
                raise pymysql.IntegrityError(3819, 'Simulated stock constraint failure')
            return real_execute(sql, params)

        with patch('main.execute', side_effect=fail_stock_update):
            response = self.post('/purchase-orders.html', {'product_id': self.product,
                                 'supplier_id': self.supplier, 'quantity': 5, 'unit_cost': '10.00'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.read('SELECT COUNT(*) AS n FROM purchases')['n'], 0)
        self.assertEqual(self.read('SELECT stock FROM products WHERE id=%s', (self.product,))['stock'], 10)

    def test_restore_command_refuses_working_database(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = self.app.test_cli_runner().invoke(args=['restore-backup', temporary,
                                                           '--database', self.mysql['database']])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn('working databases are protected', result.output)

    def test_restore_command_creates_a_separate_copy_and_refuses_to_overwrite_it(self):
        from backup import create_backup
        target = dict(self.mysql, database='hw_test_' + uuid.uuid4().hex[:12])
        try:
            with tempfile.TemporaryDirectory() as temporary:
                folder = create_backup(self.mysql, temporary)
                args = ['restore-backup', str(folder), '--database', target['database']]
                result = self.app.test_cli_runner().invoke(args=args)
                self.assertEqual(result.exit_code, 0, result.output)
                again = self.app.test_cli_runner().invoke(args=args)
                self.assertNotEqual(again.exit_code, 0)
                self.assertIn('empty database', again.output)
                with connect(target) as connection:
                    with connection.cursor() as cursor:
                        cursor.execute('SELECT COUNT(*) AS n FROM employees')
                        self.assertEqual(cursor.fetchone()['n'], 2)
        finally:
            assert re.fullmatch(r'hw_test_[a-f0-9]{12}', target['database'])
            with connect(target) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(f'DROP DATABASE `{target["database"]}`')


if __name__ == '__main__':
    unittest.main()
