"""One readable access table, shared by Flask routes and HTML templates."""

ROLES = ('Admin', 'Sales', 'Purchasing')
READ = ('GET',)
WRITE = ('GET', 'POST')

COMMON = {'dashboard': READ, 'products': READ, 'settings': WRITE}
SALES = {'sales': WRITE, 'receipt': READ}
PURCHASING = {
    'products': WRITE,
    'delete_product': ('POST',),
    'categories': WRITE,
    'delete_category': ('POST',),
    'suppliers': WRITE,
    'delete_supplier': ('POST',),
    'purchases': WRITE,
}

ROLE_ACCESS = {
    'Admin': {**COMMON, **SALES, **PURCHASING,
              'employees': WRITE, 'toggle_employee': ('POST',)},
    'Sales': {**COMMON, **SALES},
    'Purchasing': {**COMMON, **PURCHASING},
}


def allowed(role, endpoint, method='GET'):
    # HEAD reads the same resource as GET; OPTIONS performs no changes.
    if method in ('HEAD', 'OPTIONS'):
        method = 'GET'
    return method in ROLE_ACCESS.get(role, {}).get(endpoint, ())
