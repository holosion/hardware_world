"""Assignment modules implemented with ordinary Flask forms and explicit SQL."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from flask import abort, flash, g, redirect, render_template, request, url_for
from business import SUBTYPES
from db import commit, execute, query

# Each form names a fixed table and fixed columns. URL/form values never become SQL identifiers.
CATALOG = {
    'branches': ('Branches', [('name','text'),('location','text'),('contact_number','text')]),
    'departments': ('Departments', [('branch_id','branches'),('name','text')]),
    'customers': ('Registered customers', [('name','text'),('phone','text')]),
    'supply': ('Supplier product catalogue', [('supplier_id','suppliers'),('product_id','products'),('cost_price','money'),('lead_time_days','number')]),
}


def register_business_routes(app):
    from main import integer, money, required

    @app.route('/business/<entity>', methods=['GET','POST'])
    def business_records(entity):
        if entity not in CATALOG:
            abort(404)
        permitted = {'Admin'} | ({'Sales'} if entity == 'customers' else {'Purchasing'} if entity == 'supply' else set())
        if g.user['role'] not in permitted:
            abort(403)
        title, fields = CATALOG[entity]
        if request.method == 'POST':
            values = []
            for field, kind in fields:
                if kind == 'money': values.append(money(field))
                elif kind == 'number': values.append(integer(field))
                elif kind in ('branches','suppliers','products'): values.append(integer(field,1))
                else: values.append(required(field, 30 if field in ('phone','contact_number') else 150 if field == 'location' else 100))
            columns = ','.join(field for field,_ in fields)
            execute(f'INSERT INTO {entity} ({columns}) VALUES ({",".join(["%s"]*len(values))})', tuple(values))
            commit()
            flash('Record saved.', 'success')
            return redirect(url_for('business_records', entity=entity))
        choices = {kind: query(f'SELECT id,name FROM {kind} ORDER BY name') for _,kind in fields if kind in ('branches','suppliers','products')}
        return render_template('business.html', title=title, fields=fields, choices=choices,
                               rows=query(f'SELECT * FROM {entity} LIMIT 500'), entity=entity)

    @app.route('/staff-profiles.html', methods=['GET','POST'])
    def staff_profiles():
        if request.method == 'POST':
            employee_id = integer('employee_id',1)
            employee = query('SELECT id FROM employees WHERE id=%s FOR UPDATE',(employee_id,),one=True)
            if not employee: raise ValueError('Choose an existing employee.')
            job = required('job_type')
            if job not in SUBTYPES: raise ValueError('Choose an existing job type.')
            department = integer('department_id',1) if request.form.get('department_id') else None
            supervisor = integer('supervisor_id',1) if request.form.get('supervisor_id') else None
            # Serialize hierarchy edits to prevent concurrent creation of a cycle.
            all_staff = query('SELECT id,supervisor_id FROM employees ORDER BY id FOR UPDATE')
            parents = {r['id']:r['supervisor_id'] for r in all_staff}
            seen = {employee_id}
            parent = supervisor
            while parent is not None:
                if parent in seen: raise ValueError('An employee cannot supervise themselves or form a supervision cycle.')
                seen.add(parent)
                if parent not in parents: raise ValueError('Choose an existing supervisor.')
                parent = parents[parent]
            hired = request.form.get('date_hired','').strip() or None
            if hired: date.fromisoformat(hired)
            nin = request.form.get('nin','').strip() or None
            phone = request.form.get('phone','').strip()
            if (nin and len(nin)>30) or len(phone)>30: raise ValueError('NIN and phone must be at most 30 characters.')
            execute('UPDATE employees SET department_id=%s,supervisor_id=%s,nin=%s,phone=%s,date_hired=%s,salary=%s,job_type=%s WHERE id=%s',
                    (department,supervisor,nin,phone,hired,money('salary'),job,employee_id))
            field = {'Cashier':'pos_terminal_id','ProcurementOfficer':'approval_limit','Accountant':'certification_number','HRStaff':'hr_role','BranchManager':'management_level'}[job]
            detail = money('detail') if job=='ProcurementOfficer' else required('detail',50 if job=='Cashier' else 100)
            execute(f'UPDATE {SUBTYPES[job]} SET {field}=%s WHERE employee_id=%s',(detail,employee_id))
            if job=='BranchManager':
                branch = integer('branch_id',1) if request.form.get('branch_id') else None
                execute('UPDATE branch_managers SET branch_id=%s WHERE employee_id=%s',(branch,employee_id))
            commit()
            flash('Profile and employee subtype saved.', 'success')
            return redirect(url_for('staff_profiles'))
        return render_template('profiles.html', title='Staff profiles', jobs=SUBTYPES,
                               rows=query('SELECT id,name,job_type,department_id,supervisor_id,nin,phone,date_hired,salary FROM employees ORDER BY name'),
                               departments=query('SELECT d.id,CONCAT(b.name,\' / \',d.name) AS name FROM departments d JOIN branches b ON b.id=d.branch_id'),
                               branches=query('SELECT id,name FROM branches ORDER BY name'))

    @app.route('/payroll.html', methods=['GET','POST'])
    def payroll():
        if request.method == 'POST':
            month = date.fromisoformat(required('pay_month'))
            if month.day != 1: raise ValueError('Use the first day of the payroll month, for example 2026-10-01.')
            gross, deductions = money('gross_pay'),money('deductions')
            if deductions>gross: raise ValueError('Deductions cannot exceed gross pay.')
            execute('INSERT INTO payroll(employee_id,pay_month,gross_pay,deductions) VALUES(%s,%s,%s,%s)',
                    (integer('employee_id',1),month,gross,deductions))
            commit()
            flash('Payroll saved. MySQL generated the payroll ledger entry.', 'success')
            return redirect(url_for('payroll'))
        return render_template('payroll.html', title='Monthly payroll', employees=query('SELECT id,name FROM employees ORDER BY name'),
                               rows=query('SELECT p.*,e.name FROM payroll p JOIN employees e ON e.id=p.employee_id ORDER BY pay_month DESC,id DESC'))

    @app.get('/ledger.html')
    def ledger():
        rows = query('SELECT * FROM ledger_entries ORDER BY id DESC LIMIT 500')
        return render_template('records.html', title='Sales and payroll ledger', rows=rows,
                               note='Sales are positive and payroll payments are negative. This is a simple cash movement ledger, not a complete double-entry accounting system.')

    @app.route('/orders.html', methods=['GET','POST'])
    def orders():
        if request.method == 'POST':
            supplier, product = integer('supplier_id',1),integer('product_id',1)
            quantity, cost = integer('quantity',1),money('unit_cost')
            if g.user['role'] != 'Admin':
                officer = query('SELECT approval_limit FROM procurement_officers WHERE employee_id=%s FOR UPDATE',(g.user['id'],),one=True)
                if not officer or quantity*cost>officer['approval_limit']:
                    raise ValueError('This order exceeds your procurement approval limit. Ask an Admin to place it or update your staff profile.')
            today = datetime.now(timezone(timedelta(hours=3))).date()
            order_id = execute('INSERT INTO purchase_orders(supplier_id,employee_id,order_date) VALUES(%s,%s,%s)',(supplier,g.user['id'],today))
            execute('INSERT INTO purchase_order_items(order_id,product_id,quantity,unit_cost) VALUES(%s,%s,%s,%s)',(order_id,product,quantity,cost))
            commit()
            flash('Pending order created. Stock will change only when it is received.', 'success')
            return redirect(url_for('orders'))
        return render_template('orders.html', title='Supplier purchase orders',
                               suppliers=query('SELECT id,name FROM suppliers ORDER BY name'),products=query('SELECT id,name FROM products ORDER BY name'),
                               rows=query('SELECT o.*,s.name AS supplier,SUM(i.quantity*i.unit_cost) AS total FROM purchase_orders o JOIN suppliers s ON s.id=o.supplier_id JOIN purchase_order_items i ON i.order_id=o.id GROUP BY o.id ORDER BY o.id DESC'))

    @app.post('/orders/<int:order_id>/receive')
    def receive_order(order_id):
        order = query('SELECT * FROM purchase_orders WHERE id=%s FOR UPDATE',(order_id,),one=True)
        if not order: abort(404)
        if order['status'] != 'Pending': raise ValueError('This order has already been received.')
        items = query('SELECT * FROM purchase_order_items WHERE order_id=%s ORDER BY product_id',(order_id,))
        if not items: raise ValueError('An empty order cannot be received.')
        for item in items:
            query('SELECT id FROM products WHERE id=%s FOR UPDATE',(item['product_id'],),one=True)
            execute('INSERT INTO purchases(supplier_id,product_id,employee_id,quantity,unit_cost,order_id) VALUES(%s,%s,%s,%s,%s,%s)',
                    (order['supplier_id'],item['product_id'],g.user['id'],item['quantity'],item['unit_cost'],order_id))
            execute('UPDATE products SET stock=stock+%s WHERE id=%s',(item['quantity'],item['product_id']))
        execute("UPDATE purchase_orders SET status='Received' WHERE id=%s",(order_id,))
        commit()
        flash('Order received once and stock updated.', 'success')
        return redirect(url_for('orders'))

    @app.get('/data-quality.html')
    def data_quality():
        rows = []
        checks = {
            'Employees missing a department': 'SELECT COUNT(*) AS n FROM employees WHERE department_id IS NULL',
            'Employees missing NIN': "SELECT COUNT(*) AS n FROM employees WHERE nin IS NULL OR TRIM(nin)=''",
            'Branches without a manager': 'SELECT COUNT(*) AS n FROM branches b LEFT JOIN branch_managers m ON m.branch_id=b.id WHERE m.employee_id IS NULL',
            'Suppliers without email': "SELECT COUNT(*) AS n FROM suppliers WHERE TRIM(email)=''",
            'Sales without a branch': 'SELECT COUNT(*) AS n FROM sales WHERE branch_id IS NULL',
            'Products at or below reorder level': 'SELECT COUNT(*) AS n FROM products WHERE stock<=reorder_level',
        }
        for label,sql in checks.items(): rows.append({'check':label,'records_to_review':query(sql,one=True)['n']})
        return render_template('records.html', title='Data quality review', rows=rows,
                               note='Review missing master data using the relevant forms. Historical unknown details are left empty instead of being invented. Low stock is an operational alert, not invalid data.')
