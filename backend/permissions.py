"""One readable access table, shared by Flask routes and HTML templates."""

ROLES = ('Admin', 'Sales', 'Purchasing')
READ = ('GET',)
WRITE = ('GET', 'POST')

COMMON = {'dashboard': READ, 'products': READ, 'settings': WRITE}
SALES = {'sales': WRITE, 'receipt': READ, 'receipt_docx': READ, 'business_records': WRITE}
PURCHASING = {
    'products': WRITE,
    'delete_product': ('POST',),
    'categories': WRITE,
    'delete_category': ('POST',),
    'suppliers': WRITE,
    'delete_supplier': ('POST',),
    'purchases': WRITE,
    'orders': WRITE, 'receive_order': ('POST',), 'business_records': WRITE,
}

ROLE_ACCESS = {
    'Admin': {**COMMON, **SALES, **PURCHASING,
              'employees': WRITE, 'toggle_employee': ('POST',),
              'backups': READ, 'create_snapshot': ('POST',),
              'download_backup': READ, 'download_csv': READ},
    'Sales': {**COMMON, **SALES},
    'Purchasing': {**COMMON, **PURCHASING},
}
ROLE_ACCESS['Admin'].update({'staff_profiles': WRITE, 'payroll': WRITE, 'ledger': READ, 'data_quality': READ})
ROLE_ACCESS['Admin'].update({'department_jobs': WRITE, 'department_create': ('POST',),
                             'department_assign': ('POST',), 'department_manager': ('POST',),
                             'department_status': ('POST',), 'job_create': ('POST',),
                             'job_admin_action': ('POST',), 'my_jobs': READ,
                             'job_employee_action': ('POST',), 'notifications': READ})
ROLE_ACCESS['Admin'].update({'delete_employee': ('POST',), 'employee_pay': ('POST',),
                             'payroll_process': ('POST',)})
for role in ('Sales', 'Purchasing'):
    ROLE_ACCESS[role].update({'my_jobs': READ, 'job_employee_action': ('POST',), 'notifications': READ})


def allowed(role, endpoint, method='GET'):
    # HEAD reads the same resource as GET; OPTIONS performs no changes.
    if method in ('HEAD', 'OPTIONS'):
        method = 'GET'
    return method in ROLE_ACCESS.get(role, {}).get(endpoint, ())
