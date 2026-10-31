"""The five business jobs supported by the assignment, grouped by department."""
DEPARTMENT_JOBS = {
    'Sales & Marketing': ('Cashier',),
    'Procurement': ('ProcurementOfficer',),
    'Accounting': ('Accountant',),
    'Human Resources': ('HRStaff',),
    'Management': ('BranchManager',),
}
JOB_LABELS = {'Cashier': 'Cashier', 'ProcurementOfficer': 'Procurement officer',
              'Accountant': 'Accountant', 'HRStaff': 'HR staff', 'BranchManager': 'Branch manager'}
ALIASES = {'sales': 'Sales & Marketing', 'sales and marketing': 'Sales & Marketing',
           'purchasing': 'Procurement', 'accounts': 'Accounting', 'hr': 'Human Resources',
           'administration': 'Management'}


def jobs_for_department(name):
    normalized = ' '.join(name.split()).casefold()
    canonical = ALIASES.get(normalized)
    if canonical is None:
        canonical = next((n for n in DEPARTMENT_JOBS if n.casefold() == normalized), None)
    return DEPARTMENT_JOBS.get(canonical, ())


def validate_assignment(department_id, job):
    from db import query
    department = query('SELECT name FROM departments WHERE id=%s', (department_id,), one=True)
    if not department or job not in jobs_for_department(department['name']):
        raise ValueError('Choose a job that belongs to the selected department.')
