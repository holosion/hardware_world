"""Add fictional presentation data without clearing existing records.

Run from the project folder:
    backend/.venv/Scripts/python.exe backend/seed_demo.py
Prices are sample UGX amounts, not a current price list.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from db import connect, connection_settings


# Name, category, supplier index, selling price, unit cost, received quantity.
PRODUCTS = [
    ('Cement - 50 kg bag', 'Building Materials', 0, '35000', '28000', 40),
    ('Clay bricks - pack of 100', 'Building Materials', 0, '60000', '45000', 30),
    ('PVC pipe - 3 metres', 'Plumbing', 1, '18000', '12000', 20),
    ('Brass water tap', 'Plumbing', 1, '25000', '17000', 12),
    ('LED bulb - 10 watts', 'Electrical', 2, '8000', '5000', 30),
    ('Electrical cable - 50 metre roll', 'Electrical', 2, '120000', '90000', 10),
    ('Claw hammer', 'Hand Tools', 0, '22000', '15000', 15),
    ('Hand saw', 'Hand Tools', 0, '28000', '19000', 10),
    ('White emulsion paint - 4 litres', 'Paints', 3, '45000', '33000', 16),
    ('Paint brush - 3 inches', 'Paints', 3, '6000', '3500', 25),
    ('Safety helmet', 'Safety Equipment', 0, '18000', '11000', 15),
    ('Work gloves - pair', 'Safety Equipment', 0, '5000', '3000', 20),
]

SUPPLIERS = [
    ('Demo Central Hardware Supplies', '000-000-0101', 'central@example.com'),
    ('Demo Waterworks Supplies', '000-000-0102', 'waterworks@example.com'),
    ('Demo Bright Electrical Supplies', '000-000-0103', 'electrical@example.com'),
    ('Demo Colour House', '000-000-0104', 'colours@example.com'),
]

# Customer, days ago, [(product index, quantity)].
SALES = [
    ('Demo: Amina Builders', 6, [(0, 8), (1, 5), (10, 3)]),
    ('Demo: Peter Plumbing', 5, [(2, 10), (3, 4)]),
    ('Demo: Grace Electrical', 4, [(4, 8), (5, 8)]),
    ('Demo: David Repairs', 3, [(6, 3), (7, 2), (11, 7)]),
    ('Demo: Sunrise Decorators', 2, [(8, 4), (9, 10)]),
    ('Demo: Riverside Project', 1, [(2, 8), (0, 6), (11, 9)]),
    ('Demo: Walk-in customer', 0, [(9, 5), (10, 2)]),
    ('Demo: Hilltop Workshop', 0, [(6, 2), (7, 3), (4, 4)]),
]


def seed_demo():
    with connect(connection_settings()) as connection:
        with connection.cursor() as cursor:
            # Serialize repeat runs, so two invocations cannot duplicate the demo.
            cursor.execute("SELECT GET_LOCK('hardware_world_demo_seed', 10) AS acquired")
            if cursor.fetchone()['acquired'] != 1:
                raise RuntimeError('Another demo import is running. Try again shortly.')
            try:
                cursor.execute('SELECT id FROM sales WHERE customer_name=%s LIMIT 1', (SALES[0][0],))
                if cursor.fetchone():
                    print('Demo data already exists. No records were added or changed.')
                    return
                cursor.execute("SELECT id FROM employees WHERE role='Admin' AND active=1 ORDER BY id LIMIT 1")
                admin = cursor.fetchone()
                if not admin:
                    raise RuntimeError('Run init-db first to create an administrator.')
                cursor.execute("SELECT id FROM employees WHERE role='Sales' AND active=1 ORDER BY id LIMIT 1")
                seller = cursor.fetchone() or admin
                now = datetime.now(timezone(timedelta(hours=3))).replace(
                    hour=10, minute=0, second=0, microsecond=0, tzinfo=None)
                category_ids, supplier_ids, product_ids = {}, [], []
                for category in dict.fromkeys(p[1] for p in PRODUCTS):
                    cursor.execute('SELECT id FROM categories WHERE name=%s', (category,))
                    existing = cursor.fetchone()
                    if existing:
                        category_ids[category] = existing['id']
                    else:
                        cursor.execute('INSERT INTO categories (name) VALUES (%s)', (category,))
                        category_ids[category] = cursor.lastrowid
                for supplier in SUPPLIERS:
                    cursor.execute('INSERT INTO suppliers (name,phone,email) VALUES (%s,%s,%s)', supplier)
                    supplier_ids.append(cursor.lastrowid)
                for name, category, supplier, price, cost, quantity in PRODUCTS:
                    demo_name = name + ' (Demo)'
                    cursor.execute('SELECT id FROM products WHERE name=%s', (demo_name,))
                    if cursor.fetchone():
                        raise RuntimeError('Demo products already exist without the demo sales marker. No changes saved.')
                    # Zero opening stock: the delivery below accounts for all stock.
                    cursor.execute('INSERT INTO products (name,category_id,price,stock,reorder_level) '
                                   'VALUES (%s,%s,%s,0,5)', (demo_name, category_ids[category], Decimal(price)))
                    product_id = cursor.lastrowid
                    product_ids.append(product_id)
                    cursor.execute('INSERT INTO purchases (supplier_id,product_id,employee_id,quantity,unit_cost,created_at) '
                                   'VALUES (%s,%s,%s,%s,%s,%s)',
                                   (supplier_ids[supplier], product_id, admin['id'], quantity, Decimal(cost), now-timedelta(days=7)))
                    cursor.execute('UPDATE products SET stock=stock+%s WHERE id=%s', (quantity, product_id))
                for customer, days_ago, items in SALES:
                    cursor.execute('INSERT INTO sales (employee_id,customer_name,created_at) VALUES (%s,%s,%s)',
                                   (seller['id'], customer, now-timedelta(days=days_ago)))
                    sale_id = cursor.lastrowid
                    for index, quantity in items:
                        product_id = product_ids[index]
                        cursor.execute('UPDATE products SET stock=stock-%s WHERE id=%s AND stock >= %s',
                                       (quantity, product_id, quantity))
                        if cursor.rowcount != 1:
                            raise RuntimeError('Demo sale would exceed available stock.')
                        cursor.execute('INSERT INTO sale_items (sale_id,product_id,quantity,unit_price) VALUES (%s,%s,%s,%s)',
                                       (sale_id, product_id, quantity, Decimal(PRODUCTS[index][3])))
                connection.commit()
                print('Added demo data: 6 categories (reusing existing names), 4 suppliers, 12 products, 12 purchases, and 8 sales.')
                print('Demo products start at zero stock; purchases minus sales explain their current stock.')
            except Exception:
                connection.rollback()
                raise
            finally:
                cursor.execute("SELECT RELEASE_LOCK('hardware_world_demo_seed')")


if __name__ == '__main__':
    seed_demo()
